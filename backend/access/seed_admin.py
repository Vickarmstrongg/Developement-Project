
"""Create the first Admin on the explicitly confirmed development database.

Run from the backend folder, AFTER the supporting-tables migration:
    python -m access.seed_admin --name "Your Name" --email you@example.com

Requires BYTEBITE_TARGET_BRANCH=synthetic-data-dev, BYTEBITE_DEV_DB_NAME=neondb,
and BYTEBITE_DEV_DB_HOST to match the configured database host.
"""
import argparse
import getpass
import os
import sys

from sqlalchemy import select, text

import database
import models

from .constants import Role, UserStatus
from .security import hash_password


EXPECTED_BRANCH = "synthetic-data-dev"
EXPECTED_DATABASE = "neondb"


def check_target() -> None:
    if os.getenv("BYTEBITE_TARGET_BRANCH") != EXPECTED_BRANCH:
        raise RuntimeError(
            "BYTEBITE_TARGET_BRANCH must be synthetic-data-dev; no account was created."
        )
    if os.getenv("BYTEBITE_DEV_DB_NAME") != EXPECTED_DATABASE:
        raise RuntimeError(
            "BYTEBITE_DEV_DB_NAME must be neondb; no account was created."
        )

    expected_host = os.getenv("BYTEBITE_DEV_DB_HOST")
    if not expected_host or database.engine.url.host != expected_host:
        raise RuntimeError(
            "The configured database host does not match BYTEBITE_DEV_DB_HOST; "
            "no account was created."
        )
    if database.engine.url.database != EXPECTED_DATABASE:
        raise RuntimeError(
            "The configured database name is not neondb; no account was created."
        )

    try:
        with database.engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                identity = connection.execute(text("""
                    SELECT current_database() AS database_name,
                           current_schema() AS schema_name
                """)).mappings().one()
            finally:
                transaction.rollback()
    except Exception:
        raise RuntimeError(
            "Unable to verify the live database target; no account was created."
        ) from None

    if (
        identity["database_name"] != EXPECTED_DATABASE
        or identity["schema_name"] != "public"
    ):
        raise RuntimeError(
            "The live database target is not neondb.public; no account was created."
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()

    check_target()

    password = getpass.getpass("Password (min 8 characters): ")
    if len(password) < 8 or len(password.encode()) > 72:
        sys.exit("Password must be 8 to 72 bytes long.")
    if password != getpass.getpass("Repeat password: "):
        sys.exit("Passwords do not match.")

    db = next(database.get_db())
    try:
        email = args.email.lower()
        if db.scalar(select(models.User).where(models.User.email == email)):
            sys.exit(f"{email} already exists.")
        db.add(
            models.User(
                full_name=args.name,
                email=email,
                password_hash=hash_password(password),
                role=Role.ADMIN.value,
                status=UserStatus.ACTIVE.value,
                failed_login_attempts=0,
                locked=False,
            )
        )
        db.commit()
    finally:
        db.close()
    print(f"Admin {email} created.")


if __name__ == "__main__":
    main()