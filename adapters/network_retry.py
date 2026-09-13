"""
adapters/network_retry.py - Network resilience decorator with strict detection and exponential backoff.
Explicitly distinguishes between transient network failures (429, timeout, connection) and non-retryable errors.
"""

import time
import functools
import logging
from typing import Callable, Any
import requests

logger = logging.getLogger(__name__)

class NetworkTransportError(Exception):
    """Specific exception for persistent network transport failures in LLM adapters."""
    def __init__(self, message: str, status_code: int | None = None, response_text: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text

def is_transient_network_error(exc: Exception) -> tuple[bool, str, int | None, float | None]:
    """
    Evaluate whether an exception represents a retryable transient network error.
    Returns: (is_retryable, reason, status_code, retry_after_seconds)
    """
    if isinstance(exc, requests.exceptions.Timeout):
        return True, "HTTP request timeout", None, None
        
    if isinstance(exc, requests.exceptions.ConnectionError):
        return True, "Network connection or socket error", None, None

    if isinstance(exc, requests.exceptions.HTTPError):
        resp = getattr(exc, "response", None)
        if resp is not None:
            code = resp.status_code
            # Only retry 429 (Rate Limit) or temporary server errors (502, 503, 504)
            if code in (429, 502, 503, 504):
                # Extract Retry-After header if provided by server
                retry_after_header = resp.headers.get("Retry-After")
                retry_after = None
                if retry_after_header:
                    try:
                        retry_after = float(retry_after_header)
                    except ValueError:
                        pass
                return True, f"HTTP {code} ({resp.reason or 'Rate Limit / Service Unavailable'})", code, retry_after
            # 400, 401, 403, 404, etc. are permanent
            return False, f"HTTP {code} (Permanent client error, non-retryable)", code, None

    # Any other error (ValueError, JSONDecodeError, KeyError) is non-transient
    return False, type(exc).__name__, None, None

def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 30.0
):
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            delay = initial_delay
            last_error = None
            last_code = None
            last_resp_text = None
            
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
                        last_code = e.response.status_code
                        last_resp_text = e.response.text[:500]
                        
                    is_retryable, reason, code, server_retry_after = is_transient_network_error(e)
                    
                    if not is_retryable:
                        # Fail immediately without waiting or consuming retries
                        logger.error(f"[Network] Permanent error in {func.__name__}: {reason}. Aborting.")
                        raise
                        
                    wait_time = delay
                    if server_retry_after is not None and server_retry_after > 0:
                        wait_time = min(server_retry_after, max_delay)
                    else:
                        wait_time = min(delay, max_delay)
                        delay *= backoff_factor

                    print(
                        f"[Network Retry] Attempt {attempt}/{max_retries} failed for {func.__name__} "
                        f"due to {reason}. Retrying in {wait_time:.1f}s..."
                    )
                    time.sleep(wait_time)
                    
            raise NetworkTransportError(
                f"Persistent network transport failure after {max_retries} attempts in {func.__name__}: {last_error}",
                status_code=last_code,
                response_text=last_resp_text
            ) from last_error
        return wrapper
    return decorator
