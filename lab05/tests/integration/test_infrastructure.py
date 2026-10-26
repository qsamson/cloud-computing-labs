"""Does the stack you deployed look the way the design says it should?

Run after create_stack.py:     pytest -m integration
"""

import pytest

from tests.helpers import wait_until


pytestmark = pytest.mark.integration


def test_bucket_blocks_all_public_access(aws, settings):
    block = aws.s3.get_public_access_block(
        Bucket=settings.bucket_name
    )["PublicAccessBlockConfiguration"]

    assert all(block.values())


def _decision(
    aws,
    role_name,
    action,
    resource,
):
    role_arn = aws.iam.get_role(
        RoleName=role_name
    )["Role"]["Arn"]

    result = aws.iam.simulate_principal_policy(
        PolicySourceArn=role_arn,
        ActionNames=[action],
        ResourceArns=[resource],
    )

    return result[
        "EvaluationResults"
    ][0]["EvalDecision"]


def test_uploader_role_can_only_write_the_shared_object(
    aws,
    settings,
):
    role = settings.uploader.role_name

    shared = (
        f"arn:aws:s3:::{settings.bucket_name}/shared.txt"
    )

    other = (
        f"arn:aws:s3:::{settings.bucket_name}/other.txt"
    )

    assert (
        _decision(
            aws,
            role,
            "s3:PutObject",
            shared,
        )
        == "allowed"
    )

    assert (
        _decision(
            aws,
            role,
            "s3:PutObject",
            other,
        )
        != "allowed"
    )

    assert (
        _decision(
            aws,
            role,
            "s3:GetObject",
            shared,
        )
        != "allowed"
    )


def test_viewer_role_can_read_but_not_write(
    aws,
    settings,
):
    role = settings.viewer.role_name

    shared = (
        f"arn:aws:s3:::{settings.bucket_name}/shared.txt"
    )

    assert (
        _decision(
            aws,
            role,
            "s3:GetObject",
            shared,
        )
        == "allowed"
    )

    assert (
        _decision(
            aws,
            role,
            "s3:PutObject",
            shared,
        )
        != "allowed"
    )

    assert (
        _decision(
            aws,
            role,
            "s3:DeleteObject",
            shared,
        )
        != "allowed"
    )


def test_load_balancer_is_public_and_spans_two_azs(
    aws,
    settings,
    outputs,
):
    lb = aws.elbv2.describe_load_balancers(
        LoadBalancerArns=[outputs.alb_arn]
    )["LoadBalancers"][0]

    assert lb["State"]["Code"] == "active"
    assert lb["Scheme"] == "internet-facing"

    zones = {
        az["ZoneName"]
        for az in lb["AvailabilityZones"]
    }

    assert zones == {
        settings.az_a,
        settings.az_b,
    }


def test_listeners_forward_to_the_right_target_groups(
    aws,
    settings,
    outputs,
):
    listeners = aws.elbv2.describe_listeners(
        LoadBalancerArn=outputs.alb_arn
    )["Listeners"]

    forwards = {
        item["Port"]:
        item["DefaultActions"][0]["TargetGroupArn"]
        for item in listeners
    }

    for tier in settings.tiers:
        assert (
            forwards[tier.listener_port]
            == outputs.tg_arn(tier.name)
        )


def test_target_groups_use_fast_health_checks(
    aws,
    settings,
    outputs,
):
    for tier in settings.tiers:
        tg = aws.elbv2.describe_target_groups(
            TargetGroupArns=[
                outputs.tg_arn(tier.name)
            ]
        )["TargetGroups"][0]

        assert tg["HealthCheckPath"] == "/"
        assert tg["HealthCheckIntervalSeconds"] == 10
        assert tg["HealthyThresholdCount"] == 2


def test_auto_scaling_groups_are_configured_for_recovery(
    aws,
    settings,
    outputs,
):
    for tier in settings.tiers:
        group = (
            aws.autoscaling.describe_auto_scaling_groups(
                AutoScalingGroupNames=[
                    tier.asg_name
                ]
            )["AutoScalingGroups"][0]
        )

        assert group["HealthCheckType"] == "ELB"
        assert group["DesiredCapacity"] == 1

        assert set(
            group[
                "VPCZoneIdentifier"
            ].split(",")
        ) == {
            outputs.subnet_a,
            outputs.subnet_b,
        }

        assert (
            outputs.tg_arn(tier.name)
            in group["TargetGroupARNs"]
        )


def test_app_port_is_reachable_only_from_the_load_balancer(
    aws,
    settings,
    outputs,
):
    group = aws.ec2.describe_security_groups(
        GroupIds=[settings.app_sg_id]
    )["SecurityGroups"][0]

    rules = [
        permission
        for permission in group[
            "IpPermissions"
        ]
        if permission.get("FromPort")
        == settings.app_port
    ]

    assert rules, "port 3000 rule missing"

    for rule in rules:
        assert rule["IpRanges"] == [], (
            "port 3000 must not be open "
            "to a CIDR range"
        )

        assert [
            pair["GroupId"]
            for pair in rule[
                "UserIdGroupPairs"
            ]
        ] == [
            outputs.alb_security_group_id
        ]


def test_every_target_becomes_healthy(
    aws,
    settings,
    outputs,
):
    def all_healthy():
        for tier in settings.tiers:
            targets = (
                aws.elbv2.describe_target_health(
                    TargetGroupArn=outputs.tg_arn(
                        tier.name
                    )
                )[
                    "TargetHealthDescriptions"
                ]
            )

            if (
                not targets
                or any(
                    target[
                        "TargetHealth"
                    ]["State"]
                    != "healthy"
                    for target in targets
                )
            ):
                return False

        return True

    assert wait_until(
        all_healthy,
        timeout=420,
        interval=15,
    ), "targets never became healthy"
