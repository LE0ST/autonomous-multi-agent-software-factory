"""
adapters/network_retry.py - Decorador de tolerancia de red con detección estricta y backoff exponencial.
Distingue explícitamente entre fallos transitorios de red (429, timeout, conexión) y errores no reintentables.
"""

import time
import functools
import logging
from typing import Callable, Any
import requests

logger = logging.getLogger(__name__)

class NetworkTransportError(Exception):
    """Excepción específica para fallos de red persistentes en los adaptadores LLM."""
    def __init__(self, message: str, status_code: int | None = None, response_text: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text

def is_transient_network_error(exc: Exception) -> tuple[bool, str, int | None, float | None]:
    """
    Evalúa si una excepción es un error transitorio de red reintentable.
    Retorna: (es_reintentable, razon, status_code, retry_after_segundos)
    """
    if isinstance(exc, requests.exceptions.Timeout):
        return True, "Timeout de solicitud HTTP", None, None
        
    if isinstance(exc, requests.exceptions.ConnectionError):
        return True, "Fallo de conexión o socket de red", None, None

    if isinstance(exc, requests.exceptions.HTTPError):
        resp = getattr(exc, "response", None)
        if resp is not None:
            code = resp.status_code
            # Solo reintentar 429 (Rate Limit) o fallos de servidor temporales (502, 503, 504)
            if code in (429, 502, 503, 504):
                # Extraer cabecera Retry-After si el servidor la provee
                retry_after_header = resp.headers.get("Retry-After")
                retry_after = None
                if retry_after_header:
                    try:
                        retry_after = float(retry_after_header)
                    except ValueError:
                        pass
                return True, f"HTTP {code} ({resp.reason or 'Rate Limit / Servidor no disponible'})", code, retry_after
            # 400, 401, 403, 404, etc. son permanentes
            return False, f"HTTP {code} (Error de cliente permanente, no reintentable)", code, None

    # Cualquier otro error (ValueError, JSONDecodeError, KeyError) es no transitorio
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
                        # Fallar inmediatamente sin esperar ni consumir reintentos
                        logger.error(f"[Network] Error permanente en {func.__name__}: {reason}. Abortando.")
                        raise
                        
                    wait_time = delay
                    if server_retry_after is not None and server_retry_after > 0:
                        wait_time = min(server_retry_after, max_delay)
                    else:
                        wait_time = min(delay, max_delay)
                        delay *= backoff_factor

                    print(
                        f"[Network Retry] Intento {attempt}/{max_retries} falló para {func.__name__} "
                        f"por {reason}. Reintentando en {wait_time:.1f}s..."
                    )
                    time.sleep(wait_time)
                    
            raise NetworkTransportError(
                f"Fallo de transporte persistente tras {max_retries} intentos en {func.__name__}: {last_error}",
                status_code=last_code,
                response_text=last_resp_text
            ) from last_error
        return wrapper
    return decorator
