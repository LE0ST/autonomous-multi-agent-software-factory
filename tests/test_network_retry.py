import pytest
import requests
from adapters.network_retry import retry_with_backoff, NetworkTransportError

def test_non_retryable_error_fails_immediately():
    call_count = 0

    @retry_with_backoff(max_retries=3, initial_delay=0.01)
    def fail_with_value_error():
        nonlocal call_count
        call_count += 1
        raise ValueError("Invalid format")

    with pytest.raises(ValueError, match="Invalid format"):
        fail_with_value_error()

    # No debe reintentar errores no transitorios
    assert call_count == 1

def test_http_401_unauthorized_fails_immediately():
    call_count = 0

    @retry_with_backoff(max_retries=3, initial_delay=0.01)
    def fail_unauthorized():
        nonlocal call_count
        call_count += 1
        response = requests.Response()
        response.status_code = 401
        response.reason = "Unauthorized"
        raise requests.exceptions.HTTPError(response=response)

    with pytest.raises(requests.exceptions.HTTPError):
        fail_unauthorized()

    assert call_count == 1

def test_retryable_timeout_retries_and_recovers():
    call_count = 0

    @retry_with_backoff(max_retries=3, initial_delay=0.01)
    def timeout_then_succeed():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise requests.exceptions.Timeout("Connection timed out")
        return "success"

    result = timeout_then_succeed()
    assert result == "success"
    assert call_count == 2

def test_retryable_429_exhausts_and_raises_network_transport_error():
    call_count = 0

    @retry_with_backoff(max_retries=3, initial_delay=0.01, backoff_factor=1.0)
    def always_429():
        nonlocal call_count
        call_count += 1
        response = requests.Response()
        response.status_code = 429
        response.reason = "Too Many Requests"
        response.headers["Retry-After"] = "0.01"
        raise requests.exceptions.HTTPError(response=response)

    with pytest.raises(NetworkTransportError) as exc_info:
        always_429()

    assert call_count == 3
    assert exc_info.value.status_code == 429
