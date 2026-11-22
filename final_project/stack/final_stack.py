"""Final-project AWS stack for Weather Advisor."""

from __future__ import annotations

from pathlib import Path

from .config import Settings
from .database import find_default_vpc, find_subnet
from .final_resources import ensure_table, delete_table
from .weather import (
    build_advisor_user_data,
    build_weather_user_data,
    launch_template_data,
)
from .weather_stack import (
    delete_alb_security_group,
    delete_asg,
    delete_launch_template,
    delete_load_balancer,
    delete_role_and_profile,
    delete_target_group,
    ensure_alb_security_group,
    ensure_asg,
    ensure_gemini_parameter,
    ensure_launch_template,
    ensure_listener,
    ensure_load_balancer,
    ensure_role_and_profile,
    ensure_target_group,
    put_secret_policies,
    read_app_files,
    restrict_app_security_group,
    restore_app_security_group,
)


def ensure_email_identity(ses, email: str) -> str:
    """Request SES verification for the configured sender if needed."""
    result = ses.get_identity_verification_attributes(
        Identities=[email]
    )

    status = (
        result.get("VerificationAttributes", {})
        .get(email, {})
        .get("VerificationStatus", "NotStarted")
    )

    if status != "Success":
        ses.verify_email_identity(
            EmailAddress=email
        )

    return status


def create_final_stack(
    clients,
    settings: Settings,
    *,
    gemini_key: str | None = None,
    stack_outputs_path: str | Path = "stack_outputs.env",
    wait: bool = True,
) -> dict[str, str]:
    """Create the complete final-project stack."""

    ensure_gemini_parameter(
        clients.ssm,
        settings,
        gemini_key,
    )

    ensure_table(
        clients.dynamodb,
        settings.facts_table,
        "cache_key",
    )

    ensure_table(
        clients.dynamodb,
        settings.advisor_table,
        "item_key",
    )

    ensure_email_identity(
        clients.ses,
        settings.ses_from_email,
    )

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

    vpc_id = find_default_vpc(
        clients.ec2
    )

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
            "Weather user-data exceeds EC2 16 KB limit."
        )

    if len(advisor_ud.encode("utf-8")) >= 16 * 1024:
        raise RuntimeError(
            "Advisor user-data exceeds EC2 16 KB limit."
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
        "FACTS_TABLE": settings.facts_table,
        "ADVISOR_TABLE": settings.advisor_table,
    }

    Path(stack_outputs_path).write_text(
        "".join(
            f"{key}={value}\n"
            for key, value in outputs.items()
        )
    )

    return outputs


def delete_final_stack(
    clients,
    settings: Settings,
    *,
    stack_outputs_path: str | Path = "stack_outputs.env",
    wait: bool = True,
) -> None:
    """Delete final-project AWS resources safely."""

    values = {}
    path = Path(stack_outputs_path)

    if path.exists():
        for raw in path.read_text().splitlines():
            if "=" in raw:
                key, value = raw.split("=", 1)
                values[key] = value

    alb_sg_id = values.get(
        "ALB_SECURITY_GROUP_ID"
    )

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

    delete_table(
        clients.dynamodb,
        settings.facts_table,
    )

    delete_table(
        clients.dynamodb,
        settings.advisor_table,
    )

    path.unlink(
        missing_ok=True
    )
