"""
adapters/contracts.py - Pydantic schemas for structured contracts between agents and gates.
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field

class TriageOutput(BaseModel):
    failing_test: str = Field(..., description="Identifier or path of the failing test")
    project_file: str = Field(..., description="Project source file where the failure originated")
    line_number: int = Field(..., description="Approximate error line number")
    expected: str = Field(..., description="Expected behavior or value")
    received: str = Field(..., description="Received behavior or value")
    root_cause: str = Field(..., description="Root cause diagnostic explanation")

class SecurityFilterOutput(BaseModel):
    finding_id: str = Field(..., description="SAST finding identifier or rule key")
    classification: Literal["TRUE_POSITIVE", "FALSE_POSITIVE", "UNCERTAIN"] = Field(
        ..., description="Vulnerability classification"
    )
    justification: str = Field(..., description="Technical justification for the classification")

class LogicAuditOutput(BaseModel):
    status: Literal["PASS", "FAIL", "UNAVAILABLE", "SIMULATED", "UNCERTAIN"] = Field(
        ..., description="Logic and security invariants audit outcome"
    )
    violated_invariants: list[str] = Field(
        default_factory=list, description="List of violated [SEC-xx] invariants"
    )
    exploit_poc: Optional[str] = Field(
        None, description="Proof of concept or exploit vector if vulnerable"
    )
    justification: str = Field(..., description="Detailed security and logic analysis")
