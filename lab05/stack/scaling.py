"""Auto Scaling Groups: the part that launches (and relaunches) the instances."""

from __future__ import annotations

import logging
import time

from .clients import AwsClients
from .config import Tier


log = logging.getLogger("stack")


def find_asg(aws: AwsClients, name: str) -> dict | None:
    groups = aws.autoscaling.describe_auto_scaling_groups(
        AutoScalingGroupNames=[name]
    )["AutoScalingGroups"]

    return groups[0] if groups else None


def ensure_asg(
    aws: AwsClients,
    tier: Tier,
    tg_arn: str,
    subnets: list[str],
) -> None:

    if find_asg(aws, tier.asg_name):
        log.info(
            "Auto Scaling Group %s already exists, skipping.",
            tier.asg_name,
        )
        return

    aws.autoscaling.create_auto_scaling_group(
        AutoScalingGroupName=tier.asg_name,
        LaunchTemplate={
            "LaunchTemplateName": tier.lt_name,
            "Version": "$Latest",
        },
        MinSize=1,
        MaxSize=1,
        DesiredCapacity=1,
        VPCZoneIdentifier=",".join(subnets),
        TargetGroupARNs=[tg_arn],
        HealthCheckType="ELB",
        HealthCheckGracePeriod=120,
        Tags=[{
            "ResourceId": tier.asg_name,
            "ResourceType": "auto-scaling-group",
            "Key": "Name",
            "Value": f"{tier.name}-app",
            "PropagateAtLaunch": True,
        }],
    )

    log.info(
        "Created Auto Scaling Group %s",
        tier.asg_name,
    )


def delete_asg(
    aws: AwsClients,
    name: str,
    timeout: int = 300,
    poll: int = 15,
    sleep=time.sleep,
) -> None:
    """Force-delete the group and wait until it is gone."""

    if not find_asg(aws, name):
        return

    aws.autoscaling.delete_auto_scaling_group(
        AutoScalingGroupName=name,
        ForceDelete=True,
    )

    waited = 0

    while find_asg(aws, name):
        if waited >= timeout:
            log.warning(
                "%s still deleting after %ss. Check the console.",
                name,
                timeout,
            )
            return

        sleep(poll)
        waited += poll

    log.info(
        "Deleted Auto Scaling Group %s",
        name,
    )
