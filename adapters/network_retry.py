"""
adapters/network_retry.py - Decorador de tolerancia de red con backoff exponencial.
Captura timeouts, HTTP 429 (Rate Limit) y fallos de conexión sin imputar penalizaciones al Worker.
"""

import time
import functools
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)

class NetworkTransportError(Exception):
    """Excepción específica para fallos de red persistentes en los adaptadores LLM."""
    pass

def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    retryable_exceptions: tuple = (Exception,)
):
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            delay = initial_delay
            last_error = None
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_error = e
                    err_msg = str(e).lower()
                    # Identificar errores típicos de transporte / red
                    is_rate_limit = "429" in err_msg or "rate limit" in err_msg or "quota" in err_msg
                    is_timeout = "timeout" in err_msg or "timed out" in err_msg
                    is_connection = "connection" in err_msg or "failed to connect" in err_msg
                    
                    if not (is_rate_limit or is_timeout or is_connection or attempt < max_retries):
                        raise
                        
                    logger.warning(
                        f"[Network Retry] Intento {attempt}/{max_retries} falló para {func.__name__}: {e}. "
                        f"Reintentando en {delay:.2f}s..."
                    )
                    time.sleep(delay)
                    delay *= backoff_factor
            raise NetworkTransportError(
                f"Fallo de transporte persistente tras {max_retries} intentos en {func.__name__}: {last_error}"
            ) from last_error
        return wrapper
    return decorator
