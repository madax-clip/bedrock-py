"""Regression tests for v0.2.0 release-gate repairs in bedrock-cli.

Covers:
- The scaffolded project must depend on the published ``bedrock-core``
  distribution (not the legacy ``bedrock`` name) at ``>=0.2.0``.
- ``bedrock_cli.__version__`` must be single-sourced from the installed
  distribution metadata and match ``pyproject.toml``.
- ``bedrock-cli --version`` must print the distribution version.
- ``scripts/extract_release_notes.py`` must extract a ``CHANGELOG.md``
  section without dropping its final content line at EOF, and must fail
  for missing or empty sections.
- ``.github/workflows/release.yml`` must keep the smoke gate honest:
  explicit wheel paths (never unpinned names with ``--find-links``), the
  generated project installed itself, and distribution versions asserted.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from importlib import metadata
from pathlib import Path

from bedrock_cli.main import app
from typer.testing import CliRunner

runner = CliRunner()

_PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_EXTRACT_SCRIPT = _REPO_ROOT / "scripts" / "extract_release_notes.py"
_RELEASE_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "release.yml"


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


_CHANGELOG = """# Changelog

## [Unreleased]

### Added

- unreleased note

## [0.2.0] - 2026-08-04

### Added

- release note one
- release note two

## [0.1.2] - 2026-07-01

### Fixed

- older note
"""


def _run_extract(changelog_text: str, version: str) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as tmpdir:
        changelog = Path(tmpdir) / "CHANGELOG.md"
        changelog.write_text(changelog_text, encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(_EXTRACT_SCRIPT), str(changelog), version],
            capture_output=True,
            text=True,
            check=False,
        )


class TestExtractReleaseNotes:
    def test_extracts_middle_section_in_full(self) -> None:
        result = _run_extract(_CHANGELOG, "0.2.0")
        assert result.returncode == 0
        assert "release note one" in result.stdout
        assert "release note two" in result.stdout
        assert "older note" not in result.stdout
        assert "unreleased note" not in result.stdout

    def test_eof_section_keeps_its_final_content_line(self) -> None:
        # Regression: the old `sed '1d;$d'` pipeline dropped the last line of
        # a section running to EOF, failing a valid one-line release as empty.
        changelog = "# Changelog\n\n## [9.9.9] - 2026-01-01\n\n- only note\n"
        result = _run_extract(changelog, "9.9.9")
        assert result.returncode == 0
        assert "- only note" in result.stdout

    def test_missing_section_fails(self) -> None:
        result = _run_extract(_CHANGELOG, "3.1.4")
        assert result.returncode == 1

    def test_empty_section_fails(self) -> None:
        changelog = "# Changelog\n\n## [1.0.0] - 2026-01-01\n\n## [0.9.0] - 2025-01-01\n\n- note\n"
        result = _run_extract(changelog, "1.0.0")
        assert result.returncode == 1

    def test_whitespace_only_section_fails(self) -> None:
        changelog = "# Changelog\n\n## [1.0.0] - 2026-01-01\n\n   \n\t\n"
        result = _run_extract(changelog, "1.0.0")
        assert result.returncode == 1


class TestReleaseWorkflowSmokeGate:
    """Text guards against regressions of the review-mandated smoke gate."""

    def test_release_notes_use_robust_extractor(self) -> None:
        workflow = _RELEASE_WORKFLOW.read_text(encoding="utf-8")
        assert "extract_release_notes.py" in workflow
        assert "sed '1d;$d'" not in workflow

    def test_smoke_installs_explicit_wheel_paths(self) -> None:
        workflow = _RELEASE_WORKFLOW.read_text(encoding="utf-8")
        assert "dist/bedrock_core-*.whl" in workflow
        assert "dist/bedrock_cli-*.whl" in workflow
        # Unpinned package names must not be installed via --find-links:
        # that leaves PyPI as an eligible source for the artifacts under test.
        assert not re.search(r"--find-links dist bedrock-core", workflow)
        assert not re.search(r"--find-links dist bedrock-cli", workflow)

    def test_smoke_installs_generated_project_and_asserts_versions(self) -> None:
        workflow = _RELEASE_WORKFLOW.read_text(encoding="utf-8")
        # The scaffolded project itself is installed (`.` argument), and the
        # resolved bedrock-core version is asserted against the built wheel.
        assert re.search(r'uv pip install --python \.app-venv/bin/python --find-links "\$DIST_DIR" \.', workflow)
        assert "APP_CORE_INSTALLED" in workflow
        assert "CORE_WHEEL_VERSION" in workflow
        assert "CLI_INSTALLED" in workflow
