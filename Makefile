# haddolib — Makefile
#
# Cross-platform: macOS (native .venv) and Windows (native .venv-win, run from an
# MSYS2 / Git-Bash shell). GNU make sets OS=Windows_NT on Windows — including
# inside MSYS2 — so the block below flips only the things that actually differ:
# the venv dir, its bin/Scripts subdir, the Python launcher, and the reqs file.
#
# All targets and recipes are shared; coreutils (touch/rm/find/grep/awk) come
# from the POSIX shell on both sides.
#
# Note: on Windows, PYTHON = `py -3` so the venv is built by NATIVE Windows
# Python (required for PyXLL), not MSYS2's python. Override if needed, e.g.:
#   make setup PYTHON=python

# --- OS-specific variables ---
ifeq ($(OS),Windows_NT)
    VENV_DIR     = .venv-win
    VENV_BIN     = $(VENV_DIR)/Scripts
    PYTHON       = py -3
    REQUIREMENTS = requirements-win.txt
else
    VENV_DIR     = .venv
    VENV_BIN     = $(VENV_DIR)/bin
    PYTHON       = python3
    REQUIREMENTS = requirements.txt
endif

# --- Derived variables (shared) ---
VENV_ACTIVATE = $(VENV_BIN)/activate
ACTIVATE      = . $(VENV_ACTIVATE)
PIP           = $(ACTIVATE) && pip
RUN           = $(ACTIVATE) && python
SETUP_STAMP   = $(VENV_DIR)/.setup_stamp

# --- Phony targets ---
.PHONY: all setup
.PHONY: test test-verbose
.PHONY: patch commit-hash
.PHONY: clean help
.PHONY: showtree gentree filesdump filesdump-detailed
.PHONY: bootstrap backup dump isbndb-lookup isbndb-search isbndb-query photo-analysis pdf-lst-to-queries isbn-synopsis

all: setup

# --- Virtual Environment & Setup ---

$(VENV_ACTIVATE):
	$(PYTHON) -m venv $(VENV_DIR)

$(SETUP_STAMP): $(VENV_ACTIVATE) $(REQUIREMENTS) pyproject.toml
	@echo "--- Installing dependencies ($(REQUIREMENTS)) ---"
	$(PIP) install -r $(REQUIREMENTS)
	@echo "--- Installing project in editable mode ---"
	$(PIP) install -e .
	@echo "--- Setup complete ---"
	@touch $(SETUP_STAMP)

setup: $(SETUP_STAMP) ## Create venv and install dependencies

# --- Testing ---

test: $(SETUP_STAMP) ## Run all tests (quiet mode)
	$(RUN) -m pytest -q

test-verbose: $(SETUP_STAMP) ## Run tests with verbose output
	$(RUN) -m pytest -v -s

# --- Tools ---

bootstrap: $(SETUP_STAMP) ## Initialize/reset the live database (interactive)
	$(RUN) tools/bootstrap_db.py

backup: $(SETUP_STAMP) ## Safely backup the live DB to configured shares
	$(RUN) tools/backup_db.py --dest /y/Projects/haddolib/bak --dest /x/SQLite-bak/haddolib

dump: $(SETUP_STAMP) ## Export full catalogue to data/import/YYYYMMDD_HHMMSS_dump.xlsx
	$(RUN) tools/dump_db.py

isbndb-lookup: $(SETUP_STAMP) ## Look up list of ISBN13s (only!) via ISBNdb, generates csv
	$(RUN) scripts/isbndb_lookup.py $(ARGS)

isbndb-search: $(SETUP_STAMP) ## Use ISBNdb search repeatedly on passed list, generates csv
	$(RUN) scripts/isbndb_search.py $(ARGS)

isbndb-query: $(SETUP_STAMP) ## Search one query, return csv with all editions
	$(RUN) scripts/isbndb_query.py $(ARGS)

photo-analysis: $(SETUP_STAMP) ## Analyse book cover photos via VLM (ARGS="path/to/photos.csv")
	$(RUN) scripts/photo_analysis.py $(ARGS)

pdf-lst-to-queries: $(SETUP_STAMP) ## Convert a *.lst of PDF filenames into an ISBNdb query CSV
	$(RUN) scripts/pdf_lst_to_queries.py -i data/input/pdfs.lst -o data/output/pdfs_query.csv $(ARGS)

isbndb-synopsis: $(SETUP_STAMP) ## Fetch synopses for pdf-annotations PDFs (ARGS to override, or add --force)
	$(RUN) scripts/isbndb_synopsis.py -i data/output/pdfs_query.csv -o data/output/pdfs_query_result.csv --synopses-dir ~/Obsidian/Papers/Collection/Synopses $(ARGS)

# --- Utilities ---

clean: ## Remove venv, cache, and tmp files
	rm -rf $(VENV_DIR) .pytest_cache tmp
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
	find . -name "*.egg-info" -type d -prune -exec rm -rf {} +

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# --- Collaboration ---
patch: ## Apply all *.patch files in the repo root, then move them to tmp/applied-patches/
	@ls *.patch >/dev/null 2>&1 || { echo "No *.patch files in the repo root"; exit 1; }
	git apply --check *.patch
	git apply *.patch
	@mkdir -p tmp/applied-patches
	mv *.patch tmp/applied-patches/

commit-hash: ## Copy the current commit hash to the clipboard, for the start of a session
	@printf 'Commit hash: `%s`' "$$(git rev-parse --short HEAD)" | pbcopy
	@echo "Commit hash copied to clipboard"

# --- Project Documentation ---

showtree: ## Show project directory structure (needs `tree`; mac-side)
	@tree -I ".venv|.venv-win|__pycache__|tmp|*.egg-info|.git|*.jpg|*_rejected.*|bak|*-private" -L 3

gentree: ## Save tree to tmp/project_tree.txt (needs `tree`; mac-side)
	@mkdir -p tmp
	@tree -I ".venv|.venv-win|__pycache__|tmp|*.egg-info|.git|*.jpg|*_rejected.*|bak|*-private" > tmp/project_tree.txt
	@echo "Project tree saved to tmp/project_tree.txt"

filesdump: gentree ## Create context dump for LLMs
	@echo "--- Generating filesdump ---"
	$(RUN) tools/concat_files.py manifest.lst > tmp/filesdump.txt
	@echo "Filesdump created at tmp/filesdump.txt"

filesdump-detailed: gentree ## Create context dump for LLMs with per-file size details
	@echo "--- Generating filesdump ---"
	$(RUN) tools/concat_files.py --detailed --sort manifest.lst > tmp/filesdump.txt
	@echo "Filesdump created at tmp/filesdump.txt"
