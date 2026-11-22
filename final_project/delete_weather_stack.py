#!/usr/bin/env python3
"""Delete the Lab 06 Weather Advisor AWS stack."""

from stack.clients import AwsClients
from stack.config import Settings
from stack.weather_stack import delete_weather_stack


def main() -> None:
    """Delete all Weather Advisor EC2, ALB and IAM resources."""
    settings = Settings.from_file(".env")
    clients = AwsClients.create(settings.region)

    print("Deleting Weather Advisor stack...")

    delete_weather_stack(
        clients,
        settings,
    )

    print("Weather Advisor stack removed.")


if __name__ == "__main__":
    main()
