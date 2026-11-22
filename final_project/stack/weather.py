"""Helpers for Lab 06 IAM policies and EC2 user-data."""

from __future__ import annotations

import base64
import json

from .config import Settings


def parameter_arn(region: str, account_id: str, parameter_name: str) -> str:
    """Return the ARN for one SSM parameter."""
    return (
        f"arn:aws:ssm:{region}:{account_id}:"
        f"parameter{parameter_name}"
    )


def ec2_trust_policy() -> dict:
    """Return the EC2 assume-role trust policy."""
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": "ec2.amazonaws.com"
                },
                "Action": "sts:AssumeRole",
            }
        ],
    }


def secret_read_policy(parameter_arn_value: str) -> dict:
    """Allow GetParameter on exactly one SecureString parameter."""
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["ssm:GetParameter"],
                "Resource": parameter_arn_value,
            }
        ],
    }


def weather_policy(
    settings: Settings,
    account_id: str,
) -> dict:
    """Return the weather tier's DB-password-only policy."""
    return secret_read_policy(
        parameter_arn(
            settings.region,
            account_id,
            settings.db_password_param,
        )
    )


def advisor_policy(
    settings: Settings,
    account_id: str,
) -> dict:
    """Return the advisor tier's Gemini-key-only policy."""
    return secret_read_policy(
        parameter_arn(
            settings.region,
            account_id,
            settings.gemini_param_name,
        )
    )


def _encode(text: str) -> str:
    """Base64 encode application content for user-data."""
    return base64.b64encode(
        text.encode("utf-8")
    ).decode("ascii")


def build_weather_user_data(
    settings: Settings,
    db_host: str,
    app_js: str,
    package_json: str,
) -> str:
    """Build weather EC2 user-data without including any secret."""
    app_b64 = _encode(app_js)
    package_b64 = _encode(package_json)

    return f"""#!/bin/bash
set -e

dnf update -y
dnf install -y nodejs postgresql15

mkdir -p /opt/app

curl -sS -o /opt/app/rds-ca.pem \
https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem

echo "{app_b64}" | base64 -d > /opt/app/app.js
echo "{package_b64}" | base64 -d > /opt/app/package.json

cd /opt/app
npm install --omit=dev

cat > /etc/systemd/system/weather.service << 'SERVICE'
[Unit]
Description=Weather Advisor weather service
After=network.target

[Service]
Environment=PORT=3000
Environment=AWS_REGION={settings.region}
Environment="NWS_USER_AGENT=(itmo-444-544 weather lab, {settings.contact_email})"
Environment=DB_HOST={db_host}
Environment=DB_NAME={settings.db_name}
Environment=DB_USER={settings.db_user}
Environment=DB_PASSWORD_PARAM={settings.db_password_param}
Environment=CACHE_SECONDS={settings.cache_seconds}
WorkingDirectory=/opt/app
ExecStart=/usr/bin/node /opt/app/app.js
Restart=always
User=ec2-user

[Install]
WantedBy=multi-user.target
SERVICE

chown -R ec2-user:ec2-user /opt/app
systemctl daemon-reload
systemctl enable weather.service
systemctl start weather.service
"""


def build_advisor_user_data(
    settings: Settings,
    alb_dns_name: str,
    app_js: str,
    package_json: str,
) -> str:
    """Build advisor EC2 user-data using the ALB weather endpoint."""
    app_b64 = _encode(app_js)
    package_b64 = _encode(package_json)

    weather_url = (
        f"http://{alb_dns_name}:"
        f"{settings.weather.listener_port}"
    )

    return f"""#!/bin/bash
set -e

dnf update -y
dnf install -y nodejs

mkdir -p /opt/app

echo "{app_b64}" | base64 -d > /opt/app/app.js
echo "{package_b64}" | base64 -d > /opt/app/package.json

cd /opt/app
npm install --omit=dev

cat > /etc/systemd/system/advisor.service << 'SERVICE'
[Unit]
Description=Weather Advisor advice service
After=network.target

[Service]
Environment=PORT=3000
Environment=AWS_REGION={settings.region}
Environment=WEATHER_URL={weather_url}
Environment=GEMINI_KEY_PARAM={settings.gemini_param_name}
Environment=GEMINI_MODEL={settings.gemini_model}
Environment=KEY_CACHE_SECONDS={settings.key_cache_seconds}
WorkingDirectory=/opt/app
ExecStart=/usr/bin/node /opt/app/app.js
Restart=always
User=ec2-user

[Install]
WantedBy=multi-user.target
SERVICE

chown -R ec2-user:ec2-user /opt/app
systemctl daemon-reload
systemctl enable advisor.service
systemctl start advisor.service
"""


def launch_template_data(
    settings: Settings,
    profile_name: str,
    user_data: str,
    tag_name: str,
) -> dict:
    """Build EC2 launch-template data for one application tier."""
    return {
        "ImageId": settings.ami_id,
        "InstanceType": settings.instance_type,
        "KeyName": settings.key_name,
        "SecurityGroupIds": [
            settings.app_sg_id
        ],
        "IamInstanceProfile": {
            "Name": profile_name
        },
        "UserData": base64.b64encode(
            user_data.encode("utf-8")
        ).decode("ascii"),
        "TagSpecifications": [
            {
                "ResourceType": "instance",
                "Tags": [
                    {
                        "Key": "Name",
                        "Value": tag_name,
                    }
                ],
            }
        ],
    }
