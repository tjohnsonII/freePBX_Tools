# FreePBX Tools Suite – Repository Map

## Overview
This repository is a **monorepo** containing:
- Core FreePBX CLI / diagnostic tools
- Web UIs (React/Vite / Next.js)
- Backend APIs (FastAPI)
- Scraping and knowledge-base tooling
- Config/template generators (Mikrotik / Polycom / Yealink)

Not all folders are apps. Many are support, data, or generated artifacts.

---

## Top-Level Structure (Authoritative)

### Core Applications
- **freepbx-tools/**
  - Terminal-based FreePBX tools deployed to FreePBX servers
  - Installed under `/usr/local/123net/freepbx-tools`
  - Entry points live in `freepbx-tools/bin/`
  - Requires root on FreePBX hosts

- **freepbx-deploy-backend/**
  - FastAPI backend for deployment / orchestration
  - Runs locally during dev (Windows / WSL)
  - Communicates with FreePBX servers over SSH

- **freepbx-deploy-ui/**
  - React + Vite frontend
  - Depends on `freepbx-deploy-backend`
  - Local dev only

- **traceroute-visualizer-main/**
  - Traceroute visualization tool
  - Contains BOTH project root and nested app folder
  - Nested structure is intentional

- **PolycomYealinkMikrotikSwitchConfig-main/**
  - React-based config generator UI
  - Generates phone/switch configs from templates

- **webscraper/**
  - Selenium-based scraping and KB population
  - Handles credentials, cookies, and browser automation
  - Sensitive by design — outputs must not be committed

---

### Supporting / Library Code
- **scripts/** – helper scripts and glue logic
- **tools/** – standalone utilities
- **templates/** – config and text templates
- **static/** – static assets for web tools
- **mikrotik/** – Mikrotik config generation scripts
- **PhoneConfigs/** – phone config references

---

### Data / Generated Artifacts (NOT SOURCE)
- **scraped_tickets/**
- **knowledge_base/**
- **data/**
- **\_\_pycache\_\_/**
- **node_modules/**
- **dist/**

These folders may be present locally but must not be treated as source code.

---

### Development Environment
- **.venv-web-manager/** – Python virtual environment
- **.vscode/** – workspace settings
- **.github/** – CI / GitHub config

---

## Folder Duplication Notes
Some projects contain nested folders with the same name (e.g.):
- `traceroute-visualizer-main/traceroute-visualizer-main/`

This is intentional and common in monorepos.  
Do **not** flatten or refactor without explicit instruction.

---

## Golden Rule
If a folder is not listed above as an app or library, assume:
- It may be generated
- It may be sensitive
- It should not be modified without confirmation
