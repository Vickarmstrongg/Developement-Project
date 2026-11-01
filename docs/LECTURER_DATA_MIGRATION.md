# Lecturer data migration (test branch)

Script: `backend/migrate_lecturer_data.py`. Nothing runs by itself. Test it only on the
Neon branch `lecturer-data-migration-test`. Never run it on `synthetic-data-dev`, production or any shared branch.

## What it does

| Area | Approach |
|---|---|
| IDs | App integer IDs are kept. Lecturer UUIDs go in new `source_uuid` columns (UNIQUE) on `vendor_types`, `vendors`, `transactions`, `contextual_events`. |
| Students | `students.id_number` (text) holds the lecturer UUID. Only the ID is imported; the script rejects any other student column. |
| Vendors | `gps` is built as `POINT(longitude latitude)`, the format Rush Hour Radar parses. |
| Transactions | Loaded in batches of 100,000 with PostgreSQL `COPY` into a temporary staging table, then inserted in file order. Each batch is verified row by row and recorded in `lecturer_migration_batches` in the same transaction. `value`, `discount`, `datetime` are compared with the source after loading. Meaning/units are not interpreted. |
| Events | Inserted into `contextual_events` with the lecturer UUID and a new `recurring` column. `context_events` is untouched. |
| Users | All users are kept. Old links are deleted and rebuilt from your completed mapping file. |
| Models | `models.py` is deliberately unchanged, so branches without the new columns keep working. |

New integer IDs continue upward from the previous maximum (sequences are never reset).

## Steps

All commands run from the `backend` folder in Windows PowerShell:

```powershell
Set-Location "<project>\backend"
```

1. **Offline check (no database):**
   `.\venv\Scripts\python.exe migrate_lecturer_data.py preflight`
2. **Set the target in this PowerShell session only** (not `.env`, not Git):
   ```powershell
   $env:BYTEBITE_MIGRATION_TARGET = "lecturer-data-migration-test"
   $env:BYTEBITE_MIGRATION_DB_HOST = "<host of the test branch, as in DATABASE_URL>"
   $env:BYTEBITE_MIGRATION_FORBIDDEN_DB_HOSTS = "<production host>,<synthetic-data-dev host>"
   ```
   Neon branches can share a database name and expose no SQL-visible branch name, so the endpoint host is the identifier. The deny list is mandatory, and `BYTEBITE_DEV_DB_HOST` is always treated as forbidden. Pooled (`-pooler`) and direct hostnames count as the same endpoint; a direct connection is recommended for the large load.
3. **Create the user mapping template (read-only):**
   `.\venv\Scripts\python.exe migrate_lecturer_data.py write-user-mapping-template --confirm-target lecturer-data-migration-test`
   This writes `data\migration\user_vendor_mapping.csv` and `data\migration\vendor_reference.csv` (Git-ignored; the template contains user emails).
4. **Complete the mapping.** For each row, paste the `vendor_source_uuid` from `vendor_reference.csv`.
   Add one row per extra vendor for a Manager. Staff need exactly one vendor, Managers at least one, and Admins are not listed. Every non-Admin user must be covered. Example: [user_vendor_mapping.example.csv](./user_vendor_mapping.example.csv). The script never guesses.
5. **Preflight with mapping and read-only database checks:**
   `.\venv\Scripts\python.exe migrate_lecturer_data.py preflight --user-vendor-map ..\data\migration\user_vendor_mapping.csv --check-db --confirm-target lecturer-data-migration-test`
   It checks the schema types, foreign-key delete rules, ID defaults, the user mapping and the marker.
6. **Backup.** The Neon parent branch (`synthetic-data-dev`) is the backup. The script also writes `data\migration\pre_migration_snapshot_*.json` (user IDs, roles, links, row counts; no emails or password hashes).
7. **Mark the test branch** (creates one small table; asks you to type the target name; stores a fingerprint of the endpoint):
   `.\venv\Scripts\python.exe migrate_lecturer_data.py init-marker --confirm-target lecturer-data-migration-test`
8. **Switch to the direct Neon connection (session only).** The pooled (`-pooler`) host drops long jobs, and `apply` refuses it.
   In the Neon console: project, Branches, `lecturer-data-migration-test`, **Connect**; choose the branch, database and role, and turn **Connection pooling OFF**. The host no longer contains `-pooler`. Do not edit `.env` and do not paste the URL into chat or Git:
   ```powershell
   $s = Read-Host "Direct Neon URL" -AsSecureString
   $env:DATABASE_URL = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))
   $env:BYTEBITE_MIGRATION_DB_HOST = "<the direct host>"
   ```
   A session variable overrides `.env`. Closing PowerShell discards it. The existing marker still matches because `-pooler` is ignored in the endpoint fingerprint; re-run step 5 to confirm (`target_marker_matches_endpoint: true`). Only if it is false, run step 7.
9. **Test one batch:**
   `.\venv\Scripts\python.exe migrate_lecturer_data.py apply --confirm-target lecturer-data-migration-test --replace-synthetic-data --replace-synthetic-events --purge-vendor-bound-records --user-vendor-map ..\data\migration\user_vendor_mapping.csv --max-batches 1`
   The first run clears the synthetic data (committed in steps), loads vendors, types, students, events and links, then commits one batch and stops.
10. **Finish.** Re-run the exact same command without `--max-batches`. It resumes at the first missing batch. Do not change flags, batch size or the CSV files between runs (a changed fingerprint is refused).
11. **Check:** `preflight --user-vendor-map ... --check-db --confirm-target lecturer-data-migration-test` shows `migration_progress` with status `complete`.
12. Start the backend and click through Dashboard, Rush Hour Radar, Demand Forecast, Fair Comparison, Context Events and Users.

## How the batched migration works

| Phase | What happens | Commit |
|---|---|---|
| A | Add columns and two bookkeeping tables; record the user digest; status `clearing`. | one transaction |
| B | Clear synthetic links, notifications, transactions (100,000 ids per step, `source_uuid IS NULL` only), students, vendors, types, synthetic events; status `loading`. | one transaction per step, repeatable |
| C | Insert types, vendors, students, events (`ON CONFLICT DO NOTHING`); rebuild user links from the mapping. | one transaction |
| D | For each 100,000-row batch: COPY to temp table, insert with `ON CONFLICT (source_uuid) DO NOTHING`, compare every row with the source, insert the `lecturer_migration_batches` row. | one transaction per batch |
| E | Status `validating`; create the `(vendor_id, datetime)` index; run all final checks; only then status `complete`. | one transaction |

**App gate.** While `lecturer_migration_state.status` is not `complete`, every API route (except `/`, `/db-check`, `/migration-status`, docs) returns 503, including for Admins. If the status cannot be read the app also answers 503. `GET /migration-status` returns `{"ready": true|false}`.

**Fingerprint.** The stored fingerprint is the SHA-256 of all five CSVs, the user-vendor mapping CSV, the batch size, both `--replace-*`/`--purge-*` flags and the script's `MIGRATION_VERSION`. Every resume recomputes it during the read-only inspection and stops, before any write, if it differs. Editing the mapping file or the script version mid-migration therefore requires starting over (re-branch).

**One run at a time.** `apply` takes a PostgreSQL session advisory lock on its own connection before touching anything else, re-checks it before each phase and batch, and releases it on success, failure or exit. A second `apply` stops with "Another migration process is already running". If a run crashed, the server frees the lock once it notices the dropped connection (a few minutes at most).

**Recovery.** The whole run uses ONE direct connection that holds the advisory lock and performs every write; the script never reconnects or retries. If the connection drops, the script aborts and the lock goes with it (it may take a few minutes for Neon to notice). Re-run the same command to resume: re-run the same command: committed batches are skipped after their content hash is re-checked; a batch is either fully committed with its ledger row or not present. A changed batch hash aborts. Phase B is not reversible: if you need to start over, delete the test branch in Neon and re-branch from `synthetic-data-dev`.

**Risks.** Users have no vendor links between phases B and C, and the app is closed throughout. Aborted batches may leave gaps in transaction IDs (harmless). The SQL/COPY path has been tested offline only until the first real run; `--max-batches 1` is the real test.

## Checks before `complete` (any failure keeps the app closed)

Row counts for all five files and the batch ledger (batch count and row total); exact `sum(value)`/`sum(discount)` and datetime range; each transaction row compared with its source inside its batch (value and discount as text, datetime, student, vendor via UUID); unique `source_uuid`; every vendor type, vendor (name, address, GPS, type), event (type, name, dates, scope, recurring) and the full student ID set compared with the source; no orphan transactions; user links equal the mapping file; Staff have one vendor, Managers at least one, Admins none; user count and a database-side hash of user emails, roles, statuses and password hashes unchanged (only the legacy `users.vendor_id` is cleared).

## Still to confirm with the lecturer

- Units, gross/net status and meaning of `value`, and the meaning of `discount` (0.05–0.75). Revenue and discount calculations are unchanged.
- Time zone of `tx_datetime`.
- Data runs to 2026-12-31 and Rush Hour Radar uses the latest transaction date as "today", so its baseline windows will be based on that date.
- `calendar_event.csv` has no `all_day`, location or campus fields, so those stay empty.

## Frontend

The Rush Hour Radar type filter no longer hard-codes type IDs 3, 4, 5. It loads them from the new `GET /vendor-types` endpoint. Dashboard filters already load types from the API.
