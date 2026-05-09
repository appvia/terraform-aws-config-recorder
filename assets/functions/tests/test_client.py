"""Unit tests for `client.py`."""

import json
import unittest
from unittest.mock import MagicMock

from tests.test_support import (
    ensure_recorder_dir_on_path,
    load_module_from_path,
    temporarily_set_sys_module,
)


def _load_client_module():
    """
    Load recorder/client.py as a module, while ensuring:
    - boto3 is mocked so no AWS calls happen at import time
    """
    recorder_dir = ensure_recorder_dir_on_path()

    sts_client = MagicMock(name="sts_client")
    config_client = MagicMock(name="config_client")
    boto3_mod = MagicMock(name="boto3")

    def _client(service_name: str, **_kwargs):
        if service_name == "sts":
            return sts_client
        if service_name == "config":
            return config_client
        raise AssertionError(f"Unexpected boto3 client requested: {service_name}")

    boto3_mod.client.side_effect = _client

    # Default STS response
    sts_client.assume_role.return_value = {
        "Credentials": {
            "AccessKeyId": "ASIAXXXXX",
            "SecretAccessKey": "secret",
            "SessionToken": "token",
        }
    }

    with temporarily_set_sys_module("boto3", boto3_mod):
        client_mod = load_module_from_path(
            "recorder_client", recorder_dir / "client.py"
        )
        client_mod._test_sts_client = sts_client  # type: ignore[attr-defined]
        client_mod._test_config_client = config_client  # type: ignore[attr-defined]
        return client_mod


class TestGetConfigClient(unittest.TestCase):
    def setUp(self) -> None:
        self.client = _load_client_module()

    def test_assume_role_includes_restrictive_session_policy(self) -> None:
        self.client.get_config_client(
            account_id="123456789012",
            role_arn="arn:aws:iam::123456789012:role/AWSControlTowerExecution",
            region="eu-west-2",
        )

        sts_client = self.client._test_sts_client  # type: ignore[attr-defined]
        sts_client.assume_role.assert_called_once()

        kwargs = sts_client.assume_role.call_args.kwargs
        self.assertEqual(
            kwargs["RoleArn"],
            "arn:aws:iam::123456789012:role/AWSControlTowerExecution",
        )
        self.assertEqual(kwargs["RoleSessionName"], "ConfigRecorderConfigurator")
        self.assertIn("Policy", kwargs)

        expected_policy = self.client._control_tower_config_recorder_session_policy(
            "123456789012"
        )
        self.assertEqual(kwargs["Policy"], json.dumps(expected_policy))

        policy = json.loads(kwargs["Policy"])
        self.assertEqual(len(policy["Statement"]), 2)

        config_stmt = policy["Statement"][0]
        self.assertEqual(config_stmt["Effect"], "Allow")
        self.assertEqual(config_stmt["Resource"], "*")
        self.assertCountEqual(
            config_stmt["Action"],
            [
                "config:DescribeConfigurationRecorders",
                "config:DescribeConfigurationRecorderStatus",
                "config:PutConfigurationRecorder",
            ],
        )

        pass_stmt = policy["Statement"][1]
        self.assertEqual(pass_stmt["Sid"], "PassConfigServiceLinkedRole")
        self.assertEqual(pass_stmt["Action"], "iam:PassRole")
        self.assertEqual(
            pass_stmt["Resource"],
            "arn:aws:iam::123456789012:role/aws-service-role/"
            "config.amazonaws.com/AWSServiceRoleForConfig",
        )

    def test_session_policy_includes_pass_role_for_target_account(self) -> None:
        doc = self.client._control_tower_config_recorder_session_policy("999988887777")
        self.assertEqual(doc.get("Version"), "2012-10-17")
        self.assertIsInstance(doc.get("Statement"), list)
        self.assertEqual(len(doc["Statement"]), 2)
        self.assertEqual(
            doc["Statement"][1]["Resource"],
            "arn:aws:iam::999988887777:role/aws-service-role/"
            "config.amazonaws.com/AWSServiceRoleForConfig",
        )
