#!/usr/bin/env python
"""Quick test to verify backend configuration."""

from api.config import get_settings

settings = get_settings()

print("\n" + "="*50)
print("  Backend Configuration")
print("="*50)
print(f"  Host:       {settings.host}")
print(f"  Port:       {settings.port}")
print(f"  Reload:     {settings.reload}")
print(f"  Log Level:  {settings.log_level}")
print("="*50)
print(f"\n✅ Backend will run on: http://{settings.host}:{settings.port}")
print(f"✅ API Docs available at: http://localhost:{settings.port}/docs\n")
