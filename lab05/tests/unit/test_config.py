import pytest

from stack.config import ConfigError, Settings, load_dotenv
from tests.conftest import FAKE_VALUES


def test_load_dotenv_skips_comments_and_blank_lines(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "# a comment\n\nAWS_REGION=us-east-2\nKEY_NAME='quoted'\n"
    )

    assert load_dotenv(env) == {
        "AWS_REGION": "us-east-2",
        "KEY_NAME": "quoted",
    }


def test_missing_keys_are_named_in_the_error():
    values = dict(FAKE_VALUES)
    del values["ALB_NAME"]
    del values["AZ_B"]

    with pytest.raises(ConfigError) as err:
        Settings.from_values(values)

    assert "ALB_NAME" in str(err.value)
    assert "AZ_B" in str(err.value)


def test_tiers_are_built_from_prefixed_keys(fake_settings):
    up, vw = fake_settings.tiers

    assert (
        up.name,
        up.listener_port,
        up.asg_name,
    ) == (
        "uploader",
        8080,
        "t-uploader-asg",
    )

    assert (
        vw.name,
        vw.listener_port,
        vw.lt_name,
    ) == (
        "viewer",
        8081,
        "t-viewer-lt",
    )

    assert up.policy_name == "t-uploader-role-policy"
    assert up.app_dir.name == "uploader-app"


def test_ports_are_integers(fake_settings):
    assert isinstance(
        fake_settings.uploader.listener_port,
        int,
    )

    assert isinstance(
        fake_settings.recovery_slo_seconds,
        int,
    )
