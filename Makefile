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
# root and break `dibs.cli:main`). Install: cp dist/dibs.pyz ~/bin/
build: clean
	mkdir -p build/zipapp dist
	cp -R dibs build/zipapp/dibs
	find build/zipapp -name '__pycache__' -type d -exec rm -rf {} +
	$(PY) -m zipapp build/zipapp -m "dibs.cli:main" -o dist/dibs.pyz \
		-p "/usr/bin/env python3"

clean:
	rm -rf build dist
