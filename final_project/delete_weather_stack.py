#!/usr/bin/env python3
"""Delete the final Weather Advisor AWS stack."""

from stack.clients import AwsClients
from stack.config import Settings
from stack.final_stack import delete_final_stack


def main() -> None:
    settings = Settings.from_file(".env")
    clients = AwsClients.create(settings.region)

    print("Deleting final Weather Advisor stack...")

    delete_final_stack(
        clients,
        settings,
    )

    print("Final Weather Advisor stack removed.")


if __name__ == "__main__":
    main()
