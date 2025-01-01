"""
This module manages the Click CLI for yaml-doc. It provides a command line interface for the 
yaml-doc package, which in turn calls "entrypoint" functions from the `core` yaml-doc module.

The parameters used across the CLI commands are defined in the `params` module.
"""

from pathlib import Path
import click
from yaml_doc import params, core


@click.group()
@click.version_option()
@params.project_path
@click.pass_context
def cli(ctx: click.Context, project_path: Path) -> None:
    """Entry point for the yaml-doc command line interface."""
    ctx.ensure_object(dict)
    ctx.obj["PROJECT_PATH"] = Path(project_path)
    core.set_import_relative_dir(Path(project_path))


@cli.command()
@click.pass_context
def init(ctx: click.Context) -> Path:
    """Initialize a fresh .yaml-doc.yml configuration file.

    Args:
        ctx (click.Context): Click context object.

    Returns:
        Path: Path to the newly created configuration file.
    """
    return core.yaml_doc_init(ctx.obj["PROJECT_PATH"])


@cli.command()
@params.select
@click.pass_context
def ls(ctx: click.Context, select: list[str]) -> list[str]:
    """List the build plan for the current project

    Args:
        ctx (click.Context): Click context object.
        select (list[str]): String argument(s) passed to --select / -s.

    Returns:
        list[str]: List of strings representing the build plan for each stage in a human-readable
            format.
    """
    ls_result: list[str] = core.yaml_doc_ls(ctx.obj["PROJECT_PATH"], select)
    click.echo("\n\n".join(ls_result))
    return ls_result


@cli.command()
@params.select
@click.pass_context
def build(ctx: click.Context, select: list[str]) -> list[Path]:
    """Build the selected stages in the current project.

    Args:
        ctx (click.Context): Click context object.
        select (list[str]): String argument(s) passed to --select / -s.
    """
    return core.yaml_doc_build(ctx.obj["PROJECT_PATH"], select)
