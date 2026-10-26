import base64
import re

from stack.compute import build_user_data, launch_template_data


def test_app_files_are_embedded_and_round_trip(fake_settings):
    tier = fake_settings.uploader
    script = build_user_data(fake_settings, tier)

    encoded = re.findall(
        r'echo "([A-Za-z0-9+/=]+)" \| base64 -d',
        script,
    )

    decoded = [
        base64.b64decode(item).decode()
        for item in encoded
    ]

    assert decoded[0] == (
        tier.app_dir / "app.js"
    ).read_text()

    assert decoded[1] == (
        tier.app_dir / "package.json"
    ).read_text()


def test_service_gets_the_right_environment(fake_settings):
    script = build_user_data(
        fake_settings,
        fake_settings.viewer,
    )

    assert (
        "Environment=BUCKET_NAME=unit-test-bucket-12345"
        in script
    )

    assert (
        "Environment=AWS_REGION=us-east-2"
        in script
    )

    assert "systemctl start viewer.service" in script
    assert "Restart=always" in script


def test_script_starts_with_a_shebang(fake_settings):
    assert build_user_data(
        fake_settings,
        fake_settings.uploader,
    ).startswith("#!/bin/bash\n")


def test_launch_template_user_data_is_base64_of_the_script(
    fake_settings,
):
    data = launch_template_data(
        fake_settings,
        fake_settings.viewer,
    )

    decoded = base64.b64decode(
        data["UserData"]
    ).decode()

    assert decoded == build_user_data(
        fake_settings,
        fake_settings.viewer,
    )

    assert data["IamInstanceProfile"] == {
        "Name": "t-viewer-profile"
    }

    assert data["SecurityGroupIds"] == [
        "sg-placeholder"
    ]
