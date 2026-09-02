#!/usr/bin/env python3
"""Quick standalone check: are my LLM provider keys actually responding?

Tests each key against the SAME thing the app needs it for, using only the
Python standard library (no venv, no extra installs required).

  Hugging Face -> whoami (identity + token role) AND a real embedding call to
                  the router the app uses (router.huggingface.co/hf-inference)
  Groq         -> GET /openai/v1/models
  Gemini       -> GET /v1beta/models?key=...   (API-key auth, not OAuth)

Key sources, in priority order, per provider:
  1. command-line flag:  --hf hf_xxx   --groq gsk_xxx   --gemini AIza_xxx
  2. environment var:     HF_TOKEN / HUGGINGFACE_API_TOKEN, GROQ_API_KEY, GEMINI_API_KEY
  3. backend/.env  (KEY=value lines, next to this script)

Examples:
  python test_llm_keys.py                 # test whatever is in backend/.env
  python test_llm_keys.py --hf hf_abc123  # test one specific token
  python test_llm_keys.py --only hf
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

HF_EMBED_MODEL = "BAAI/bge-base-en-v1.5"
TIMEOUT = 20

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
if os.name == "nt" and not os.environ.get("WT_SESSION"):
    # Old cmd.exe won't render ANSI; strip colours.
    GREEN = RED = YELLOW = DIM = RESET = ""


def _load_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _request(method: str, url: str, headers: dict, body: bytes | None = None):
    """Return (status_code, text). Never raises for HTTP errors."""
    # Some providers sit behind Cloudflare, which 403s ("error code: 1010") the
    # default urllib User-Agent. Present a normal browser UA.
    headers = {"User-Agent": "Mozilla/5.0 (token-check script)", **headers}
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001 - network/DNS/timeout
        return 0, f"{type(e).__name__}: {e}"


def _ok(msg: str) -> None:
    print(f"  {GREEN}OK{RESET}   {msg}")


def _bad(msg: str) -> None:
    print(f"  {RED}FAIL{RESET} {msg}")


def _info(msg: str) -> None:
    print(f"  {DIM}{msg}{RESET}")


def test_hf(token: str) -> bool:
    print(f"{YELLOW}Hugging Face{RESET}  (token {token[:6]}...{token[-4:] if len(token) > 10 else ''})")
    ok = True

    status, text = _request(
        "GET", "https://huggingface.co/api/whoami-v2",
        {"Authorization": f"Bearer {token}"},
    )
    if status == 200:
        try:
            who = json.loads(text)
            name = who.get("name") or who.get("fullname") or "?"
            auth = (who.get("auth") or {}).get("accessToken") or {}
            role = auth.get("role") or who.get("type") or "?"
            _ok(f"token is valid - user '{name}', role '{role}'")
            fine = auth.get("fineGrained")
            if fine:
                perms = sorted({p for scope in fine.get("scoped", [])
                                for p in scope.get("permissions", [])})
                _info(f"fine-grained permissions: {', '.join(perms) or '(none listed)'}")
                if not any("inference" in p.lower() for p in perms):
                    _bad("no 'inference.*' permission - this token can't call Inference Providers")
                    ok = False
        except json.JSONDecodeError:
            _ok("token is valid (could not parse whoami detail)")
    else:
        _bad(f"whoami returned HTTP {status}: {text.strip()[:200]}")
        return False

    # The exact call the app makes for RAG embeddings.
    url = f"https://router.huggingface.co/hf-inference/models/{HF_EMBED_MODEL}/pipeline/feature-extraction"
    status, text = _request(
        "POST", url,
        {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json.dumps({"inputs": "hello"}).encode("utf-8"),
    )
    if status == 200:
        try:
            vec = json.loads(text)
            dim = len(vec[0]) if vec and isinstance(vec[0], list) else len(vec)
            _ok(f"embedding call works - got a {dim}-dim vector back")
        except (json.JSONDecodeError, TypeError):
            _ok("embedding call returned HTTP 200")
    else:
        _bad(f"embedding call failed - HTTP {status}: {text.strip()[:240]}")
        if status in (401, 403):
            _info("401 'Invalid username or password' / 403 'sufficient permissions' = "
                  "token invalid or missing the 'Make calls to Inference Providers' permission")
        elif status in (402, 429):
            _info("402/429 = quota or billing: enable Inference Providers billing on your HF account")
        ok = False
    return ok


def test_groq(key: str) -> bool:
    print(f"{YELLOW}Groq{RESET}  (key {key[:6]}...{key[-4:] if len(key) > 10 else ''})")
    status, text = _request(
        "GET", "https://api.groq.com/openai/v1/models",
        {"Authorization": f"Bearer {key}"},
    )
    if status == 200:
        try:
            n = len(json.loads(text).get("data", []))
            _ok(f"key is valid - {n} models available")
        except json.JSONDecodeError:
            _ok("key is valid (HTTP 200)")
        return True
    _bad(f"HTTP {status}: {text.strip()[:200]}")
    return False


def test_gemini(key: str) -> bool:
    print(f"{YELLOW}Gemini{RESET}  (key {key[:6]}...{key[-4:] if len(key) > 10 else ''})")
    status, text = _request(
        "GET",
        f"https://generativelanguage.googleapis.com/v1beta/models?key={key}",
        {},
    )
    if status == 200:
        try:
            n = len(json.loads(text).get("models", []))
            _ok(f"key is valid - {n} models available")
        except json.JSONDecodeError:
            _ok("key is valid (HTTP 200)")
        return True
    _bad(f"HTTP {status}: {text.strip()[:200]}")
    if status in (400, 401, 403):
        _info("This is an API-key check via ?key=... - if it fails here the key value itself is wrong "
              "(get a fresh one at https://aistudio.google.com/apikey)")
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hf", help="Hugging Face token to test")
    ap.add_argument("--groq", help="Groq API key to test")
    ap.add_argument("--gemini", help="Gemini API key to test")
    ap.add_argument("--only", choices=["hf", "groq", "gemini"], help="test just one provider")
    ap.add_argument("--env", default=str(Path(__file__).parent / "backend" / ".env"),
                    help="path to a .env file to read keys from (default: backend/.env)")
    args = ap.parse_args()

    env = _load_dotenv(Path(args.env))

    def pick(flag, *names):
        if flag:
            return flag
        for n in names:
            if os.environ.get(n):
                return os.environ[n]
        for n in names:
            if env.get(n):
                return env[n]
        return None

    hf = pick(args.hf, "HF_TOKEN", "HUGGINGFACE_API_TOKEN")
    groq = pick(args.groq, "GROQ_API_KEY")
    gemini = pick(args.gemini, "GEMINI_API_KEY")

    wanted = [args.only] if args.only else ["hf", "groq", "gemini"]
    results: dict[str, bool | None] = {}

    print()
    for prov in wanted:
        key = {"hf": hf, "groq": groq, "gemini": gemini}[prov]
        if not key:
            print(f"{YELLOW}{prov}{RESET}\n  {DIM}no key found (pass --{prov} or set it in {args.env}){RESET}\n")
            results[prov] = None
            continue
        fn = {"hf": test_hf, "groq": test_groq, "gemini": test_gemini}[prov]
        results[prov] = fn(key)
        print()

    print("summary:")
    for prov, r in results.items():
        tag = f"{GREEN}responding{RESET}" if r else (f"{DIM}skipped{RESET}" if r is None else f"{RED}not responding{RESET}")
        print(f"  {prov:7} {tag}")
    print()

    return 0 if all(r is not False for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
