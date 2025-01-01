# pylint: disable=missing-module-docstring
from dataclasses import dataclass
from pathlib import Path
import re
from yaml_extras.file_utils import PathPattern, PathWithMetadata, NAMED_WILDCARD_PATTERN


__all__ = ["PathPattern", "PathTemplate", "PathWithMetadata", "is_path_pattern", "is_path_template"]

TEMPLATE_PATTERN = re.compile(r"\{(?P<name>\w+)\}")


@dataclass
class PathTemplate:
    """Utility class to represent a path template, e.g. a path which contains template holes like a
    Python f-string:

    ```python
    path_template = PathTemplate("docs/{name}.md")
    ```

    Attributes:
        template (str): A path template string with holes that can be filled with additional
            data.

    Methods:
        render: Substitute the template holes with the provided keyword arguments.

    """

    template: str

    def render(self, **kwargs) -> Path:
        """Substitute the template holes with the provided keyword arguments to this function.

        Raises:
            KeyError: When a template key is missing in the provided keyword arguments.
            Exception: When the path string cannot be formed from the template and keyword
                arguments.

        Returns:
            Path: A Path object formed from the template and keyword arguments.
        """
        try:
            path_str: str = self.template.format(**kwargs)
            return Path(path_str)
        except KeyError as ke:
            raise KeyError(
                f"Missing template key in path pattern.\n\n"
                f"Template: {self.template}\n\n"
                f"Path metadata: {kwargs}\n\n"
            ) from ke
        except Exception as e:
            raise Exception(  # pylint: disable=broad-exception-raised
                f"Failed to form a path from generated Path:{path_str}"
            ) from e


def is_path_template(path: str) -> bool:
    """Check if the given string appears to be a valid PathTemplate (via regex).

    Args:
        path (str): Subject string to check if it is a valid PathTemplate.

    Returns:
        bool: True if the given string is a valid PathTemplate, False otherwise.
    """
    return bool(TEMPLATE_PATTERN.search(path))


def is_path_pattern(path: str) -> bool:
    """Check if the given string appears to be a valid PathPattern (via regex).

    Args:
        path (str): Subject string to check if it is a valid PathPattern.

    Returns:
        bool: True if the given string is a valid PathPattern, False otherwise.
    """
    return bool(NAMED_WILDCARD_PATTERN.search(path))
