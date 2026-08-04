import click
import typer
from click import Context
from typer.core import TyperGroup

from bedrock.settings import settings


def _parse_run_args_for_app(argv: list[str]) -> str | None:
    """Scan *argv* for the module import path passed after ``run``.

    The ``run`` command contract is flag-only: ``--app MODULE`` (or ``-a
    MODULE``) selects the module to load. Explicit flags take precedence over
    the ``BEDROCK_APP`` environment variable. Positional tokens are module
    commands or command arguments and are never interpreted as module names.

    Args:
        argv: Raw argument list (typically ``sys.argv[1:]``).

    Returns:
        The module import path from ``--app`` / ``-a``, or ``None``.
    """
    run_seen = False
    for i, arg in enumerate(argv):
        if arg == "run":
            run_seen = True
            continue
        if run_seen:
            if arg in ("--app", "-a") and i + 1 < len(argv):
                return argv[i + 1]
            if arg.startswith("--app="):
                return arg.split("=", 1)[1]
            if arg.startswith("-a="):
                return arg.split("=", 1)[1]
    return None


def _resolve_run_app(args: list[str]) -> str | None:
    """Return the module to load for ``run`` from raw args or ``BEDROCK_APP``.

    Args:
        args: Raw argument list that follows the ``run`` command.

    Returns:
        The module import path selected by ``--app`` / ``-a``, falling back
        to the ``BEDROCK_APP`` environment variable, or ``None``.
    """
    app = _parse_run_args_for_app(list(args))
    if app:
        return app
    return settings.APP or None


class _AppCommandGroup(TyperGroup):
    """Click group that lazily loads app Typer subcommands before resolution.

    Each loaded module's declared Typer app is mounted under its module name,
    so ``bedrock run --app MODULE MODULE COMMAND`` invokes the module command.
    Module names are unique registry keys, so module command groups can never
    collide with each other; only collisions with built-in ``run`` commands
    are possible, and those are resolved deterministically in favor of the
    built-in command with a warning on stderr.
    """

    def _load_app_commands(self, app_name: str) -> None:
        from bedrock.module import apps

        apps.populate([app_name])

        for app_instance in apps.all():
            commands_app = app_instance.commands()
            if commands_app is None:
                continue
            # Wrap in a parent Typer so get_command returns a Group containing
            # the app as a subcommand.
            parent = typer.Typer()
            parent.add_typer(commands_app, name=app_instance.name)
            parent_cmd = typer.main.get_command(parent)
            if not (hasattr(parent_cmd, "commands") and app_instance.name in parent_cmd.commands):
                continue
            if app_instance.name in self.commands:
                click.echo(
                    f"Warning: module '{app_instance.name}' conflicts with a built-in 'run' command; "
                    "the built-in command takes precedence. "
                    "Module names must not shadow built-in commands.",
                    err=True,
                )
                continue
            self.commands[app_instance.name] = parent_cmd.commands[app_instance.name]

    def _ensure_app_commands(self, ctx: Context) -> None:
        """Load the selected app's commands exactly once for this invocation."""
        app = ctx.params.get("app")
        if not isinstance(app, str) or not app:
            app = _resolve_run_app(getattr(ctx, "args", None) or [])
        if app and not getattr(self, "_bedrock_commands_loaded", False):
            self._load_app_commands(app)
            self._bedrock_commands_loaded = True

    def make_context(
        self,
        info_name: str | None,
        args: list[str],
        parent: Context | None = None,
        **extra: object,
    ) -> Context:
        if not getattr(self, "_bedrock_commands_loaded", False):
            app = _resolve_run_app(args)
            if app:
                self._load_app_commands(app)
                self._bedrock_commands_loaded = True
        return super().make_context(info_name, args, parent, **extra)

    def format_help(self, ctx: Context, formatter: click.HelpFormatter) -> None:
        self._ensure_app_commands(ctx)
        return super().format_help(ctx, formatter)

    def get_help(self, ctx: Context) -> str:
        self._ensure_app_commands(ctx)
        return super().get_help(ctx)

    def resolve_command(self, ctx: Context, args: list[str]) -> tuple[str, click.Command, list[str]]:
        self._ensure_app_commands(ctx)
        return super().resolve_command(ctx, args)

    def get_command(self, ctx: Context, cmd_name: str) -> click.Command | None:
        self._ensure_app_commands(ctx)
        return super().get_command(ctx, cmd_name)

    def list_commands(self, ctx: Context) -> list[str]:
        self._ensure_app_commands(ctx)
        return super().list_commands(ctx)


def _create_run_app() -> typer.Typer:
    """Create the ``run`` Typer with dynamic app command loading."""
    run_app = typer.Typer(
        cls=_AppCommandGroup,
        help="Run a Bedrock application's commands",
    )

    @run_app.callback(invoke_without_command=True)
    def main(
        ctx: typer.Context,
        app: str | None = typer.Option(
            None,
            "--app",
            "-a",
            envvar="BEDROCK_APP",
            help="Module to load (or set the BEDROCK_APP environment variable).",
        ),
    ):
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())
            ctx.exit(0)

    return run_app


run_app = _create_run_app()
