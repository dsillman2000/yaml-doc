"""
This module holds the core abstractions for the yaml-doc package, such as the core engine
for compiling the YAML documents according to a given configuration file.

It also provides "entrypoint functions" which are to be called from the Click CLI interface
defined in `yaml_doc.cli`.
"""

from dataclasses import dataclass
import itertools
from pathlib import Path
from pprint import pformat
from typing import Any, TypeAlias
from concurrent.futures import ThreadPoolExecutor, as_completed

import yaml
from yaml_extras import ExtrasLoader, yaml_import

from yaml_doc.env import YamlDocEnvironment
from yaml_doc.logging import logger
from yaml_doc import exceptions, file_utils


def set_import_relative_dir(project_path: Path):
    """Wrapper function around the corresponding configuration function in `yaml_extras.yaml_import`
    to set the relative directory for importing YAML files using `!import` tags.

    Args:
        project_path (Path): Path to use as the base directory for relative imports.
    """
    yaml_import.set_import_relative_dir(project_path)


@dataclass
class YamlDocBuildStage:
    """Utility interface for interacting with individual entries in the `.yaml-doc.yml`
    configuration file. Each stage represents a single build step in the project's build
    pipeline, consisting at least of a `template`, `sources`, and `outputs` key.

    They are stored in a `.yaml-doc.yml` file in the root of the project directory with root-
    level-keys representing _groups of stages_ (stage groups). Each group contains a sequence of
    _build stages._

    ```yaml
    # Stage group is called "build-website"
    build-website:
      # Contains one build stage
      - template: docs/templates/homepage.md.j2
        sources: [...]
        outputs: [...]
    ```

    Attributes:
        project_path (Path): Path to the root of the project directory.
        template (Path): Path to the Jinja2 template file to render.
        group (str): Name of the group this stage belongs to.
        name (str): Name of the stage.
        sources (list[Path]): List of source files to render into the template.
        outputs (list[Path]): List of output files to write the rendered template to.

    Properties:
        env (YamlDocEnvironment): Environment object for rendering Jinja2 templates.

    Methods:
        __init__: Initialize a new YamlDocBuildStage object, validating its structure.
        from_dict: Specialized constructor for a new YamlDocBuildStage object from a dictionary
            representation of a stage from the YAML config.
        build_plan_str: Generate a human-readable string representation of the build plan as
            displayed by the CLI's `ls` command.
        _render_template: Internal method for rendering the template with the given data.
        _write_document: Internal method for writing the rendered document to the output file.
        build: Render the template with the given data and write the output to the output file,
            calling the internal method `_write_document` one or more times.
    """

    project_path: Path
    template: Path
    group: str | None
    name: str | None
    sources: list[Path]
    outputs: list[Path]

    @property
    def env(self) -> YamlDocEnvironment:
        """Property method for accessing the Jinja2 environment object for rendering templates.
        Contains customized filters and functions for use in the templates.

        Returns:
            YamlDocEnvironment: Jinja2 environment object for rendering templates.
        """
        return YamlDocEnvironment(self.project_path)

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def __init__(
        self,
        project_path: Path,
        template: Path,
        sources: Path | file_utils.PathPattern | list[Path | file_utils.PathPattern],
        outputs: Path | file_utils.PathTemplate | list[Path | file_utils.PathTemplate],
        group: str | None = None,
        name: str | None = None,
    ):
        """Construct a new YamlDocBuildStage object, validating its structure. Expects the
        `template` parameter to be a valid path to a Jinja2 template file, the `sources` parameter
        to be a collection of paths or path patterns, and the `outputs` parameter to be a collection
        of paths or path templates.

        Args:
            project_path (Path): Path to the root of the project directory.
            template (Path): Path to the Jinja2 template file to render.
            sources (Path | file_utils.PathPattern | list[Path  |  file_utils.PathPattern]):
                Collection of source files to render into the template, either as a list of Paths
                or PathPatterns.
            outputs (Path | file_utils.PathTemplate | list[Path  |  file_utils.PathTemplate]):
                Collection of output files to write the rendered document(s) to, either as a list of
                Paths or PathTemplates.
            group (str | None, optional): Name of the stage group from the YAML configuration.
                Defaults to None.
            name (str | None, optional): Name of the stage within the group, if one was provided.
                Defaults to None.

        Raises:
            ValueError: When either:
                - The number of sources and outputs are not equal.
                - The corresponding sources and outputs are not Path objects if not PathPatterns.
                - The template file does not exist.
        """
        self.project_path = project_path
        self.template = template
        self.group = group
        self.name = name

        # Normalize sources and outputs to lists
        if not isinstance(sources, list):
            sources = [sources]
        if not isinstance(outputs, list):
            outputs = [outputs]

        # Inputs and outputs must be the same length
        if not len(sources) == len(outputs):
            logger.error(
                "Number of sources and outputs must be equal: %s != %s", len(sources), len(outputs)
            )
            raise ValueError

        # If sources or outputs are PathPatterns, resolve them into lists of Path objects

        _sources: list[Path] = []
        _outputs: list[Path] = []
        for source_i, output_i in zip(sources, outputs):
            if isinstance(source_i, file_utils.PathPattern):
                if not isinstance(output_i, file_utils.PathTemplate):
                    raise ValueError(
                        "Corresponding sources and outputs must be PathPatterns and PathTemplates, "
                        "respectively."
                    )
                source_paths_w_metadata: list[file_utils.PathWithMetadata] = source_i.results()
                sources_i: list[Path] = [source.path for source in source_paths_w_metadata]
                outputs_i: list[Path] = [
                    output_i.render(**source.metadata) for source in source_paths_w_metadata
                ]
                _sources.extend(sources_i)
                _outputs.extend(outputs_i)
            else:
                if not isinstance(output_i, Path):
                    raise ValueError(
                        "Corresponding sources and outputs must be Path objects if not "
                        "PathPatterns."
                    )
                _sources.append(source_i)
                _outputs.append(output_i)

        self.sources = [
            self.project_path / source if not source.is_relative_to(self.project_path) else source
            for source in _sources
        ]
        self.outputs = [
            self.project_path / output if not output.is_relative_to(self.project_path) else output
            for output in _outputs
        ]

    @classmethod
    def _validate_template(cls, project_path: Path, stage_dict: dict[str, Any]) -> Path:
        """Internal classmethod for validating the template path from a dict of yaml-doc stage data.

        Args:
            project_path (Path): Path to the root of the project directory.
            stage_dict (dict[str, Any]): Dictionary representation of a stage from the YAML config.

        Raises:
            exceptions.YamlDocConfigError: When either:
              - The stage dictionary is missing the required key "template".
              - The stage dictionary has an invalid type for the "template" key.
              - The template file is not found.

        Returns:
            Path: Path to the template file, assuming it was valid.
        """
        if "template" not in stage_dict:
            raise exceptions.YamlDocConfigError(
                f"Stage missing required key: 'template':\n{pformat(stage_dict, indent=2)}"
            )
        if not isinstance(stage_dict["template"], str):
            raise exceptions.YamlDocConfigError(
                f"Invalid type for 'template' (expected str): {stage_dict['template']}"
            )
        template_path = project_path / str(stage_dict["template"])
        if not template_path.exists():
            raise exceptions.YamlDocConfigError(f"Template file not found: {template_path}")
        return template_path

    @classmethod
    def _validate_sources(
        cls, project_path: Path, stage_dict: dict[str, Any]
    ) -> Path | file_utils.PathPattern | list[Path | file_utils.PathPattern]:
        """Internal classmethod for validating the "sources" configuration from a dict of yaml-doc
        stage data.

        Args:
            project_path (Path): Path to the root of the project directory.
            stage_dict (dict[str, Any]): Dictionary representation of a stage from the YAML config.

        Raises:
            exceptions.YamlDocConfigError: When either,
              - The stage dictionary is missing the required key "sources".
              - The "sources" key is not a string or list of strings.
              - Any member of the "sources" key is not a valid path or path pattern.
              - An error occurs parsing the source path specifications.

        Returns:
            Path | file_utils.PathPattern | list[Path | file_utils.PathPattern]: The validated
                sources configuration, parsed as Path objects or PathPatterns.
        """
        if "sources" not in stage_dict:
            raise exceptions.YamlDocConfigError(
                f"Stage missing required key: 'sources':\n{pformat(stage_dict, indent=2)}"
            )
        if not isinstance(stage_dict["sources"], (str, list)):
            raise exceptions.YamlDocConfigError(
                f"Invalid type for 'sources' (expected str or list): {stage_dict['sources']}"
            )
        sources = stage_dict["sources"]

        # Handle parsing the sources configuration
        if isinstance(sources, str):
            if file_utils.is_path_pattern(sources):
                try:
                    sources = file_utils.PathPattern(sources, relative_to=project_path)
                except Exception as e:  # pylint: disable=broad-except
                    raise exceptions.YamlDocConfigError(
                        f"Error parsing source pattern: {sources}\n\n{e}"
                    )
            else:
                try:
                    sources = project_path / Path(sources)
                except Exception as e:
                    raise exceptions.YamlDocConfigError(f"Error parsing source: {sources}\n\n{e}")
                if not sources.exists():
                    raise exceptions.YamlDocConfigError(f"Source file not found: {sources}")
        elif isinstance(sources, list):
            sources = [
                (
                    file_utils.PathPattern(source, relative_to=project_path)
                    if file_utils.is_path_pattern(source)
                    else project_path / Path(source)
                )
                for source in sources
            ]
            for source in sources:
                if isinstance(source, Path) and not source.exists():
                    raise exceptions.YamlDocConfigError(f"Source file not found: {source}")

        return sources

    @classmethod
    def _validate_outputs(
        cls, project_path: Path, stage_dict: dict[str, Any]
    ) -> Path | file_utils.PathTemplate | list[Path | file_utils.PathTemplate]:
        """Internal classmethod for validating the "outputs" configuration from a dict of yaml-doc
        stage data.

        Args:
            project_path (Path): Path to the root of the project directory.
            stage_dict (dict[str, Any]): Dictionary representation of a stage from the YAML config.

        Raises:
            exceptions.YamlDocConfigError: When either,
              - The stage dictionary is missing the required key "outputs".
              - The "outputs" key is not a string or list of strings.
              - Any member of the "outputs" key is not a valid path or path pattern.
              - An error occurs parsing the output path specifications.

        Returns:
            Path | file_utils.PathTemplate | list[Path | file_utils.PathTemplate]: The validated
                outputs configuration, parsed as Path objects or PathTemplates.
        """
        if "outputs" not in stage_dict:
            raise exceptions.YamlDocConfigError(
                f"Stage missing required key: 'outputs':\n{pformat(stage_dict, indent=2)}"
            )
        if not isinstance(stage_dict["outputs"], (str, list)):
            raise exceptions.YamlDocConfigError(
                f"Invalid type for 'outputs' (expected str or list): {stage_dict['outputs']}"
            )
        outputs = stage_dict["outputs"]

        # Handle parsing the outputs configuration
        if isinstance(outputs, str):
            if file_utils.is_path_template(outputs):
                outputs = file_utils.PathTemplate(outputs)
            else:
                try:
                    outputs = project_path / Path(outputs)
                except Exception as e:
                    raise exceptions.YamlDocConfigError(
                        f"Error parsing output path: {outputs}\n\n{e}"
                    )
        elif isinstance(outputs, list):
            try:
                outputs = [
                    (
                        file_utils.PathTemplate(output)
                        if file_utils.is_path_template(output)
                        else project_path / Path(output)
                    )
                    for output in outputs
                ]
            except Exception as e:
                raise exceptions.YamlDocConfigError(
                    f"Error parsing output path template: {outputs}\n\n{e}"
                )

        return outputs

    @classmethod
    def from_dict(
        cls, project_path: Path, stage_dict: dict[str, Any], group: str | None = None
    ) -> "YamlDocBuildStage":
        """Specialized constructor for a new YamlDocBuildStage object from a dictionary whose
        structure matches the expected structure of a stage in the YAML configuration file.

        This method is the primary interface for parsing `.yaml-doc.yml` configs into an actionable
        plan of Jinja compilations.

        Args:
            project_path (Path): Path to the root of the project directory.
            stage_dict (dict[str, Any]): Dictionary representation of a stage from the YAML config.
            group (str | None, optional): Name of the stage group with which this stage is
                associated. Defaults to None.

        Raises:
            YamlDocConfigError: When either,
              - The stage dictionary is missing the required key "template".
              - The stage dictionary has an invalid type for the "template" key.
              - The template file is not found.
              - The stage dictionary is missing the required key "sources".
              - The "sources" key is not a string or list of strings.
              - The members of the "sources" key is not a valid path or path pattern.
              - An error occurs parsing the source path specifications.
              - The stage dictionary is missing the required key "outputs".
              - The "outputs" key is not a string or list of strings.
              - Any member of the "outputs" key is not a valid path or path pattern.
              - An error occurs parsing the output path specifications.

        Returns:
            YamlDocBuildStage: A new YamlDocBuildStage object representing the stage from the YAML
                configuration file.
        """

        # One overarching try/except block for performing validation steps.
        try:

            # Validate stage_dict["template"]
            template = cls._validate_template(project_path, stage_dict)

            # Validate stage_dict["sources"]
            sources = cls._validate_sources(project_path, stage_dict)

            # Validate stage_dict["outputs"]
            outputs = cls._validate_outputs(project_path, stage_dict)

        except exceptions.YamlDocConfigError as config_error:
            logger.error(
                "Error encountered while validating stage: %s", pformat(stage_dict, indent=2)
            )
            raise config_error

        # Pass validated results to the constructor
        return cls(
            project_path=project_path,
            template=template,
            sources=sources,
            outputs=outputs,
            group=group,
            name=stage_dict.get("name", None),
        )

    def build_plan_str(self) -> str:
        """Generate a human-readable string representation of the build plan as displayed by the
        CLI's `ls` command.

        Returns:
            str: Human-readable string representation of the build plan.
        """
        render_steps: str = "\n".join(
            f"Render {source.relative_to(self.project_path)} -> "
            f"{output.relative_to(self.project_path)}"
            for source, output in zip(self.sources, self.outputs)
        ).replace("\n", "\n\t")
        return f"Using template: {self.template.relative_to(self.project_path)}\n\t{render_steps}"

    def _render_template(self, data: dict[str, Any]) -> str:
        """Internal method for rendering the template with the given data.

        Args:
            data (dict[str, Any]): Jinja context data to render the template with.

        Raises:
            FileNotFoundError: When the template file is not found.

        Returns:
            str: Rendered document content as a string.
        """
        if not self.template.exists():
            logger.error("Template file not found: %s", self.template)
            raise FileNotFoundError
        template = self.env.from_string(self.template.read_text(encoding="utf-8"))
        return template.render(**data)

    def _write_document(self, source: Path, output: Path) -> Path:
        """Internal method for writing the rendered document to the output file.

        Args:
            source (Path): Path to the source file to render.
            output (Path): Path to the output file to write the rendered document to.

        Raises:
            FileNotFoundError: When the source file is not found.

        Returns:
            Path: Path to the rendered output file.
        """
        data = yaml.load(source.read_text(), Loader=ExtrasLoader)
        data["__source__"] = source.relative_to(self.project_path)
        rendered = self._render_template(data)
        if not output.parent.exists():
            output.parent.mkdir(parents=True)
        output.write_text(rendered)
        return output

    def build(self, parallel: bool = True) -> list[Path]:
        """Render the template with each of the provided sources and write the output to each
        corresponding output file in the stage. Calls the internal method `_write_document` one or
        more times according to the specification.

        Args:
            parallel (bool, optional): Whether or not the documents within this stage shall be built
                in parallel. Defaults to True.

        Returns:
            list[Path]: List of paths to the successfully rendered output files.
        """
        logger.info("Building stage: %s", self.name or self.template.name)
        jobs = dict(zip(self.sources, self.outputs))
        successful_outputs: list[Path] = []
        if parallel:
            with ThreadPoolExecutor() as executor:
                futures = {
                    executor.submit(self._write_document, source, output): (source, output)
                    for source, output in jobs.items()
                }
                for future in as_completed(futures):
                    source, output = futures[future]
                    try:
                        successful_outputs.append(future.result())
                        logger.info(
                            "Rendered %s -> %s",
                            source.relative_to(self.project_path),
                            output.relative_to(self.project_path),
                        )
                    except Exception as e:  # pylint: disable=broad-except
                        logger.error(
                            "Error rendering %s -> %s: %s",
                            source.relative_to(self.project_path),
                            source.relative_to(self.project_path),
                            e,
                        )
        else:
            for source, output in jobs.items():
                try:
                    successful_outputs.append(self._write_document(source, output))
                    logger.info("Rendered %s -> %s", source, output)
                except Exception as e:  # pylint: disable=broad-except
                    logger.error("Error rendering %s -> %s: %s", source, output, e)
        return successful_outputs


@dataclass
class YamlStageSelector:
    """Utility interface for handling the string arguments passed to the yaml-doc Click CLI
    via --select/-s. The selector is used to filter the stage groups in the configuration file
    based on the given selection criteria.

    Currently supports:
      - Selecting all stages by passing no arguments.
      - Selecting specific stage groups by passing their names as space-separated arguments.

    Attributes:
        stages (list[str] | None): List of stage group names to select. If None, all stages are
            selected.

    Methods:
        from_strs: Specialized constructor for a new YamlStageSelector object from a list of
            strings.
        __call__: Filter the stage groups based on the given selection criteria.
    """

    stages: list[str] | None = None

    @classmethod
    def from_strs(cls, spec: list[str]) -> "YamlStageSelector":
        """Specialized constructor for a new YamlStageSelector object from a list of strings such
        as those passed to the yaml-doc Click CLI via --select/-s.

        Args:
            spec (list[str]): List of strings representing the selection criteria.

        Returns:
            YamlStageSelector: A new YamlStageSelector object representing the selection criteria.
        """
        return cls(stages=spec)

    def __call__(
        self, stage_group_name: str, stages: list[YamlDocBuildStage]
    ) -> list[YamlDocBuildStage]:
        """Where the arguments are a corresponding stage group name and its list of build stages,
        return the subset of build stages which meet the selection criteria specified in the
        selector.

        Args:
            stage_group_name (str): Name of the stage group to filter.
            stages (list[YamlDocBuildStage]): List of build stages in the stage group.

        Returns:
            list[YamlDocBuildStage]: List of build stages to select from this stage group.
        """
        return stages if not self.stages or stage_group_name in self.stages else []


YamlDocStageGroups: TypeAlias = "dict[str, list[YamlDocBuildStage]]"


@dataclass
class YamlDocConfig:
    """Utility interface for interacting with the `.yaml-doc.yml` configuration file in the root
    of the project directory. The configuration file contains a series of stage groups, each
    containing a sequence of build stages.

    ```yaml
    # Stage group is called "build-website"
    build-website:
      # Contains one build stage
      - template: docs/templates/homepage.md.j2
        sources: [...]
        outputs: [...]
    ```

    Attributes:
        project_path (Path): Path to the root of the project directory.
        stage_groups (YamlDocStageGroups): Dictionary mapping stage group names to sequences of
            build stages, parsed into `YamlDocBuildStage` objects.
    """

    project_path: Path
    stage_groups: YamlDocStageGroups

    @classmethod
    def from_yaml(cls, config_path: Path) -> "YamlDocConfig":
        """Specialized constructor for a new YamlDocConfig object from a `.yaml-doc.yml` file.
        Loads the configuration file from the given path and parses it into a dictionary of stage
        groups, each containing a sequence of build stages.

        Args:
            config_path (Path): Path to the `.yaml-doc.yml` configuration file to parse.

        Returns:
            YamlDocConfig: A new YamlDocConfig object representing the configuration file.
        """
        project_path = config_path.parent
        with config_path.open() as f:
            config: dict = yaml.load(f, Loader=ExtrasLoader)
        return cls(
            project_path,
            {
                key: [
                    YamlDocBuildStage.from_dict(project_path, stage_dict, group=key)
                    for stage_dict in stages
                ]
                for key, stages in config.items()
            },
        )

    def build(self, selection: YamlStageSelector) -> list[Path]:
        """Build the selected stages in the current project. First scans the stage groups for which
        stages satisfy the given selection, then builds each of the selected stages by calling their
        `build` method.

        Args:
            selection (YamlStageSelector): Selector object for filtering the stage groups.

        Returns:
            list[Path]: List of paths to the successfully rendered output files.
        """
        stages = list(
            itertools.chain.from_iterable(
                selection(stage, group) for stage, group in self.stage_groups.items()
            )
        )
        return list(itertools.chain.from_iterable(stage.build() for stage in stages))

    def list(self, selection: YamlStageSelector) -> list[str]:
        """List the build plan for the current project satisfying the given selection criteria.
        First scans the stage groups for which stages satisfy the given selection, then generates a
        human-readable string representation of the build plan for each of the selected stages.

        Args:
            selection (YamlStageSelector): Selector object for filtering the stage groups.

        Returns:
            list[str]: List of human-readable strings representing the build plan.
        """
        stages = list(
            itertools.chain.from_iterable(
                list(selection(stage, group) for stage, group in self.stage_groups.items())
            )
        )
        return [stage.build_plan_str() for stage in stages]


## Entrypoint functions
def yaml_doc_init(project_path: Path) -> Path:
    """Entrypoint function for initializing a fresh `.yaml-doc.yml` configuration file in the root
    of the project directory. If the configuration file already exists, this function will do
    nothing.

    Args:
        project_path (Path): Path to the root of the project directory.

    Returns:
        Path: Path to the generated (or already-existing) configuration file.
    """
    config_path: Path = project_path / ".yaml-doc.yml"
    if config_path.exists():
        logger.info("Configuration file already exists at %s.", config_path)
    else:
        config_path.touch()
        logger.info("Created configuration file at %s.", config_path)
    return config_path


def yaml_doc_ls(project_path: Path, select: list[str]) -> list[str]:
    """Entrypoint function for listing the build plan for the current project. First parses the
    `.yaml-doc.yml` configuration file, then generates a human-readable string representation of
    the build plan for each of the selected stages.

    Args:
        project_path (Path): Path to the root of the project directory.
        select (list[str]): List of strings representing the selection criteria.

    Returns:
        list[str]: List of human-readable strings representing each stage of the build plan.
    """
    config_path: Path = project_path / ".yaml-doc.yml"
    config = YamlDocConfig.from_yaml(config_path)
    ls_result = config.list(YamlStageSelector.from_strs(select))
    return ls_result


def yaml_doc_build(project_path: Path, select: list[str]) -> list[Path]:
    """Entrypoint function for building the selected stages in the current project. First parses the
    `.yaml-doc.yml` configuration file, then builds each of the selected stages.

    Args:
        project_path (Path): Path to the root of the project directory.
        select (list[str]): List of strings representing the selection criteria.

    Returns:
        list[Path]: List of paths to the successfully rendered output files.
    """
    config_path: Path = project_path / ".yaml-doc.yml"
    config = YamlDocConfig.from_yaml(config_path)
    return config.build(YamlStageSelector.from_strs(select))
