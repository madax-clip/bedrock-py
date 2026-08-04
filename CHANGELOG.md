# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- contrib: new `bedrock.contrib.metrics` module with `MetricsRegistry` — minimal in-process,
  thread-safe counters and gauges with immutable, name-sorted `MetricSnapshot` snapshots
- contrib: new `bedrock.contrib.rate_limit` module with `RateLimit` — process-local,
  thread-safe rolling-window admission decisions with injectable clock and immutable
  `RateLimitDecision` results
- cli: `bedrock --version` / `-v` now reports the installed `bedrock-core` distribution
  version and exits
- cli: `bedrock-cli --version` / `-v` reports the installed `bedrock-cli` distribution
  version and exits; `bedrock_cli.__version__` now derives from distribution metadata
  instead of a hardcoded string

### Fixed

- packaging: `bedrock-cli init` now scaffolds a dependency on the published
  `bedrock-core>=0.2.0` distribution instead of the nonexistent `bedrock>=0.1.0`
- packaging: `bedrock-core` declares its real `click>=8.3.3` dependency and caps
  `typer<0.27` (0.27 vendored click), so `bedrock --help` works from a fresh wheel
  install

### Fixed

- cli: `bedrock run --app MODULE COMMAND` is repaired — the `--app`/`-a` flag (or the
  `BEDROCK_APP` environment variable) selects the module, and each loaded module's Typer
  app is mounted under its module name; module command names can no longer be misread as
  module names, and command-group collisions are deterministic (namespaced per module;
  built-in commands win with a warning)
- cli: `bedrock app inspect` is now passive — installation hooks of the inspected module
  and its dependencies are signature-checked but never executed
- cli: `bedrock manage` accepts `--app` as well as `-A`, and both `run` and `manage`
  document the `BEDROCK_APP` environment variable

### Security

- docs: the CLI reference now states explicitly that installed modules are trusted
  executable plugins — importing a module executes its code and Bedrock provides no
  sandboxing or passive-import guarantee
- deps: `click` upgraded to 8.4.2 (PYSEC-2026-2132) and `pydantic-settings` to 2.14.2
  (GHSA-4xgf-cpjx-pc3j); CI and the release pipeline now run `pip-audit` over the
  locked runtime dependency set and fail on known vulnerabilities

### Release

- release: `release.yml` now validates that the git tag matches both `bedrock-core`
  and `bedrock-cli` versions and that the `CHANGELOG.md` section for the tag exists and
  is non-empty before anything is built or published
- release: both `bedrock-core` and `bedrock-cli` distributions are built,
  smoke-tested (fresh-wheel install, `import bedrock`, `bedrock --help`,
  `bedrock-cli --help`, scaffolded project resolving `bedrock-core`), published to
  PyPI, and attached to the GitHub Release
- docs: `SECURITY.md` supported-version table now covers 0.2.x; `CONTRIBUTING.md`
  documents the dual-package release process and the vulnerability-scan exception policy

### Fixed

- di: `@inject` preserves the async identity of decorated coroutine functions and
  awaits their result instead of returning an unawaited coroutine
- hooks: async dispatch awaits awaitables returned by sync wrappers (e.g.
  decorator-wrapped async hook implementations)
- signal: integer sender `0` is now a distinct sender and is no longer aliased to
  the `ANY` wildcard route
- signal: exiting `connected_to(..., sender=X)` removes only the temporary `X`
  route and preserves the receiver's pre-existing routes

## [0.1.2] - 2026-05-23

### Fixed

- cli: populate apps on `bedrock app install` to ensure module state is ready
- database: allow calling `get_primary_keys` as a classmethod on `BedrockModel` classes
- database: correct type hint for `_registry` in `migrations/env.py` using quoted type annotations
- logging: update return type of `get_logger` to return `Logger` instead of `logger` module instance

## [0.1.1] - 2026-05-18

### Added

- CLI: `bedrock playbook` command for running module playbooks, with optional path argument
- Database: model-level full-text search support in `search_filter_sort_paginate`

### Fixed

- docs: `uv sync` corrected to `uv sync --all-packages` in `AGENTS.md`, `README.md`, and
  contributing guides — plain `uv sync` does not install workspace packages, breaking fresh
  contributor and CI setups
- database: removed `from __future__ import annotations` from `migrations_manager.py` and
  `migrations/env.py` per project policy; `TYPE_CHECKING`-guarded annotations quoted for
  runtime safety
- di: `_scope.py` now raises `ScopeError` instead of bare `RuntimeError` when writing to an
  inactive scope
- database: `DatabaseNotConfiguredError` now subclasses `ImproperlyConfigured` (BedrockExc
  hierarchy) with an explicit `detail` message
- database: `MigrationError` now subclasses `BedrockExc` with `detail` attribute;
  `BranchOwnershipError` inherits correctly
- database: six silent `except Exception` blocks in `MigrationsManager` now log at `DEBUG`
  level with `exc_info=True` instead of silently suppressing errors
- module: `populate()` re-entrancy guard now raises `ModuleLifecycleError` instead of bare
  `RuntimeError`
- module: invalid bootstrap hook signatures now raise `InvalidModuleCallableError` instead of
  bare `TypeError`
- database: `search_filter_sort_paginate` `model` parameter tightened from `Any` to
  `type[BedrockModel]`
- cli: `install` command implemented; `run` positional argument parsing fixed

### Changed

- database: filter and helper typing normalised across `service.py` and related modules
- hooks: `HookRegistry.namespace()` return type narrowed from `Any` to `HookNamespace`
- common: `DictManager.all()` return type corrected from `Iterable[str, str]` to
  `ItemsView[str, str]`
- utils: all functions in `inspect_func` fully annotated with strict type hints

### Documentation

- Aligned database README examples with the current API
- Updated all module structure references from `modules/` to `my_app/`
- Updated homepage and PyPI links in `pyproject.toml`

## [0.1.0] - 2026-05-08

### Added

- Module registry with manifest-driven dependency resolution and lifecycle hooks
- SQLAlchemy 2.0 database layer with Alembic migrations support
- Cache system with memory and Redis backends, distributed locks, and typed schemas
- Signal/event system (blinker-derived) with sync and async dispatch
- Typer-based CLI for module and database management
- Utility library: lazy loading, proxy objects, introspection, string helpers
- SettingsProxy for optional deferred environment reads on module-level singletons
- Exception hierarchy with `BedrockExc` base and `detail` attribute pattern
- Pydantic entity base class with `arbitrary_types_allowed`
- Fumadocs documentation site (`docs-web/`)
