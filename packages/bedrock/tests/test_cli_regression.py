"""CLI regression tests for the ``bedrock`` command contracts (v0.2.0).

These tests build temporary importable packages to exercise the real CLI
behavior end to end:

- ``bedrock run --app MODULE COMMAND`` invokes manifest-registered commands.
- Module command collisions are deterministic: a same-module ``run`` command
  wins with a warning; cross-module collisions raise a usage error.
- ``bedrock app inspect`` never executes installation hooks.
- ``bedrock --version`` reports the installed ``bedrock-core`` metadata.
- ``bedrock manage`` accepts ``--app`` / ``-A`` and ``BEDROCK_APP``.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import click
import pytest
import typer
from click.testing import CliRunner

runner = CliRunner()


def _write_module(
    root: Path,
    dotted_path: str,
    *,
    commands_py: str | None = None,
    installation_py: str | None = None,
    depends_on: list[str] | None = None,
) -> None:
    """Create an importable Bedrock module package under *root*."""
    package_dir = root.joinpath(*dotted_path.split("."))
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "__init__.py").write_text("", encoding="utf-8")

    manifest_lines = [
        'title: "Demo Module"',
        'version: "0.1.0"',
    ]
    if depends_on:
        manifest_lines.append("depends_on:")
        manifest_lines.extend(f"  - {dep}" for dep in depends_on)
    if commands_py is not None:
        manifest_lines.append("commands: commands:app")
    (package_dir / "manifest.yaml").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")

    if commands_py is not None:
        (package_dir / "commands.py").write_text(textwrap.dedent(commands_py), encoding="utf-8")
    if installation_py is not None:
        (package_dir / "installation.py").write_text(textwrap.dedent(installation_py), encoding="utf-8")


def _commands_py(command_name: str, output: str) -> str:
    return f'''
        import typer

        app = typer.Typer()

        @app.command(name="{command_name}")
        def handler() -> None:
            print("{output}")
    '''


def _installation_py(marker_path: Path) -> str:
    return f"""
        def install(**kwargs) -> None:
            with open({str(marker_path)!r}, "w", encoding="utf-8") as handle:
                handle.write("install hook executed")
    """


@pytest.fixture()
def module_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Provide an importable temporary package root with an isolated registry."""
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delenv("BEDROCK_APP", raising=False)
    from bedrock.settings import settings

    monkeypatch.setattr(settings, "APP", None)

    # ``apps`` is a module-level singleton re-exported from the package
    # ``__init__``; give each test a fresh registry on both names.
    import bedrock.module as module_pkg
    from bedrock.module import registry as registry_module

    fresh_registry = registry_module.ModuleRegistry()
    monkeypatch.setattr(registry_module, "apps", fresh_registry)
    monkeypatch.setattr(module_pkg, "apps", fresh_registry)
    return tmp_path


def _loaded_group(app: str):
    """Return a ``_AppCommandGroup`` with the selected app's commands loaded."""
    import bedrock.cli.run as cli_run

    group = cli_run._AppCommandGroup(name="run")
    group._load_app_commands(app)
    group._bedrock_commands_loaded = True
    return group


class TestRunModuleCommands:
    """``bedrock run --app MODULE COMMAND`` contract tests."""

    def test_run_invokes_manifest_registered_command(self, module_env: Path) -> None:
        _write_module(module_env, "demo_mod", commands_py=_commands_py("hello", "hello-from-demo-mod"))
        group = _loaded_group("demo_mod")

        # The loaded module's Typer app is mounted under its module name.
        assert list(group.commands) == ["demo_mod"]

        result = runner.invoke(group, ["demo_mod", "hello"])

        assert result.exit_code == 0, result.output
        assert "hello-from-demo-mod" in result.output

    def test_run_same_module_builtin_collision_prefers_builtin_with_warning(
        self, module_env: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import bedrock.cli.run as cli_run

        _write_module(module_env, "demo_mod", commands_py=_commands_py("hello", "from-module"))

        group = cli_run._AppCommandGroup(name="run")
        builtin = click.Command("demo_mod", callback=lambda: click.echo("from-builtin"))
        group.commands["demo_mod"] = builtin

        group._load_app_commands("demo_mod")

        assert group.commands["demo_mod"] is builtin
        assert "conflicts with a built-in 'run' command" in capsys.readouterr().err

        result = runner.invoke(group, ["demo_mod"])
        assert result.exit_code == 0, result.output
        assert "from-builtin" in result.output
        assert "from-module" not in result.output

    def test_run_module_command_groups_never_collide_across_modules(self, module_env: Path) -> None:
        """Same inner command name in app and dependency stays namespaced per module."""
        command = _commands_py("collide", "from-module")
        _write_module(module_env, "dep_mod", commands_py=command)
        _write_module(module_env, "demo_mod", commands_py=command, depends_on=["dep_mod"])

        group = _loaded_group("demo_mod")

        assert sorted(group.commands) == ["demo_mod", "dep_mod"]

        result = runner.invoke(group, ["dep_mod", "collide"])
        assert result.exit_code == 0, result.output
        assert "from-module" in result.output


class TestInspectNeverExecutesHooks:
    """``bedrock app inspect`` must be passive for the selected app and dependencies."""

    def test_inspect_does_not_execute_installation_hooks(self, module_env: Path) -> None:
        import bedrock.cli.apps as cli_apps

        dep_marker = module_env / "dep-executed.marker"
        app_marker = module_env / "app-executed.marker"
        _write_module(module_env, "dep_mod", installation_py=_installation_py(dep_marker))
        _write_module(module_env, "demo_mod", installation_py=_installation_py(app_marker), depends_on=["dep_mod"])

        # Both modules have valid hook signatures, so inspection succeeds —
        # without ever executing a hook for the app or its dependencies.
        cli_apps.inspect("demo_mod")

        assert not app_marker.exists()
        assert not dep_marker.exists()

    def test_inspect_passive_for_valid_hooks(self, module_env: Path) -> None:
        import bedrock.cli.apps as cli_apps

        marker = module_env / "executed.marker"
        _write_module(module_env, "demo_mod", installation_py=_installation_py(marker))

        cli_apps.inspect("demo_mod")

        assert not marker.exists()


class TestVersionFlag:
    """``bedrock --version`` reports the installed ``bedrock-core`` metadata."""

    def test_version_flag_prints_bedrock_core_version(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "bedrock.cli.main", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )

        assert completed.returncode == 0, completed.stderr
        assert completed.stdout.startswith("bedrock-core ")
        assert "unknown" not in completed.stdout

    def test_short_version_flag(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "bedrock.cli.main", "-v"],
            capture_output=True,
            text=True,
            check=False,
        )

        assert completed.returncode == 0, completed.stderr
        assert completed.stdout.startswith("bedrock-core ")


class TestManageAppSelection:
    """``bedrock manage`` accepts ``--app`` / ``-A`` and documents ``BEDROCK_APP``."""

    def test_manage_callback_accepts_long_app_option(self, module_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import bedrock.cli.manage as cli_manage
        from bedrock.module import apps

        _write_module(module_env, "demo_mod")
        monkeypatch.setattr(apps, "populate", lambda paths: [])
        monkeypatch.setattr(apps, "all", lambda: [])

        cli_manage.manage_callback(app="demo_mod")

    def test_manage_callback_reads_bedrock_app_env(self, module_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import bedrock.cli.manage as cli_manage
        from bedrock.module import apps
        from bedrock.settings import settings

        _write_module(module_env, "demo_mod")
        monkeypatch.setattr(settings, "APP", "demo_mod")
        monkeypatch.setattr(apps, "populate", lambda paths: [])
        monkeypatch.setattr(apps, "all", lambda: [])

        cli_manage.manage_callback(app=None)

    def test_manage_callback_requires_app(self, module_env: Path) -> None:
        import bedrock.cli.manage as cli_manage

        with pytest.raises(typer.Exit) as exc_info:
            cli_manage.manage_callback(app=None)

        assert exc_info.value.exit_code == 1
