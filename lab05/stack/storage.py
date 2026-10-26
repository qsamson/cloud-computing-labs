"""S3 bucket and IAM role and instance profile: the foundation of the stack."""

from __future__ import annotations

import json
import logging

from botocore.exceptions import ClientError

from .clients import AwsClients
from .config import Settings, Tier
from .policies import policy_for, trust_policy
from .util import error_code, ignore_errors


log = logging.getLogger("stack")


def ensure_bucket(aws: AwsClients, settings: Settings) -> None:
    try:
        aws.s3.head_bucket(Bucket=settings.bucket_name)
        log.info(
            "Bucket %s already exists, skipping.",
            settings.bucket_name,
        )

    except ClientError as err:
        if error_code(err) not in (
            "404",
            "NoSuchBucket",
            "NotFound",
        ):
            raise

        args = {
            "Bucket": settings.bucket_name
        }

        if settings.region != "us-east-1":
            args["CreateBucketConfiguration"] = {
                "LocationConstraint": settings.region
            }

        aws.s3.create_bucket(**args)

        log.info(
            "Created bucket %s",
            settings.bucket_name,
        )

    aws.s3.put_public_access_block(
        Bucket=settings.bucket_name,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )


def ensure_role_and_profile(
    aws: AwsClients,
    settings: Settings,
    tier: Tier,
) -> None:
    """Create the role, its inline policy, and an instance profile."""

    with ignore_errors("EntityAlreadyExists"):
        aws.iam.create_role(
            RoleName=tier.role_name,
            AssumeRolePolicyDocument=json.dumps(
                trust_policy()
            ),
        )

    aws.iam.put_role_policy(
        RoleName=tier.role_name,
        PolicyName=tier.policy_name,
        PolicyDocument=json.dumps(
            policy_for(
                tier.name,
                settings.bucket_name,
            )
        ),
    )

    with ignore_errors("EntityAlreadyExists"):
        aws.iam.create_instance_profile(
            InstanceProfileName=tier.profile_name
        )

    profile = aws.iam.get_instance_profile(
        InstanceProfileName=tier.profile_name
    )

    roles = [
        role["RoleName"]
        for role in profile[
            "InstanceProfile"
        ]["Roles"]
    ]

    if tier.role_name not in roles:
        aws.iam.add_role_to_instance_profile(
            InstanceProfileName=tier.profile_name,
            RoleName=tier.role_name,
        )

    log.info(
        "%s role and instance profile are ready.",
        tier.name,
    )


def delete_role_and_profile(
    aws: AwsClients,
    tier: Tier,
) -> None:

    with ignore_errors("NoSuchEntity"):
        aws.iam.remove_role_from_instance_profile(
            InstanceProfileName=tier.profile_name,
            RoleName=tier.role_name,
        )

    with ignore_errors("NoSuchEntity"):
        aws.iam.delete_instance_profile(
            InstanceProfileName=tier.profile_name
        )

    with ignore_errors("NoSuchEntity"):
        aws.iam.delete_role_policy(
            RoleName=tier.role_name,
            PolicyName=tier.policy_name,
        )

    with ignore_errors("NoSuchEntity"):
        attached = aws.iam.list_attached_role_policies(
            RoleName=tier.role_name
        )

        for policy in attached[
            "AttachedPolicies"
        ]:
            aws.iam.detach_role_policy(
                RoleName=tier.role_name,
                PolicyArn=policy["PolicyArn"],
            )

    with ignore_errors("NoSuchEntity"):
        aws.iam.delete_role(
            RoleName=tier.role_name
        )

    log.info(
        "Removed %s role and instance profile.",
        tier.name,
    )


def delete_bucket(
    aws: AwsClients,
    settings: Settings,
) -> None:

    with ignore_errors("NoSuchBucket"):
        paginator = aws.s3.get_paginator(
            "list_objects_v2"
        )

        for page in paginator.paginate(
            Bucket=settings.bucket_name
        ):
            objects = [
                {"Key": obj["Key"]}
                for obj in page.get(
                    "Contents",
                    [],
                )
            ]

            if objects:
                aws.s3.delete_objects(
                    Bucket=settings.bucket_name,
                    Delete={
                        "Objects": objects
                    },
                )

        aws.s3.delete_bucket(
            Bucket=settings.bucket_name
        )

        log.info(
            "Deleted bucket %s",
            settings.bucket_name,
        )
