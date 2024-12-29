import click


project_path = click.option(
    "--project-path",
    "-p",
    type=click.Path(exists=True),
    help="Path to the project root directory containing .yaml-doc.yml config.",
    default=".",
)

select = click.option(
    "--select",
    "-s",
    type=str,
    help="Select specific stages to build.",
    multiple=True,
)
