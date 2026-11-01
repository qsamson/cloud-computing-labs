#!/usr/bin/env python3
"""Create the Lab 06 private PostgreSQL database."""

from stack.clients import AwsClients
from stack.config import Settings
from stack.database import create_database


def main() -> None:
    """Load configuration and create the database resources."""
    settings = Settings.from_file(".env")
    clients = AwsClients.create(settings.region)

    print("Creating Lab 06 database resources...")

    outputs = create_database(
        clients,
        settings,
    )

    print("Database is available.")
    print("Database endpoint:", outputs["DB_HOST"])
    print(
        "Backups are disabled and the database "
        "is private, encrypted and single-AZ."
    )


if __name__ == "__main__":
    main()
