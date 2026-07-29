import os
import sys
import unittest.mock as mock

# Mock modules that main.py imports but may not be installed in CI
_bcrypt_mock = mock.MagicMock()
_bcrypt_mock.__name__ = "bcrypt"
sys.modules["bcrypt"] = _bcrypt_mock

_jose_mock = mock.MagicMock()
_jose_mock.__name__ = "jose"
sys.modules["jose"] = _jose_mock

# Save original env vars
_saved_env = {k: os.environ.get(k) for k in ("DB_HOST", "REDIS_HOST", "REDIS_PASSWORD")}
os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PASSWORD", "plagio_redis_pass")

_api_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _api_dir not in sys.path:
    sys.path.insert(0, _api_dir)

_root = os.path.abspath(os.path.join(_api_dir, ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)
