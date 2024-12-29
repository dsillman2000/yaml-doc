from pathlib import Path
import shutil
import pytest


@pytest.fixture
def cp_integration_project(tmp_path: Path) -> Path:
    integration_dir = Path(__file__).parent / "integration"
    target_dir = tmp_path / "integration"
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(integration_dir, target_dir)
    return target_dir


@pytest.fixture
def project_path(cp_integration_project: Path) -> Path:
    return cp_integration_project


@pytest.fixture
def integration_ls() -> str:
    result = """Using template: docs/templates/homepage/installation.md.j2
	Render definitions/ctx/installation.ctx.yml -> docs/homepage/installation.md

Using template: docs/templates/homepage.md.j2
	Render definitions/ctx/homepage.ctx.yml -> docs/index.md

Using template: docs/templates/param-list.md.j2
	Render definitions/ctx/param-list.ctx.yml -> docs/param-list.md

Using template: docs/templates/each-param-page.md.j2
	Render definitions/param_defs/param2.yml -> docs/param-list/param2.md
	Render definitions/param_defs/param1.yml -> docs/param-list/param1.md"""
    return result
