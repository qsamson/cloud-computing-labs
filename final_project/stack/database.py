"""RDS PostgreSQL resources for the Lab 06 Weather Advisor."""

from __future__ import annotations

import secrets
import time
from pathlib import Path

from botocore.exceptions import ClientError

from .clients import AwsClients
from .config import Settings


def error_code(exc: ClientError) -> str:
    """Return the AWS error code from a ClientError."""
    return exc.response.get("Error", {}).get("Code", "")


def find_default_vpc(ec2) -> str:
    """Return the default VPC ID."""
    response = ec2.describe_vpcs(
        Filters=[{"Name": "isDefault", "Values": ["true"]}]
    )
    if not response["Vpcs"]:
        raise RuntimeError("No default VPC was found.")
    return response["Vpcs"][0]["VpcId"]


def find_subnet(ec2, vpc_id: str, az: str) -> str:
    """Return one subnet in the requested availability zone."""
    response = ec2.describe_subnets(
        Filters=[
            {"Name": "vpc-id", "Values": [vpc_id]},
            {"Name": "availability-zone", "Values": [az]},
        ]
    )
    if not response["Subnets"]:
        raise RuntimeError(f"No subnet found in {az}.")
    return response["Subnets"][0]["SubnetId"]


def ensure_db_security_group(
    ec2,
    settings: Settings,
    vpc_id: str,
) -> str:
    """Create the database security group and its least-privilege rule."""
    response = ec2.describe_security_groups(
        Filters=[
            {"Name": "group-name", "Values": [settings.db_sg_name]},
            {"Name": "vpc-id", "Values": [vpc_id]},
        ]
    )

    if response["SecurityGroups"]:
        group_id = response["SecurityGroups"][0]["GroupId"]
    else:
        created = ec2.create_security_group(
            GroupName=settings.db_sg_name,
            Description="PostgreSQL access from Lab 06 application instances",
            VpcId=vpc_id,
        )
        group_id = created["GroupId"]

    try:
        ec2.authorize_security_group_ingress(
            GroupId=group_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 5432,
                    "ToPort": 5432,
                    "UserIdGroupPairs": [
                        {"GroupId": settings.app_sg_id}
                    ],
                }
            ],
        )
    except ClientError as exc:
        if error_code(exc) != "InvalidPermission.Duplicate":
            raise

    return group_id


def ensure_db_subnet_group(
    rds,
    settings: Settings,
    subnet_a: str,
    subnet_b: str,
) -> None:
    """Create the RDS subnet group if it does not already exist."""
    try:
        rds.describe_db_subnet_groups(
            DBSubnetGroupName=settings.db_subnet_group_name
        )
        return
    except ClientError as exc:
        if error_code(exc) != "DBSubnetGroupNotFoundFault":
            raise

    rds.create_db_subnet_group(
        DBSubnetGroupName=settings.db_subnet_group_name,
        DBSubnetGroupDescription="Lab 06 weather database subnets",
        SubnetIds=[subnet_a, subnet_b],
    )


def ensure_db_password(ssm, settings: Settings) -> str:
    """Return the DB password, creating a random SecureString if needed."""
    try:
        response = ssm.get_parameter(
            Name=settings.db_password_param,
            WithDecryption=True,
        )
        return response["Parameter"]["Value"]
    except ClientError as exc:
        if error_code(exc) != "ParameterNotFound":
            raise

    password = secrets.token_hex(16)

    ssm.put_parameter(
        Name=settings.db_password_param,
        Type="SecureString",
        Value=password,
        Overwrite=False,
    )

    return password


def database_exists(rds, identifier: str) -> bool:
    """Return True when the RDS database already exists."""
    try:
        rds.describe_db_instances(
            DBInstanceIdentifier=identifier
        )
        return True
    except ClientError as exc:
        if error_code(exc) == "DBInstanceNotFound":
            return False
        raise


def ensure_database(
    rds,
    settings: Settings,
    db_security_group_id: str,
    password: str,
) -> None:
    """Create the PostgreSQL instance if it is not already present."""
    if database_exists(rds, settings.db_instance_id):
        return

    rds.create_db_instance(
        DBInstanceIdentifier=settings.db_instance_id,
        DBInstanceClass=settings.db_instance_class,
        Engine="postgres",
        AllocatedStorage=20,
        StorageType="gp2",
        MasterUsername=settings.db_user,
        MasterUserPassword=password,
        DBName=settings.db_name,
        DBSubnetGroupName=settings.db_subnet_group_name,
        VpcSecurityGroupIds=[db_security_group_id],
        AvailabilityZone=settings.az_a,
        BackupRetentionPeriod=0,
        MultiAZ=False,
        PubliclyAccessible=False,
        AutoMinorVersionUpgrade=False,
        DeletionProtection=False,
        StorageEncrypted=True,
    )


def write_database_outputs(
    path: str | Path,
    host: str,
    security_group_id: str,
) -> None:
    """Write non-secret database outputs for the application stack."""
    Path(path).write_text(
        f"DB_HOST={host}\n"
        f"DB_SECURITY_GROUP_ID={security_group_id}\n"
    )


def create_database(
    clients: AwsClients,
    settings: Settings,
    output_path: str | Path = "db_outputs.env",
    wait: bool = True,
) -> dict[str, str]:
    """Create all database resources idempotently."""

    vpc_id = find_default_vpc(clients.ec2)
    subnet_a = find_subnet(
        clients.ec2, vpc_id, settings.az_a
    )
    subnet_b = find_subnet(
        clients.ec2, vpc_id, settings.az_b
    )

    db_security_group_id = ensure_db_security_group(
        clients.ec2,
        settings,
        vpc_id,
    )

    ensure_db_subnet_group(
        clients.rds,
        settings,
        subnet_a,
        subnet_b,
    )

    password = ensure_db_password(
        clients.ssm,
        settings,
    )

    ensure_database(
        clients.rds,
        settings,
        db_security_group_id,
        password,
    )

    # Do not keep the password longer than necessary.
    password = None

    if wait:
        waiter = clients.rds.get_waiter(
            "db_instance_available"
        )
        waiter.wait(
            DBInstanceIdentifier=settings.db_instance_id
        )

    response = clients.rds.describe_db_instances(
        DBInstanceIdentifier=settings.db_instance_id
    )
    instance = response["DBInstances"][0]

    host = instance.get("Endpoint", {}).get(
        "Address",
        "",
    )

    write_database_outputs(
        output_path,
        host,
        db_security_group_id,
    )

    return {
        "DB_HOST": host,
        "DB_SECURITY_GROUP_ID": db_security_group_id,
    }


def delete_db_instance(
    rds,
    settings: Settings,
    wait: bool = True,
) -> None:
    """Delete the RDS instance without snapshots or retained backups."""
    try:
        rds.describe_db_instances(
            DBInstanceIdentifier=settings.db_instance_id
        )
    except ClientError as exc:
        if error_code(exc) == "DBInstanceNotFound":
            return
        raise

    try:
        rds.delete_db_instance(
            DBInstanceIdentifier=settings.db_instance_id,
            SkipFinalSnapshot=True,
            DeleteAutomatedBackups=True,
        )
    except ClientError as exc:
        if error_code(exc) not in {
            "DBInstanceNotFound",
            "InvalidDBInstanceState",
        }:
            raise

    if wait:
        try:
            waiter = rds.get_waiter(
                "db_instance_deleted"
            )
            waiter.wait(
                DBInstanceIdentifier=settings.db_instance_id
            )
        except ClientError as exc:
            if error_code(exc) != "DBInstanceNotFound":
                raise


def delete_db_subnet_group(
    rds,
    settings: Settings,
) -> None:
    """Delete the database subnet group when present."""
    try:
        rds.delete_db_subnet_group(
            DBSubnetGroupName=settings.db_subnet_group_name
        )
    except ClientError as exc:
        if error_code(exc) != "DBSubnetGroupNotFoundFault":
            raise


def delete_db_security_group(
    ec2,
    settings: Settings,
    retries: int = 10,
    delay: int = 15,
) -> None:
    """Delete the database security group, retrying dependencies."""
    response = ec2.describe_security_groups(
        Filters=[
            {
                "Name": "group-name",
                "Values": [settings.db_sg_name],
            }
        ]
    )

    if not response["SecurityGroups"]:
        return

    group_id = response["SecurityGroups"][0]["GroupId"]

    for attempt in range(retries):
        try:
            ec2.delete_security_group(
                GroupId=group_id
            )
            return
        except ClientError as exc:
            code = error_code(exc)

            if code == "InvalidGroup.NotFound":
                return

            if code != "DependencyViolation":
                raise

            if attempt == retries - 1:
                raise

            time.sleep(delay)


def delete_password_parameter(
    ssm,
    settings: Settings,
) -> None:
    """Delete the database password SecureString when present."""
    try:
        ssm.delete_parameter(
            Name=settings.db_password_param
        )
    except ClientError as exc:
        if error_code(exc) != "ParameterNotFound":
            raise


def delete_database(
    clients: AwsClients,
    settings: Settings,
    output_path: str | Path = "db_outputs.env",
    wait: bool = True,
) -> None:
    """Delete all Lab 06 database resources safely."""

    delete_db_instance(
        clients.rds,
        settings,
        wait=wait,
    )

    delete_db_subnet_group(
        clients.rds,
        settings,
    )

    delete_db_security_group(
        clients.ec2,
        settings,
        retries=10 if wait else 1,
        delay=15 if wait else 0,
    )

    delete_password_parameter(
        clients.ssm,
        settings,
    )

    Path(output_path).unlink(
        missing_ok=True
    )
