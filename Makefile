.PHONY: help install install-dev install-rich run clean uninstall

PYTHON  ?= python3
PIP     ?= pip3
PLUGIN  ?= $(word 2, $(MAKECMDGOALS))

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# ── Installation ────────────────────────────────────────────────────

install: ## Install the package (editable / development mode)
	$(PIP) install -e .

install-rich: ## Install with rich (colored) output support
	$(PIP) install -e ".[rich]"

install-dev: ## Install editable + rich extras
	$(PIP) install -e ".[rich]"

uninstall: ## Uninstall the package
	$(PIP) uninstall -y port-claude-plugins

# ── Running ─────────────────────────────────────────────────────────

run: ## Run as a Python module:  make run <plugin_name> [ARGS="--dry-run"]
	$(PYTHON) -m port_claude_plugin $(PLUGIN) $(ARGS)

run-script: ## Run the standalone script directly:  make run-script <plugin_name> [ARGS="--dry-run"]
	$(PYTHON) port-claude-plugin.py $(PLUGIN) $(ARGS)

run-cli: ## Run via the installed CLI entry-point:  make run-cli <plugin_name> [ARGS="--dry-run"]
	port_claude_plugin $(PLUGIN) $(ARGS)

# ── Utilities ───────────────────────────────────────────────────────

clean: ## Remove build artifacts and caches
	rm -rf build/ dist/ *.egg-info .eggs/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true

# Catch-all so make doesn't complain about plugin_name as a target
%:
	@:
