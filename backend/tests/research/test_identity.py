"""Acceptance tests for local financial identity verification and authorization.

All cryptographic material in this module is generated within pytest's temporary
directory.  No application configuration or external identity service is read.

Author: Damon Li
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import jwt
import pytest
from app.research.auth import LocalRS256IdentityVerifier, ResearchAuthorizer
from app.research.errors import NON_ENUMERATING_DENIAL_CODE, DomainError
from app.research.ports import BearerCredential, Principal
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

TEST_NOW = datetime(2026, 10, 30, 2, 0, tzinfo=UTC)
ISSUER = "https://identity.example.test"
AUDIENCE = "finnews-research"
ENTITY_ID = "CN.SH.600519"
PRINCIPAL_A = UUID("11111111-1111-1111-1111-111111111111")
PRINCIPAL_B = UUID("22222222-2222-2222-2222-222222222222")


@dataclass(frozen=True)
class TemporaryIdentityMaterial:
    """Keep only temporary-path and public JWK references for an individual test."""

    private_key_path: Path
    jwks: dict[str, object]


@pytest.fixture
def temporary_identity_material(tmp_path: Path) -> TemporaryIdentityMaterial:
    """Generate test-only RSA material exclusively below pytest's temp directory."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_key_path = tmp_path / "test-only-rs256-private.pem"
    private_key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": "test-local-key", "alg": "RS256", "use": "sig"})
    return TemporaryIdentityMaterial(
        private_key_path=private_key_path,
        jwks={"keys": [public_jwk]},
    )


def _claims(
    *,
    principal_id: UUID = PRINCIPAL_A,
    issuer: str = ISSUER,
    audience: str = AUDIENCE,
    scopes: str = "research:create research:read",
    entity_ids: list[str] | None = None,
    expires_at: datetime | None = None,
    not_before: datetime | None = None,
) -> dict[str, object]:
    """Build a signed-token claim set with a test-only ignored request marker."""
    return {
        "iss": issuer,
        "aud": audience,
        "sub": str(principal_id),
        "scope": scopes,
        "entity_ids": entity_ids or [ENTITY_ID],
        "exp": int((expires_at or TEST_NOW + timedelta(minutes=5)).timestamp()),
        "nbf": int((not_before or TEST_NOW - timedelta(minutes=1)).timestamp()),
        "request_id": "same-request-id-does-not-authorize-a-principal",
        "untrusted_raw_claim": "claims-sentinel-must-not-reach-principal",
    }


def _rs256_token(
    material: TemporaryIdentityMaterial,
    *,
    claims: dict[str, object] | None = None,
    kid: str = "test-local-key",
    extra_headers: dict[str, str] | None = None,
) -> str:
    """Sign a test token using only the private material stored in tmp_path."""
    headers = {"kid": kid}
    if extra_headers:
        headers.update(extra_headers)
    return jwt.encode(
        claims or _claims(),
        material.private_key_path.read_bytes(),
        algorithm="RS256",
        headers=headers,
    )


def _verify(
    verifier: LocalRS256IdentityVerifier,
    credential: BearerCredential,
) -> Principal:
    """Run the asynchronous frozen port with the fixed test clock."""
    return asyncio.run(verifier.verify_bearer(credential=credential, now=TEST_NOW))


def test_valid_rs256_local_jwks_produces_immutable_principal(
    temporary_identity_material: TemporaryIdentityMaterial,
) -> None:
    """AC-B1: only valid local RS256 material produces a safe immutable Principal."""
    verifier = LocalRS256IdentityVerifier(
        issuer=ISSUER,
        audience=AUDIENCE,
        trusted_jwks=temporary_identity_material.jwks,
    )
    token = _rs256_token(temporary_identity_material)

    principal = _verify(verifier, BearerCredential(token))

    assert principal.principal_id == PRINCIPAL_A
    assert principal.scopes == frozenset({"research:create", "research:read"})
    assert principal.entity_ids == frozenset({ENTITY_ID})
    assert principal.expires_at > TEST_NOW
    assert "claims-sentinel-must-not-reach-principal" not in repr(principal)
    with pytest.raises(AttributeError):
        principal.issuer = "not-mutable"  # type: ignore[misc]


def test_invalid_identity_inputs_fail_closed(
    temporary_identity_material: TemporaryIdentityMaterial,
    tmp_path: Path,
) -> None:
    """AC-B2: unsupported or malformed identity inputs never receive a fallback."""
    verifier = LocalRS256IdentityVerifier(
        issuer=ISSUER,
        audience=AUDIENCE,
        trusted_jwks=temporary_identity_material.jwks,
    )
    hmac_key_path = tmp_path / "test-only-hmac.key"
    hmac_key_path.write_text("test-only-hmac-key-material-32bytes", encoding="utf-8")
    hmac_key = hmac_key_path.read_text(encoding="utf-8")
    valid_claims = _claims()
    valid_token = _rs256_token(temporary_identity_material, claims=valid_claims)
    signature = valid_token.rsplit(".", maxsplit=1)[1]
    altered_signature = "A" if signature[-1] != "A" else "B"
    bad_signature = (
        f"{valid_token.rsplit('.', maxsplit=1)[0]}.{signature[:-1]}{altered_signature}"
    )
    client_principal = Principal(
        principal_id=PRINCIPAL_A,
        scopes=frozenset({"research:read"}),
        entity_ids=frozenset({ENTITY_ID}),
        issuer=ISSUER,
        audience=AUDIENCE,
        expires_at=TEST_NOW + timedelta(minutes=5),
    )
    invalid_credentials: list[BearerCredential | Principal] = [
        BearerCredential(
            _rs256_token(
                temporary_identity_material,
                claims=_claims(issuer="https://wrong-issuer.example.test"),
            )
        ),
        BearerCredential(
            _rs256_token(
                temporary_identity_material,
                claims=_claims(audience="wrong-audience"),
            )
        ),
        BearerCredential(
            _rs256_token(
                temporary_identity_material,
                claims=_claims(expires_at=TEST_NOW - timedelta(seconds=1)),
            )
        ),
        BearerCredential(
            _rs256_token(
                temporary_identity_material,
                claims=_claims(not_before=TEST_NOW + timedelta(seconds=1)),
            )
        ),
        BearerCredential(jwt.encode(valid_claims, key=None, algorithm="none")),
        BearerCredential(jwt.encode(valid_claims, key=hmac_key, algorithm="HS256")),
        BearerCredential(
            _rs256_token(temporary_identity_material, kid="unknown-test-local-key")
        ),
        BearerCredential(
            _rs256_token(temporary_identity_material, extra_headers={"jku": "x"})
        ),
        BearerCredential(
            _rs256_token(temporary_identity_material, extra_headers={"x5u": "x"})
        ),
        BearerCredential(bad_signature),
        BearerCredential("not-a-jwt"),
        client_principal,
    ]

    for credential in invalid_credentials:
        with pytest.raises(DomainError) as raised:
            _verify(verifier, credential)  # type: ignore[arg-type]
        assert raised.value.code == "identity_invalid"
        assert (
            "claims-sentinel-must-not-reach-principal" not in raised.value.safe_message
        )
        assert "claims-sentinel-must-not-reach-principal" not in str(raised.value)

    unavailable = LocalRS256IdentityVerifier(
        issuer=ISSUER,
        audience=AUDIENCE,
        trusted_jwks=None,
    )
    with pytest.raises(DomainError) as raised:
        _verify(unavailable, BearerCredential(valid_token))
    assert raised.value.code == "identity_material_unavailable"


def test_authorize_resource_has_scope_entity_and_owner_isolation(
    temporary_identity_material: TemporaryIdentityMaterial,
) -> None:
    """AC-B3: owner, scope, and entity checks are non-enumerating and isolated."""
    verifier = LocalRS256IdentityVerifier(
        issuer=ISSUER,
        audience=AUDIENCE,
        trusted_jwks=temporary_identity_material.jwks,
    )
    authorizer = ResearchAuthorizer()
    principal_a = _verify(
        verifier,
        BearerCredential(_rs256_token(temporary_identity_material)),
    )
    principal_b = _verify(
        verifier,
        BearerCredential(
            _rs256_token(
                temporary_identity_material,
                claims=_claims(principal_id=PRINCIPAL_B, scopes="research:read"),
            )
        ),
    )

    authorizer.authorize_resource(
        principal=principal_a,
        owner_id=PRINCIPAL_A,
        entity_ids=frozenset({ENTITY_ID}),
        required_scope="research:create",
        now=TEST_NOW,
    )

    denial_cases = (
        (principal_b, PRINCIPAL_B, frozenset({ENTITY_ID}), "research:create"),
        (principal_a, PRINCIPAL_A, frozenset({"CN.SZ.000001"}), "research:read"),
        (principal_a, PRINCIPAL_B, frozenset({ENTITY_ID}), "research:read"),
    )
    for principal, owner_id, entity_ids, required_scope in denial_cases:
        with pytest.raises(DomainError) as raised:
            authorizer.authorize_resource(
                principal=principal,
                owner_id=owner_id,
                entity_ids=entity_ids,
                required_scope=required_scope,  # type: ignore[arg-type]
                now=TEST_NOW,
            )
        assert raised.value.code == NON_ENUMERATING_DENIAL_CODE
        assert raised.value.safe_message == "resource was not found or access is denied"

    for malformed in (None, "CN.SH.600519", ["CN.SH.600519"], {1}):
        with pytest.raises(DomainError) as raised:
            authorizer.authorize_resource(
                principal=principal_a,
                owner_id=PRINCIPAL_A,
                entity_ids=malformed,
                required_scope="research:read",
                now=TEST_NOW,
            )  # type: ignore[arg-type]
        assert raised.value.code == NON_ENUMERATING_DENIAL_CODE
        assert raised.value.safe_message == "resource was not found or access is denied"


def test_jwks_mutation_cannot_add_attacker_signing_key(
    temporary_identity_material: TemporaryIdentityMaterial, tmp_path: Path
) -> None:
    """The verifier trusts only the deep snapshot captured during construction."""
    verifier = LocalRS256IdentityVerifier(
        issuer=ISSUER, audience=AUDIENCE, trusted_jwks=temporary_identity_material.jwks
    )
    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    attacker_path = tmp_path / "attacker-test-only.pem"
    attacker_path.write_bytes(
        attacker.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    attacker_public = json.loads(RSAAlgorithm.to_jwk(attacker.public_key()))
    attacker_public.update({"kid": "attacker-key", "alg": "RS256", "use": "sig"})
    temporary_identity_material.jwks["keys"].append(attacker_public)
    token = jwt.encode(
        _claims(),
        attacker_path.read_bytes(),
        algorithm="RS256",
        headers={"kid": "attacker-key"},
    )
    with pytest.raises(DomainError) as raised:
        _verify(verifier, BearerCredential(token))
    assert raised.value.code == "identity_invalid"
