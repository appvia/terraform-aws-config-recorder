"""AWS client helpers used by the Lambda function."""

from __future__ import annotations

import json
from typing import Any

import boto3
from logger import logger

# Initialize the AWS clients
sts = boto3.client("sts")


def _control_tower_config_recorder_session_policy(account_id: str) -> dict[str, Any]:
    """
    Inline session policy for sts:AssumeRole into AWSControlTowerExecution.

    PutConfigurationRecorder requires iam:PassRole on the Config service-linked
    role; the session policy must allow that in addition to Config APIs or AWS
    denies PassRole even when the execution role grants it.
    """
    config_slr_arn = (
        f"arn:aws:iam::{account_id}:role/aws-service-role/"
        "config.amazonaws.com/AWSServiceRoleForConfig"
    )
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "RestrictToConfigRecorderOps",
                "Effect": "Allow",
                "Action": [
                    "config:DescribeConfigurationRecorders",
                    "config:DescribeConfigurationRecorderStatus",
                    "config:PutConfigurationRecorder",
                ],
                "Resource": "*",
            },
            {
                "Sid": "PassConfigServiceLinkedRole",
                "Effect": "Allow",
                "Action": "iam:PassRole",
                "Resource": config_slr_arn,
            },
        ],
    }


def _assume_control_tower_execution_role(
    role_arn: str, account_id: str
) -> dict[str, Any]:
    """
    Assume the Control Tower execution role with a mandatory inline session policy.

    The Policy argument is always set so temporary credentials cannot exceed the
    actions declared in _control_tower_config_recorder_session_policy.
    """

    policy = json.dumps(_control_tower_config_recorder_session_policy(account_id))
    return sts.assume_role(
        RoleArn=role_arn,
        RoleSessionName="ConfigRecorderConfigurator",
        Policy=policy,
    )


def get_config_client(
    account_id: str,
    role_arn: str,
    region: str,
) -> Any:
    """
    Use the STS AssumeRole API to assume into the AWSControlTowerExecution
    role for the given account and return a Config service boto3 client.

    Args:
        account_id: The account id to assume into
        role_arn: The role ARN to assume into
        region: The Config API region for the returned client

    Returns:
        A config boto3 client

    Raises:
        Exception: If the credentials cannot be assumed
    """

    logger.debug(
        "Assuming into the AWSControlTowerExecution role for the given account",
        extra={
            "action": "get_control_tower_execution_role",
            "account_id": account_id,
            "role_arn": role_arn,
            "region": region,
        },
    )

    response = _assume_control_tower_execution_role(role_arn, account_id)

    return boto3.client(
        "config",
        aws_access_key_id=response["Credentials"]["AccessKeyId"],
        aws_secret_access_key=response["Credentials"]["SecretAccessKey"],
        aws_session_token=response["Credentials"]["SessionToken"],
        region_name=region,
    )
