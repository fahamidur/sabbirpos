import json
import os
from getpass import getpass
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")

import django

django.setup()

from django.contrib.auth.hashers import check_password, make_password


BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS_FILE = BASE_DIR / "admin_credentials.json"


def create_admin():
    print("\nCreate or replace administrator\n")

    username = input("New admin username: ").strip()

    if not username:
        print("Error: Username cannot be empty.")
        return

    password = getpass("New admin password: ")
    confirm_password = getpass("Confirm password: ")

    if not password:
        print("Error: Password cannot be empty.")
        return

    if password != confirm_password:
        print("Error: Passwords do not match.")
        return

    if len(password) < 8:
        print("Error: Password must contain at least 8 characters.")
        return

    credentials = {
        "username": username,
        "password_hash": make_password(password),
    }

    temporary_file = CREDENTIALS_FILE.with_suffix(".json.tmp")

    temporary_file.write_text(
        json.dumps(credentials, indent=2),
        encoding="utf-8",
    )

    temporary_file.replace(CREDENTIALS_FILE)

    # Confirm that the newly written password works
    saved_credentials = json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))

    password_is_valid = check_password(
        password,
        saved_credentials["password_hash"],
    )

    if password_is_valid:
        print("\nAdministrator created successfully.")
        print(f"Username: {username}")
        print(f"Credentials file: {CREDENTIALS_FILE}")
        print("The previous administrator has been replaced.")
    else:
        print("Error: Credential validation failed.")


if __name__ == "__main__":
    create_admin()
