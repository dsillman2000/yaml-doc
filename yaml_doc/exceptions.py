# pylint: disable=missing-module-docstring


class YamlDocException(Exception):
    """Base exception type for errors raised from yaml-doc."""


class YamlDocConfigError(YamlDocException):
    """When there's something wrong with a `.yaml-doc.yml` configuration file."""
