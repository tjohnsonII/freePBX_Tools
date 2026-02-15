param(
  [string]$DbPath = "webscraper/output/tickets.sqlite"
)

$env:TICKETS_DB_PATH = $DbPath
python -m uvicorn webscraper.ticket_api.app:app --host 127.0.0.1 --port 8787 --reload
