"""Shared fixtures. Unit tests use fake settings, integration tests use your real .env."""

from pathlib import Path

import pytest

from stack.clients import AwsClients
from stack.config import Settings
from stack.outputs import StackOutputs


ROOT = Path(__file__).resolve().parent.parent


FAKE_VALUES = {
    "AWS_REGION": "us-east-2",
    "AMI_ID": "ami-12345678",
    "KEY_NAME": "test-key",
    "INSTANCE_TYPE": "t3.micro",
    "BUCKET_NAME": "unit-test-bucket-12345",
    "APP_SECURITY_GROUP_ID": "sg-placeholder",
    "UPLOADER_ROLE_NAME": "t-uploader-role",
    "UPLOADER_PROFILE_NAME": "t-uploader-profile",
    "UPLOADER_LT_NAME": "t-uploader-lt",
    "UPLOADER_TG_NAME": "t-uploader-tg",
    "UPLOADER_ASG_NAME": "t-uploader-asg",
    "UPLOADER_LISTENER_PORT": "8080",
    "VIEWER_ROLE_NAME": "t-viewer-role",
    "VIEWER_PROFILE_NAME": "t-viewer-profile",
    "VIEWER_LT_NAME": "t-viewer-lt",
    "VIEWER_TG_NAME": "t-viewer-tg",
    "VIEWER_ASG_NAME": "t-viewer-asg",
    "VIEWER_LISTENER_PORT": "8081",
    "ALB_NAME": "t-alb",
    "ALB_SG_NAME": "t-alb-sg",
    "AZ_A": "us-east-2a",
    "AZ_B": "us-east-2b",
    "RECOVERY_SLO_SECONDS": "180",
}


@pytest.fixture
def fake_settings(tmp_path):
    """Settings pointing at two tiny fake app folders, so no real files are needed."""

    for name in ("uploader-app", "viewer-app"):
        folder = tmp_path / name
        folder.mkdir()

        (folder / "app.js").write_text(
            f"console.log('{name}');\n"
        )

        (folder / "package.json").write_text(
            '{"name": "%s"}\n' % name
        )

    return Settings.from_values(
        FAKE_VALUES,
        base_dir=tmp_path,
    )


@pytest.fixture(scope="session")
def settings():
    return Settings.from_file(ROOT / ".env")


@pytest.fixture(scope="session")
def aws(settings):
    return AwsClients.create(settings.region)


@pytest.fixture(scope="session")
def outputs():
    try:
        return StackOutputs.load(ROOT)
    except FileNotFoundError:
        pytest.skip(
            "stack_outputs.json not found. Run python create_stack.py first."
        )
