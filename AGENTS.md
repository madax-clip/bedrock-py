# AGENTS.md

Agent guidance for the Bedrock monorepo.

## Language Policy

- **Code**: English only (comments, docstrings, variables, docs)
- **Interactions**: Match user's language

## Overview

Python monorepo for Bedrock modular framework. `uv` workspaces, `src/` layout.

- `packages/bedrock` — Core runtime (active)
- `packages/bedrock-cli` — Scaffolding CLI (planned, gitignored)
- `packages/bedrock-example` — Example app (gitignored)
- `docs-web/` — Derived fumadocs Web Doc site (don't hand-edit)
- `docs-web/content/docs` — Docs source-of-truth (MDX)
- `xboc/` — Reference prototype (gitignored, not for production)

## Commands

```bash
# Setup
uv sync --all-packages

# Build
uv build --all-packages
uv build --package bedrock

# Run
bedrock -v

# Lint (ruff configured, line-length=120)
uv run ruff check .
uv run ruff format .

# Tests (pytest, 4 test files in packages/bedrock/tests/)
uv run pytest packages/bedrock/tests/

# Docs
cd starlight-docs && npm run dev    # Dev server with live sync
cd starlight-docs && npm run build  # Production build

# Release (tag-driven, publishes both packages)
uv build --all-packages
git tag vX.Y.Z && git push origin vX.Y.Z  # tag must match both package versions

# Dependency vulnerability audit (same gate as CI/release)
uv export --locked --all-packages --no-dev --no-emit-project \
  | grep -vE '^\s*(#|$)' | grep -vE '^-e \./' > /tmp/reqs.txt
uvx pip-audit --disable-pip -r /tmp/reqs.txt
```

## Architecture

### Module Anatomy (Standard)

```
<name>/
├── __init__.py
├── manifest.yaml    # name, package, version, depends_on
├── entities.py      # Business domain entities (internal data flow)
├── schemas.py       # Optional: API input/output contracts (request/response DTOs)
├── service.py       # Business logic (no HTTP)
├── exc.py           # Module exceptions
└── bootstrap.py     # Optional: lifecycle hooks
```

### Key Singletons

| Instance | Class | Module |
|----------|-------|--------|
| `apps` | `ModuleRegistry` | `bedrock.module` |
| `db` | `DatabaseManager` | `bedrock.database` |

## Coding Standards

- **Line length**: 120 (ruff configured)
- **Docstrings**: Google-style mandatory
- **Type hints**: Strict, always include
- **Async prefix**: `a` (e.g., `aget()`, `aset()`, `adelete()`)
- **Exceptions**: `BedrockExc` hierarchy with `detail` attribute
- **Settings**: `Pydantic BaseSettings` with optional `SettingsProxy` for lazy singletons
- **Imports**: Relative within-package, absolute cross-package

## Exceptions
- All custom exceptions must inherit from `BedrockExc`
- Always raise exceptions which are subclasses of `BedrockExc` for Business Error.
- Always Write Human-Readable Messages in `detail` attribute of BedrockExc.

## Documentation
- Hand-write under `docs-web/content/docs/`


## Anti-Patterns (This Project)

- Never treat `bedrock-cli` commands as stable contracts
- Never use `from __future__ import annotations` in database/ modules
- Never import HTTP frameworks in core runtime
- Never use import-time side effects for module registration

## Notes

- Root `pyproject.toml` is workspace coordinator only, not application package
- `bedrock-cli` is planned/future work—current CLI lives in `packages/bedrock/src/bedrock/cli/`
- Ruff config: `[tool.ruff]` in root `pyproject.toml`
- Pytest: dev dependency, 4 test files, no conftest.py
- Both packages (`bedrock-core`, `bedrock-cli`) are versioned in lockstep; runtime versions derive from installed distribution metadata, so `pyproject.toml` is the single source of truth
- Releases are tag-driven (`vX.Y.Z`) via `.github/workflows/release.yml`: tag must match both package versions, non-empty `CHANGELOG.md` section for the tag is required before publish, both wheels are smoke-installed, and locked runtime deps are scanned with `pip-audit` (fail on findings; exceptions need a documented `--ignore-vuln` plus a `SECURITY.md` note)

## Agent skills

### Issue tracker

GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels

5 canonical roles mapped to GitHub labels. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at repo root. See `docs/agents/domain.md`.
