"""One place that builds the boto3 clients the stack needs."""

from __future__ import annotations

from dataclasses import dataclass

import boto3


@dataclass
class AwsClients:
    s3: object
    iam: object
    ec2: object
    elbv2: object
    autoscaling: object

    @classmethod
    def create(cls, region: str) -> "AwsClients":
        session = boto3.session.Session(
            region_name=region
        )

        return cls(
            s3=session.client("s3"),
            iam=session.client("iam"),
            ec2=session.client("ec2"),
            elbv2=session.client("elbv2"),
            autoscaling=session.client("autoscaling"),
        )
