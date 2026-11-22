"""AWS infrastructure for the Lab 06 Weather Advisor application."""

from __future__ import annotations

import json
import time
from pathlib import Path

from botocore.exceptions import ClientError

from .clients import AwsClients
from .config import Settings, load_dotenv
from .database import (
    error_code,
    find_default_vpc,
    find_subnet,
)
from .weather import (
    advisor_policy,
    build_advisor_user_data,
    build_weather_user_data,
    ec2_trust_policy,
    launch_template_data,
    weather_policy,
)


def ensure_gemini_parameter(
    ssm,
    settings: Settings,
    value: str | None = None,
) -> None:
    """Ensure the Gemini API key exists as an SSM SecureString."""
    try:
        ssm.get_parameter(Name=settings.gemini_param_name)
        return
    except ClientError as exc:
        if error_code(exc) != "ParameterNotFound":
            raise

    if not value:
        raise RuntimeError(
            "Gemini API key parameter does not exist."
        )

    ssm.put_parameter(
        Name=settings.gemini_param_name,
        Type="SecureString",
        Value=value,
        Overwrite=False,
    )


def ensure_role_and_profile(
    iam,
    role_name: str,
    profile_name: str,
) -> None:
    """Create one EC2 role and instance profile idempotently."""
    try:
        iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(
                ec2_trust_policy()
            ),
        )
    except ClientError as exc:
        if error_code(exc) != "EntityAlreadyExists":
            raise

    try:
        iam.create_instance_profile(
            InstanceProfileName=profile_name
        )
    except ClientError as exc:
        if error_code(exc) != "EntityAlreadyExists":
            raise

    profile = iam.get_instance_profile(
        InstanceProfileName=profile_name
    )["InstanceProfile"]

    attached_roles = {
        role["RoleName"]
        for role in profile.get("Roles", [])
    }

    if role_name not in attached_roles:
        iam.add_role_to_instance_profile(
            InstanceProfileName=profile_name,
            RoleName=role_name,
        )


def put_secret_policies(
    iam,
    settings: Settings,
    account_id: str,
) -> None:
    """Attach one-secret-only inline policies to both roles."""
    iam.put_role_policy(
        RoleName=settings.weather.role_name,
        PolicyName=f"{settings.weather.role_name}-policy",
        PolicyDocument=json.dumps(
            weather_policy(settings, account_id)
        ),
    )

    iam.put_role_policy(
        RoleName=settings.advisor.role_name,
        PolicyName=f"{settings.advisor.role_name}-policy",
        PolicyDocument=json.dumps(
            advisor_policy(settings, account_id)
        ),
    )


def ensure_alb_security_group(
    ec2,
    settings: Settings,
    vpc_id: str,
) -> str:
    """Create the ALB security group and public listener rules."""
    response = ec2.describe_security_groups(
        Filters=[
            {
                "Name": "group-name",
                "Values": [settings.alb_sg_name],
            },
            {
                "Name": "vpc-id",
                "Values": [vpc_id],
            },
        ]
    )

    if response["SecurityGroups"]:
        sg_id = response["SecurityGroups"][0]["GroupId"]
    else:
        created = ec2.create_security_group(
            GroupName=settings.alb_sg_name,
            Description="Lab 06 public ALB listener access",
            VpcId=vpc_id,
        )
        sg_id = created["GroupId"]

    for port in (
        settings.weather.listener_port,
        settings.advisor.listener_port,
    ):
        try:
            ec2.authorize_security_group_ingress(
                GroupId=sg_id,
                IpProtocol="tcp",
                FromPort=port,
                ToPort=port,
                CidrIp="0.0.0.0/0",
            )
        except ClientError as exc:
            if error_code(exc) != "InvalidPermission.Duplicate":
                raise

    return sg_id


def restrict_app_security_group(
    ec2,
    settings: Settings,
    alb_sg_id: str,
) -> None:
    """Allow application port 3000 only from the ALB SG."""
    try:
        ec2.revoke_security_group_ingress(
            GroupId=settings.app_sg_id,
            IpProtocol="tcp",
            FromPort=3000,
            ToPort=3000,
            CidrIp="0.0.0.0/0",
        )
    except ClientError as exc:
        if error_code(exc) not in {
            "InvalidPermission.NotFound",
            "InvalidGroup.NotFound",
        }:
            raise

    try:
        ec2.authorize_security_group_ingress(
            GroupId=settings.app_sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 3000,
                    "ToPort": 3000,
                    "UserIdGroupPairs": [
                        {"GroupId": alb_sg_id}
                    ],
                }
            ],
        )
    except ClientError as exc:
        if error_code(exc) != "InvalidPermission.Duplicate":
            raise


def ensure_target_group(
    elbv2,
    name: str,
    vpc_id: str,
) -> str:
    """Return an existing target group ARN or create it."""
    try:
        result = elbv2.describe_target_groups(
            Names=[name]
        )
        return result["TargetGroups"][0]["TargetGroupArn"]
    except ClientError as exc:
        if error_code(exc) != "TargetGroupNotFound":
            raise

    created = elbv2.create_target_group(
        Name=name,
        Protocol="HTTP",
        Port=3000,
        VpcId=vpc_id,
        TargetType="instance",
        HealthCheckProtocol="HTTP",
        HealthCheckPath="/",
        HealthCheckIntervalSeconds=10,
        HealthCheckTimeoutSeconds=5,
        HealthyThresholdCount=2,
        UnhealthyThresholdCount=2,
    )

    return created["TargetGroups"][0]["TargetGroupArn"]


def ensure_load_balancer(
    elbv2,
    settings: Settings,
    subnet_a: str,
    subnet_b: str,
    alb_sg_id: str,
    wait: bool = True,
) -> tuple[str, str]:
    """Create or find the Application Load Balancer."""
    try:
        result = elbv2.describe_load_balancers(
            Names=[settings.alb_name]
        )
        lb = result["LoadBalancers"][0]
    except ClientError as exc:
        if error_code(exc) != "LoadBalancerNotFound":
            raise

        created = elbv2.create_load_balancer(
            Name=settings.alb_name,
            Subnets=[subnet_a, subnet_b],
            SecurityGroups=[alb_sg_id],
            Scheme="internet-facing",
            Type="application",
            IpAddressType="ipv4",
        )
        lb = created["LoadBalancers"][0]

    arn = lb["LoadBalancerArn"]

    if wait:
        elbv2.get_waiter(
            "load_balancer_available"
        ).wait(
            LoadBalancerArns=[arn]
        )

        lb = elbv2.describe_load_balancers(
            LoadBalancerArns=[arn]
        )["LoadBalancers"][0]

    return arn, lb["DNSName"]


def ensure_listener(
    elbv2,
    alb_arn: str,
    port: int,
    target_group_arn: str,
) -> None:
    """Create one ALB listener when it does not already exist."""
    existing = elbv2.describe_listeners(
        LoadBalancerArn=alb_arn
    )["Listeners"]

    if any(listener["Port"] == port for listener in existing):
        return

    elbv2.create_listener(
        LoadBalancerArn=alb_arn,
        Protocol="HTTP",
        Port=port,
        DefaultActions=[
            {
                "Type": "forward",
                "TargetGroupArn": target_group_arn,
            }
        ],
    )


def ensure_launch_template(
    ec2,
    name: str,
    data: dict,
) -> None:
    """Create a launch template once, without duplicate versions."""
    try:
        ec2.describe_launch_templates(
            LaunchTemplateNames=[name]
        )
        return
    except ClientError as exc:
        if error_code(exc) != "InvalidLaunchTemplateName.NotFoundException":
            raise

    ec2.create_launch_template(
        LaunchTemplateName=name,
        LaunchTemplateData=data,
    )


def ensure_asg(
    autoscaling,
    *,
    name: str,
    launch_template_name: str,
    target_group_arn: str,
    subnet_a: str,
    subnet_b: str,
    tag_name: str,
) -> None:
    """Create a single-instance Auto Scaling Group idempotently."""
    response = autoscaling.describe_auto_scaling_groups(
        AutoScalingGroupNames=[name]
    )

    if response["AutoScalingGroups"]:
        return

    autoscaling.create_auto_scaling_group(
        AutoScalingGroupName=name,
        LaunchTemplate={
            "LaunchTemplateName": launch_template_name,
            "Version": "$Latest",
        },
        MinSize=1,
        MaxSize=1,
        DesiredCapacity=1,
        VPCZoneIdentifier=f"{subnet_a},{subnet_b}",
        TargetGroupARNs=[target_group_arn],
        HealthCheckType="ELB",
        HealthCheckGracePeriod=120,
        Tags=[
            {
                "ResourceId": name,
                "ResourceType": "auto-scaling-group",
                "Key": "Name",
                "Value": tag_name,
                "PropagateAtLaunch": True,
            }
        ],
    )


def read_app_files(app_dir: Path) -> tuple[str, str]:
    """Read app.js and package.json for one application tier."""
    return (
        (app_dir / "app.js").read_text(),
        (app_dir / "package.json").read_text(),
    )


def create_weather_stack(
    clients: AwsClients,
    settings: Settings,
    *,
    gemini_key: str | None = None,
    db_outputs_path: str | Path = "db_outputs.env",
    stack_outputs_path: str | Path = "stack_outputs.env",
    wait: bool = True,
) -> dict[str, str]:
    """Create the complete two-tier Weather Advisor stack."""

    ensure_gemini_parameter(
        clients.ssm,
        settings,
        gemini_key,
    )

    db_values = load_dotenv(db_outputs_path)

    if not db_values.get("DB_HOST"):
        raise RuntimeError(
            "db_outputs.env is missing DB_HOST. "
            "Run create_database.py first."
        )

    db_host = db_values["DB_HOST"]

    account_id = clients.sts.get_caller_identity()["Account"]

    ensure_role_and_profile(
        clients.iam,
        settings.weather.role_name,
        settings.weather.profile_name,
    )
    ensure_role_and_profile(
        clients.iam,
        settings.advisor.role_name,
        settings.advisor.profile_name,
    )

    put_secret_policies(
        clients.iam,
        settings,
        account_id,
    )

    vpc_id = find_default_vpc(clients.ec2)
    subnet_a = find_subnet(
        clients.ec2,
        vpc_id,
        settings.az_a,
    )
    subnet_b = find_subnet(
        clients.ec2,
        vpc_id,
        settings.az_b,
    )

    alb_sg_id = ensure_alb_security_group(
        clients.ec2,
        settings,
        vpc_id,
    )

    restrict_app_security_group(
        clients.ec2,
        settings,
        alb_sg_id,
    )

    weather_tg_arn = ensure_target_group(
        clients.elbv2,
        settings.weather.tg_name,
        vpc_id,
    )

    advisor_tg_arn = ensure_target_group(
        clients.elbv2,
        settings.advisor.tg_name,
        vpc_id,
    )

    # ALB is intentionally created before launch templates.
    alb_arn, alb_dns_name = ensure_load_balancer(
        clients.elbv2,
        settings,
        subnet_a,
        subnet_b,
        alb_sg_id,
        wait=wait,
    )

    ensure_listener(
        clients.elbv2,
        alb_arn,
        settings.weather.listener_port,
        weather_tg_arn,
    )

    ensure_listener(
        clients.elbv2,
        alb_arn,
        settings.advisor.listener_port,
        advisor_tg_arn,
    )

    weather_js, weather_pkg = read_app_files(
        settings.weather.app_dir
    )
    advisor_js, advisor_pkg = read_app_files(
        settings.advisor.app_dir
    )

    weather_ud = build_weather_user_data(
        settings,
        db_host,
        weather_js,
        weather_pkg,
    )

    advisor_ud = build_advisor_user_data(
        settings,
        alb_dns_name,
        advisor_js,
        advisor_pkg,
    )

    if len(weather_ud.encode("utf-8")) >= 16 * 1024:
        raise RuntimeError(
            "Weather user-data exceeds the 16 KB EC2 limit."
        )

    if len(advisor_ud.encode("utf-8")) >= 16 * 1024:
        raise RuntimeError(
            "Advisor user-data exceeds the 16 KB EC2 limit."
        )

    ensure_launch_template(
        clients.ec2,
        settings.weather.lt_name,
        launch_template_data(
            settings,
            settings.weather.profile_name,
            weather_ud,
            "weather-app",
        ),
    )

    ensure_launch_template(
        clients.ec2,
        settings.advisor.lt_name,
        launch_template_data(
            settings,
            settings.advisor.profile_name,
            advisor_ud,
            "advisor-app",
        ),
    )

    ensure_asg(
        clients.autoscaling,
        name=settings.weather.asg_name,
        launch_template_name=settings.weather.lt_name,
        target_group_arn=weather_tg_arn,
        subnet_a=subnet_a,
        subnet_b=subnet_b,
        tag_name="weather-app",
    )

    ensure_asg(
        clients.autoscaling,
        name=settings.advisor.asg_name,
        launch_template_name=settings.advisor.lt_name,
        target_group_arn=advisor_tg_arn,
        subnet_a=subnet_a,
        subnet_b=subnet_b,
        tag_name="advisor-app",
    )

    outputs = {
        "VPC_ID": vpc_id,
        "SUBNET_A": subnet_a,
        "SUBNET_B": subnet_b,
        "ALB_SECURITY_GROUP_ID": alb_sg_id,
        "ALB_ARN": alb_arn,
        "ALB_DNS_NAME": alb_dns_name,
        "WEATHER_TG_ARN": weather_tg_arn,
        "ADVISOR_TG_ARN": advisor_tg_arn,
    }

    Path(stack_outputs_path).write_text(
        "".join(
            f"{key}={value}\n"
            for key, value in outputs.items()
        )
    )

    return outputs


def delete_asg(autoscaling, name: str, wait: bool = True) -> None:
    """Delete an ASG and tolerate one that is already gone."""
    response = autoscaling.describe_auto_scaling_groups(
        AutoScalingGroupNames=[name]
    )

    if not response["AutoScalingGroups"]:
        return

    autoscaling.delete_auto_scaling_group(
        AutoScalingGroupName=name,
        ForceDelete=True,
    )

    if not wait:
        return

    for _ in range(20):
        current = autoscaling.describe_auto_scaling_groups(
            AutoScalingGroupNames=[name]
        )
        if not current["AutoScalingGroups"]:
            return
        time.sleep(15)


def delete_load_balancer(
    elbv2,
    name: str,
    wait: bool = True,
) -> None:
    """Delete the ALB if present."""
    try:
        result = elbv2.describe_load_balancers(
            Names=[name]
        )
    except ClientError as exc:
        if error_code(exc) == "LoadBalancerNotFound":
            return
        raise

    arn = result["LoadBalancers"][0]["LoadBalancerArn"]

    elbv2.delete_load_balancer(
        LoadBalancerArn=arn
    )

    if wait:
        try:
            elbv2.get_waiter(
                "load_balancers_deleted"
            ).wait(
                LoadBalancerArns=[arn]
            )
        except ClientError as exc:
            if error_code(exc) != "LoadBalancerNotFound":
                raise


def delete_target_group(elbv2, name: str) -> None:
    """Delete one target group when present."""
    try:
        result = elbv2.describe_target_groups(
            Names=[name]
        )
    except ClientError as exc:
        if error_code(exc) == "TargetGroupNotFound":
            return
        raise

    try:
        elbv2.delete_target_group(
            TargetGroupArn=result["TargetGroups"][0]["TargetGroupArn"]
        )
    except ClientError as exc:
        if error_code(exc) != "TargetGroupNotFound":
            raise


def delete_launch_template(ec2, name: str) -> None:
    """Delete a launch template when present."""
    try:
        ec2.delete_launch_template(
            LaunchTemplateName=name
        )
    except ClientError as exc:
        if error_code(exc) != "InvalidLaunchTemplateName.NotFoundException":
            raise


def delete_role_and_profile(
    iam,
    role_name: str,
    profile_name: str,
) -> None:
    """Remove one inline policy, profile and IAM role safely."""
    try:
        profile = iam.get_instance_profile(
            InstanceProfileName=profile_name
        )["InstanceProfile"]

        for role in profile.get("Roles", []):
            iam.remove_role_from_instance_profile(
                InstanceProfileName=profile_name,
                RoleName=role["RoleName"],
            )

        iam.delete_instance_profile(
            InstanceProfileName=profile_name
        )
    except ClientError as exc:
        if error_code(exc) != "NoSuchEntity":
            raise

    try:
        iam.delete_role_policy(
            RoleName=role_name,
            PolicyName=f"{role_name}-policy",
        )
    except ClientError as exc:
        if error_code(exc) != "NoSuchEntity":
            raise

    try:
        iam.delete_role(RoleName=role_name)
    except ClientError as exc:
        if error_code(exc) != "NoSuchEntity":
            raise


def restore_app_security_group(
    ec2,
    settings: Settings,
    alb_sg_id: str | None,
) -> None:
    """Restore direct port 3000 access used by the earlier labs."""
    if alb_sg_id:
        try:
            ec2.revoke_security_group_ingress(
                GroupId=settings.app_sg_id,
                IpPermissions=[
                    {
                        "IpProtocol": "tcp",
                        "FromPort": 3000,
                        "ToPort": 3000,
                        "UserIdGroupPairs": [
                            {"GroupId": alb_sg_id}
                        ],
                    }
                ],
            )
        except ClientError as exc:
            if error_code(exc) != "InvalidPermission.NotFound":
                raise

    try:
        ec2.authorize_security_group_ingress(
            GroupId=settings.app_sg_id,
            IpProtocol="tcp",
            FromPort=3000,
            ToPort=3000,
            CidrIp="0.0.0.0/0",
        )
    except ClientError as exc:
        if error_code(exc) != "InvalidPermission.Duplicate":
            raise


def delete_alb_security_group(
    ec2,
    settings: Settings,
    retries: int = 10,
    delay: int = 15,
) -> None:
    """Delete the ALB security group after ENIs are released."""
    response = ec2.describe_security_groups(
        Filters=[
            {
                "Name": "group-name",
                "Values": [settings.alb_sg_name],
            }
        ]
    )

    if not response["SecurityGroups"]:
        return

    sg_id = response["SecurityGroups"][0]["GroupId"]

    for attempt in range(retries):
        try:
            ec2.delete_security_group(GroupId=sg_id)
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


def delete_weather_stack(
    clients: AwsClients,
    settings: Settings,
    *,
    stack_outputs_path: str | Path = "stack_outputs.env",
    wait: bool = True,
) -> None:
    """Delete all EC2/ALB/IAM resources for the weather stack."""

    values = {}
    path = Path(stack_outputs_path)

    if path.exists():
        values = load_dotenv(path)

    alb_sg_id = values.get("ALB_SECURITY_GROUP_ID")

    delete_asg(
        clients.autoscaling,
        settings.weather.asg_name,
        wait=wait,
    )
    delete_asg(
        clients.autoscaling,
        settings.advisor.asg_name,
        wait=wait,
    )

    delete_load_balancer(
        clients.elbv2,
        settings.alb_name,
        wait=wait,
    )

    delete_target_group(
        clients.elbv2,
        settings.weather.tg_name,
    )
    delete_target_group(
        clients.elbv2,
        settings.advisor.tg_name,
    )

    restore_app_security_group(
        clients.ec2,
        settings,
        alb_sg_id,
    )

    delete_alb_security_group(
        clients.ec2,
        settings,
        retries=10 if wait else 1,
        delay=15 if wait else 0,
    )

    delete_launch_template(
        clients.ec2,
        settings.weather.lt_name,
    )
    delete_launch_template(
        clients.ec2,
        settings.advisor.lt_name,
    )

    delete_role_and_profile(
        clients.iam,
        settings.weather.role_name,
        settings.weather.profile_name,
    )
    delete_role_and_profile(
        clients.iam,
        settings.advisor.role_name,
        settings.advisor.profile_name,
    )

    path.unlink(missing_ok=True)
