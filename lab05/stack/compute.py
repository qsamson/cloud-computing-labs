"""User-data and launch templates."""

from __future__ import annotations

import base64
import logging

from botocore.exceptions import ClientError

from .clients import AwsClients
from .config import Settings, Tier
from .util import error_code


log = logging.getLogger("stack")


def _b64_file(path) -> str:
    return base64.b64encode(
        path.read_bytes()
    ).decode()


def build_user_data(
    settings: Settings,
    tier: Tier,
) -> str:
    """Build the EC2 boot script."""

    app_js = _b64_file(
        tier.app_dir / "app.js"
    )

    package_json = _b64_file(
        tier.app_dir / "package.json"
    )

    return f"""#!/bin/bash
dnf update -y
dnf install -y nodejs
mkdir -p /opt/app
echo "{app_js}" | base64 -d > /opt/app/app.js
echo "{package_json}" | base64 -d > /opt/app/package.json
cd /opt/app
npm install --omit=dev

cat > /etc/systemd/system/{tier.service_name}.service << 'SERVICE'
[Unit]
Description={tier.name.capitalize()} App
After=network.target

[Service]
Environment=BUCKET_NAME={settings.bucket_name}
Environment=AWS_REGION={settings.region}
Environment=PORT={settings.app_port}
WorkingDirectory=/opt/app
ExecStart=/usr/bin/node /opt/app/app.js
Restart=always
User=ec2-user

[Install]
WantedBy=multi-user.target
SERVICE

chown -R ec2-user:ec2-user /opt/app
systemctl daemon-reload
systemctl enable {tier.service_name}.service
systemctl start {tier.service_name}.service
"""


def launch_template_data(
    settings: Settings,
    tier: Tier,
) -> dict:

    user_data = build_user_data(
        settings,
        tier,
    )

    return {
        "ImageId": settings.ami_id,
        "InstanceType": settings.instance_type,
        "KeyName": settings.key_name,
        "SecurityGroupIds": [
            settings.app_sg_id
        ],
        "IamInstanceProfile": {
            "Name": tier.profile_name
        },
        "UserData": base64.b64encode(
            user_data.encode()
        ).decode(),
        "TagSpecifications": [{
            "ResourceType": "instance",
            "Tags": [{
                "Key": "Name",
                "Value": f"{tier.name}-app",
            }],
        }],
    }


def launch_template_exists(
    aws: AwsClients,
    tier: Tier,
) -> bool:

    try:
        aws.ec2.describe_launch_templates(
            LaunchTemplateNames=[
                tier.lt_name
            ]
        )

        return True

    except ClientError as err:
        if (
            error_code(err)
            != "InvalidLaunchTemplateName.NotFoundException"
        ):
            raise

        return False


def ensure_launch_template(
    aws: AwsClients,
    settings: Settings,
    tier: Tier,
) -> int:
    """Create the template or publish a new version."""

    data = launch_template_data(
        settings,
        tier,
    )

    if not launch_template_exists(
        aws,
        tier,
    ):
        aws.ec2.create_launch_template(
            LaunchTemplateName=tier.lt_name,
            LaunchTemplateData=data,
        )

        log.info(
            "Created launch template %s",
            tier.lt_name,
        )

        return 1

    response = (
        aws.ec2.create_launch_template_version(
            LaunchTemplateName=tier.lt_name,
            SourceVersion="1",
            LaunchTemplateData=data,
        )
    )

    version = response[
        "LaunchTemplateVersion"
    ]["VersionNumber"]

    log.info(
        "Template %s exists, published version %s",
        tier.lt_name,
        version,
    )

    return version


def delete_launch_template(
    aws: AwsClients,
    tier: Tier,
) -> None:

    if launch_template_exists(
        aws,
        tier,
    ):
        aws.ec2.delete_launch_template(
            LaunchTemplateName=tier.lt_name
        )

        log.info(
            "Deleted launch template %s",
            tier.lt_name,
        )
