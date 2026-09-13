"""
adapters/contracts.py - Esquemas Pydantic para los contratos estructurados entre agentes y compuertas.
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field

class TriageOutput(BaseModel):
    failing_test: str = Field(..., description="Identificador o ruta del test que falló")
    project_file: str = Field(..., description="Archivo de código donde se originó el fallo")
    line_number: int = Field(..., description="Línea aproximada del error")
    expected: str = Field(..., description="Comportamiento o valor esperado")
    received: str = Field(..., description="Comportamiento o valor recibido")
    root_cause: str = Field(..., description="Diagnóstico de la causa raíz")

class SecurityFilterOutput(BaseModel):
    finding_id: str = Field(..., description="Identificador o regla del hallazgo SAST")
    classification: Literal["TRUE_POSITIVE", "FALSE_POSITIVE", "UNCERTAIN"] = Field(
        ..., description="Clasificación de la vulnerabilidad"
    )
    justification: str = Field(..., description="Justificación técnica de la clasificación")

class LogicAuditOutput(BaseModel):
    status: Literal["PASS", "FAIL", "UNCERTAIN"] = Field(
        ..., description="Resultado de la auditoría de lógica de negocio e invariantes"
    )
    violated_invariants: list[str] = Field(
        default_factory=list, description="Lista de invariantes [SEC-xx] violados"
    )
    exploit_poc: Optional[str] = Field(
        None, description="Prueba de concepto o vector de ataque si fue vulnerable"
    )
    justification: str = Field(..., description="Análisis detallado de seguridad y lógica")
