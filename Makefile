# Dev loop (ARCHITECTURE §12). DoD per module: tests green AND lint
# silent. Activate your venv first; `make install` once.
PY ?= python3

.PHONY: install lint test build clean

install:
	$(PY) -m pip install -e '.[dev]'

lint:
	flake8 dibs tests
	ruff check dibs tests

test:
	$(PY) -m pytest -q

# zipapp needs the *package directory* inside the archive root, so the
# package is staged first (a bare `zipapp dibs` would put cli.py at the
# root and break `dibs.cli:main`). The package's own __main__.py is
# staged as the archive entry rather than passing -m: zipapp's generated
# stub calls main() and drops its return value, which would make every
# refusal exit 0 (ARCHITECTURE §6 exit codes). Install: cp dist/dibs.pyz
# ~/bin/
build: clean
	mkdir -p build/zipapp dist
	cp -R dibs build/zipapp/dibs
	cp dibs/__main__.py build/zipapp/__main__.py
	find build/zipapp -name '__pycache__' -type d -exec rm -rf {} +
	$(PY) -m zipapp build/zipapp -o dist/dibs.pyz -p "/usr/bin/env python3"

clean:
	rm -rf build dist
