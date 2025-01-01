PYTEST_ARGS=-sxv

lint:
	@poetry run pylint yaml_doc/ --rcfile=.pylintrc --disable=E0015

unit:
	@poetry run pytest $(PYTEST_ARGS) tests/unit

integration:
	@poetry run pytest $(PYTEST_ARGS) tests/test_integration.py
