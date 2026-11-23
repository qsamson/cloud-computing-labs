"""DynamoDB resources for the Weather Advisor final project."""

from __future__ import annotations

from botocore.exceptions import ClientError


def error_code(exc: ClientError) -> str:
    return exc.response.get("Error", {}).get("Code", "")


def ensure_table(dynamodb, name: str, key_name: str) -> None:
    """Create one on-demand DynamoDB table if it does not exist."""
    try:
        dynamodb.describe_table(
            TableName=name
        )
        return
    except ClientError as exc:
        if error_code(exc) != "ResourceNotFoundException":
            raise

    dynamodb.create_table(
        TableName=name,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {
                "AttributeName": key_name,
                "AttributeType": "S",
            }
        ],
        KeySchema=[
            {
                "AttributeName": key_name,
                "KeyType": "HASH",
            }
        ],
    )

    dynamodb.get_waiter(
        "table_exists"
    ).wait(
        TableName=name
    )

    dynamodb.update_time_to_live(
        TableName=name,
        TimeToLiveSpecification={
            "Enabled": True,
            "AttributeName": "expires_at",
        },
    )


def delete_table(dynamodb, name: str) -> None:
    """Delete a DynamoDB table and tolerate an already-deleted table."""
    try:
        dynamodb.delete_table(
            TableName=name
        )
    except ClientError as exc:
        if error_code(exc) != "ResourceNotFoundException":
            raise


def table_arn(
    region: str,
    account_id: str,
    table_name: str,
) -> str:
    return (
        f"arn:aws:dynamodb:{region}:"
        f"{account_id}:table/{table_name}"
    )


def ensure_topic(sns, name: str) -> str:
    """Create or return the single Weather Advisor SNS topic."""
    response = sns.create_topic(
        Name=name
    )
    return response["TopicArn"]


def delete_topic(sns, topic_arn: str | None) -> None:
    """Delete the SNS topic when it exists."""
    if not topic_arn:
        return

    try:
        sns.delete_topic(
            TopicArn=topic_arn
        )
    except ClientError as exc:
        if error_code(exc) not in {
            "NotFound",
            "NotFoundException",
        }:
            raise
