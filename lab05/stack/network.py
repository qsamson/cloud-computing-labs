"""Default VPC, subnets, and the two security groups."""

from __future__ import annotations

import logging
import time

from .clients import AwsClients
from .config import Settings
from .util import ignore_errors, retry_on


log = logging.getLogger("stack")


class StackError(Exception):
    """Something the lab cannot continue without."""


def default_vpc_id(aws: AwsClients) -> str:
    vpcs = aws.ec2.describe_vpcs(
        Filters=[
            {
                "Name": "isDefault",
                "Values": ["true"],
            }
        ]
    )["Vpcs"]

    if not vpcs:
        raise StackError(
            "No default VPC found in this region."
        )

    return vpcs[0]["VpcId"]


def subnet_in_az(
    aws: AwsClients,
    vpc_id: str,
    az: str,
) -> str:

    subnets = aws.ec2.describe_subnets(
        Filters=[
            {
                "Name": "vpc-id",
                "Values": [vpc_id],
            },
            {
                "Name": "availability-zone",
                "Values": [az],
            },
        ]
    )["Subnets"]

    if not subnets:
        raise StackError(
            f"The default VPC has no subnet in {az}."
        )

    return subnets[0]["SubnetId"]


def _cidr_rule(
    port: int,
    cidr: str = "0.0.0.0/0",
) -> list[dict]:

    return [{
        "IpProtocol": "tcp",
        "FromPort": port,
        "ToPort": port,
        "IpRanges": [
            {"CidrIp": cidr}
        ],
    }]


def _group_rule(
    port: int,
    group_id: str,
) -> list[dict]:

    return [{
        "IpProtocol": "tcp",
        "FromPort": port,
        "ToPort": port,
        "UserIdGroupPairs": [
            {"GroupId": group_id}
        ],
    }]


def find_security_group(
    aws: AwsClients,
    name: str,
    vpc_id: str,
) -> str | None:

    groups = aws.ec2.describe_security_groups(
        Filters=[
            {
                "Name": "group-name",
                "Values": [name],
            },
            {
                "Name": "vpc-id",
                "Values": [vpc_id],
            },
        ]
    )["SecurityGroups"]

    return (
        groups[0]["GroupId"]
        if groups
        else None
    )


def ensure_alb_security_group(
    aws: AwsClients,
    settings: Settings,
    vpc_id: str,
) -> str:

    group_id = find_security_group(
        aws,
        settings.alb_sg_name,
        vpc_id,
    )

    if group_id is None:
        group_id = (
            aws.ec2.create_security_group(
                GroupName=settings.alb_sg_name,
                Description=(
                    "Allow inbound to the ALB "
                    "on the app listener ports"
                ),
                VpcId=vpc_id,
            )["GroupId"]
        )

        log.info(
            "Created ALB security group %s",
            group_id,
        )

    for tier in settings.tiers:
        with ignore_errors(
            "InvalidPermission.Duplicate"
        ):
            aws.ec2.authorize_security_group_ingress(
                GroupId=group_id,
                IpPermissions=_cidr_rule(
                    tier.listener_port
                ),
            )

    return group_id


def restrict_app_security_group(
    aws: AwsClients,
    settings: Settings,
    alb_sg_id: str,
) -> None:
    """Replace port 3000 open to the world with ALB-only access."""

    with ignore_errors(
        "InvalidPermission.NotFound"
    ):
        aws.ec2.revoke_security_group_ingress(
            GroupId=settings.app_sg_id,
            IpPermissions=_cidr_rule(
                settings.app_port
            ),
        )

    with ignore_errors(
        "InvalidPermission.Duplicate"
    ):
        aws.ec2.authorize_security_group_ingress(
            GroupId=settings.app_sg_id,
            IpPermissions=_group_rule(
                settings.app_port,
                alb_sg_id,
            ),
        )


def restore_app_security_group(
    aws: AwsClients,
    settings: Settings,
    alb_sg_id: str | None,
) -> None:

    if alb_sg_id:
        with ignore_errors(
            "InvalidPermission.NotFound"
        ):
            aws.ec2.revoke_security_group_ingress(
                GroupId=settings.app_sg_id,
                IpPermissions=_group_rule(
                    settings.app_port,
                    alb_sg_id,
                ),
            )

    with ignore_errors(
        "InvalidPermission.Duplicate"
    ):
        aws.ec2.authorize_security_group_ingress(
            GroupId=settings.app_sg_id,
            IpPermissions=_cidr_rule(
                settings.app_port
            ),
        )


def delete_alb_security_group(
    aws: AwsClients,
    group_id: str,
    sleep=time.sleep,
) -> None:

    with ignore_errors(
        "InvalidGroup.NotFound"
    ):
        retry_on(
            {"DependencyViolation"},
            lambda: aws.ec2.delete_security_group(
                GroupId=group_id
            ),
            attempts=10,
            delay=15,
            sleep=sleep,
        )

        log.info(
            "Deleted ALB security group %s",
            group_id,
        )
