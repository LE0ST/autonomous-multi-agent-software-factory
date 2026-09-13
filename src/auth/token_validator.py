import hmac
import hashlib

def validate_token(token: str, secret: str = 'key') -> bool:
    if not token or not isinstance(token, str):
        return False
    expected = hmac.new(secret.encode(), b'valid', hashlib.sha256).hexdigest()
    return hmac.compare_digest(token, expected)
