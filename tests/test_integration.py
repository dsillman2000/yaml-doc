from pathlib import Path
import pytest


@pytest.mark.parametrize(
    "select,expected",
    [
        pytest.param(
            [],
            [
                "Using template: docs/templates/homepage/installation.md.j2",
                "definitions/ctx/installation.ctx.yml -> docs/homepage/installation.md",
                "Using template: docs/templates/homepage.md.j2",
                "definitions/ctx/homepage.ctx.yml -> docs/index.md",
                "Using template: docs/templates/param-list.md.j2",
                "definitions/ctx/param-list.ctx.yml -> docs/param-list.md",
                "Using template: docs/templates/each-param-page.md.j2",
                "definitions/param_defs/param1.yml -> docs/param-list/param1.md",
                "definitions/param_defs/param2.yml -> docs/param-list/param2.md",
            ],
            id="ls",
        ),
        pytest.param(
            ["homepage"],
            [
                "Using template: docs/templates/homepage/installation.md.j2",
                "definitions/ctx/installation.ctx.yml -> docs/homepage/installation.md",
                "Using template: docs/templates/homepage.md.j2",
                "definitions/ctx/homepage.ctx.yml -> docs/index.md",
            ],
            id="ls -s homepage",
        ),
        pytest.param(
            ["params"],
            [
                "Using template: docs/templates/param-list.md.j2",
                "definitions/ctx/param-list.ctx.yml -> docs/param-list.md",
                "Using template: docs/templates/each-param-page.md.j2",
                "definitions/param_defs/param1.yml -> docs/param-list/param1.md",
                "definitions/param_defs/param2.yml -> docs/param-list/param2.md",
            ],
            id="ls -s params",
        ),
        pytest.param(
            ["homepage", "params"],
            [
                "Using template: docs/templates/homepage/installation.md.j2",
                "definitions/ctx/installation.ctx.yml -> docs/homepage/installation.md",
                "Using template: docs/templates/homepage.md.j2",
                "definitions/ctx/homepage.ctx.yml -> docs/index.md",
                "Using template: docs/templates/param-list.md.j2",
                "definitions/ctx/param-list.ctx.yml -> docs/param-list.md",
                "Using template: docs/templates/each-param-page.md.j2",
                "definitions/param_defs/param1.yml -> docs/param-list/param1.md",
                "definitions/param_defs/param2.yml -> docs/param-list/param2.md",
            ],
            id="ls -s homepage params",
        ),
    ],
)
def test_integration__ls(
    project_path: Path, integration_ls: str, select: list[str], expected: list[str]
) -> None:
    from yaml_doc.core import yaml_doc_ls

    result: list[str] = yaml_doc_ls(project_path, select)
    full_result: list[str] = list(integration_ls.split("\n\n"))

    # The `integration_ls` fixture is the full `ls` result of the `integration` project.
    # So for the case that `select` is empty, we expect the full `integration_ls` result.
    if select == []:
        assert set(result) == set(full_result)
        return

    # For other cases where we only expect a subset,

    # Assert that what we expect is in the result
    for expect in expected:
        assert any(
            expect in each_result for each_result in result
        ), f"Did not find expected: {expect} in:\n\n{result}"

    # Assert that nothing else we don't expect is in the result
    for each_full_result in full_result:
        if any(expect in each_full_result for expect in expected):
            continue
        else:
            assert not any(
                each_result in each_full_result for each_result in result
            ), f"Did not expect: {each_full_result}\n\nin:\n\n{result}"
