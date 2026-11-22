"""Integration tests for the real Lab 06 AWS stack."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from pathlib import Path

import boto3
import pytest

from stack.config import Settings, load_dotenv


pytestmark = pytest.mark.integration


def http_get(url: str, timeout: int = 30):
    """Return HTTP status and parsed JSON/text."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            status = response.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        status = exc.code

    try:
        return status, json.loads(body)
    except json.JSONDecodeError:
        return status, body


@pytest.fixture(scope="module")
def settings():
    """Load the real Lab 06 configuration."""
    return Settings.from_file(".env")


@pytest.fixture(scope="module")
def outputs():
    """Load stack and database outputs."""
    stack = load_dotenv("stack_outputs.env")
    db = load_dotenv("db_outputs.env")
    return {**stack, **db}


@pytest.fixture(scope="module")
def clients(settings):
    """Create real AWS clients."""
    session = boto3.session.Session(
        region_name=settings.region
    )

    return {
        "elbv2": session.client("elbv2"),
        "ec2": session.client("ec2"),
        "iam": session.client("iam"),
    }


def test_both_target_groups_are_healthy(
    clients,
    outputs,
):
    """Both application tiers must be healthy behind the ALB."""
    for key in (
        "WEATHER_TG_ARN",
        "ADVISOR_TG_ARN",
    ):
        result = clients["elbv2"].describe_target_health(
            TargetGroupArn=outputs[key]
        )

        states = [
            item["TargetHealth"]["State"]
            for item in result["TargetHealthDescriptions"]
        ]

        assert states
        assert all(state == "healthy" for state in states)


def test_weather_miss_then_hit_and_history(
    settings,
    outputs,
):
    """The first lookup is stored and the repeat lookup uses PostgreSQL."""
    base = (
        f"http://{outputs['ALB_DNS_NAME']}:"
        f"{settings.weather.listener_port}"
    )

    history_status, existing = http_get(
        f"{base}/history"
    )

    used = {
        row["zip"].strip()
        for row in existing.get("lookups", [])
    } if history_status == 200 else set()

    candidates = [
        "98101",
        "94105",
        "02108",
        "30303",
        "80202",
        "19103",
        "20001",
    ]

    zip_code = next(
        z for z in candidates
        if z not in used
    )

    status1, first = http_get(
        f"{base}/weather?zip={zip_code}"
    )

    assert status1 == 200
    assert "forecast" in first
    assert first["cache"] == "miss"

    status2, second = http_get(
        f"{base}/weather?zip={zip_code}"
    )

    assert status2 == 200
    assert second["cache"] == "hit"

    history_status, history = http_get(
        f"{base}/history"
    )

    assert history_status == 200
    assert history["count"] >= 1
    assert any(
        row["zip"].strip() == zip_code
        for row in history["lookups"]
    )


def test_weather_zip_errors(
    settings,
    outputs,
):
    """Bad syntax returns 400 and an unknown ZIP returns 404."""
    base = (
        f"http://{outputs['ALB_DNS_NAME']}:"
        f"{settings.weather.listener_port}"
    )

    status, _ = http_get(
        f"{base}/weather?zip=abc"
    )
    assert status == 400

    status, _ = http_get(
        f"{base}/weather?zip=00000"
    )
    assert status == 404


def test_advisor_returns_advice(
    settings,
    outputs,
):
    """The advisor returns a useful answer through the ALB."""
    url = (
        f"http://{outputs['ALB_DNS_NAME']}:"
        f"{settings.advisor.listener_port}"
        "/advice?zip=60616"
    )

    status, body = http_get(
        url,
        timeout=40,
    )

    assert status == 200
    assert body.get("advice")
    assert body.get("source") in {
        "gemini",
        "fallback",
    }


def test_app_instance_not_reachable_directly(
    settings,
    outputs,
    clients,
):
    """Port 3000 is not exposed directly from an app instance."""
    result = clients["ec2"].describe_instances(
        Filters=[
            {
                "Name": "tag:Name",
                "Values": ["weather-app"],
            },
            {
                "Name": "instance-state-name",
                "Values": ["running"],
            },
        ]
    )

    instances = [
        instance
        for reservation in result["Reservations"]
        for instance in reservation["Instances"]
    ]

    assert instances

    public_ip = instances[0].get(
        "PublicIpAddress"
    )

    # No public IP is already proof that it cannot be reached directly.
    if not public_ip:
        return

    try:
        sock = socket.create_connection(
            (public_ip, 3000),
            timeout=4,
        )
    except OSError:
        return

    sock.close()
    pytest.fail(
        "Weather instance accepted a direct TCP connection on port 3000."
    )


def test_database_not_reachable_from_test_machine(
    outputs,
):
    """The private PostgreSQL endpoint is not reachable from this machine."""
    host = outputs["DB_HOST"]

    try:
        sock = socket.create_connection(
            (host, 5432),
            timeout=4,
        )
    except OSError:
        return

    sock.close()
    pytest.fail(
        "The database unexpectedly accepted a direct connection."
    )


def test_each_role_can_read_only_its_secret(
    settings,
    clients,
):
    """IAM simulator proves each tier can read only its own SSM secret."""
    sts = boto3.client(
        "sts",
        region_name=settings.region,
    )

    account = sts.get_caller_identity()["Account"]

    db_arn = (
        f"arn:aws:ssm:{settings.region}:{account}:"
        f"parameter{settings.db_password_param}"
    )

    gemini_arn = (
        f"arn:aws:ssm:{settings.region}:{account}:"
        f"parameter{settings.gemini_param_name}"
    )

    cases = [
        (
            settings.weather.role_name,
            db_arn,
            "allowed",
        ),
        (
            settings.weather.role_name,
            gemini_arn,
            "implicitDeny",
        ),
        (
            settings.advisor.role_name,
            gemini_arn,
            "allowed",
        ),
        (
            settings.advisor.role_name,
            db_arn,
            "implicitDeny",
        ),
    ]

    for role_name, resource, expected in cases:
        role = clients["iam"].get_role(
            RoleName=role_name
        )["Role"]

        result = clients["iam"].simulate_principal_policy(
            PolicySourceArn=role["Arn"],
            ActionNames=["ssm:GetParameter"],
            ResourceArns=[resource],
        )

        actual = result[
            "EvaluationResults"
        ][0]["EvalDecision"]

        assert actual == expected
