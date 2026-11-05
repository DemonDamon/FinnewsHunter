"""Define stable, safe research-domain failures.

Author: Damon Li
"""

from __future__ import annotations

from typing import Literal, TypeAlias

from app.research.contracts import ContractError

DomainErrorCode: TypeAlias = Literal[
    "identity_invalid",
    "identity_material_unavailable",
    "resource_not_found_or_denied",
    "request_conflict",
    "evidence_ineligible",
    "market_data_unverifiable",
    "license_revoked",
    "execution_unavailable",
    "quota_exceeded",
    "invalid_run_state",
    "dispatch_mismatch",
    "snapshot_frozen",
    "lease_expired",
    "execution_fenced",
    "terminal_state",
    "citation_invalid",
    "brief_gate_rejected",
    "event_cursor_invalid",
    "persistence_failed",
]

NON_ENUMERATING_DENIAL_CODE: DomainErrorCode = "resource_not_found_or_denied"


class DomainError(Exception):
    """Carry a stable safe code without retaining unsafe diagnostic material."""

    __slots__ = ("code", "retryable", "safe_message")

    def __init__(
        self,
        *,
        code: DomainErrorCode,
        safe_message: str,
        retryable: bool,
    ) -> None:
        """Bind a stable error code and safe message without secret material."""
        if not safe_message:
            raise ValueError("safe_message must not be empty")
        self.code = code
        self.safe_message = safe_message
        self.retryable = retryable
        super().__init__(code)

    def __str__(self) -> str:
        """Render only the stable code so generic exception logging stays safe."""
        return self.code

    def as_contract_error(self) -> ContractError:
        """Build the bounded public error projection without internal diagnostics."""
        return ContractError(
            code=self.code,
            message=self.safe_message,
            retryable=self.retryable,
        )
