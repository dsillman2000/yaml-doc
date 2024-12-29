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
    # config_path: Path = ctx.obj["PROJECT_PATH"] / ".yaml-doc.yml"
    # if config_path.exists():
    #     click.echo(f"Configuration file already exists at {config_path}.")
    # else:
    #     config_path.touch()
    #     click.echo(f"Created configuration file at {config_path}.")
    # return config_path


@cli.command()
@params.select
@click.pass_context
def ls(ctx: click.Context, select: list[str]) -> list[str]:
    """List the build plan for the current project

    Args:
        ctx (click.Context): Click context object.
    """
    ls_result: list[str] = core.yaml_doc_ls(ctx.obj["PROJECT_PATH"], select)
    click.echo("\n\n".join(ls_result))
    return ls_result
    # config_path: Path = ctx.obj["PROJECT_PATH"] / ".yaml-doc.yml"
    # config = core.YamlDocConfig.from_yaml(config_path)
    # ls_result = config.list(core.YamlStageSelector.from_strs(select))
    # click.echo("\n\n".join(ls_result))
    # return ls_result


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
    # config_path: Path = ctx.obj["PROJECT_PATH"] / ".yaml-doc.yml"
    # config = core.YamlDocConfig.from_yaml(config_path)
    # return config.build(core.YamlStageSelector.from_strs(select))
