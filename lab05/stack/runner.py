"""The two entry points: build the whole stack, and tear it down."""

from __future__ import annotations

import logging
import time

from . import balancer, compute, network, scaling, storage
from .clients import AwsClients
from .config import Settings
from .outputs import StackOutputs


log = logging.getLogger("stack")


def create_stack(
    settings: Settings,
    aws: AwsClients,
    iam_wait: int = 15,
    sleep=time.sleep,
) -> StackOutputs:

    log.info("== S3 bucket ==")
    storage.ensure_bucket(aws, settings)

    log.info("== IAM roles and instance profiles ==")
    for tier in settings.tiers:
        storage.ensure_role_and_profile(
            aws,
            settings,
            tier,
        )

    log.info(
        "Waiting %ss for IAM propagation...",
        iam_wait,
    )
    sleep(iam_wait)

    log.info("== Launch templates ==")
    for tier in settings.tiers:
        compute.ensure_launch_template(
            aws,
            settings,
            tier,
        )

    log.info("== Network ==")

    vpc_id = network.default_vpc_id(aws)

    subnet_a = network.subnet_in_az(
        aws,
        vpc_id,
        settings.az_a,
    )

    subnet_b = network.subnet_in_az(
        aws,
        vpc_id,
        settings.az_b,
    )

    alb_sg_id = network.ensure_alb_security_group(
        aws,
        settings,
        vpc_id,
    )

    network.restrict_app_security_group(
        aws,
        settings,
        alb_sg_id,
    )

    log.info(
        "== Target groups, load balancer, listeners =="
    )

    tg_arns = {
        tier.name: balancer.ensure_target_group(
            aws,
            settings,
            tier,
            vpc_id,
        )
        for tier in settings.tiers
    }

    alb_arn, alb_dns = balancer.ensure_load_balancer(
        aws,
        settings,
        [subnet_a, subnet_b],
        alb_sg_id,
    )

    for tier in settings.tiers:
        balancer.ensure_listener(
            aws,
            alb_arn,
            tier.listener_port,
            tg_arns[tier.name],
        )

    log.info("== Auto Scaling Groups ==")

    for tier in settings.tiers:
        scaling.ensure_asg(
            aws,
            tier,
            tg_arns[tier.name],
            [subnet_a, subnet_b],
        )

    return StackOutputs(
        vpc_id=vpc_id,
        subnet_a=subnet_a,
        subnet_b=subnet_b,
        alb_security_group_id=alb_sg_id,
        alb_arn=alb_arn,
        alb_dns_name=alb_dns,
        uploader_tg_arn=tg_arns["uploader"],
        viewer_tg_arn=tg_arns["viewer"],
    )


def delete_stack(
    settings: Settings,
    aws: AwsClients,
    keep_foundation: bool = False,
    sleep=time.sleep,
) -> None:

    log.info(
        "== Auto Scaling Groups "
        "(this also terminates their instances) =="
    )

    for tier in settings.tiers:
        scaling.delete_asg(
            aws,
            tier.asg_name,
            sleep=sleep,
        )

    log.info(
        "== Load balancer and target groups =="
    )

    balancer.delete_load_balancer(
        aws,
        settings.alb_name,
    )

    for tier in settings.tiers:
        balancer.delete_target_group(
            aws,
            tier.tg_name,
        )

    log.info("== Security groups ==")

    vpc_id = network.default_vpc_id(aws)

    alb_sg_id = network.find_security_group(
        aws,
        settings.alb_sg_name,
        vpc_id,
    )

    network.restore_app_security_group(
        aws,
        settings,
        alb_sg_id,
    )

    if alb_sg_id:
        network.delete_alb_security_group(
            aws,
            alb_sg_id,
            sleep=sleep,
        )

    if keep_foundation:
        log.info(
            "Keeping the bucket, IAM roles and "
            "launch templates (--keep-foundation)."
        )

    else:
        log.info(
            "== Launch templates, IAM, bucket =="
        )

        for tier in settings.tiers:
            compute.delete_launch_template(
                aws,
                tier,
            )

            storage.delete_role_and_profile(
                aws,
                tier,
            )

        storage.delete_bucket(
            aws,
            settings,
        )

    StackOutputs.remove()

    log.info("Cleanup complete.")
