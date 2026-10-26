"""Terminate a real instance and measure how long recovery takes against your SLO.

Slow (a few minutes per tier). Run with:     pytest -m chaos -s
"""

import time

import pytest

from tests.helpers import probe, tier_url


pytestmark = pytest.mark.chaos


def _in_service_instance(
    aws,
    asg_name,
):
    group = (
        aws.autoscaling.describe_auto_scaling_groups(
            AutoScalingGroupNames=[
                asg_name
            ]
        )["AutoScalingGroups"][0]
    )

    for instance in group["Instances"]:
        if (
            instance["LifecycleState"]
            == "InService"
        ):
            return instance["InstanceId"]

    return None


@pytest.mark.parametrize(
    "tier_name",
    ["uploader", "viewer"],
)
def test_tier_recovers_within_the_slo(
    aws,
    settings,
    outputs,
    tier_name,
):
    tier = settings.tier(tier_name)

    url = tier_url(
        outputs,
        settings,
        tier_name,
    )

    assert probe(url), (
        "the endpoint must be healthy "
        "before the experiment starts"
    )

    victim = _in_service_instance(
        aws,
        tier.asg_name,
    )

    assert victim, (
        f"no in-service instance "
        f"in {tier.asg_name}"
    )

    aws.autoscaling.terminate_instance_in_auto_scaling_group(
        InstanceId=victim,
        ShouldDecrementDesiredCapacity=False,
    )

    started = time.time()

    saw_outage = False
    recovered_after = None

    while (
        time.time() - started
        < settings.recovery_slo_seconds * 2
    ):
        if probe(
            url,
            timeout=2,
        ):
            if saw_outage:
                recovered_after = (
                    time.time() - started
                )
                break

        else:
            saw_outage = True

        time.sleep(2)

    print(
        f"\n{tier_name}: terminated {victim}, "
        f"recovery took {recovered_after}s "
        f"(SLO {settings.recovery_slo_seconds}s)"
    )

    assert saw_outage, (
        "the endpoint never went down, "
        "so there was nothing to recover from"
    )

    assert recovered_after is not None, (
        "the endpoint did not come back in time"
    )

    assert (
        recovered_after
        <= settings.recovery_slo_seconds
    )
