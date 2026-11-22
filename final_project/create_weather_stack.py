#!/usr/bin/env python3
"""Create the Lab 06 Weather Advisor AWS stack."""

from getpass import getpass

from botocore.exceptions import ClientError

from stack.clients import AwsClients
from stack.config import Settings
from stack.database import error_code
from stack.weather_stack import create_weather_stack


def main() -> None:
    """Create all Lab 06 weather/advisor resources."""
    settings = Settings.from_file(".env")
    clients = AwsClients.create(settings.region)

    gemini_key = None

    try:
        clients.ssm.get_parameter(
            Name=settings.gemini_param_name
        )
    except ClientError as exc:
        if error_code(exc) != "ParameterNotFound":
            raise

        gemini_key = getpass(
            "Gemini API key: "
        ).strip()

        if not gemini_key:
            raise RuntimeError(
                "Gemini API key cannot be empty."
            )

    print("Creating Weather Advisor stack...")

    outputs = create_weather_stack(
        clients,
        settings,
        gemini_key=gemini_key,
    )

    dns = outputs["ALB_DNS_NAME"]

    print()
    print("Stack created.")
    print(
        "Weather:",
        f"http://{dns}:{settings.weather.listener_port}/weather?zip=60616",
    )
    print(
        "Advisor:",
        f"http://{dns}:{settings.advisor.listener_port}/",
    )


if __name__ == "__main__":
    main()
