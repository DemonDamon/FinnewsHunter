# S03-D handoff — Manus credit stop → Cursor completion

**Branch:** `feat/finnews-s03d-app-integration`  
**Baseline:** `197d9848` (S03-A/B/C in tree)  
**Resume commit:** `b46ec39` (WIP composition/settings/main + draft integration test)

## Completed in this pass

- Verified WIP wiring: `build_research_components` composes ledger/service/verifier/MCP with safe readiness; `main.py` mounts research router + MCP with dependency overrides; defaults remain legacy/disabled.
- Hardened `test_research_app_boot.py` for AC1 (legacy default + research-disabled route set) and AC2 (per-field readiness gaps, malformed JWKS liveness, execution flag vs executor readiness).
- Kept `test_research_surface_integration.py` (HTTP + MCP SDK share one `FakeService` and principal).

## Verification (local agent env)

```bash
cd backend
PYTHONPATH="$HOME/.local/lib/python3.12/site-packages:$PWD" python3 -m pytest \
  tests/research/test_research_app_boot.py \
  tests/research/test_research_surface_integration.py -q

# Broader research suite (excluding PG migrations), from repo root:
cd ..
PYTHONPATH="$HOME/.local/lib/python3.12/site-packages:backend" python3 -m pytest \
  backend/tests/research/ --ignore=backend/tests/research/test_research_migrations.py -q
```

Static gates on touched modules: `ruff check`, `ruff format --check`, `python3 -m py_compile`, `scripts/generate_research_contracts.py --check`, `git diff --check` — no lockfile changes.

## Notes

- Executor readiness intentionally stays `executor_not_installed` until S04.
- Integration tests use in-memory RS256 + fake service; not a PostgreSQL E2E claim.

Made-with: Damon Li
