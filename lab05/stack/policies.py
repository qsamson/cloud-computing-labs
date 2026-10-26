"""IAM policy documents as plain Python dictionaries.

Keeping them as pure functions means we can test them without touching AWS.
"""

from __future__ import annotations


OBJECT_KEY = "shared.txt"


def trust_policy() -> dict:
    """Who may assume the role: the EC2 service, nobody else."""
    return {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {
                "Service": "ec2.amazonaws.com"
            },
            "Action": "sts:AssumeRole",
        }],
    }


def uploader_policy(bucket: str) -> dict:
    """Write one object and nothing else."""
    return {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": ["s3:PutObject"],
            "Resource": (
                f"arn:aws:s3:::{bucket}/{OBJECT_KEY}"
            ),
        }],
    }


def viewer_policy(bucket: str) -> dict:
    """Read one object, and list the bucket."""
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["s3:GetObject"],
                "Resource": (
                    f"arn:aws:s3:::{bucket}/{OBJECT_KEY}"
                ),
            },
            {
                "Effect": "Allow",
                "Action": ["s3:ListBucket"],
                "Resource": (
                    f"arn:aws:s3:::{bucket}"
                ),
            },
        ],
    }


def policy_for(
    tier_name: str,
    bucket: str,
) -> dict:
    return {
        "uploader": uploader_policy,
        "viewer": viewer_policy,
    }[tier_name](bucket)
