# Cleaned food-only Byte & Bite datasets from the lecturer CSV files

import csv
import hashlib
import json
import re
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "data" / "new"
TARGET = ROOT / "data" / "cleaned"
TEMP = ROOT / "data" / "cleaned.tmp"

FOOD_TYPES = (
    "Restaurant",
    "Cafe / Coffee Shop",
    "Fast Food & Takeaway",
    "Bakery & Snacks",
)
TRANSACTION_FILES = (
    "transaction.csv",
    "transaction.part01.csv",
    "transaction.part02.csv",
    "transaction.part03.csv",
    "transaction.part04.csv",
)
HEADERS = {
    "vendor_type.csv": ["id", "name"],
    "vendor.csv": ["id", "name", "address", "latitude", "longitude", "type_id"],
    "student.csv": ["id", "first_name", "last_name", "dob", "gender", "email", "phone", "address"],
    "calendar_event.csv": ["event_id", "event_type", "name", "start_date", "end_date", "scope", "recurring"],
    "transaction": ["id", "student_id", "vendor_id", "tx_datetime", "value", "discount"],
}
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
# Rows after this are kept but flagged
LATEST_EXPECTED_TX = "2026-12-31 23:59:59"
FLAG_FIELDS = ["source_file", "line_number", "record_type", "record_id", "action", "reason"]


def open_csv(path, expected_headers):
    handle = path.open("r", encoding="utf-8-sig", newline="")
    reader = csv.reader(handle)
    header = next(reader)
    if header != expected_headers:
        handle.close()
        sys.exit(f"Stopped: {path.name} headers differ from the expected layout.")
    return handle, reader


def is_uuid(value):
    return bool(UUID_RE.match(value))


def main():
    if not SOURCE.is_dir():
        sys.exit(f"Stopped: {SOURCE} not found.")
    if TEMP.exists():
        shutil.rmtree(TEMP)
    TEMP.mkdir(parents=True)

    report = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    flags = (TEMP / "flagged_for_review.csv").open("w", encoding="utf-8", newline="")
    flag_writer = csv.writer(flags, lineterminator="\n")
    flag_writer.writerow(FLAG_FIELDS)
    flag_reasons = Counter()

    def flag(source, line, record_type, record_id, action, reason):
        flag_reasons[(record_type, action, reason)] += 1
        flag_writer.writerow([source, line, record_type, record_id, action, reason])

    # Vendor types
    type_names, type_rows, seen = {}, [], set()
    handle, reader = open_csv(SOURCE / "vendor_type.csv", HEADERS["vendor_type.csv"])
    with handle:
        for line, row in enumerate(reader, start=2):
            if len(row) != 2 or not is_uuid(row[0]) or not row[1].strip():
                flag("vendor_type.csv", line, "vendor_type", row[0] if row else "", "flagged_excluded", "invalid_or_missing_field")
                continue
            if row[0] in seen:
                flag("vendor_type.csv", line, "vendor_type", row[0], "flagged_retained", "duplicate_id")
                continue
            seen.add(row[0])
            type_names[row[0]] = row[1]
            if row[1] in FOOD_TYPES:
                type_rows.append(row)
    food_type_ids = {i for i, n in type_names.items() if n in FOOD_TYPES}
    missing_types = [n for n in FOOD_TYPES if n not in type_names.values()]
    if missing_types:
        sys.exit(f"Stopped: food types missing from vendor_type.csv: {missing_types}")

    # Vendors
    vendor_type_of, vendor_rows, seen = {}, [], set()
    vendors_total = Counter()
    handle, reader = open_csv(SOURCE / "vendor.csv", HEADERS["vendor.csv"])
    with handle:
        for line, row in enumerate(reader, start=2):
            if len(row) != 6 or not is_uuid(row[0]):
                flag("vendor.csv", line, "vendor", row[0] if row else "", "flagged_excluded", "invalid_or_missing_id")
                continue
            if row[0] in seen:
                flag("vendor.csv", line, "vendor", row[0], "flagged_retained", "duplicate_id")
                continue
            seen.add(row[0])
            if row[5] not in type_names:
                flag("vendor.csv", line, "vendor", row[0], "flagged_excluded", "missing_or_invalid_vendor_type")
                continue
            vendor_type_of[row[0]] = row[5]
            vendors_total[type_names[row[5]]] += 1
            if row[5] in food_type_ids:
                vendor_rows.append(row)
    food_vendor_ids = {r[0] for r in vendor_rows}

    # Students 
    student_ids, student_total, seen = set(), 0, set()
    handle, reader = open_csv(SOURCE / "student.csv", HEADERS["student.csv"])
    with handle:
        for line, row in enumerate(reader, start=2):
            student_total += 1
            if not row or not is_uuid(row[0]):
                flag("student.csv", line, "student", "", "flagged_excluded", "invalid_or_missing_id")
            elif row[0] in seen:
                flag("student.csv", line, "student", row[0], "flagged_retained", "duplicate_id")
            else:
                seen.add(row[0])
                student_ids.add(row[0])

    # Transactions 
    tx_stats = Counter()
    per_file = {}
    non_food_by_type = Counter()
    food_by_type = Counter()
    used_students = set()
    row_hash_by_id = {}
    tx_out = (TEMP / "transaction.csv").open("w", encoding="utf-8", newline="")
    tx_writer = csv.writer(tx_out, lineterminator="\n")
    tx_writer.writerow(HEADERS["transaction"])
    min_dt = max_dt = None

    for name in TRANSACTION_FILES:
        stats = Counter()
        handle, reader = open_csv(SOURCE / name, HEADERS["transaction"])
        with handle:
            for line, row in enumerate(reader, start=2):
                stats["checked"] += 1
                if len(row) != 6:
                    stats["flagged_excluded"] += 1
                    flag(name, line, "transaction", row[0] if row else "", "flagged_excluded", "wrong_field_count")
                    continue
                tid, sid, vid, when, value, discount = row
                problems = []
                if not is_uuid(tid):
                    problems.append("invalid_or_missing_transaction_id")
                if not sid or sid not in student_ids:
                    problems.append("missing_or_unknown_student_id")
                if not vid or vid not in vendor_type_of:
                    problems.append("missing_or_unknown_vendor_id")
                if problems:
                    stats["flagged_excluded"] += 1
                    for reason in problems:
                        flag(name, line, "transaction", tid, "flagged_excluded", reason)
                    continue

                type_name = type_names[vendor_type_of[vid]]
                if vid not in food_vendor_ids:
                    stats["excluded_non_food"] += 1
                    non_food_by_type[type_name] += 1
                    continue

                digest = hashlib.md5("\x1f".join(row).encode("utf-8")).digest()
                previous = row_hash_by_id.get(tid)
                if previous is not None:
                    if previous == digest:
                        stats["excluded_exact_duplicate"] += 1
                        flag(name, line, "transaction", tid, "excluded", "exact_duplicate_of_earlier_row")
                        continue
                    flag(name, line, "transaction", tid, "flagged_retained", "same_id_different_content")
                else:
                    row_hash_by_id[tid] = digest

                review = []
                try:
                    amount = Decimal(value)
                    if amount <= 0:
                        review.append("value_not_positive")
                except InvalidOperation:
                    review.append("value_not_numeric")
                try:
                    rate = Decimal(discount)
                    if rate < 0 or rate > 1:
                        review.append("discount_outside_0_to_1")
                except InvalidOperation:
                    review.append("discount_not_numeric")
                if not re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", when):
                    review.append("datetime_unexpected_format")
                elif when > LATEST_EXPECTED_TX:
                    review.append("datetime_after_expected_end")
                for reason in review:
                    flag(name, line, "transaction", tid, "flagged_retained", reason)
                if review:
                    stats["retained_and_flagged"] += 1

                tx_writer.writerow(row)
                stats["retained"] += 1
                food_by_type[type_name] += 1
                used_students.add(sid)
                if when[:4].isdigit():
                    min_dt = when if min_dt is None or when < min_dt else min_dt
                    max_dt = when if max_dt is None or when > max_dt else max_dt
        per_file[name] = dict(stats)
        tx_stats.update(stats)
    tx_out.close()
    flags.close()

    # Other outputs
    with (TEMP / "vendor_type.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n"); w.writerow(HEADERS["vendor_type.csv"]); w.writerows(type_rows)
    with (TEMP / "vendor.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n"); w.writerow(HEADERS["vendor.csv"]); w.writerows(vendor_rows)
    with (TEMP / "student.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n"); w.writerow(["id"])
        handle, reader = open_csv(SOURCE / "student.csv", HEADERS["student.csv"])
        with handle:
            written = set()
            for row in reader:
                if row and row[0] in used_students and row[0] not in written:
                    written.add(row[0]); w.writerow([row[0]])
    shutil.copyfile(SOURCE / "calendar_event.csv", TEMP / "calendar_event.csv")
    event_count = sum(1 for _ in (SOURCE / "calendar_event.csv").open(encoding="utf-8-sig")) - 1

    report.update({
        "rules": {
            "food_vendor_types": list(FOOD_TYPES),
            "duplicates": "exact duplicate transaction rows collapsed to the first occurrence; same ID with different content is kept and flagged",
            "flagged_excluded": "missing or invalid student, vendor or vendor-type reference, malformed row",
            "flagged_retained": "value or discount oddities, unexpected date format, or dates after " + LATEST_EXPECTED_TX,
            "students": "IDs only, for students with at least one retained transaction",
        },
        "totals": {
            "transactions_checked": tx_stats["checked"],
            "transactions_retained": tx_stats["retained"],
            "transactions_excluded_non_food": tx_stats["excluded_non_food"],
            "transactions_excluded_exact_duplicate": tx_stats["excluded_exact_duplicate"],
            "transactions_flagged_excluded_invalid_reference": tx_stats["flagged_excluded"],
            "transactions_retained_and_flagged": tx_stats["retained_and_flagged"],
            "vendors_checked": len(vendor_type_of),
            "vendors_retained": len(vendor_rows),
            "vendor_types_retained": len(type_rows),
            "students_checked": student_total,
            "students_retained_ids_only": len(used_students),
            "calendar_events_copied_unchanged": event_count,
            "retained_transaction_datetime_range": [min_dt, max_dt],
        },
        "vendor_counts_by_type_all": dict(vendors_total.most_common()),
        "retained_transactions_by_food_type": dict(food_by_type.most_common()),
        "excluded_non_food_transactions_by_type": dict(non_food_by_type.most_common()),
        "per_file": per_file,
        "flag_reasons": [
            {"record_type": a, "action": b, "reason": c, "count": n}
            for (a, b, c), n in sorted(flag_reasons.items())
        ],
    })
    (TEMP / "cleaning_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Move file by file: renaming whole folders can be blocked by OneDrive.
    TARGET.mkdir(exist_ok=True)
    for stale in TARGET.iterdir():
        if stale.is_file():
            stale.unlink()
    for produced in TEMP.iterdir():
        shutil.move(str(produced), str(TARGET / produced.name))
    TEMP.rmdir()
    print(json.dumps(report["totals"], indent=2))


if __name__ == "__main__":
    main()
