PYTEST_ARGS=-sxv


install:
	@poetry install

lint:
	@poetry run pylint yaml_doc/ --rcfile=.pylintrc --disable=E0015

unit:
	@poetry run pytest $(PYTEST_ARGS) tests/unit

integration:
	@poetry run pytest $(PYTEST_ARGS) tests/test_integration.py

test: unit integration

build:
	@poetry build
