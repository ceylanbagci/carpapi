## CarPapi — local dev convenience targets.
##
## The actual work happens in `scripts/dev.sh`; the Makefile is just
## a friendly entry point. Run `make help` for the list.

SHELL := /usr/bin/env bash

.DEFAULT_GOAL := help

## help: show this list
help:
	@printf "CarPapi — local dev targets\n\n"
	@awk 'BEGIN{FS=":"} \
	  /^## [a-zA-Z_-]+:/ { \
	    sub(/^## /, ""); \
	    name = $$1; sub(/^[^:]+: */, "", $$0); \
	    printf "  \033[36m%-10s\033[0m %s\n", name, $$0; \
	  }' $(MAKEFILE_LIST)

## dev: start Django + Vite together (Ctrl+C stops both)
dev:
	@./scripts/dev.sh both

## backend: start Django only (port 8000)
backend:
	@./scripts/dev.sh backend

## frontend: start Vite only (port 5173)
frontend:
	@./scripts/dev.sh frontend

## install: create venv + npm install (idempotent, no servers started)
install:
	@./scripts/dev.sh check

## stop: kill anything listening on :8000 or :5173
stop:
	@for p in 8000 5173; do \
		pids=$$(lsof -ti tcp:$$p -sTCP:LISTEN 2>/dev/null || true); \
		if [ -n "$$pids" ]; then \
			echo "stopping :$$p (pid $$pids)"; kill $$pids; \
		else \
			echo ":$$p already free"; \
		fi; \
	done

## logs: tail backend + frontend logs (in .logs/)
logs:
	@mkdir -p .logs && touch .logs/backend.log .logs/frontend.log
	@tail -n 50 -f .logs/backend.log .logs/frontend.log

## clean: remove .logs/, venv, and node_modules (full reset)
clean:
	@echo "removing .logs, web/backend/.venv, web/frontend/node_modules"
	@rm -rf .logs web/backend/.venv web/frontend/node_modules

## verify: hit the running servers and report status
verify:
	@code=$$(curl -sS -o /dev/null -w "%{http_code}" --max-time 2 http://127.0.0.1:8000/ 2>/dev/null); \
		if [ -z "$$code" ] || [ "$$code" = "000" ]; then echo "backend  :8000   offline"; \
		else echo "backend  :8000   $$code"; fi
	@code=$$(curl -sS -o /dev/null -w "%{http_code}" --max-time 2 http://127.0.0.1:5173/ 2>/dev/null); \
		if [ -z "$$code" ] || [ "$$code" = "000" ]; then echo "frontend :5173   offline"; \
		else echo "frontend :5173   $$code"; fi

.PHONY: help dev backend frontend install stop logs clean verify
