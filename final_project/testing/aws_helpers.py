"""Talks to the Auto Scaling Group this lab manages."""

import boto3


def get_inservice_instance_id(asg_name: str, region: str):
    client = boto3.client("autoscaling", region_name=region)

    resp = client.describe_auto_scaling_groups(
        AutoScalingGroupNames=[asg_name]
    )

    groups = resp.get("AutoScalingGroups", [])

    if not groups:
        raise RuntimeError(
            f"Auto Scaling Group '{asg_name}' not found in {region}."
        )

    for inst in groups[0].get("Instances", []):
        if inst.get("LifecycleState") == "InService":
            return inst["InstanceId"]

    return None


def terminate_instance_via_asg(instance_id: str, region: str) -> None:
    client = boto3.client("autoscaling", region_name=region)

    client.terminate_instance_in_auto_scaling_group(
        InstanceId=instance_id,
        ShouldDecrementDesiredCapacity=False,
    )
