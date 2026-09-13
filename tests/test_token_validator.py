import hmac
import hashlib
from src.auth.token_validator import validate_token

def test_token_empty():
    assert validate_token('') is False
    assert validate_token(None) is False

def test_token_valid():
    valid_token = hmac.new(b'key', b'valid', hashlib.sha256).hexdigest()
    assert validate_token(valid_token) is True
