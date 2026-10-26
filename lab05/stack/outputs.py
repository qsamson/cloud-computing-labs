"""Identifiers the create step generates, saved so tests and other tools can find them."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class StackOutputs:
    vpc_id: str
    subnet_a: str
    subnet_b: str
    alb_security_group_id: str
    alb_arn: str
    alb_dns_name: str
    uploader_tg_arn: str
    viewer_tg_arn: str

    def tg_arn(self, tier_name: str) -> str:
        return {
            "uploader": self.uploader_tg_arn,
            "viewer": self.viewer_tg_arn,
        }[tier_name]

    def save(
        self,
        directory: str | Path = ".",
    ) -> None:
        """Write stack_outputs.json and stack_outputs.env."""

        directory = Path(directory)
        data = asdict(self)

        (directory / "stack_outputs.json").write_text(
            json.dumps(data, indent=2) + "\n"
        )

        env_lines = [
            f"{key.upper()}={value}"
            for key, value in data.items()
        ]

        (directory / "stack_outputs.env").write_text(
            "\n".join(env_lines) + "\n"
        )

    @classmethod
    def load(
        cls,
        directory: str | Path = ".",
    ) -> "StackOutputs":

        directory = Path(directory)

        return cls(
            **json.loads(
                (
                    directory
                    / "stack_outputs.json"
                ).read_text()
            )
        )

    @staticmethod
    def remove(
        directory: str | Path = ".",
    ) -> None:

        directory = Path(directory)

        for name in (
            "stack_outputs.json",
            "stack_outputs.env",
        ):
            (
                directory / name
            ).unlink(missing_ok=True)
