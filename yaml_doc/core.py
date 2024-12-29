from dataclasses import dataclass
import itertools
from pathlib import Path
from typing import Any, Generator, Sequence, TypeAlias
from concurrent.futures import ThreadPoolExecutor, as_completed

from yaml_doc.env import YamlDocEnvironment
from yaml_doc.logging import logger
from yaml_doc import file_utils
from yaml_extras import ExtrasLoader, yaml_import
import yaml


def set_import_relative_dir(project_path: Path):
    yaml_import.set_import_relative_dir(project_path)


@dataclass
class YamlDocBuildStage:
    project_path: Path
    template: Path
    group: str | None
    name: str | None
    sources: list[Path]
    outputs: list[Path]

    @property
    def env(self) -> YamlDocEnvironment:
        return YamlDocEnvironment(self.project_path)

    def __init__(
        self,
        project_path: Path,
        template: Path,
        sources: Path | file_utils.PathPattern | list[Path | file_utils.PathPattern],
        outputs: Path | file_utils.PathTemplate | list[Path | file_utils.PathTemplate],
        group: str | None = None,
        name: str | None = None,
    ):
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
        for i in range(len(sources)):
            source_i, output_i = sources[i], outputs[i]
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
                        "Corresponding sources and outputs must be Path objects if not PathPatterns."
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
    def from_dict(
        cls, project_path: Path, stage_dict: dict[str, Any], group: str | None = None
    ) -> "YamlDocBuildStage":

        # Validate stage_dict["template"]
        if "template" not in stage_dict:
            logger.error("Stage missing required key: 'template'")
            raise ValueError
        template = project_path / str(stage_dict["template"])
        if not template.exists():
            logger.error("Template file not found: %s", template)
            raise FileNotFoundError

        # Validate stage_dict["sources"]
        if "sources" not in stage_dict:
            logger.error("Stage missing required key: 'sources'")
            raise ValueError
        sources = stage_dict["sources"]
        if isinstance(sources, str):
            if file_utils.is_path_pattern(sources):
                sources = file_utils.PathPattern(sources, relative_to=project_path)
            else:
                try:
                    sources = project_path / Path(sources)
                except Exception as e:
                    logger.error("Error parsing source: %s\n\n%s", sources, e)
                    raise e
                if not sources.exists():
                    logger.error("Source file not found: %s", sources)
                    raise FileNotFoundError
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
                    logger.error("Source file not found: %s", source)
                    raise FileNotFoundError
        else:
            logger.error("Invalid type for 'sources': %s", type(sources))
            raise ValueError

        # Validate stage_dict["outputs"]
        if "outputs" not in stage_dict:
            logger.error("Stage missing required key: 'outputs'")
            raise ValueError
        outputs = stage_dict["outputs"]
        if isinstance(outputs, str):
            if file_utils.is_path_template(outputs):
                outputs = file_utils.PathTemplate(outputs)
            else:
                try:
                    outputs = project_path / Path(outputs)
                except Exception as e:
                    logger.error("Error parsing output path: %s\n\n%s", outputs, e)
                    raise e
        elif isinstance(outputs, list):
            outputs = [
                (
                    file_utils.PathTemplate(output)
                    if file_utils.is_path_template(output)
                    else project_path / Path(output)
                )
                for output in outputs
            ]
        else:
            logger.error("Invalid type for 'outputs': %s", type(outputs))
            raise ValueError

        return cls(
            project_path=project_path,
            template=template,
            sources=sources,
            outputs=outputs,
            group=group,
            name=stage_dict.get("name", None),
        )

    def build_plan_str(self) -> str:
        render_steps: str = "\n".join(
            f"Render {source.relative_to(self.project_path)} -> {output.relative_to(self.project_path)}"
            for source, output in zip(self.sources, self.outputs)
        ).replace("\n", "\n\t")
        return f"Using template: {self.template.relative_to(self.project_path)}\n\t{render_steps}"

    def _render_template(self, data: dict[str, Any]) -> str:
        if not self.template.exists():
            logger.error("Template file not found: %s", self.template)
            raise FileNotFoundError
        template = self.env.from_string(self.template.read_text())
        return template.render(**data)

    def _write_document(self, source: Path, output: Path) -> Path:
        data = yaml.load(source.read_text(), Loader=ExtrasLoader)
        data["__source__"] = source.relative_to(self.project_path)
        rendered = self._render_template(data)
        if not output.parent.exists():
            output.parent.mkdir(parents=True)
        output.write_text(rendered)
        return output

    def build(self, parallel: bool = True) -> list[Path]:
        logger.info("Building stage: %s", self.name or self.template.name)
        jobs = {source: output for source, output in zip(self.sources, self.outputs)}
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
                    except Exception as e:
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
                except Exception as e:
                    logger.error("Error rendering %s -> %s: %s", source, output, e)
        return successful_outputs


@dataclass
class YamlStageSelector:
    stages: list[str] | None = None

    @classmethod
    def from_strs(cls, spec: list[str]) -> "YamlStageSelector":
        return cls(stages=spec)

    def __call__(self, stage_group_name: str, stages: list[YamlDocBuildStage]) -> bool:
        return not self.stages or stage_group_name in self.stages


YamlDocStageGroups: TypeAlias = "dict[str, list[YamlDocBuildStage]]"


@dataclass
class YamlDocConfig:
    project_path: Path
    stage_groups: YamlDocStageGroups

    @classmethod
    def from_yaml(cls, config_path: Path) -> "YamlDocConfig":
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
        stages = list(
            itertools.chain.from_iterable(
                group for stage, group in self.stage_groups.items() if selection(stage, group)
            )
        )
        return list(itertools.chain.from_iterable(stage.build() for stage in stages))

    def list(self, selection: YamlStageSelector) -> list[str]:
        stages = list(
            itertools.chain.from_iterable(
                list(group for stage, group in self.stage_groups.items() if selection(stage, group))
            )
        )
        return [stage.build_plan_str() for stage in stages]


## Entrypoint functions
def yaml_doc_init(project_path: Path) -> Path:
    config_path: Path = project_path / ".yaml-doc.yml"
    if config_path.exists():
        logger.info(f"Configuration file already exists at {config_path}.")
    else:
        config_path.touch()
        logger.info(f"Created configuration file at {config_path}.")
    return config_path


def yaml_doc_ls(project_path: Path, select: list[str]) -> list[str]:
    config_path: Path = project_path / ".yaml-doc.yml"
    config = YamlDocConfig.from_yaml(config_path)
    ls_result = config.list(YamlStageSelector.from_strs(select))
    return ls_result


def yaml_doc_build(project_path: Path, select: list[str]) -> list[Path]:
    config_path: Path = project_path / ".yaml-doc.yml"
    config = YamlDocConfig.from_yaml(config_path)
    return config.build(YamlStageSelector.from_strs(select))
