"""Settings for the stack, read from the same .env file the bash scripts use."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


REQUIRED_KEYS = [
    "AWS_REGION",
    "AMI_ID",
    "KEY_NAME",
    "INSTANCE_TYPE",
    "BUCKET_NAME",
    "APP_SECURITY_GROUP_ID",
    "UPLOADER_ROLE_NAME",
    "UPLOADER_PROFILE_NAME",
    "UPLOADER_LT_NAME",
    "UPLOADER_TG_NAME",
    "UPLOADER_ASG_NAME",
    "UPLOADER_LISTENER_PORT",
    "VIEWER_ROLE_NAME",
    "VIEWER_PROFILE_NAME",
    "VIEWER_LT_NAME",
    "VIEWER_TG_NAME",
    "VIEWER_ASG_NAME",
    "VIEWER_LISTENER_PORT",
    "ALB_NAME",
    "ALB_SG_NAME",
    "AZ_A",
    "AZ_B",
    "RECOVERY_SLO_SECONDS",
]


class ConfigError(Exception):
    """Raised when .env is missing keys, with a message that says which."""


def load_dotenv(path: str | Path = ".env") -> dict[str, str]:
    """Read KEY=VALUE lines into a dict. Comments and blank lines are skipped."""

    values: dict[str, str] = {}

    for raw in Path(path).read_text().splitlines():
        line = raw.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, _, value = line.partition("=")

        values[key.strip()] = (
            value.strip()
            .strip('"')
            .strip("'")
        )

    return values


@dataclass(frozen=True)
class Tier:
    name: str
    role_name: str
    profile_name: str
    lt_name: str
    tg_name: str
    asg_name: str
    listener_port: int
    app_dir: Path

    @property
    def policy_name(self) -> str:
        return f"{self.role_name}-policy"

    @property
    def service_name(self) -> str:
        return self.name


@dataclass(frozen=True)
class Settings:
    region: str
    ami_id: str
    key_name: str
    instance_type: str
    bucket_name: str
    app_sg_id: str
    alb_name: str
    alb_sg_name: str
    az_a: str
    az_b: str
    recovery_slo_seconds: int
    uploader: Tier
    viewer: Tier
    app_port: int = 3000

    @property
    def tiers(self) -> tuple[Tier, Tier]:
        return (
            self.uploader,
            self.viewer,
        )

    def tier(self, name: str) -> Tier:
        return {
            "uploader": self.uploader,
            "viewer": self.viewer,
        }[name]

    @classmethod
    def from_values(
        cls,
        v: dict[str, str],
        base_dir: str | Path = ".",
    ) -> "Settings":

        missing = [
            key
            for key in REQUIRED_KEYS
            if not v.get(key)
        ]

        if missing:
            raise ConfigError(
                "Missing keys in .env: "
                + ", ".join(missing)
            )

        base = Path(base_dir)

        def tier(prefix: str) -> Tier:
            return Tier(
                name=prefix.lower(),
                role_name=v[f"{prefix}_ROLE_NAME"],
                profile_name=v[f"{prefix}_PROFILE_NAME"],
                lt_name=v[f"{prefix}_LT_NAME"],
                tg_name=v[f"{prefix}_TG_NAME"],
                asg_name=v[f"{prefix}_ASG_NAME"],
                listener_port=int(
                    v[f"{prefix}_LISTENER_PORT"]
                ),
                app_dir=base / f"{prefix.lower()}-app",
            )

        return cls(
            region=v["AWS_REGION"],
            ami_id=v["AMI_ID"],
            key_name=v["KEY_NAME"],
            instance_type=v["INSTANCE_TYPE"],
            bucket_name=v["BUCKET_NAME"],
            app_sg_id=v["APP_SECURITY_GROUP_ID"],
            alb_name=v["ALB_NAME"],
            alb_sg_name=v["ALB_SG_NAME"],
            az_a=v["AZ_A"],
            az_b=v["AZ_B"],
            recovery_slo_seconds=int(
                v["RECOVERY_SLO_SECONDS"]
            ),
            uploader=tier("UPLOADER"),
            viewer=tier("VIEWER"),
        )

    @classmethod
    def from_file(
        cls,
        path: str | Path = ".env",
    ) -> "Settings":

        path = Path(path)

        return cls.from_values(
            load_dotenv(path),
            base_dir=path.resolve().parent,
        )
