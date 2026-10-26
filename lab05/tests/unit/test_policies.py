"""Least privilege, checked as code. These tests need no AWS account."""

from stack.policies import policy_for, trust_policy


BUCKET = "my-bucket"


def _allowed_actions(policy):
    actions = []

    for statement in policy["Statement"]:
        assert statement["Effect"] == "Allow"
        actions += statement["Action"]

    return actions


def test_trust_policy_only_trusts_ec2():
    statement = trust_policy()["Statement"][0]

    assert statement["Principal"] == {
        "Service": "ec2.amazonaws.com"
    }

    assert statement["Action"] == "sts:AssumeRole"


def test_uploader_can_only_put_one_object():
    policy = policy_for("uploader", BUCKET)

    assert _allowed_actions(policy) == [
        "s3:PutObject"
    ]

    assert policy["Statement"][0]["Resource"] == (
        f"arn:aws:s3:::{BUCKET}/shared.txt"
    )


def test_viewer_can_read_but_never_write():
    actions = _allowed_actions(
        policy_for("viewer", BUCKET)
    )

    assert "s3:GetObject" in actions

    assert not any(
        action in actions
        for action in (
            "s3:PutObject",
            "s3:DeleteObject",
            "s3:*",
            "*",
        )
    )


def test_no_policy_uses_a_wildcard_resource():
    for tier in ("uploader", "viewer"):
        for statement in policy_for(
            tier,
            BUCKET,
        )["Statement"]:
            assert statement["Resource"] != "*"
