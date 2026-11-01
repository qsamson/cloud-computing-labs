"""Unit tests for Lab 06 IAM policy and user-data helpers."""

from pathlib import Path

from stack.config import Settings
from stack.weather import (
    advisor_policy,
    build_advisor_user_data,
    build_weather_user_data,
    weather_policy,
)


def settings(tmp_path: Path) -> Settings:
    """Return a complete Lab 06 test configuration."""
    values = {
        "AWS_REGION": "us-east-2",
        "AMI_ID": "ami-test",
        "KEY_NAME": "test-key",
        "INSTANCE_TYPE": "t3.micro",
        "APP_SECURITY_GROUP_ID": "sg-test",
        "AZ_A": "us-east-2a",
        "AZ_B": "us-east-2b",
        "ALB_NAME": "weather-alb",
        "ALB_SG_NAME": "weather-alb-sg",
        "DB_INSTANCE_ID": "weather-db",
        "DB_INSTANCE_CLASS": "db.t4g.micro",
        "DB_NAME": "weather",
        "DB_USER": "weatherapp",
        "DB_SG_NAME": "weather-db-sg",
        "DB_SUBNET_GROUP_NAME": "weather-db-subnets",
        "DB_PASSWORD_PARAM": "/lab/db-password",
        "CACHE_SECONDS": "600",
        "GEMINI_PARAM_NAME": "/lab/gemini-api-key",
        "GEMINI_MODEL": "gemini-test",
        "KEY_CACHE_SECONDS": "60",
        "CONTACT_EMAIL": "student@example.com",
        "WEATHER_ROLE_NAME": "weather-role",
        "WEATHER_PROFILE_NAME": "weather-profile",
        "WEATHER_LT_NAME": "weather-lt",
        "WEATHER_TG_NAME": "weather-tg",
        "WEATHER_ASG_NAME": "weather-asg",
        "WEATHER_LISTENER_PORT": "8080",
        "ADVISOR_ROLE_NAME": "advisor-role",
        "ADVISOR_PROFILE_NAME": "advisor-profile",
        "ADVISOR_LT_NAME": "advisor-lt",
        "ADVISOR_TG_NAME": "advisor-tg",
        "ADVISOR_ASG_NAME": "advisor-asg",
        "ADVISOR_LISTENER_PORT": "8081",
    }

    return Settings.from_values(
        values,
        base_dir=tmp_path,
    )


def test_each_role_policy_mentions_only_its_secret(tmp_path):
    """Each tier may read exactly one SSM parameter."""
    s = settings(tmp_path)
    account = "123456789012"

    wp = weather_policy(s, account)
    ap = advisor_policy(s, account)

    weather_resource = wp["Statement"][0]["Resource"]
    advisor_resource = ap["Statement"][0]["Resource"]

    assert wp["Statement"][0]["Action"] == [
        "ssm:GetParameter"
    ]
    assert ap["Statement"][0]["Action"] == [
        "ssm:GetParameter"
    ]

    assert s.db_password_param in weather_resource
    assert s.gemini_param_name not in weather_resource

    assert s.gemini_param_name in advisor_resource
    assert s.db_password_param not in advisor_resource


def test_user_data_contains_required_addresses_but_no_password(
    tmp_path,
):
    """Advisor gets ALB DNS and weather gets DB host, never DB password."""
    s = settings(tmp_path)

    weather = build_weather_user_data(
        s,
        "database.example.internal",
        "console.log('weather');",
        '{"name":"weather"}',
    )

    advisor = build_advisor_user_data(
        s,
        "weather-alb.example.com",
        "console.log('advisor');",
        '{"name":"advisor"}',
    )

    assert "database.example.internal" in weather
    assert s.db_password_param in weather

    # The parameter NAME is allowed in user-data.
    # The secret VALUE must never appear.
    assert "super-secret-password" not in weather

    assert "weather-alb.example.com" in advisor
    assert (
        f":{s.weather.listener_port}"
        in advisor
    )


def test_generated_user_data_is_under_16_kb(tmp_path):
    """Both launch-template user-data scripts stay below EC2's limit."""
    s = settings(tmp_path)

    weather = build_weather_user_data(
        s,
        "database.internal",
        "console.log('weather');",
        '{"name":"weather"}',
    )

    advisor = build_advisor_user_data(
        s,
        "alb.example.com",
        "console.log('advisor');",
        '{"name":"advisor"}',
    )

    assert len(weather.encode("utf-8")) < 16 * 1024
    assert len(advisor.encode("utf-8")) < 16 * 1024
