# Target yang sama dengan yang dijalankan CI. Di Windows (Git Bash) make
# memakai .venv/Scripts; di Linux/macOS .venv/bin.

ifeq ($(OS),Windows_NT)
PYTHON := .venv/Scripts/python.exe
else
PYTHON := .venv/bin/python
endif

.PHONY: install lint type test check serve

install:
	uv sync --all-extras

lint:
	$(PYTHON) -m ruff check horus_graph tests

type:
	$(PYTHON) -m mypy horus_graph

test:
	$(PYTHON) -m pytest -q

check: lint type test

serve:
	$(PYTHON) -m horus_graph serve --port 8000
