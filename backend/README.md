# Financial Complaint Routing Backend

The FastAPI backend foundation for the Financial Complaint Routing Benchmark and Human Review System. It currently provides typed application configuration, reusable asynchronous persistence infrastructure, and a health endpoint.

Python 3.12 or later is required.

## Setup

From the `backend` directory:

```powershell
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

`GET /health` returns `{"status":"healthy"}`.
