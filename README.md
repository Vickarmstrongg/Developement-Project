# Developement-Project

## Development performance timings

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