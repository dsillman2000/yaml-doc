# pylint: disable=missing-module-docstring
from pathlib import Path
import jinja2


class YamlDocEnvironment(jinja2.Environment):
    """Custom Jinja2 environment for yaml-doc.

    To-do:
        - Allow user to define their own Python code for custom filters and macros.
    """

    def __init__(self, project_path: Path, *args, **kwargs):
        extensions: list = kwargs.pop("extensions", [])
        extensions.append("jinja2.ext.do")
        extensions.append("jinja2.ext.loopcontrols")
        kwargs["extensions"] = extensions
        kwargs["loader"] = jinja2.FileSystemLoader(project_path)
        super().__init__(*args, **kwargs)
