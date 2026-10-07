# AI-Privacy-Firewall

AI-Privacy-Firewall is a research project scaffold for exploring privacy-preserving AI workflows.

## Project status

Sprint 4.2 adds Alembic migration configuration to the backend scaffold. No migrations or application business logic have been implemented.

## Project structure

- `backend/` — FastAPI application scaffold and backend tests.
- `frontend/` — React, Vite, and TypeScript application scaffold.
- `docs/` — Project documentation placeholders.
- `PROJECT_STATUS.md` — Current sprint and implementation status.

## Run the backend

From the repository root, create and activate a virtual environment, then install the backend requirements:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
python -m uvicorn app.main:app --app-dir backend --reload
```

The health endpoint is available at `http://127.0.0.1:8000/health`.
Backend settings are read from `backend\.env` (create it from the example above); environment variables can override those values.
Set `DATABASE_URL` in `backend\.env` to the PostgreSQL connection URL for your environment. The SQLAlchemy engine and session factory are available for future database work; creating a session alone does not open a connection.
Alembic is configured in `backend\alembic.ini`. Run Alembic commands from `backend\`; it reads the database URL from Pydantic Settings and targets `Base.metadata`.

## Run the frontend

```powershell
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite in your browser.

## Scope

This scaffold intentionally contains no machine-learning implementation, authentication, database models or CRUD operations, Docker configuration, or application endpoints other than `/health`.
