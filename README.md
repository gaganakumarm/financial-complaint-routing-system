# Financial Complaint Routing Benchmark and Human Review System

This project will support financial complaint routing, AI predictions, and human review. It is currently at the backend-foundation stage, with a minimal FastAPI application and health check.

## Current status

Backend foundation only.

## Backend setup

Python 3.12 or later is required. From the repository root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
```

Run the tests:

```powershell
python -m pytest -v
```

Start the API:

```powershell
python -m uvicorn app.main:app
```

The health endpoint is available at `GET /health` and returns:

```json
{"status":"healthy"}
```
