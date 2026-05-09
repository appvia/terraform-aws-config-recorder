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

        self.assertEqual(
            kwargs["Policy"],
            json.dumps(self.client.CONTROL_TOWER_CONFIG_RECORDER_SESSION_POLICY),
        )

        policy = json.loads(kwargs["Policy"])
        statement = policy["Statement"][0]
        self.assertEqual(statement["Effect"], "Allow")
        self.assertEqual(statement["Resource"], "*")
        self.assertCountEqual(
            statement["Action"],
            [
                "config:DescribeConfigurationRecorders",
                "config:DescribeConfigurationRecorderStatus",
                "config:PutConfigurationRecorder",
            ],
        )

    def test_session_policy_constant_is_non_empty_document(self) -> None:
        doc = self.client.CONTROL_TOWER_CONFIG_RECORDER_SESSION_POLICY
        self.assertEqual(doc.get("Version"), "2012-10-17")
        self.assertIsInstance(doc.get("Statement"), list)
        self.assertGreaterEqual(len(doc["Statement"]), 1)
