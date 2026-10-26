#!/usr/bin/env python3
"""Tear the stack down: the Python replacement for delete_app_stack.sh."""

import argparse
import logging

from stack.clients import AwsClients
from stack.config import Settings
from stack.runner import delete_stack


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--env",
        default=".env",
        help="path to the settings file",
    )

    parser.add_argument(
        "--keep-foundation",
        action="store_true",
        help="keep the bucket, IAM roles and launch templates",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )

    settings = Settings.from_file(args.env)

    delete_stack(
        settings,
        AwsClients.create(settings.region),
        keep_foundation=args.keep_foundation,
    )


if __name__ == "__main__":
    main()
