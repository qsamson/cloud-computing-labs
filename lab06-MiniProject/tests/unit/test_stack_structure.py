"""Unit tests for Lab 06 stack ordering and idempotency."""

from pathlib import Path
from types import SimpleNamespace

from moto import mock_aws

from stack.clients import AwsClients
from stack.config import Settings
from stack.weather_stack import (
    create_weather_stack,
    ensure_alb_security_group,
    ensure_asg,
    ensure_launch_template,
    ensure_listener,
    ensure_load_balancer,
    ensure_role_and_profile,
    ensure_target_group,
)


def make_settings(tmp_path: Path) -> Settings:
    """Build complete settings for stack unit tests."""
    values = {
        "AWS_REGION": "us-east-2",
        "AMI_ID": "ami-12345678",
        "KEY_NAME": "test-key",
        "INSTANCE_TYPE": "t3.micro",
        "APP_SECURITY_GROUP_ID": "sg-placeholder",
        "AZ_A": "us-east-2a",
        "AZ_B": "us-east-2b",
        "ALB_NAME": "test-weather-alb",
        "ALB_SG_NAME": "test-weather-alb-sg",
        "DB_INSTANCE_ID": "test-weather-db",
        "DB_INSTANCE_CLASS": "db.t4g.micro",
        "DB_NAME": "weather",
        "DB_USER": "weatherapp",
        "DB_SG_NAME": "test-db-sg",
        "DB_SUBNET_GROUP_NAME": "test-db-subnets",
        "DB_PASSWORD_PARAM": "/test/db-password",
        "CACHE_SECONDS": "600",
        "GEMINI_PARAM_NAME": "/test/gemini-key",
        "GEMINI_MODEL": "gemini-test",
        "KEY_CACHE_SECONDS": "60",
        "CONTACT_EMAIL": "student@example.com",
        "WEATHER_ROLE_NAME": "test-weather-role",
        "WEATHER_PROFILE_NAME": "test-weather-profile",
        "WEATHER_LT_NAME": "test-weather-lt",
        "WEATHER_TG_NAME": "test-weather-tg",
        "WEATHER_ASG_NAME": "test-weather-asg",
        "WEATHER_LISTENER_PORT": "8080",
        "ADVISOR_ROLE_NAME": "test-advisor-role",
        "ADVISOR_PROFILE_NAME": "test-advisor-profile",
        "ADVISOR_LT_NAME": "test-advisor-lt",
        "ADVISOR_TG_NAME": "test-advisor-tg",
        "ADVISOR_ASG_NAME": "test-advisor-asg",
        "ADVISOR_LISTENER_PORT": "8081",
    }

    return Settings.from_values(values, base_dir=tmp_path)


@mock_aws
def test_create_helpers_are_idempotent(tmp_path):
    """Calling create helpers twice does not duplicate AWS resources."""
    settings = make_settings(tmp_path)
    clients = AwsClients.create(settings.region)

    vpc_id = clients.ec2.create_vpc(
        CidrBlock="10.0.0.0/16"
    )["Vpc"]["VpcId"]

    subnet_a = clients.ec2.create_subnet(
        VpcId=vpc_id,
        CidrBlock="10.0.1.0/24",
        AvailabilityZone=settings.az_a,
    )["Subnet"]["SubnetId"]

    subnet_b = clients.ec2.create_subnet(
        VpcId=vpc_id,
        CidrBlock="10.0.2.0/24",
        AvailabilityZone=settings.az_b,
    )["Subnet"]["SubnetId"]

    app_sg = clients.ec2.create_security_group(
        GroupName="test-app-sg",
        Description="test application SG",
        VpcId=vpc_id,
    )["GroupId"]

    object.__setattr__(
        settings,
        "app_sg_id",
        app_sg,
    )

    # IAM role/profile twice.
    ensure_role_and_profile(
        clients.iam,
        settings.weather.role_name,
        settings.weather.profile_name,
    )
    ensure_role_and_profile(
        clients.iam,
        settings.weather.role_name,
        settings.weather.profile_name,
    )

    roles = clients.iam.list_roles()["Roles"]
    assert sum(
        r["RoleName"] == settings.weather.role_name
        for r in roles
    ) == 1

    profiles = clients.iam.list_instance_profiles()[
        "InstanceProfiles"
    ]
    assert sum(
        p["InstanceProfileName"]
        == settings.weather.profile_name
        for p in profiles
    ) == 1

    # ALB security group twice.
    alb_sg_1 = ensure_alb_security_group(
        clients.ec2,
        settings,
        vpc_id,
    )
    alb_sg_2 = ensure_alb_security_group(
        clients.ec2,
        settings,
        vpc_id,
    )

    assert alb_sg_1 == alb_sg_2

    # Target group twice.
    tg_1 = ensure_target_group(
        clients.elbv2,
        settings.weather.tg_name,
        vpc_id,
    )
    tg_2 = ensure_target_group(
        clients.elbv2,
        settings.weather.tg_name,
        vpc_id,
    )

    assert tg_1 == tg_2

    # ALB twice.
    alb_arn_1, dns_1 = ensure_load_balancer(
        clients.elbv2,
        settings,
        subnet_a,
        subnet_b,
        alb_sg_1,
        wait=False,
    )

    alb_arn_2, dns_2 = ensure_load_balancer(
        clients.elbv2,
        settings,
        subnet_a,
        subnet_b,
        alb_sg_1,
        wait=False,
    )

    assert alb_arn_1 == alb_arn_2
    assert dns_1 == dns_2

    # Listener twice.
    ensure_listener(
        clients.elbv2,
        alb_arn_1,
        settings.weather.listener_port,
        tg_1,
    )
    ensure_listener(
        clients.elbv2,
        alb_arn_1,
        settings.weather.listener_port,
        tg_1,
    )

    listeners = clients.elbv2.describe_listeners(
        LoadBalancerArn=alb_arn_1
    )["Listeners"]

    assert len(
        [
            x
            for x in listeners
            if x["Port"] == settings.weather.listener_port
        ]
    ) == 1

    # Launch template twice.
    lt_data = {
        "ImageId": settings.ami_id,
        "InstanceType": settings.instance_type,
    }

    ensure_launch_template(
        clients.ec2,
        settings.weather.lt_name,
        lt_data,
    )
    ensure_launch_template(
        clients.ec2,
        settings.weather.lt_name,
        lt_data,
    )

    templates = clients.ec2.describe_launch_templates(
        LaunchTemplateNames=[settings.weather.lt_name]
    )["LaunchTemplates"]

    assert len(templates) == 1

    # ASG twice.
    ensure_asg(
        clients.autoscaling,
        name=settings.weather.asg_name,
        launch_template_name=settings.weather.lt_name,
        target_group_arn=tg_1,
        subnet_a=subnet_a,
        subnet_b=subnet_b,
        tag_name="weather-app",
    )

    ensure_asg(
        clients.autoscaling,
        name=settings.weather.asg_name,
        launch_template_name=settings.weather.lt_name,
        target_group_arn=tg_1,
        subnet_a=subnet_a,
        subnet_b=subnet_b,
        tag_name="weather-app",
    )

    groups = clients.autoscaling.describe_auto_scaling_groups(
        AutoScalingGroupNames=[settings.weather.asg_name]
    )["AutoScalingGroups"]

    assert len(groups) == 1


def test_alb_exists_before_launch_templates(monkeypatch, tmp_path):
    """The ALB DNS name exists before advisor user-data is built."""
    settings = make_settings(tmp_path)

    for tier in (settings.weather, settings.advisor):
        tier.app_dir.mkdir(parents=True, exist_ok=True)
        (tier.app_dir / "app.js").write_text(
            "console.log('test');"
        )
        (tier.app_dir / "package.json").write_text(
            '{"name":"test"}'
        )

    db_outputs = tmp_path / "db_outputs.env"
    db_outputs.write_text(
        "DB_HOST=database.internal\n"
        "DB_SECURITY_GROUP_ID=sg-db\n"
    )

    stack_outputs = tmp_path / "stack_outputs.env"

    events = []

    fake = SimpleNamespace(
        ssm=object(),
        iam=object(),
        ec2=object(),
        elbv2=object(),
        autoscaling=object(),
        sts=SimpleNamespace(
            get_caller_identity=lambda: {
                "Account": "123456789012"
            }
        ),
    )

    monkeypatch.setattr(
        "stack.weather_stack.ensure_gemini_parameter",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "stack.weather_stack.ensure_role_and_profile",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "stack.weather_stack.put_secret_policies",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "stack.weather_stack.find_default_vpc",
        lambda *args: "vpc-test",
    )
    monkeypatch.setattr(
        "stack.weather_stack.find_subnet",
        lambda ec2, vpc, az: (
            "subnet-a"
            if az == settings.az_a
            else "subnet-b"
        ),
    )
    monkeypatch.setattr(
        "stack.weather_stack.ensure_alb_security_group",
        lambda *args: "sg-alb",
    )
    monkeypatch.setattr(
        "stack.weather_stack.restrict_app_security_group",
        lambda *args: None,
    )
    monkeypatch.setattr(
        "stack.weather_stack.ensure_target_group",
        lambda client, name, vpc: f"arn:{name}",
    )

    def fake_alb(*args, **kwargs):
        events.append("alb")
        return (
            "arn:alb",
            "weather.example.com",
        )

    monkeypatch.setattr(
        "stack.weather_stack.ensure_load_balancer",
        fake_alb,
    )
    monkeypatch.setattr(
        "stack.weather_stack.ensure_listener",
        lambda *args: None,
    )

    def fake_advisor_ud(
        settings,
        alb_dns,
        app_js,
        package_json,
    ):
        assert alb_dns == "weather.example.com"
        events.append("advisor_user_data")
        return "advisor-user-data"

    monkeypatch.setattr(
        "stack.weather_stack.build_advisor_user_data",
        fake_advisor_ud,
    )
    monkeypatch.setattr(
        "stack.weather_stack.build_weather_user_data",
        lambda *args: "weather-user-data",
    )
    monkeypatch.setattr(
        "stack.weather_stack.launch_template_data",
        lambda *args: {},
    )

    def fake_lt(*args, **kwargs):
        events.append("launch_template")

    monkeypatch.setattr(
        "stack.weather_stack.ensure_launch_template",
        fake_lt,
    )
    monkeypatch.setattr(
        "stack.weather_stack.ensure_asg",
        lambda *args, **kwargs: None,
    )

    outputs = create_weather_stack(
        fake,
        settings,
        db_outputs_path=db_outputs,
        stack_outputs_path=stack_outputs,
        wait=False,
    )

    assert outputs["ALB_DNS_NAME"] == "weather.example.com"
    assert events.index("alb") < events.index("advisor_user_data")
    assert events.index("alb") < events.index("launch_template")
