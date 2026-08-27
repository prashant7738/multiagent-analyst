"""POST /api/health/test-llm tests the signed-in user's saved key per provider."""

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.app import app
from api.models.schemas import AuthUser
from api.routes import health
from api.routes.auth import get_optional_user


class TestTestLlmEndpoint(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        health._health_cache.clear()

    def tearDown(self):
        app.dependency_overrides.pop(get_optional_user, None)
        health._health_cache.clear()

    def test_anonymous_tests_shared_keys_and_caches(self):
        app.dependency_overrides[get_optional_user] = lambda: None
        with patch.object(health, "_check_groq_health", return_value="healthy") as groq, \
             patch.object(health, "_check_gemini_health", return_value="healthy"), \
             patch.object(health, "_check_huggingface_health", return_value="healthy"), \
             patch.object(health, "_check_database_health", return_value="healthy"):
            r = self.client.post("/api/health/test-llm")
        self.assertEqual(r.status_code, 200)
        groq.assert_called_once_with(None)               # shared key path
        self.assertIn("groq", health._health_cache)       # shared result IS cached

    def test_signed_in_user_tests_saved_keys_and_skips_cache(self):
        app.dependency_overrides[get_optional_user] = lambda: AuthUser(
            user_id="u1", email="u@x.com", name="U",
            created_at=datetime.now(timezone.utc),
        )
        saved = {"groq_api_key": "gsk_mine", "gemini_api_key": "", "hf_token": "hf_mine"}
        with patch.object(health, "_saved_user_keys", return_value={k: v for k, v in saved.items() if v}), \
             patch.object(health, "_check_groq_health", return_value="healthy") as groq, \
             patch.object(health, "_check_gemini_health", return_value="not_configured") as gem, \
             patch.object(health, "_check_huggingface_health", return_value="healthy") as hf, \
             patch.object(health, "_check_database_health", return_value="healthy"):
            r = self.client.post("/api/health/test-llm")
        self.assertEqual(r.status_code, 200)
        groq.assert_called_once_with("gsk_mine")          # user's own key
        gem.assert_called_once_with(None)                 # no saved gemini -> shared default
        hf.assert_called_once_with("hf_mine")
        # personalized result must NOT leak into the public /api/health cache
        self.assertNotIn("groq", health._health_cache)
        self.assertIn("database", health._health_cache)   # db has no per-user variant


if __name__ == "__main__":
    unittest.main()
