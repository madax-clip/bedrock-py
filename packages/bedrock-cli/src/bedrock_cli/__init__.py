"""bedrock-cli package metadata.

The runtime version is single-sourced from the installed distribution
metadata (see ``[project] version`` in ``pyproject.toml``) so the CLI can
never drift from the released artifact version.
"""

from __future__ import annotations

from importlib import metadata

__all__ = ["__version__"]

try:
    __version__ = metadata.version("bedrock-cli")
except metadata.PackageNotFoundError:  # pragma: no cover - editable/source tree without install
    __version__ = "0.0.0+unknown"
