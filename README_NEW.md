# Byte & Bite

Byte & Bite is a web application for analysing vendor transactions, demand forecasts, and contextual events.

**Technology:** React (Vite) frontend, FastAPI (Python) backend, and PostgreSQL database (hosted on Neon or run locally).

## 1. Requirements

Install:
- [Python](https://www.python.org/downloads/)
- [Node.js and npm](https://nodejs.org/)
- [Git](https://git-scm.com/)
- A PostgreSQL database, such as [Neon](https://neon.tech/)

The commands below are for **Windows PowerShell**.

## 2. Download the project

Clone the repository and open its folder:

```powershell
git clone <YOUR_REPOSITORY_URL>
cd <YOUR_PROJECT_FOLDER>
```

The project has two main folders: `backend` and `frontend`.

## 3. Configure the database

1. Create a PostgreSQL project/database in [Neon](https://neon.tech/) (or use your own PostgreSQL server).
2. In the Neon dashboard, open **Connect** and copy the PostgreSQL connection string.
3. Create a file called **`backend/.env`** and add:

```env
DATABASE_URL=postgresql://USERNAME:PASSWORD@HOST/DATABASE?sslmode=require
JWT_SECRET=OBpbrJ7fEUriRLwIBGHtJC78eg03UEe33eQz9pTC_CBhGHEhrU9uHTajMBMuseZ_
FRONTEND_URL=http://localhost:5173
GMAIL_ADDRESS=coker199gk@gmail.com
GMAIL_APP_PASSWORD=lixggtnuxwlssajk
```

Replace `DATABASE_URL` with your **actual** connection string from Neon. Generate a random JWT secret using:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

The Gmail settings are only needed if email invitations are configured. **Never upload `.env` to GitHub.**

**Important:** A new database also needs the application's tables and transaction data. Run the SQL/migration and data-import scripts supplied with the project before starting the application. If the repository does not yet contain those scripts or a database dump, they must be added for a completely new user to set up the system.

## 4. Start the backend

Open a terminal in the project folder:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload
```

The backend runs at **http://127.0.0.1:8000**.

API documentation: **http://127.0.0.1:8000/docs**

Keep this terminal open.

## 5. Start the frontend

Open a **second terminal** in the project folder:

```powershell
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** (or the address displayed in the terminal).

The frontend connects to `http://127.0.0.1:8000` by default. If the backend uses a different address, create `frontend/.env` with:

```env
VITE_API_URL=http://127.0.0.1:8000
```

Restart the frontend after editing this file.

## 6. Log in

Use an existing account to log in. The application supports **Admin**, **Manager**, and **Staff** roles. An Admin can invite additional users and assign vendor access.

**First-time installation:** A fresh database needs an initial Admin account. Include the project's Admin setup/bootstrap procedure with the database setup files; existing account credentials from another database will not work automatically.

## Troubleshooting

- **Backend won't start:** Check that the Python packages installed and `backend/.env` contains a valid `DATABASE_URL`.
- **Database error:** Check the Neon connection string, database tables, and imported data.
- **Frontend won't load:** Check that `npm install` completed and `npm run dev` is running.
- **Frontend cannot fetch data:** Make sure the backend is running on port `8000`.
- **No forecasts shown:** Ensure the database contains historical vendor transactions.

> **Before submission:** Add the exact database schema/import command and initial Admin setup command to this README once the relevant scripts are confirmed. Without them, a stranger cannot initialise a completely empty database.

## Development performance timings (optional)

The backend has opt-in request, SQL execution, analytics-stage, and JSON-render
timings. Logging is disabled unless both development settings are enabled.
From PowerShell:

```powershell
Set-Location backend
$env:APP_ENV = "development"
$env:BB_PERFORMANCE_LOGS = "1"
.\venv\Scripts\python.exe -m uvicorn main:app --reload
```

Open the Dashboard, Demand Forecast, Fair Comparison, and Rush Hour Radar in
the frontend. Each API request emits one `api_performance` JSON log containing
the route template, status, elapsed milliseconds, SQL query count, SQL cursor
execution milliseconds, response byte count, and recorded calculation/JSON
render stages. Route templates are logged instead of concrete URLs; SQL
statements, parameters, request bodies, tokens, and response contents are not
logged.

`db_execute_ms` covers database cursor execution time, not all result fetching
or ORM conversion. Compare it with each calculation-stage duration and total
`elapsed_ms` to identify whether more detailed profiling is needed. Collect
several runs per feature (including a warm repeat) using the same account,
vendor, and filters; use the median and slowest run as a local baseline. These
instrumentation logs are intended for development only.
