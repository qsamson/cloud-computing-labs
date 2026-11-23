"""IAM policies and Python EC2 boot configuration for Weather Advisor."""

from __future__ import annotations

import base64

from .config import Settings
from .final_boot import build_python_boot_script
from .final_resources import table_arn


def parameter_arn(
    region: str,
    account_id: str,
    parameter_name: str,
) -> str:
    return (
        f"arn:aws:ssm:{region}:{account_id}:"
        f"parameter{parameter_name}"
    )


def sns_topic_arn(
    region: str,
    account_id: str,
    topic_name: str,
) -> str:
    return (
        f"arn:aws:sns:{region}:{account_id}:"
        f"{topic_name}"
    )


def ec2_trust_policy() -> dict:
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


def weather_policy(
    settings: Settings,
    account_id: str,
) -> dict:
    """Weather tier: only its DynamoDB facts table."""
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                ],
                "Resource": table_arn(
                    settings.region,
                    account_id,
                    settings.facts_table,
                ),
            }
        ],
    }


def advisor_policy(
    settings: Settings,
    account_id: str,
) -> dict:
    """Advisor tier: report table, Gemini key, and SES sender."""
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                ],
                "Resource": table_arn(
                    settings.region,
                    account_id,
                    settings.advisor_table,
                ),
            },
            {
                "Effect": "Allow",
                "Action": [
                    "ssm:GetParameter",
                ],
                "Resource": parameter_arn(
                    settings.region,
                    account_id,
                    settings.gemini_param_name,
                ),
            },
            {
                "Effect": "Allow",
                "Action": [
                    "sns:Subscribe",
                    "sns:Publish",
                ],
                "Resource": sns_topic_arn(
                    settings.region,
                    account_id,
                    settings.sns_topic_name,
                ),
            },
        ],
    }


def build_weather_user_data(
    settings: Settings,
    app_js: str,
    package_json: str,
) -> str:
    return build_python_boot_script(
        "weather",
        app_js,
        package_json,
        {
            "PORT": 3000,
            "AWS_REGION": settings.region,
            "NWS_USER_AGENT": (
                f"(ITMO 544 Weather Advisor, "
                f"{settings.contact_email})"
            ),
            "FACTS_TABLE": settings.facts_table,
            "CACHE_SECONDS": settings.cache_seconds,
            "STALE_SECONDS": settings.stale_seconds,
        },
    )


def build_advisor_user_data(
    settings: Settings,
    alb_dns_name: str,
    topic_arn: str,
    app_js: str,
    package_json: str,
) -> str:
    weather_url = (
        f"http://{alb_dns_name}:"
        f"{settings.weather.listener_port}"
    )

    return build_python_boot_script(
        "advisor",
        app_js,
        package_json,
        {
            "PORT": 3000,
            "AWS_REGION": settings.region,
            "WEATHER_URL": weather_url,
            "GEMINI_KEY_PARAM": settings.gemini_param_name,
            "GEMINI_MODEL": settings.gemini_model,
            "KEY_CACHE_SECONDS": settings.key_cache_seconds,
            "ADVISOR_TABLE": settings.advisor_table,
            "REPORT_TTL_SECONDS": settings.report_ttl_seconds,
            "DAILY_GEMINI_CAP": settings.daily_gemini_cap,
            "EMAIL_LIMIT": settings.email_limit,
            "SNS_TOPIC_ARN": topic_arn,
        },
    )


def launch_template_data(
    settings: Settings,
    profile_name: str,
    user_data: str,
    tag_name: str,
) -> dict:
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
