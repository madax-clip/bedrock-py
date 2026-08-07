# bedrock

`bedrock` is the runtime core of the Bedrock modular framework.

It provides manifest-driven module loading, lifecycle management, and first-party contrib modules for common capabilities.

## Status

**The core runtime is fully implemented and functional.**

This package contains production-ready subsystems:

- Module registry with dependency resolution and lifecycle hooks
- Dependency injection container with singleton/transient/scoped lifetimes
- Hook system for structured call/response extension points (sync, async, robust)
- SQLAlchemy 2.0 database layer with Alembic migrations
- Cache system with memory and Redis backends
- Synchronous local and S3 storage with provider-neutral metadata
- Structured count/gauge metrics with an optional provider ABC
- Signal/event system (blinker-derived)
- Typer-based CLI for module and database management
- Comprehensive utility library (lazy loading, introspection, string helpers)

## Installation

```bash
# With uv (recommended)
uv add bedrock-core

# With poetry
poetry add bedrock-core

# With pip
pip install bedrock-core

# With S3 storage support
pip install 'bedrock-core[storage-s3]'
```

## Quick Start

```python
import bedrock

# Initialize the runtime (discovers and loads modules)
bedrock.setup()

# Access key singletons
from bedrock.module import apps          # ModuleRegistry
from bedrock.database import db          # DatabaseManager
from bedrock.contrib.cache import cache  # CacheService
from bedrock.contrib.metrics import metrics  # MetricsService
from bedrock.contrib.storage import storage  # StorageService
```

## Key Singletons

| Singleton | Class | Import |
|-----------|-------|--------|
| `apps` | `ModuleRegistry` | `from bedrock.module import apps` |
| `container` | `Container` | `from bedrock.di import container` |
| `hooks` | `HookRegistry` | `from bedrock.hooks import hooks` |
| `db` | `DatabaseManager` | `from bedrock.database import db` |
| `cache` | `CacheService` | `from bedrock.contrib.cache import cache` |
| `metrics` | `MetricsService` | `from bedrock.contrib.metrics import metrics` |
| `storage` | `StorageService` | `from bedrock.contrib.storage import storage` |

## 0.2.1 contrib contracts

Storage and metrics are stable public APIs in the 0.2 release line. Storage is synchronous and provider-neutral;
the local backend is included and S3 requires `storage-s3`. Metrics validates and logs `count`/`gauge` events and
optionally forwards them to a custom `MetricsProvider`; no concrete exporter is bundled.

## Module Structure

```
my_app/
├── __init__.py
├── manifest.yaml    # Module identity and dependencies
├── models.py        # SQLAlchemy models (optional)
├── entities.py      # Pydantic models for validation
├── service.py       # Business logic
├── exc.py           # Module exceptions
└── bootstrap.py     # Lifecycle hooks
```

## Architecture

Bedrock is framework-agnostic by design. The core runtime has no HTTP dependencies and is usable in:

- API servers (FastAPI, Flask, etc.)
- Background workers (Celery, etc.)
- CLI tools
- Scripts and automation

For more details, see the [documentation](https://bedrock-py.com).
