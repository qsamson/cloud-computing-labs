"""Run the real create and delete code against moto, an in-memory fake of AWS.

Nothing here touches your AWS account, costs money, or needs credentials.
"""

import json

import pytest
from moto import mock_aws

from stack.clients import AwsClients
from stack.config import Settings
from stack.runner import create_stack, delete_stack
from tests.conftest import FAKE_VALUES


@pytest.fixture
def env(tmp_path, monkeypatch, fake_settings):
    monkeypatch.chdir(tmp_path)

    with mock_aws():
        aws = AwsClients.create("us-east-2")

        vpc = aws.ec2.describe_vpcs(
            Filters=[{
                "Name": "isDefault",
                "Values": ["true"],
            }]
        )["Vpcs"][0]

        sg = aws.ec2.create_security_group(
            GroupName="app-sg",
            Description="app",
            VpcId=vpc["VpcId"],
        )["GroupId"]

        aws.ec2.authorize_security_group_ingress(
            GroupId=sg,
            IpPermissions=[{
                "IpProtocol": "tcp",
                "FromPort": 3000,
                "ToPort": 3000,
                "IpRanges": [
                    {"CidrIp": "0.0.0.0/0"}
                ],
            }],
        )

        aws.ec2.create_key_pair(
            KeyName="test-key"
        )

        ami = aws.ec2.describe_images()[
            "Images"
        ][0]["ImageId"]

        values = dict(
            FAKE_VALUES,
            APP_SECURITY_GROUP_ID=sg,
            AMI_ID=ami,
        )

        settings = Settings.from_values(
            values,
            base_dir=fake_settings.uploader.app_dir.parent,
        )

        yield settings, aws


def _app_sg_rules(aws, settings):
    group = aws.ec2.describe_security_groups(
        GroupIds=[settings.app_sg_id]
    )["SecurityGroups"][0]

    return [
        permission
        for permission in group["IpPermissions"]
        if permission["FromPort"] == 3000
    ]


def test_create_builds_every_resource(env):
    settings, aws = env

    outputs = create_stack(
        settings,
        aws,
        iam_wait=0,
    )

    aws.s3.head_bucket(
        Bucket=settings.bucket_name
    )

    block = aws.s3.get_public_access_block(
        Bucket=settings.bucket_name
    )["PublicAccessBlockConfiguration"]

    assert all(block.values())

    for tier in settings.tiers:
        role_policy = aws.iam.get_role_policy(
            RoleName=tier.role_name,
            PolicyName=tier.policy_name,
        )

        assert role_policy[
            "PolicyDocument"
        ]["Statement"]

        profile = aws.iam.get_instance_profile(
            InstanceProfileName=tier.profile_name
        )

        assert [
            role["RoleName"]
            for role in profile[
                "InstanceProfile"
            ]["Roles"]
        ] == [tier.role_name]

        assert aws.ec2.describe_launch_templates(
            LaunchTemplateNames=[tier.lt_name]
        )["LaunchTemplates"]

        group = aws.autoscaling.describe_auto_scaling_groups(
            AutoScalingGroupNames=[tier.asg_name]
        )["AutoScalingGroups"][0]

        assert (
            group["MinSize"],
            group["MaxSize"],
            group["DesiredCapacity"],
        ) == (1, 1, 1)

        assert group["HealthCheckType"] == "ELB"

        tg = aws.elbv2.describe_target_groups(
            Names=[tier.tg_name]
        )["TargetGroups"][0]

        assert tg["HealthCheckIntervalSeconds"] == 10
        assert tg["UnhealthyThresholdCount"] == 2

    listeners = aws.elbv2.describe_listeners(
        LoadBalancerArn=outputs.alb_arn
    )["Listeners"]

    assert sorted(
        item["Port"]
        for item in listeners
    ) == [8080, 8081]

    assert outputs.alb_dns_name


def test_app_security_group_only_accepts_the_alb(env):
    settings, aws = env

    outputs = create_stack(
        settings,
        aws,
        iam_wait=0,
    )

    rules = _app_sg_rules(
        aws,
        settings,
    )

    assert len(rules) == 1
    assert rules[0]["IpRanges"] == []

    assert (
        rules[0]["UserIdGroupPairs"][0]["GroupId"]
        == outputs.alb_security_group_id
    )


def test_create_twice_does_not_duplicate_anything(env):
    settings, aws = env

    first = create_stack(
        settings,
        aws,
        iam_wait=0,
    )

    second = create_stack(
        settings,
        aws,
        iam_wait=0,
    )

    assert first == second

    assert len(
        aws.elbv2.describe_load_balancers()[
            "LoadBalancers"
        ]
    ) == 1

    assert len(
        aws.elbv2.describe_target_groups()[
            "TargetGroups"
        ]
    ) == 2

    assert len(
        aws.autoscaling.describe_auto_scaling_groups()[
            "AutoScalingGroups"
        ]
    ) == 2

    assert len(
        _app_sg_rules(aws, settings)
    ) == 1

    versions = aws.ec2.describe_launch_template_versions(
        LaunchTemplateName=settings.uploader.lt_name
    )["LaunchTemplateVersions"]

    assert len(versions) == 2


def test_delete_removes_everything_and_restores_the_app_sg(env):
    settings, aws = env

    create_stack(
        settings,
        aws,
        iam_wait=0,
    ).save()

    delete_stack(
        settings,
        aws,
        sleep=lambda _: None,
    )

    assert (
        aws.elbv2.describe_load_balancers()[
            "LoadBalancers"
        ] == []
    )

    assert (
        aws.elbv2.describe_target_groups()[
            "TargetGroups"
        ] == []
    )

    assert (
        aws.autoscaling.describe_auto_scaling_groups()[
            "AutoScalingGroups"
        ] == []
    )

    assert (
        aws.ec2.describe_launch_templates()[
            "LaunchTemplates"
        ] == []
    )

    assert aws.iam.list_roles()["Roles"] == []

    assert (
        aws.iam.list_instance_profiles()[
            "InstanceProfiles"
        ] == []
    )

    assert settings.bucket_name not in [
        bucket["Name"]
        for bucket in aws.s3.list_buckets()[
            "Buckets"
        ]
    ]

    rules = _app_sg_rules(
        aws,
        settings,
    )

    assert rules[0]["IpRanges"] == [
        {"CidrIp": "0.0.0.0/0"}
    ]

    assert rules[0]["UserIdGroupPairs"] == []


def test_delete_is_safe_to_run_twice(env):
    settings, aws = env

    create_stack(
        settings,
        aws,
        iam_wait=0,
    )

    delete_stack(
        settings,
        aws,
        sleep=lambda _: None,
    )

    delete_stack(
        settings,
        aws,
        sleep=lambda _: None,
    )


def test_keep_foundation_leaves_bucket_roles_and_templates(env):
    settings, aws = env

    create_stack(
        settings,
        aws,
        iam_wait=0,
    )

    delete_stack(
        settings,
        aws,
        keep_foundation=True,
        sleep=lambda _: None,
    )

    assert (
        aws.autoscaling.describe_auto_scaling_groups()[
            "AutoScalingGroups"
        ] == []
    )

    assert len(
        aws.iam.list_roles()["Roles"]
    ) == 2

    assert len(
        aws.ec2.describe_launch_templates()[
            "LaunchTemplates"
        ]
    ) == 2

    aws.s3.head_bucket(
        Bucket=settings.bucket_name
    )


def test_delete_detaches_extra_managed_policies(env):
    settings, aws = env

    create_stack(
        settings,
        aws,
        iam_wait=0,
    )

    extra = aws.iam.create_policy(
        PolicyName="extra",
        PolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": "logs:PutLogEvents",
                "Resource": "*",
            }],
        }),
    )

    aws.iam.attach_role_policy(
        RoleName=settings.uploader.role_name,
        PolicyArn=extra["Policy"]["Arn"],
    )

    delete_stack(
        settings,
        aws,
        sleep=lambda _: None,
    )

    assert aws.iam.list_roles()["Roles"] == []
