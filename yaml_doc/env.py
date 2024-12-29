from pathlib import Path
import jinja2


class YamlDocEnvironment(jinja2.Environment):
    def __init__(self, project_path: Path, *args, **kwargs):
        extensions: list = kwargs.pop("extensions", [])
        extensions.append("jinja2.ext.do")
        extensions.append("jinja2.ext.loopcontrols")
        kwargs["extensions"] = extensions
        kwargs["loader"] = jinja2.FileSystemLoader(project_path)
        super().__init__(*args, **kwargs)
