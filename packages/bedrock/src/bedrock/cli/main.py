import importlib.metadata

import typer
from typer import Typer

from .apps import apps
from .db import db_app
from .manage import manage_app
from .run import run_app

bedrock_cli = Typer(rich_markup_mode="rich", help="Bedrock CLI for managing Bedrock applications and modules.")

bedrock_cli.add_typer(run_app, name="run")
bedrock_cli.add_typer(apps, name="app")
bedrock_cli.add_typer(manage_app, name="manage")
bedrock_cli.add_typer(db_app, name="db")


def _version_callback(value: bool) -> None:
    """Print the installed ``bedrock-core`` distribution version and exit."""
    if not value:
        return
    try:
        version = importlib.metadata.version("bedrock-core")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown (bedrock-core distribution metadata not found)"
    typer.echo(f"bedrock-core {version}")
    raise typer.Exit()


@bedrock_cli.callback(invoke_without_command=True)
def bedrock_callback(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        callback=_version_callback,
        is_eager=True,
        help="Show the installed bedrock-core version and exit.",
    ),
):
    """ """

    if ctx.invoked_subcommand is None:
        pass


def entrypoint():
    bedrock_cli()


if __name__ == "__main__":
    entrypoint()
