# webscraper-manager

`webscraper-manager` is a Windows-friendly CLI to orchestrate the `webscraper/` stack from one place.

## Install (editable from repo root)

```powershell
python -m pip install -e .\webscraper-manager
```

## Run

```powershell
python -m webscraper_manager doctor
webscraper-manager doctor --fix
webscraper-manager auth chrome --login-url https://secure.123.net
webscraper-manager start everything --fix --detach
webscraper-manager test all
```

## Common workflows

### 1) Check + auto-fix

```powershell
webscraper-manager doctor --fix
```

### 2) Authenticate browser profile

```powershell
webscraper-manager auth chrome
webscraper-manager auth edge
```

Profiles are stored under `.webscraper_manager/profiles/` and auth exports are written to `.webscraper_manager/auth/`.

### 3) Start stack

```powershell
webscraper-manager start ui
webscraper-manager start scraper
webscraper-manager start everything --fix
```

### 4) API checks

```powershell
webscraper-manager api health
webscraper-manager api ping --path /api/events/latest?limit=50
webscraper-manager api tail --seconds 20 --interval 2
```

### 5) Tests

```powershell
webscraper-manager test smoke
webscraper-manager test unit
webscraper-manager test integration
webscraper-manager test all --keep-going
```

## Troubleshooting

- **Driver mismatch**: run `webscraper-manager doctor` and inspect the browser/driver version lines. If auto-fix cannot download drivers, the CLI prints exact URLs and expected destination paths.
- **Port 8787 conflict**: run `webscraper-manager status` to see PID/command using the port, then `webscraper-manager stop ui`.
- **Not using scraper venv**: create/use `.venv-webscraper` and re-run with `.venv-webscraper\Scripts\python.exe -m webscraper_manager doctor`.
