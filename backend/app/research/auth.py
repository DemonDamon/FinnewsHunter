"""Verify local RS256 bearers and apply research resource authorization.

This module accepts only parent-injected local public JWK material.  It neither
loads configuration nor discovers identity material over the network.

Author: Damon Li
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Final
from uuid import UUID

import jwt
from jwt.algorithms import RSAAlgorithm
from jwt.exceptions import InvalidTokenError

from app.research.errors import NON_ENUMERATING_DENIAL_CODE, DomainError
from app.research.ports import (
    AuthorizationPort,
    BearerCredential,
    IdentityVerifierPort,
    Principal,
    ResearchScope,
)

_ALLOWED_ALGORITHM: Final = "RS256"
_ALLOWED_SCOPES: Final = frozenset({"research:create", "research:read"})
_ENTITY_ID_PATTERN: Final = re.compile(r"^CN\.(?:SH|SZ|BJ)\.[0-9]{6}$")


def _is_aware(value: object) -> bool:
    """Return whether a value is an aware datetime without raising diagnostics."""
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _identity_invalid() -> DomainError:
    """Return the one safe failure used for all untrusted bearer problems."""
    return DomainError(
        code="identity_invalid",
        safe_message="identity verification failed",
        retryable=False,
    )


def _identity_material_unavailable() -> DomainError:
    """Return the one safe failure used for unavailable trusted key material."""
    return DomainError(
        code="identity_material_unavailable",
        safe_message="identity material is unavailable",
        retryable=True,
    )


def _denied() -> DomainError:
    """Return the shared denial without distinguishing resource state or reason."""
    return DomainError(
        code=NON_ENUMERATING_DENIAL_CODE,
        safe_message="resource was not found or access is denied",
        retryable=False,
    )


class LocalRS256IdentityVerifier(IdentityVerifierPort):
    """Build Principals only from fully validated local RS256 bearer tokens.

    ``trusted_jwks`` may be either a conventional local JWKS mapping containing
    ``keys`` or a mapping from trusted ``kid`` values to public JWK mappings.
    It is deliberately an injected value: no environment, file, cache, or URL
    is consulted by this adapter.
    """

    __slots__ = ("_audience", "_issuer", "_trusted_jwks")

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        trusted_jwks: Mapping[str, object] | None,
    ) -> None:
        """Keep only parent-supplied local verification parameters."""
        self._issuer = issuer
        self._audience = audience
        self._trusted_jwks = self._freeze(trusted_jwks)

    @classmethod
    def _freeze(cls, value: object) -> object:
        """Deep-copy local JWKS into immutable containers at construction."""
        if isinstance(value, Mapping):
            return MappingProxyType(
                {key: cls._freeze(item) for key, item in value.items()}
            )
        if isinstance(value, (list, tuple)):
            return tuple(cls._freeze(item) for item in value)
        return value

    async def verify_bearer(
        self,
        *,
        credential: BearerCredential,
        now: datetime,
    ) -> Principal:
        """Verify a bearer and return a Principal without retaining its contents."""
        if not isinstance(credential, BearerCredential) or not _is_aware(now):
            raise _identity_invalid()
        if not self._is_configured():
            raise _identity_material_unavailable()

        serialized = credential.for_verification()
        header = self._read_header(serialized)
        kid = header.get("kid")
        if (
            header.get("alg") != _ALLOWED_ALGORITHM
            or not isinstance(kid, str)
            or not kid
            or "jku" in header
            or "x5u" in header
        ):
            raise _identity_invalid()

        jwk = self._select_trusted_jwk(kid)
        try:
            public_key = RSAAlgorithm.from_jwk(
                json.dumps(dict(jwk), separators=(",", ":"), sort_keys=True)
            )
        except (KeyError, TypeError, ValueError):
            raise _identity_material_unavailable() from None

        try:
            claims = jwt.decode(
                serialized,
                key=public_key,
                algorithms=[_ALLOWED_ALGORITHM],
                audience=self._audience,
                issuer=self._issuer,
                options={
                    "require": ["exp", "nbf", "iss", "aud", "sub"],
                    "verify_exp": False,
                    "verify_nbf": False,
                    "verify_iat": False,
                },
            )
        except (InvalidTokenError, TypeError, ValueError):
            raise _identity_invalid() from None

        expires_at = self._numeric_date(claims, "exp")
        not_before = self._numeric_date(claims, "nbf")
        if now >= expires_at or now < not_before or expires_at <= not_before:
            raise _identity_invalid()

        principal_id = self._principal_id(claims)
        scopes = self._scopes(claims)
        entity_ids = self._entity_ids(claims)
        try:
            return Principal(
                principal_id=principal_id,
                scopes=scopes,
                entity_ids=entity_ids,
                issuer=self._issuer,
                audience=self._audience,
                expires_at=expires_at,
            )
        except ValueError:
            raise _identity_invalid() from None

    def _is_configured(self) -> bool:
        """Require explicit issuer, audience, and nonempty local JWKS material."""
        return (
            isinstance(self._issuer, str)
            and bool(self._issuer)
            and isinstance(self._audience, str)
            and bool(self._audience)
            and isinstance(self._trusted_jwks, Mapping)
            and bool(self._trusted_jwks)
        )

    @staticmethod
    def _read_header(serialized: str) -> Mapping[str, object]:
        """Parse only the untrusted header needed to select a local public key."""
        try:
            header = jwt.get_unverified_header(serialized)
        except (InvalidTokenError, TypeError, ValueError):
            raise _identity_invalid() from None
        if not isinstance(header, Mapping):
            raise _identity_invalid()
        return header

    def _select_trusted_jwk(self, kid: str) -> Mapping[str, object]:
        """Select one configured public RSA JWK without using token-supplied URLs."""
        material = self._trusted_jwks
        if not isinstance(material, Mapping):
            raise _identity_material_unavailable()

        if "keys" in material:
            keys = material["keys"]
            if isinstance(keys, (str, bytes)) or not isinstance(keys, Sequence):
                raise _identity_material_unavailable()
            matches = [
                item
                for item in keys
                if isinstance(item, Mapping) and item.get("kid") == kid
            ]
            if not matches:
                raise _identity_invalid()
            if len(matches) != 1:
                raise _identity_material_unavailable()
            selected = matches[0]
        else:
            selected = material.get(kid)
            if selected is None:
                raise _identity_invalid()

        if not isinstance(selected, Mapping):
            raise _identity_material_unavailable()
        if not self._is_public_rs256_jwk(selected, kid):
            raise _identity_material_unavailable()
        return selected

    @staticmethod
    def _is_public_rs256_jwk(jwk: Mapping[str, object], kid: str) -> bool:
        """Reject symmetric, private, mismatched, or non-RS256 local material."""
        algorithm = jwk.get("alg")
        use = jwk.get("use")
        return (
            jwk.get("kid") == kid
            and jwk.get("kty") == "RSA"
            and isinstance(jwk.get("n"), str)
            and bool(jwk["n"])
            and isinstance(jwk.get("e"), str)
            and bool(jwk["e"])
            and "d" not in jwk
            and "k" not in jwk
            and algorithm in (None, _ALLOWED_ALGORITHM)
            and use in (None, "sig")
        )

    @staticmethod
    def _numeric_date(claims: Mapping[str, object], name: str) -> datetime:
        """Parse one signed NumericDate claim with no tolerance or fallback."""
        value = claims.get(name)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise _identity_invalid()
        try:
            return datetime.fromtimestamp(value, tz=UTC)
        except (OverflowError, OSError, ValueError):
            raise _identity_invalid() from None

    @staticmethod
    def _principal_id(claims: Mapping[str, object]) -> UUID:
        """Read a UUID subject only from the verified claim set."""
        subject = claims.get("sub")
        if not isinstance(subject, str):
            raise _identity_invalid()
        try:
            return UUID(subject)
        except ValueError:
            raise _identity_invalid() from None

    @staticmethod
    def _scopes(claims: Mapping[str, object]) -> frozenset[ResearchScope]:
        """Accept one strict verified scope representation and no client default."""
        if "scope" in claims and "scopes" in claims:
            raise _identity_invalid()
        raw_scopes = claims.get("scope", claims.get("scopes"))
        if isinstance(raw_scopes, str):
            values = raw_scopes.split()
        elif isinstance(raw_scopes, Sequence) and not isinstance(
            raw_scopes, (bytes, str)
        ):
            values = list(raw_scopes)
        else:
            raise _identity_invalid()
        if not values or any(not isinstance(value, str) for value in values):
            raise _identity_invalid()
        scopes = frozenset(values)
        if not scopes or not scopes.issubset(_ALLOWED_SCOPES):
            raise _identity_invalid()
        return scopes  # type: ignore[return-value]

    @staticmethod
    def _entity_ids(claims: Mapping[str, object]) -> frozenset[str]:
        """Require a nonempty canonical entity scope from verified claims."""
        raw_entities = claims.get("entity_ids")
        if isinstance(raw_entities, (str, bytes)) or not isinstance(
            raw_entities, Sequence
        ):
            raise _identity_invalid()
        if not raw_entities or any(
            not isinstance(entity_id, str)
            or _ENTITY_ID_PATTERN.fullmatch(entity_id) is None
            for entity_id in raw_entities
        ):
            raise _identity_invalid()
        entity_ids = frozenset(raw_entities)
        if len(entity_ids) != len(raw_entities):
            raise _identity_invalid()
        return entity_ids


class ResearchAuthorizer(AuthorizationPort):
    """Apply an identical non-enumerating owner, scope, and entity rule."""

    __slots__ = ()

    def authorize_resource(
        self,
        *,
        principal: Principal,
        owner_id: UUID,
        entity_ids: frozenset[str],
        required_scope: ResearchScope,
        now: datetime,
    ) -> None:
        """Authorize only a live owner with the exact scope and entity coverage."""
        if (
            not isinstance(principal, Principal)
            or not isinstance(owner_id, UUID)
            or not isinstance(required_scope, str)
            or required_scope not in _ALLOWED_SCOPES
            or not isinstance(entity_ids, (set, frozenset))
            or not entity_ids
            or any(
                not isinstance(entity_id, str)
                or _ENTITY_ID_PATTERN.fullmatch(entity_id) is None
                for entity_id in entity_ids
            )
            or not _is_aware(now)
            or now >= principal.expires_at
            or principal.principal_id != owner_id
            or required_scope not in principal.scopes
            or not entity_ids.issubset(principal.entity_ids)
        ):
            raise _denied()
