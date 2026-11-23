"""Unit tests for final-project IAM policies and Python user-data."""

from pathlib import Path

from stack.config import Settings
from stack.weather import (
    advisor_policy,
    build_advisor_user_data,
    build_weather_user_data,
    weather_policy,
)


def settings(tmp_path: Path) -> Settings:
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

        # Legacy Lab06 values remain in Settings
        # but are not used by the final stack.
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

        "FACTS_TABLE": "test-weather-facts",
        "ADVISOR_TABLE": "test-advisor",
        "STALE_SECONDS": "21600",
        "REPORT_TTL_SECONDS": "1800",
        "DAILY_GEMINI_CAP": "50",
        "EMAIL_LIMIT": "5",
        "SES_FROM_EMAIL": "student@example.com",
        "SNS_TOPIC_NAME": "test-weather-email",

        "WEATHER_ROLE_NAME": "weather-role",
        "WEATHER_PROFILE_NAME": "weather-profile",
        "WEATHER_LT_NAME": "weather-lt",
        "WEATHER_TG_NAME": "weather-tg",
        "WEATHER_ASG_NAME": "weather-asg",
        "WEATHER_LISTENER_PORT": "8081",

        "ADVISOR_ROLE_NAME": "advisor-role",
        "ADVISOR_PROFILE_NAME": "advisor-profile",
        "ADVISOR_LT_NAME": "advisor-lt",
        "ADVISOR_TG_NAME": "advisor-tg",
        "ADVISOR_ASG_NAME": "advisor-asg",
        "ADVISOR_LISTENER_PORT": "8080",
    }

    return Settings.from_values(
        values,
        base_dir=tmp_path,
    )


def test_tier_policies_are_least_privilege(tmp_path):
    s = settings(tmp_path)
    account = "123456789012"

    wp = weather_policy(s, account)
    ap = advisor_policy(s, account)

    weather_statement = wp["Statement"][0]

    assert weather_statement["Action"] == [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
    ]

    assert s.facts_table in weather_statement["Resource"]
    assert s.advisor_table not in weather_statement["Resource"]

    advisor_actions = {
        action
        for statement in ap["Statement"]
        for action in statement["Action"]
    }

    assert "dynamodb:GetItem" in advisor_actions
    assert "dynamodb:PutItem" in advisor_actions
    assert "dynamodb:UpdateItem" in advisor_actions
    assert "ssm:GetParameter" in advisor_actions
    assert "sns:Subscribe" in advisor_actions
    assert "sns:Publish" in advisor_actions

    for statement in wp["Statement"] + ap["Statement"]:
        assert statement["Resource"] != "*"


def test_user_data_is_python_not_bash(tmp_path):
    s = settings(tmp_path)

    weather = build_weather_user_data(
        s,
        "console.log('weather');",
        '{"name":"weather"}',
    )

    advisor = build_advisor_user_data(
        s,
        "weather-alb.example.com",
        "arn:aws:sns:us-east-2:123456789012:test-weather-email",
        "console.log('advisor');",
        '{"name":"advisor"}',
    )

    assert weather.startswith("#!/usr/bin/env python3")
    assert advisor.startswith("#!/usr/bin/env python3")

    assert "#!/bin/bash" not in weather
    assert "#!/bin/bash" not in advisor

    assert "super-secret-password" not in weather
    assert "super-secret-password" not in advisor


def test_generated_user_data_is_under_16_kb(tmp_path):
    s = settings(tmp_path)

    weather = build_weather_user_data(
        s,
        "console.log('weather');",
        '{"name":"weather"}',
    )

    advisor = build_advisor_user_data(
        s,
        "alb.example.com",
        "arn:aws:sns:us-east-2:123456789012:test-weather-email",
        "console.log('advisor');",
        '{"name":"advisor"}',
    )

    assert len(weather.encode("utf-8")) < 16 * 1024
    assert len(advisor.encode("utf-8")) < 16 * 1024
