from dataclasses import dataclass
from pathlib import Path
import re
from yaml_extras.file_utils import PathPattern, PathWithMetadata, NAMED_WILDCARD_PATTERN


__all__ = ["PathPattern", "PathTemplate", "PathWithMetadata", "is_path_pattern", "is_path_template"]

TEMPLATE_PATTERN = re.compile(r"\{(?P<name>\w+)\}")


@dataclass
class PathTemplate:
    template: str

    def render(self, **kwargs) -> Path:
        try:
            path_str: str = self.template.format(**kwargs)
            return Path(path_str)
        except KeyError as ke:
            raise KeyError(
                f"Missing template key in path pattern: {ke}.\n\n"
                f"Template: {self.template}\n\n"
                f"Path metadata: {kwargs}\n\n"
            )
        except Exception as e:
            raise Exception(f"Failed to form a path from generated Path:{path_str}\n\n{e}.")


def is_path_template(path: str) -> bool:
    return bool(TEMPLATE_PATTERN.search(path))


def is_path_pattern(path: str) -> bool:
    return bool(NAMED_WILDCARD_PATTERN.search(path))
