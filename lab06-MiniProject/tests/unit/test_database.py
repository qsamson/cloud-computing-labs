"""Unit tests for the Lab 06 PostgreSQL infrastructure."""

from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from stack.clients import AwsClients
from stack.config import Settings
from stack.database import (
    create_database,
    delete_database,
)


def make_settings(tmp_path: Path) -> Settings:
    """Return Lab 06 settings suitable for Moto tests."""
    values = {
        "AWS_REGION": "us-east-2",
        "AMI_ID": "ami-12345678",
        "KEY_NAME": "test-key",
        "INSTANCE_TYPE": "t3.micro",
        "APP_SECURITY_GROUP_ID": "sg-app12345",
        "AZ_A": "us-east-2a",
        "AZ_B": "us-east-2b",
        "ALB_NAME": "test-weather-alb",
        "ALB_SG_NAME": "test-weather-alb-sg",
        "DB_INSTANCE_ID": "test-weather-db",
        "DB_INSTANCE_CLASS": "db.t4g.micro",
        "DB_NAME": "weather",
        "DB_USER": "weatherapp",
        "DB_SG_NAME": "test-weather-db-sg",
        "DB_SUBNET_GROUP_NAME": "test-weather-db-subnets",
        "DB_PASSWORD_PARAM": "/test/db-password",
        "CACHE_SECONDS": "600",
        "GEMINI_PARAM_NAME": "/test/gemini-api-key",
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

    return Settings.from_values(
        values,
        base_dir=tmp_path,
    )


def prepare_network(ec2, settings: Settings) -> None:
    """Create a default VPC, two subnets and the application SG."""
    vpc = ec2.create_vpc(
        CidrBlock="10.0.0.0/16",
        AmazonProvidedIpv6CidrBlock=False,
    )
    vpc_id = vpc["Vpc"]["VpcId"]

    ec2.modify_vpc_attribute(
        VpcId=vpc_id,
        EnableDnsSupport={"Value": True},
    )

    ec2.create_tags(
        Resources=[vpc_id],
        Tags=[{"Key": "Name", "Value": "test-default-vpc"}],
    )

    # Moto may not mark create_vpc as default, so monkey-patch the
    # describe_vpcs result through a custom default-VPC fixture below.
    subnet_a = ec2.create_subnet(
        VpcId=vpc_id,
        CidrBlock="10.0.1.0/24",
        AvailabilityZone=settings.az_a,
    )
    subnet_b = ec2.create_subnet(
        VpcId=vpc_id,
        CidrBlock="10.0.2.0/24",
        AvailabilityZone=settings.az_b,
    )

    app_sg = ec2.create_security_group(
        GroupName="app-sg",
        Description="application SG",
        VpcId=vpc_id,
    )

    # Settings is frozen, so return the IDs through test-local monkeypatching.
    return (
        vpc_id,
        subnet_a["Subnet"]["SubnetId"],
        subnet_b["Subnet"]["SubnetId"],
        app_sg["GroupId"],
    )


@mock_aws
def test_database_configuration(monkeypatch, tmp_path):
    """Database uses the exact required RDS settings."""
    settings = make_settings(tmp_path)
    clients = AwsClients.create(settings.region)

    vpc_id, subnet_a, subnet_b, app_sg_id = prepare_network(
        clients.ec2,
        settings,
    )

    object.__setattr__(settings, "app_sg_id", app_sg_id)

    monkeypatch.setattr(
        "stack.database.find_default_vpc",
        lambda ec2: vpc_id,
    )

    subnets = {
        settings.az_a: subnet_a,
        settings.az_b: subnet_b,
    }

    monkeypatch.setattr(
        "stack.database.find_subnet",
        lambda ec2, vpc, az: subnets[az],
    )

    output = tmp_path / "db_outputs.env"

    create_database(
        clients,
        settings,
        output_path=output,
        wait=False,
    )

    result = clients.rds.describe_db_instances(
        DBInstanceIdentifier=settings.db_instance_id
    )
    db = result["DBInstances"][0]

    assert db["DBInstanceClass"] == "db.t4g.micro"
    assert db["AllocatedStorage"] == 20
    assert db["BackupRetentionPeriod"] == 0
    assert db["MultiAZ"] is False
    assert db["PubliclyAccessible"] is False
    assert db["StorageEncrypted"] is True


@mock_aws
def test_database_security_group_allows_only_app_sg(
    monkeypatch,
    tmp_path,
):
    """Port 5432 is allowed from the app SG and from no CIDR range."""
    settings = make_settings(tmp_path)
    clients = AwsClients.create(settings.region)

    vpc_id, subnet_a, subnet_b, app_sg_id = prepare_network(
        clients.ec2,
        settings,
    )

    object.__setattr__(settings, "app_sg_id", app_sg_id)

    monkeypatch.setattr(
        "stack.database.find_default_vpc",
        lambda ec2: vpc_id,
    )

    subnets = {
        settings.az_a: subnet_a,
        settings.az_b: subnet_b,
    }

    monkeypatch.setattr(
        "stack.database.find_subnet",
        lambda ec2, vpc, az: subnets[az],
    )

    create_database(
        clients,
        settings,
        output_path=tmp_path / "db_outputs.env",
        wait=False,
    )

    response = clients.ec2.describe_security_groups(
        Filters=[
            {
                "Name": "group-name",
                "Values": [settings.db_sg_name],
            }
        ]
    )

    sg = response["SecurityGroups"][0]

    postgres_rules = [
        rule
        for rule in sg["IpPermissions"]
        if rule.get("FromPort") == 5432
        and rule.get("ToPort") == 5432
    ]

    assert len(postgres_rules) == 1

    rule = postgres_rules[0]

    assert rule["IpRanges"] == []
    assert rule["UserIdGroupPairs"]
    assert (
        rule["UserIdGroupPairs"][0]["GroupId"]
        == app_sg_id
    )


@mock_aws
def test_create_delete_removes_database_and_password(
    monkeypatch,
    tmp_path,
):
    """Create then delete leaves no DB, snapshots or password parameter."""
    settings = make_settings(tmp_path)
    clients = AwsClients.create(settings.region)

    vpc_id, subnet_a, subnet_b, app_sg_id = prepare_network(
        clients.ec2,
        settings,
    )

    object.__setattr__(settings, "app_sg_id", app_sg_id)

    monkeypatch.setattr(
        "stack.database.find_default_vpc",
        lambda ec2: vpc_id,
    )

    subnets = {
        settings.az_a: subnet_a,
        settings.az_b: subnet_b,
    }

    monkeypatch.setattr(
        "stack.database.find_subnet",
        lambda ec2, vpc, az: subnets[az],
    )

    output = tmp_path / "db_outputs.env"

    create_database(
        clients,
        settings,
        output_path=output,
        wait=False,
    )

    delete_database(
        clients,
        settings,
        output_path=output,
        wait=False,
    )

    databases = clients.rds.describe_db_instances()["DBInstances"]
    snapshots = clients.rds.describe_db_snapshots()["DBSnapshots"]

    assert databases == []
    assert snapshots == []

    parameters = clients.ssm.describe_parameters()["Parameters"]

    assert not any(
        p["Name"] == settings.db_password_param
        for p in parameters
    )

    assert not output.exists()


@mock_aws
def test_database_create_twice_has_no_duplicates(
    monkeypatch,
    tmp_path,
):
    """Running database creation twice creates no duplicate resources."""
    settings = make_settings(tmp_path)
    clients = AwsClients.create(settings.region)

    vpc_id, subnet_a, subnet_b, app_sg_id = prepare_network(
        clients.ec2,
        settings,
    )

    object.__setattr__(
        settings,
        "app_sg_id",
        app_sg_id,
    )

    monkeypatch.setattr(
        "stack.database.find_default_vpc",
        lambda ec2: vpc_id,
    )

    subnets = {
        settings.az_a: subnet_a,
        settings.az_b: subnet_b,
    }

    monkeypatch.setattr(
        "stack.database.find_subnet",
        lambda ec2, vpc, az: subnets[az],
    )

    output = tmp_path / "db_outputs.env"

    create_database(
        clients,
        settings,
        output_path=output,
        wait=False,
    )

    create_database(
        clients,
        settings,
        output_path=output,
        wait=False,
    )

    databases = clients.rds.describe_db_instances()[
        "DBInstances"
    ]

    parameters = clients.ssm.describe_parameters()[
        "Parameters"
    ]

    subnet_groups = clients.rds.describe_db_subnet_groups()[
        "DBSubnetGroups"
    ]

    assert len(databases) == 1

    assert sum(
        p["Name"] == settings.db_password_param
        for p in parameters
    ) == 1

    assert sum(
        g["DBSubnetGroupName"]
        == settings.db_subnet_group_name
        for g in subnet_groups
    ) == 1
