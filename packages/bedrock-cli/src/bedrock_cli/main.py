"""Entry point for the bedrock-cli command-line tool."""

from __future__ import annotations

import typer

from bedrock_cli import __version__
from bedrock_cli.commands import add_app, gen_command, init_command

app = typer.Typer(
    name="bedrock-cli",
    help="Bedrock CLI — scaffold and manage Bedrock modular applications.",
    no_args_is_help=True,
)

app.command("init")(init_command)
app.command("gen")(gen_command)
app.add_typer(add_app, name="add")


def _version_callback(value: bool) -> None:
    """Print the installed ``bedrock-cli`` distribution version and exit."""
    if not value:
        return
    typer.echo(f"bedrock-cli {__version__}")
    raise typer.Exit()


@app.callback()
def _main_callback(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        callback=_version_callback,
        is_eager=True,
        help="Show the installed bedrock-cli version and exit.",
    ),
) -> None:
    """Bedrock CLI global options."""


def main() -> None:
    """CLI entry point invoked by the ``bedrock-cli`` console script."""
    app()


if __name__ == "__main__":
    main()
