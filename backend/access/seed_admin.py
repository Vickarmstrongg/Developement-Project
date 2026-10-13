
"""This code is used to create the first Admin (invite-only system, so someone must exist first).

Run from the backend folder, AFTER the supporting-tables migration:
    python -m access.seed_admin --name "Your Name" --email you@example.com
"""
import argparse
import getpass
import sys

from sqlalchemy import select

import database
import models

from .constants import Role, UserStatus
from .security import hash_password


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()

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