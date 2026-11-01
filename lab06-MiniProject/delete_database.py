#!/usr/bin/env python3
"""Delete the Lab 06 PostgreSQL database and supporting resources."""

from stack.clients import AwsClients
from stack.config import Settings
from stack.database import delete_database


def main() -> None:
    """Load configuration and remove database resources."""
    settings = Settings.from_file(".env")
    clients = AwsClients.create(settings.region)

    print(
        "Deleting Lab 06 database "
        "without a final snapshot..."
    )

    delete_database(
        clients,
        settings,
    )

    print(
        "Database, subnet group, security group "
        "and password parameter removed."
    )


if __name__ == "__main__":
    main()
