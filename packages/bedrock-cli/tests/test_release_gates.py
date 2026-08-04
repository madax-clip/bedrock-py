"""Regression tests for v0.2.0 release-gate repairs in bedrock-cli.

Covers:
- The scaffolded project must depend on the published ``bedrock-core``
  distribution (not the legacy ``bedrock`` name) at ``>=0.2.0``.
- ``bedrock_cli.__version__`` must be single-sourced from the installed
  distribution metadata and match ``pyproject.toml``.
- ``bedrock-cli --version`` must print the distribution version.
"""

from __future__ import annotations

import re
import tempfile
from importlib import metadata
from pathlib import Path

from bedrock_cli.main import app
from typer.testing import CliRunner

runner = CliRunner()

_PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


class TestScaffoldDependency:
    def test_scaffolded_pyproject_depends_on_bedrock_core(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.invoke(app, ["init", "rel-app", "-o", tmpdir])
            assert result.exit_code == 0

            pyproject = (Path(tmpdir) / "rel-app" / "pyproject.toml").read_text(encoding="utf-8")
            assert '"bedrock-core>=0.2.0"' in pyproject
            # The legacy/wrong distribution name must not be rendered.
            assert not re.search(r'"bedrock(?!-core)[><=]', pyproject)

    def test_scaffolded_dependency_spec_is_valid_pep508(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.invoke(app, ["init", "rel-app", "-o", tmpdir])
            assert result.exit_code == 0

            pyproject = (Path(tmpdir) / "rel-app" / "pyproject.toml").read_text(encoding="utf-8")
            match = re.search(r'"(bedrock-core[^"]*)"', pyproject)
            assert match is not None
            from packaging.requirements import Requirement  # noqa: PLC0415

            req = Requirement(match.group(1))
            assert req.name == "bedrock-core"


class TestVersionSingleSourcing:
    def test_runtime_version_matches_distribution_metadata(self) -> None:
        import bedrock_cli  # noqa: PLC0415

        assert bedrock_cli.__version__ == metadata.version("bedrock-cli")

    def test_distribution_version_matches_pyproject(self) -> None:
        declared = re.search(r'^version = "([^"]+)"', _PYPROJECT.read_text(encoding="utf-8"), re.MULTILINE)
        assert declared is not None
        assert metadata.version("bedrock-cli") == declared.group(1)

    def test_version_flag_prints_distribution_version(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert metadata.version("bedrock-cli") in result.output
