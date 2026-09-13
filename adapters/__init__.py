"""
adapters - Módulo de adaptadores para proveedores de modelos LLM con soporte de simulación y resiliencia.
"""

from .contracts import TriageOutput, SecurityFilterOutput, LogicAuditOutput
from .network_retry import retry_with_backoff, NetworkTransportError

__all__ = [
    "TriageOutput",
    "SecurityFilterOutput",
    "LogicAuditOutput",
    "retry_with_backoff",
    "NetworkTransportError",
]
