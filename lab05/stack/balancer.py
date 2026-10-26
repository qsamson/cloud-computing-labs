"""Target groups, the load balancer, and its listeners."""

from __future__ import annotations

import logging

from botocore.exceptions import ClientError

from .clients import AwsClients
from .config import Settings, Tier
from .util import error_code, ignore_errors


log = logging.getLogger("stack")


HEALTH_CHECK = {
    "HealthCheckProtocol": "HTTP",
    "HealthCheckPath": "/",
    "HealthCheckIntervalSeconds": 10,
    "HealthCheckTimeoutSeconds": 5,
    "HealthyThresholdCount": 2,
    "UnhealthyThresholdCount": 2,
}


def find_target_group(
    aws: AwsClients,
    name: str,
) -> str | None:

    try:
        return aws.elbv2.describe_target_groups(
            Names=[name]
        )["TargetGroups"][0]["TargetGroupArn"]

    except ClientError as err:
        if error_code(err) != "TargetGroupNotFound":
            raise

        return None


def ensure_target_group(
    aws: AwsClients,
    settings: Settings,
    tier: Tier,
    vpc_id: str,
) -> str:

    arn = find_target_group(
        aws,
        tier.tg_name,
    )

    if arn:
        log.info(
            "Target group %s already exists, skipping.",
            tier.tg_name,
        )
        return arn

    response = aws.elbv2.create_target_group(
        Name=tier.tg_name,
        Protocol="HTTP",
        Port=settings.app_port,
        VpcId=vpc_id,
        TargetType="instance",
        **HEALTH_CHECK,
    )

    return response[
        "TargetGroups"
    ][0]["TargetGroupArn"]


def find_load_balancer(
    aws: AwsClients,
    name: str,
) -> dict | None:

    try:
        return aws.elbv2.describe_load_balancers(
            Names=[name]
        )["LoadBalancers"][0]

    except ClientError as err:
        if error_code(err) != "LoadBalancerNotFound":
            raise

        return None


def ensure_load_balancer(
    aws: AwsClients,
    settings: Settings,
    subnets: list[str],
    alb_sg_id: str,
) -> tuple[str, str]:

    lb = find_load_balancer(
        aws,
        settings.alb_name,
    )

    if lb:
        log.info(
            "Load balancer %s already exists, skipping.",
            settings.alb_name,
        )

        return (
            lb["LoadBalancerArn"],
            lb["DNSName"],
        )

    lb = aws.elbv2.create_load_balancer(
        Name=settings.alb_name,
        Subnets=subnets,
        SecurityGroups=[alb_sg_id],
        Scheme="internet-facing",
        Type="application",
    )["LoadBalancers"][0]

    log.info(
        "Waiting for the ALB to become active..."
    )

    aws.elbv2.get_waiter(
        "load_balancer_available"
    ).wait(
        LoadBalancerArns=[
            lb["LoadBalancerArn"]
        ]
    )

    return (
        lb["LoadBalancerArn"],
        lb["DNSName"],
    )


def ensure_listener(
    aws: AwsClients,
    alb_arn: str,
    port: int,
    tg_arn: str,
) -> None:

    existing = aws.elbv2.describe_listeners(
        LoadBalancerArn=alb_arn
    )["Listeners"]

    if any(
        listener["Port"] == port
        for listener in existing
    ):
        log.info(
            "Listener on port %s already exists, skipping.",
            port,
        )
        return

    aws.elbv2.create_listener(
        LoadBalancerArn=alb_arn,
        Protocol="HTTP",
        Port=port,
        DefaultActions=[{
            "Type": "forward",
            "TargetGroupArn": tg_arn,
        }],
    )


def delete_load_balancer(
    aws: AwsClients,
    name: str,
) -> None:

    lb = find_load_balancer(
        aws,
        name,
    )

    if not lb:
        return

    aws.elbv2.delete_load_balancer(
        LoadBalancerArn=lb["LoadBalancerArn"]
    )

    aws.elbv2.get_waiter(
        "load_balancers_deleted"
    ).wait(
        LoadBalancerArns=[
            lb["LoadBalancerArn"]
        ]
    )

    log.info(
        "Deleted load balancer %s",
        name,
    )


def delete_target_group(
    aws: AwsClients,
    name: str,
) -> None:

    arn = find_target_group(
        aws,
        name,
    )

    if arn:
        with ignore_errors(
            "TargetGroupNotFound"
        ):
            aws.elbv2.delete_target_group(
                TargetGroupArn=arn
            )

            log.info(
                "Deleted target group %s",
                name,
            )
