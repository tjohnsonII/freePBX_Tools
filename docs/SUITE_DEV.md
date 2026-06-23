> **SUPERSEDED (2026-04-27):** This document describes a Windows/VS Code Tasks development workflow that no longer applies. The suite now runs on an always-on Ubuntu Linux server managed by systemd and `FULL_START.sh`. For current dev workflow see **RUNBOOK.md**, **ENVIRONMENT.md**, and **docs/ARCHITECTURE.md**. This file is retained as historical context only.

# FreePBX-Tools Suite (Dev Workspace) — HISTORICAL

This repo is a **suite** of tools. Keep each subproject self-contained and use VS Code Tasks to run common workflows.

## Recommended VS Code Setup

- Open the multi-root workspace: `freepbx-tools-suite.code-workspace`
- Run tasks via: **Terminal → Run Task**

## Subprojects

### Core FreePBX Tools

- Entry point (Windows dev machine): run the interactive manager:
  - Task: **FreePBX Tools: manager (interactive)**

### Traceroute Visualizer (Next.js)

- Install deps:
  - Task: **Traceroute Visualizer: npm ci**
- Run dev server:
  - Task: **Traceroute Visualizer: dev**
- Quality gates:
  - Task: **Traceroute Visualizer: lint**
  - Task: **Traceroute Visualizer: build**

### Traceroute Backend (FastAPI, optional local dev)

This is an optional local backend for development; production/remote is typically the lightweight `traceroute_server.py` running on the target host.

- Create venv:
  - Task: **Traceroute Backend (FastAPI): venv create**
- Install deps:
  - Task: **Traceroute Backend (FastAPI): deps install**
- Run:
  - Task: **Traceroute Backend (FastAPI): run (localhost:8001)**

### Webscraper

- Create venv:
  - Task: **Webscraper: venv create**
- Install deps:
  - Task: **Webscraper: deps install**
- Quick validation:
  - Task: **Webscraper: smoke test**

### Polycom/Yealink/Mikrotik/Switch Config App (Vite)

- Install deps:
  - Task: **Polycom Config App: npm ci**
- Run dev server:
  - Task: **Polycom Config App: dev**
- Build:
  - Task: **Polycom Config App: build**
