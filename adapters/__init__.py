"""
adapters - Módulo de adaptadores para proveedores de modelos LLM con soporte de simulación y resiliencia.
"""

from .contracts import TriageOutput, SecurityFilterOutput, LogicAuditOutput
from .network_retry import retry_with_backoff, NetworkTransportError
from .gemini_adapter import GeminiAdapter
from .deepseek_adapter import DeepSeekAdapter
from .glm_adapter import GLMAdapter
from .sanitizer import sanitize_secret_text

__all__ = [
    "TriageOutput",
    "SecurityFilterOutput",
    "LogicAuditOutput",
    "retry_with_backoff",
    "NetworkTransportError",
    "GeminiAdapter",
    "DeepSeekAdapter",
    "GLMAdapter",
    "sanitize_secret_text"
]
