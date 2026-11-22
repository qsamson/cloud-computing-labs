"""Chaos tests for the real Lab 06 Weather Advisor stack."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

import boto3
import pytest

from stack.config import Settings, load_dotenv


pytestmark = pytest.mark.chaos


def http_get(url: str, timeout: int = 10):
    """Return HTTP status and parsed response."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            status = response.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        status = exc.code
    except Exception:
        return 0, {}

    try:
        return status, json.loads(body)
    except json.JSONDecodeError:
        return status, body


@pytest.fixture(scope="module")
def settings():
    return Settings.from_file(".env")


@pytest.fixture(scope="module")
def outputs():
    return {
        **load_dotenv("stack_outputs.env"),
        **load_dotenv("db_outputs.env"),
    }


@pytest.fixture(scope="module")
def aws(settings):
    session = boto3.session.Session(
        region_name=settings.region
    )
    return {
        "ec2": session.client("ec2"),
        "autoscaling": session.client("autoscaling"),
    }


def weather_instance_id(ec2):
    """Return the running weather EC2 instance ID."""
    result = ec2.describe_instances(
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

    for reservation in result["Reservations"]:
        for instance in reservation["Instances"]:
            return instance["InstanceId"]

    raise RuntimeError("No running weather instance found.")


def test_database_failure_degrades_gracefully(
    settings,
    outputs,
    aws,
):
    """Weather still works when PostgreSQL becomes unreachable."""
    ec2 = aws["ec2"]
    db_sg = outputs["DB_SECURITY_GROUP_ID"]

    base = (
        f"http://{outputs['ALB_DNS_NAME']}:"
        f"{settings.weather.listener_port}"
    )

    try:
        ec2.revoke_security_group_ingress(
            GroupId=db_sg,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 5432,
                    "ToPort": 5432,
                    "UserIdGroupPairs": [
                        {
                            "GroupId": settings.app_sg_id
                        }
                    ],
                }
            ],
        )

        instance_id = weather_instance_id(ec2)

        # Reboot forces systemd and database connections to restart.
        ec2.reboot_instances(
            InstanceIds=[instance_id]
        )

        deadline = time.time() + 180
        result = None

        while time.time() < deadline:
            status, body = http_get(
                f"{base}/weather?zip=10001",
                timeout=10,
            )

            if (
                status == 200
                and isinstance(body, dict)
                and body.get("cache") == "unavailable"
            ):
                result = body
                break

            time.sleep(10)

        assert result is not None

    finally:
        try:
            ec2.authorize_security_group_ingress(
                GroupId=db_sg,
                IpPermissions=[
                    {
                        "IpProtocol": "tcp",
                        "FromPort": 5432,
                        "ToPort": 5432,
                        "UserIdGroupPairs": [
                            {
                                "GroupId": settings.app_sg_id
                            }
                        ],
                    }
                ],
            )
        except Exception:
            pass

    time.sleep(35)

    status, body = http_get(
        f"{base}/weather?zip=10001",
        timeout=20,
    )

    assert status == 200
    assert body.get("cache") in {
        "miss",
        "hit",
    }


def test_weather_instance_failure_and_recovery(
    settings,
    outputs,
    aws,
):
    """Advisor returns 502 during weather outage and weather recovers."""
    ec2 = aws["ec2"]
    autoscaling = aws["autoscaling"]

    weather_url = (
        f"http://{outputs['ALB_DNS_NAME']}:"
        f"{settings.weather.listener_port}"
        "/weather?zip=60616"
    )

    advisor_url = (
        f"http://{outputs['ALB_DNS_NAME']}:"
        f"{settings.advisor.listener_port}"
        "/advice?zip=33101"
    )

    group = autoscaling.describe_auto_scaling_groups(
        AutoScalingGroupNames=[
            settings.weather.asg_name
        ]
    )["AutoScalingGroups"][0]

    victim = group["Instances"][0]["InstanceId"]

    autoscaling.terminate_instance_in_auto_scaling_group(
        InstanceId=victim,
        ShouldDecrementDesiredCapacity=False,
    )

    start = time.time()
    saw_502 = False

    while time.time() - start < 120:
        status, body = http_get(
            advisor_url,
            timeout=10,
        )

        if (
            status == 502
            and isinstance(body, dict)
            and body.get("error")
            == "weather_service_unavailable"
        ):
            saw_502 = True
            break

        time.sleep(5)

    assert saw_502

    recovered = False

    while time.time() - start < 300:
        status, _ = http_get(
            weather_url,
            timeout=10,
        )

        if status == 200:
            recovered = True
            break

        time.sleep(10)

    recovery_seconds = time.time() - start

    print(
        f"Weather service recovered after "
        f"{recovery_seconds:.1f} seconds"
    )

    assert recovered
    assert recovery_seconds <= 300
