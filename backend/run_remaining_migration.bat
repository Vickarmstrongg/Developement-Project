@echo off
rem Runs the lecturer-data migration ONE batch at a time until the ledger says it is complete.
rem Run it from a CMD window where DATABASE_URL and the BYTEBITE_MIGRATION_* variables are set.
rem The script asks you to type the target name on EVERY run; this file never types it for you.
setlocal
cd /d "%~dp0"

if not defined DATABASE_URL goto missing_env
if not defined BYTEBITE_MIGRATION_TARGET goto missing_env
if not defined BYTEBITE_MIGRATION_DB_HOST goto missing_env
if not defined BYTEBITE_MIGRATION_FORBIDDEN_DB_HOSTS goto missing_env

set "STATE_FILE=%TEMP%\bytebite_migration_status_%RANDOM%.txt"
set RUNS=0
set LAST_COUNT=

:loop
echo.
echo Checking migration status (read-only)...
if exist "%STATE_FILE%" del "%STATE_FILE%"
venv\Scripts\python.exe check_migration_status.py "%STATE_FILE%"
set RC=%ERRORLEVEL%
if %RC%==10 goto done
if %RC%==20 goto not_started
if not %RC%==0 goto failed
if not exist "%STATE_FILE%" goto failed_nostate

set /p STATE_LINE=<"%STATE_FILE%"
call :parse %STATE_LINE%
if defined LAST_COUNT if "%COUNT%"=="%LAST_COUNT%" goto no_progress
set LAST_COUNT=%COUNT%

set /a RUNS+=1
if %RUNS% GTR 60 goto too_many

echo.
echo Starting one batch (run %RUNS%). Type lecturer-data-migration-test when asked.
venv\Scripts\python.exe migrate_lecturer_data.py apply --confirm-target lecturer-data-migration-test --replace-synthetic-data --replace-synthetic-events --purge-vendor-bound-records --user-vendor-map ..\data\migration\user_vendor_mapping.csv --max-batches 1
set RC=%ERRORLEVEL%
if not %RC%==0 goto failed
goto loop

:parse
set STATUS=%1
set COUNT=%2
exit /b 0

:done
echo.
echo The ledger reports status complete. Nothing more to run.
if exist "%STATE_FILE%" del "%STATE_FILE%"
endlocal & exit /b 0

:not_started
echo.
echo STOPPED: no migration has been started on this database. This file only continues one that exists.
endlocal & exit /b 20

:missing_env
echo.
echo STOPPED: set DATABASE_URL, BYTEBITE_MIGRATION_TARGET, BYTEBITE_MIGRATION_DB_HOST and
echo BYTEBITE_MIGRATION_FORBIDDEN_DB_HOSTS in this CMD window first.
endlocal & exit /b 1

:no_progress
echo.
echo STOPPED: the committed batch count did not change after the last run (%COUNT%). Not looping.
endlocal & exit /b 23

:too_many
echo.
echo STOPPED: safety ceiling of 60 runs reached.
endlocal & exit /b 1

:failed_nostate
echo.
echo STOPPED: the status check produced no result.
endlocal & exit /b 22

:failed
echo.
echo STOPPED: a command failed with exit code %RC%. Nothing was retried. Read the message above.
endlocal & exit /b %RC%
