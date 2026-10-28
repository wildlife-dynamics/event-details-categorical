.PHONY: help build compile recompile run test open clean all dev dev-refresh

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------

.DEFAULT_GOAL := help

-include Makefile.local

WORKFLOW_ID   := event-details-categorical
WORKFLOW_DIR  ?= ecoscope-workflows-categorical-workflow
PARAM_FILE    ?= param.yaml
OUTPUT_DIR    ?= /tmp/event-details-categorical/output
# Categorical tasks live in ext-wd (wd-partner-tasks, checked out at
# ../wd-partner-tasks-categorical: src/ecoscope-workflows-ext-wd/.../_categorical.py),
# released to prefix.dev. `make build` builds ext-wd into a local channel for trying
# unreleased changes (point spec.yaml at it while you do).
EXT_LIB_DIR   ?= $(shell dirname $(CURDIR))/wd-partner-tasks-categorical
EXT_VERSION   ?= 0.0.10
# the editable ext-wd (wt-compiler-env-overrides.toml) takes its version from git tags, and
# the nearest tag may be another partner's: pin it
export SETUPTOOLS_SCM_PRETEND_VERSION ?= $(EXT_VERSION)
LOCAL_CHANNEL ?= /tmp/ecoscope-workflows-custom/categorical/artifacts
CASE          ?= naibungalower-post-report

# Mock-IO data lives in this repo (mock-io/), not in the ext-wd package; wt-task reads
# this override instead of looking for an example-return file next to the task. A case
# with its own data has a folder mock-io/<case>/; the others share mock-io/.
MOCK_IO_DIR   ?= $(if $(wildcard mock-io/$(CASE)/*.parquet),$(CURDIR)/mock-io/$(CASE),$(CURDIR)/mock-io)
export WT_TASK_MOCK_IO__ECOSCOPE_WORKFLOWS_EXT_WD_TASKS_GET_CATEGORICAL_FIELD_CATALOGUE ?= $(MOCK_IO_DIR)/get-categorical-field-catalogue.example-return.parquet
export WT_TASK_MOCK_IO__ECOSCOPE_WORKFLOWS_EXT_WD_TASKS_GET_CATEGORICAL_EVENTS ?= $(MOCK_IO_DIR)/get-categorical-events.example-return.parquet

# ------------------------------------------------------------------------------
# AESTHETICS & THEME
# ------------------------------------------------------------------------------

VIOLET     := \033[38;5;183m
SKY_BLUE   := \033[38;5;111m
MINT_GREEN := \033[38;5;114m
AQUA       := \033[38;5;123m
PEACH      := \033[38;5;216m
CORAL      := \033[38;5;210m
ROSE       := \033[38;5;218m
SLATE      := \033[38;5;246m
GOLD       := \033[38;5;222m
RESET      := \033[0m
BOLD       := \033[1m

T_TOP     := ╭────────────────────┬────────────────────────────────────────────────╮
T_MID     := ├────────────────────┼────────────────────────────────────────────────┤
T_BOT     := ╰────────────────────┴────────────────────────────────────────────────╯
B_TOP     := ╭───────────────────────────────────────────────────────────────╮
B_BOT     := ╰───────────────────────────────────────────────────────────────╯
SEPARATOR := ───────────────────────────────────────────────────────────────

define print_row
	@printf "$(VIOLET)│$(RESET)  $(SLATE)%-16s$(RESET)  $(VIOLET)│$(RESET)  $(AQUA)%-44s$(RESET)  $(VIOLET)│$(RESET)\n" "$(1)" "$(2)"
endef

define print_head
	@echo ""
	@echo " $(BOLD)$(3)$(1)  $(2)$(RESET)"
	@echo " $(SLATE)$(SEPARATOR)$(RESET)"
endef

# ------------------------------------------------------------------------------
# TARGETS
# ------------------------------------------------------------------------------

help: ## Show this help menu
	@echo ""
	@echo "$(VIOLET)$(T_TOP)$(RESET)"
	@printf "$(VIOLET)│$(RESET)  $(BOLD)$(SKY_BLUE)%-16s$(RESET)  $(VIOLET)│$(RESET)  $(BOLD)$(SKY_BLUE)%-44s$(RESET)  $(VIOLET)│$(RESET)\n" "Target" "Description"
	@echo "$(VIOLET)$(T_MID)$(RESET)"
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*?##/ { printf "$(VIOLET)│$(RESET)  $(MINT_GREEN)%-16s$(RESET)  $(VIOLET)│$(RESET)  $(SLATE)%-44s$(RESET)  $(VIOLET)│$(RESET)\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@echo "$(VIOLET)$(T_BOT)$(RESET)"
	@echo ""
	@echo "  $(SLATE)Override defaults in $(AQUA)Makefile.local$(RESET)  e.g.  $(AQUA)PARAM_FILE=test-cases/case1/param.yaml$(RESET)"
	@echo ""

all: build compile run ## Build ext-wd, compile, then run the workflow

build: ## Build ext-wd (categorical tasks) into the local channel
	@echo ""
	@echo "$(VIOLET)➜ $(BOLD)Building ecoscope-workflows-ext-wd $(EXT_VERSION)...$(RESET)"
	@# Calls rattler-build directly rather than publish/build.sh, which first
	@# deletes every other ext-* artifact in the shared local channel.
	@cd $(EXT_LIB_DIR) && HATCH_VCS_VERSION=$(EXT_VERSION) SETUPTOOLS_SCM_PRETEND_VERSION=$(EXT_VERSION) \
		pixi run rattler-build build \
		--recipe $(EXT_LIB_DIR)/publish/recipes/release/ecoscope-workflows-ext-wd.yaml \
		--output-dir $(LOCAL_CHANNEL) \
		--channel https://prefix.dev/ecoscope-workflows --channel conda-forge
	@# Rebuilding the same version keeps the old sha256 in repodata and the old
	@# extracted package in the rattler cache (install then fails on a hash
	@# mismatch, or silently uses stale code): re-index from scratch, drop the cache.
	@find $(LOCAL_CHANNEL) -name 'repodata*' -delete
	@pixi exec rattler-index fs $(LOCAL_CHANNEL) >/dev/null
	@rm -rf ~/Library/Caches/rattler/cache/pkgs/ecoscope-workflows-ext-wd-$(EXT_VERSION)-*
	@echo "$(MINT_GREEN)✔ Artifact written to $(LOCAL_CHANNEL)$(RESET)"

WTC_PY       ?= pixi run python
DEV_MODE     ?= skip-solve

dev: ## Fast dev compile: cached env + local ext-wd (editable). Do not commit the output.
	@if [ -d $(WORKFLOW_DIR)/.pixi ]; then mv $(WORKFLOW_DIR)/.pixi .pixi-workflow-keep; fi; \
	WTC_DEV_MODE=$(DEV_MODE) $(WTC_PY) dev/wtc_dev.py compile --spec spec.yaml \
		--pkg-name-prefix=ecoscope-workflows \
		--results-env-var=ECOSCOPE_WORKFLOWS_RESULTS \
		--env-overrides wt-compiler-env-overrides.toml --clobber --no-progress; \
	rc=$$?; \
	if [ -d .pixi-workflow-keep ]; then mkdir -p $(WORKFLOW_DIR); mv .pixi-workflow-keep $(WORKFLOW_DIR)/.pixi; fi; \
	exit $$rc

dev-refresh: ## Like dev, but re-solve so newer package releases are picked up
	@$(MAKE) --no-print-directory dev DEV_MODE=persistent-env

recompile: ## Compile spec and update workflow env (faster)
	@echo ""
	@echo "$(VIOLET)➜ $(BOLD)Recompiling spec.yaml...$(RESET)"
	@pixi run recompile-event-details-categorical
	@echo ""
	@echo "$(MINT_GREEN)✔ Recompile complete$(RESET)"

compile: ## Compile spec and install workflow env
	@echo ""
	@echo "$(VIOLET)➜ $(BOLD)Compiling spec.yaml...$(RESET)"
	@pixi run compile-event-details-categorical
	@echo ""
	@echo "$(MINT_GREEN)✔ Compile complete$(RESET)"

setup: ## Create output directory
	$(call print_head,⚙,Setting up Environment,$(VIOLET))
	@mkdir -p $(OUTPUT_DIR)
	@echo "  $(MINT_GREEN)✔$(RESET) $(SLATE)Output directory ready:$(RESET) $(OUTPUT_DIR)"

run: setup ## Run the workflow with param.yaml (real data — no mock IO)
	@echo ""
	@echo "$(VIOLET)$(T_TOP)$(RESET)"
	@printf "$(VIOLET)│$(RESET)  $(BOLD)$(SKY_BLUE)%-16s$(RESET)  $(VIOLET)│$(RESET)  $(BOLD)$(SKY_BLUE)%-44s$(RESET)  $(VIOLET)│$(RESET)\n" "Settings" ""
	@echo "$(VIOLET)$(T_MID)$(RESET)"
	$(call print_row,Workflow,$(WORKFLOW_ID))
	$(call print_row,Params,$(PARAM_FILE))
	$(call print_row,Output,$(OUTPUT_DIR))
	$(call print_row,Exec Mode,sequential)
	@echo "$(VIOLET)$(T_BOT)$(RESET)"
	$(call print_head,🚀,Execution Log,$(PEACH))
	@cd $(WORKFLOW_DIR) && \
	ECOSCOPE_WORKFLOWS_RESULTS="file://$(OUTPUT_DIR)" \
	pixi run ecoscope-workflows-categorical-workflow run \
		--config-file $(abspath $(PARAM_FILE)) \
		--execution-mode sequential \
		--no-mock-io
	@echo ""
	@echo "$(MINT_GREEN)$(B_TOP)$(RESET)"
	@printf "$(MINT_GREEN)│$(RESET)   $(BOLD)$(MINT_GREEN)✨  Workflow Completed Successfully$(RESET)                         $(MINT_GREEN)│$(RESET)\n"
	@echo "$(MINT_GREEN)$(B_BOT)$(RESET)"
	$(call print_head,📂,Output Directory Contents,$(CORAL))
	@eza -lha --group-directories-first --icons $(OUTPUT_DIR) 2>/dev/null || ls -lh $(OUTPUT_DIR)
	$(call print_head,📃,Result JSON Preview,$(ROSE))
	@if [ -f "$(OUTPUT_DIR)/result.json" ]; then \
		python3 -c "import json; r=json.load(open('$(OUTPUT_DIR)/result.json')); print('error:', r.get('error'))"; \
	else \
		echo "$(GOLD)⚠ result.json not found$(RESET)"; \
	fi
	@echo ""

test: ## Run the compiled workflow's tests for one case (CASE=naibungalower-post-report)
	$(call print_head,🧪,Testing case $(CASE),$(AQUA))
	@cd $(WORKFLOW_DIR) && pixi run -e test test-app-metadata --case $(CASE)
	@# the map/chart screenshot tests (test_iframes) can hang on WebGL in headless Chromium and
	@# differ between runs, so they are left out here
	@cd $(WORKFLOW_DIR) && pixi run -e test python -m pytest -v tests/test_results.py \
		-k "cli and sequential and mock-io and not iframes and not otel" --case $(CASE)
	@echo ""

open: ## Preview the dashboard (layout.json grid, view selector) in the browser
	$(call print_head,🌐,Opening Dashboard,$(AQUA))
	@pixi run python dev/preview_dashboard.py $(OUTPUT_DIR)
	@echo ""

refresh: ## Clear rattler package cache for a clean rebuild
	$(call print_head,🔄,Clearing Rattler Cache,$(GOLD))
	@rm -rf ~/Library/Caches/rattler/cache/pkgs/.icu-* ~/Library/Caches/rattler/cache/pkgs/icu-*
	@rm -rf ~/Library/Caches/rattler/cache/pkgs/.python-3* ~/Library/Caches/rattler/cache/pkgs/python-3*
	@echo "  $(MINT_GREEN)✔$(RESET) $(SLATE)Cache cleared — run$(RESET) $(AQUA)make compile$(RESET) $(SLATE)to rebuild$(RESET)"
	@echo ""

clean: ## Clean output directory
	$(call print_head,🗑️,Cleaning Output,$(PEACH))
	@rm -rf $(OUTPUT_DIR)
	@echo "  $(ROSE)✔ Deleted:$(RESET) $(SLATE)$(OUTPUT_DIR)$(RESET)"
	@echo ""
