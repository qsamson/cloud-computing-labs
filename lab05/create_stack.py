#!/usr/bin/env python3
"""Build the whole stack: the Python replacement for create_app_stack.sh."""

import argparse
import logging

from stack.clients import AwsClients
from stack.config import Settings
from stack.runner import create_stack


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env",
        default=".env",
        help="path to the settings file",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )

    settings = Settings.from_file(args.env)

    outputs = create_stack(
        settings,
        AwsClients.create(settings.region),
    )

    outputs.save()

    print()
    print(
        f"Uploader: http://{outputs.alb_dns_name}:"
        f"{settings.uploader.listener_port}/"
    )
    print(
        f"Viewer:   http://{outputs.alb_dns_name}:"
        f"{settings.viewer.listener_port}/"
    )
    print(
        "Give the target groups 1 to 2 minutes to report healthy, "
        "then run: pytest -m integration"
    )


if __name__ == "__main__":
    main()
