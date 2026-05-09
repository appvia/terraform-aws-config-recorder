"""Unit tests for `handler.py`."""

import os
import unittest
from unittest.mock import MagicMock

from tests.test_support import (
    ensure_recorder_dir_on_path,
    load_module_from_path,
    temporarily_set_sys_module,
)


def _load_recorder_handler_module():
    """
    Load recorder/handler.py as a module, while ensuring:
    - boto3 is mocked so no AWS calls happen at import time
    """
    recorder_dir = ensure_recorder_dir_on_path()

    # Provide a mocked boto3 module so handler module init doesn't create real clients
    secretsmanager_client = MagicMock(name="secretsmanager_client")
    config_client = MagicMock(
        name="config_client"
    )  # not used directly (assumed role client is)
    organizations_client = MagicMock(name="organizations_client")
    sts_client = MagicMock(name="sts_client")

    # This is the per-member-account config client returned by get_config_client()
    assumed_config_client = MagicMock(name="assumed_config_client")
    boto3_mod = MagicMock(name="boto3")

    def _client(service_name: str):
        if service_name == "secretsmanager":
            return secretsmanager_client
        if service_name == "config":
            return config_client
        if service_name == "organizations":
            return organizations_client
        if service_name == "sts":
            return sts_client
        raise AssertionError(f"Unexpected boto3 client requested: {service_name}")

    boto3_mod.client.side_effect = _client

    # Temporarily override sys.modules for handler imports.
    with temporarily_set_sys_module("boto3", boto3_mod):
        handler_mod = load_module_from_path(
            "recorder_handler", recorder_dir / "handler.py"
        )
        # Attach the mocks so tests can access them easily
        handler_mod._test_secretsmanager_client = secretsmanager_client  # type: ignore[attr-defined]
        handler_mod._test_organizations_client = organizations_client  # type: ignore[attr-defined]
        handler_mod._test_sts_client = sts_client  # type: ignore[attr-defined]
        handler_mod._test_config_client = config_client  # type: ignore[attr-defined]
        handler_mod._test_assumed_config_client = assumed_config_client  # type: ignore[attr-defined]
        return handler_mod


class TestMergeConfigurations(unittest.TestCase):
    def setUp(self) -> None:
        self.handler = _load_recorder_handler_module()
        self.config_types = __import__("config_types")

    def test_merge_configuration_sets_frequency_resources_and_overrides(self) -> None:
        desired = self.config_types.DesiredConfig(
            mode="DAILY",
            resources=["AWS::S3::Bucket"],
            exclude_resources=["AWS::IAM::Role"],
            overrides=[
                self.config_types.Override(
                    description="Record EC2 continuously",
                    override_type="CONTINUOUS",
                    resources=["AWS::EC2::Instance"],
                )
            ],
        )
        existing = {
            "recordingGroup": {
                "allSupported": True,
                "exclusionByResourceTypes": {"resourceTypes": []},
            },
            "recordingMode": {"recordingFrequency": "CONTINUOUS"},
        }

        changed, merged = self.handler.merge_configurations(desired, existing)

        self.assertIs(changed, True)
        self.assertEqual(
            merged["recordingMode"],
            {
                "recordingFrequency": "DAILY",
                "recordingModeOverrides": [
                    {
                        "description": "Record EC2 continuously",
                        "recordingFrequency": "CONTINUOUS",
                        "resourceTypes": ["AWS::EC2::Instance"],
                    }
                ],
            },
        )
        self.assertEqual(merged["recordingGroup"]["resourceTypes"], ["AWS::S3::Bucket"])
        self.assertEqual(
            merged["recordingGroup"]["exclusionByResourceTypes"]["resourceTypes"],
            ["AWS::IAM::Role"],
        )
        self.assertEqual(
            merged["recordingGroup"]["recordingStrategy"]["useOnly"],
            "EXCLUSION_BY_RESOURCE_TYPES",
        )
        self.assertEqual(
            existing,
            {
                "recordingGroup": {
                    "allSupported": True,
                    "exclusionByResourceTypes": {"resourceTypes": []},
                },
                "recordingMode": {"recordingFrequency": "CONTINUOUS"},
            },
        )

    def test_merge_configuration_merges_and_dedupes_resources_exclusions_and_overrides(
        self,
    ) -> None:
        desired = self.config_types.DesiredConfig(
            mode=None,
            resources=["AWS::S3::Bucket", "AWS::EC2::Instance", "AWS::S3::Bucket"],
            exclude_resources=["AWS::IAM::Role", "AWS::KMS::Key", "AWS::IAM::Role"],
            overrides=[
                self.config_types.Override(
                    description="Existing override kept",
                    override_type="CONTINUOUS",
                    resources=["AWS::EC2::Instance"],
                ),
                self.config_types.Override(
                    description="New override added",
                    override_type="DAILY",
                    resources=["AWS::S3::Bucket"],
                ),
            ],
        )
        existing = {
            "recordingGroup": {
                "resourceTypes": ["AWS::Lambda::Function", "AWS::S3::Bucket"],
                "exclusionByResourceTypes": {
                    "resourceTypes": ["AWS::KMS::Key", "AWS::KMS::Key"]
                },
            },
            "recordingMode": {
                "recordingFrequency": "DAILY",
                "recordingModeOverrides": [
                    {
                        "description": "Existing override kept",
                        "recordingFrequency": "CONTINUOUS",
                        "resourceTypes": ["AWS::EC2::Instance"],
                    }
                ],
            },
        }

        changed, merged = self.handler.merge_configurations(desired, existing)

        self.assertIs(changed, True)
        # Existing first, then desired additions; duplicates removed
        self.assertEqual(
            merged["recordingGroup"]["resourceTypes"],
            ["AWS::Lambda::Function", "AWS::S3::Bucket", "AWS::EC2::Instance"],
        )
        self.assertEqual(
            merged["recordingGroup"]["exclusionByResourceTypes"]["resourceTypes"],
            ["AWS::KMS::Key", "AWS::IAM::Role"],
        )
        self.assertEqual(
            merged["recordingGroup"]["recordingStrategy"]["useOnly"],
            "EXCLUSION_BY_RESOURCE_TYPES",
        )
        self.assertEqual(
            merged["recordingMode"]["recordingModeOverrides"],
            [
                {
                    "description": "Existing override kept",
                    "recordingFrequency": "CONTINUOUS",
                    "resourceTypes": ["AWS::EC2::Instance"],
                },
                {
                    "description": "New override added",
                    "recordingFrequency": "DAILY",
                    "resourceTypes": ["AWS::S3::Bucket"],
                },
            ],
        )

    def test_merge_configuration_adds_values_when_existing_has_none(self) -> None:
        desired = self.config_types.DesiredConfig(
            mode=None,
            resources=["AWS::S3::Bucket"],
            exclude_resources=["AWS::IAM::Role"],
            overrides=[
                self.config_types.Override(
                    description="Record EC2 continuously",
                    override_type="CONTINUOUS",
                    resources=["AWS::EC2::Instance"],
                )
            ],
        )
        existing = {
            "recordingGroup": {},
            "recordingMode": {"recordingFrequency": "DAILY"},
        }

        changed, merged = self.handler.merge_configurations(desired, existing)

        self.assertIs(changed, True)
        self.assertEqual(merged["recordingGroup"]["resourceTypes"], ["AWS::S3::Bucket"])
        self.assertEqual(
            merged["recordingGroup"]["exclusionByResourceTypes"]["resourceTypes"],
            ["AWS::IAM::Role"],
        )
        self.assertEqual(
            merged["recordingGroup"]["recordingStrategy"]["useOnly"],
            "EXCLUSION_BY_RESOURCE_TYPES",
        )
        self.assertEqual(
            merged["recordingMode"]["recordingModeOverrides"],
            [
                {
                    "description": "Record EC2 continuously",
                    "recordingFrequency": "CONTINUOUS",
                    "resourceTypes": ["AWS::EC2::Instance"],
                }
            ],
        )

    def test_merge_configuration_does_not_create_duplicate_overrides(self) -> None:
        desired = self.config_types.DesiredConfig(
            mode=None,
            overrides=[
                self.config_types.Override(
                    description="Dup override",
                    override_type="DAILY",
                    resources=["AWS::S3::Bucket", "AWS::EC2::Instance"],
                )
            ],
        )
        existing = {
            "recordingGroup": {},
            "recordingMode": {
                "recordingFrequency": "DAILY",
                "recordingModeOverrides": [
                    {
                        "description": "Dup override",
                        "recordingFrequency": "DAILY",
                        # Intentionally different order to ensure dedupe is stable
                        "resourceTypes": ["AWS::EC2::Instance", "AWS::S3::Bucket"],
                    }
                ],
            },
        }

        changed, merged = self.handler.merge_configurations(desired, existing)

        # Desired overrides replace existing overrides entirely; the resulting
        # list contains only the desired override (with its own resource order).
        self.assertIs(changed, True)
        self.assertEqual(
            merged["recordingMode"]["recordingModeOverrides"],
            [
                {
                    "description": "Dup override",
                    "recordingFrequency": "DAILY",
                    "resourceTypes": ["AWS::S3::Bucket", "AWS::EC2::Instance"],
                },
            ],
        )

    def test_merge_configuration_does_not_create_duplicates_when_desired_only_repeats_existing(
        self,
    ) -> None:
        desired = self.config_types.DesiredConfig(
            mode=None,
            resources=["AWS::S3::Bucket", "AWS::S3::Bucket"],
            exclude_resources=["AWS::KMS::Key", "AWS::KMS::Key"],
            overrides=[],
        )
        existing = {
            "recordingGroup": {
                "resourceTypes": ["AWS::S3::Bucket"],
                "exclusionByResourceTypes": {"resourceTypes": ["AWS::KMS::Key"]},
                "recordingStrategy": {"useOnly": "EXCLUSION_BY_RESOURCE_TYPES"},
            },
            "recordingMode": {"recordingFrequency": "DAILY"},
        }

        changed, merged = self.handler.merge_configurations(desired, existing)

        self.assertIs(changed, False)
        self.assertEqual(merged, existing)

    def test_merge_configuration_returns_unchanged_when_values_match(self) -> None:
        desired = self.config_types.DesiredConfig(
            mode="DAILY",
            overrides=[
                self.config_types.Override(
                    description="Record EC2 continuously",
                    override_type="CONTINUOUS",
                    resources=["AWS::EC2::Instance"],
                )
            ],
        )
        existing = {
            "recordingGroup": {
                "recordingStrategy": {"useOnly": "ALL_SUPPORTED_RESOURCE_TYPES"},
            },
            "recordingMode": {
                "recordingFrequency": "DAILY",
                "recordingModeOverrides": [
                    {
                        "description": "Record EC2 continuously",
                        "recordingFrequency": "CONTINUOUS",
                        "resourceTypes": ["AWS::EC2::Instance"],
                    }
                ],
            },
        }

        changed, merged = self.handler.merge_configurations(desired, existing)

        # Desired overrides replace existing overrides; when they match exactly
        # the merged configuration is unchanged.
        self.assertIs(changed, False)
        self.assertEqual(
            merged["recordingMode"]["recordingModeOverrides"],
            [
                {
                    "description": "Record EC2 continuously",
                    "recordingFrequency": "CONTINUOUS",
                    "resourceTypes": ["AWS::EC2::Instance"],
                },
            ],
        )

    def test_merge_configuration_does_not_override_mode_when_not_provided(self) -> None:
        desired = self.config_types.DesiredConfig(
            mode=None,
            overrides=[
                self.config_types.Override(
                    description="Record EC2 continuously",
                    override_type="CONTINUOUS",
                    resources=["AWS::EC2::Instance"],
                )
            ],
        )
        existing = {
            "recordingGroup": {},
            "recordingMode": {"recordingFrequency": "DAILY"},
        }

        changed, merged = self.handler.merge_configurations(desired, existing)

        self.assertIs(changed, True)
        self.assertEqual(merged["recordingMode"]["recordingFrequency"], "DAILY")
        self.assertEqual(
            merged["recordingMode"]["recordingModeOverrides"][0]["recordingFrequency"],
            "CONTINUOUS",
        )

    def test_merge_configuration_does_not_override_resources_when_not_provided(
        self,
    ) -> None:
        desired = self.config_types.DesiredConfig(mode="DAILY", resources=[])
        existing = {
            "recordingGroup": {"resourceTypes": ["AWS::S3::Bucket"]},
            "recordingMode": {"recordingFrequency": "CONTINUOUS"},
        }

        changed, merged = self.handler.merge_configurations(desired, existing)

        self.assertIs(changed, True)
        self.assertEqual(merged["recordingMode"]["recordingFrequency"], "DAILY")
        self.assertEqual(merged["recordingGroup"]["resourceTypes"], ["AWS::S3::Bucket"])
        self.assertEqual(
            merged["recordingGroup"]["recordingStrategy"]["useOnly"],
            "ALL_SUPPORTED_RESOURCE_TYPES",
        )

    def test_merge_configuration_exclude_resources_sets_recording_strategy_exclusion(
        self,
    ) -> None:
        desired = self.config_types.DesiredConfig(
            mode=None,
            exclude_resources=["AWS::IAM::Role"],
        )
        existing = {
            "recordingGroup": {
                "recordingStrategy": {"useOnly": "ALL_SUPPORTED_RESOURCE_TYPES"},
            },
            "recordingMode": {"recordingFrequency": "DAILY"},
        }

        changed, merged = self.handler.merge_configurations(desired, existing)

        self.assertIs(changed, True)
        self.assertEqual(
            merged["recordingGroup"]["recordingStrategy"]["useOnly"],
            "EXCLUSION_BY_RESOURCE_TYPES",
        )
        self.assertEqual(
            merged["recordingGroup"]["exclusionByResourceTypes"]["resourceTypes"],
            ["AWS::IAM::Role"],
        )

    def test_merge_configuration_empty_exclude_resources_reverts_recording_strategy_to_all_supported(
        self,
    ) -> None:
        desired = self.config_types.DesiredConfig(
            mode=None,
            exclude_resources=[],
        )
        existing = {
            "recordingGroup": {
                "recordingStrategy": {"useOnly": "EXCLUSION_BY_RESOURCE_TYPES"},
                "exclusionByResourceTypes": {"resourceTypes": ["AWS::IAM::Role"]},
            },
            "recordingMode": {"recordingFrequency": "DAILY"},
        }

        changed, merged = self.handler.merge_configurations(desired, existing)

        self.assertIs(changed, True)
        self.assertEqual(
            merged["recordingGroup"]["recordingStrategy"]["useOnly"],
            "ALL_SUPPORTED_RESOURCE_TYPES",
        )


class TestLambdaHandler(unittest.TestCase):
    def setUp(self) -> None:
        self.handler = _load_recorder_handler_module()

        # Ensure a clean env for each test
        self._saved_env = dict(os.environ)
        os.environ.pop("RECORDER_NAME", None)
        os.environ.pop("SECRET_MANAGER_NAME", None)
        os.environ.pop("LOG_LEVEL", None)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._saved_env)

    def test_missing_environment_variables_recorder_name(self) -> None:
        os.environ["SECRET_MANAGER_NAME"] = "desired/config"

        spy = MagicMock(wraps=self.handler.lambda_response)
        self.handler.lambda_response = spy

        with self.assertRaisesRegex(
            ValueError, "RECORDER_NAME environment variable is required"
        ):
            self.handler.lambda_handler({}, None)

        spy.assert_called()
        args, _kwargs = spy.call_args
        self.assertEqual(args[0], "error")

    def test_missing_environment_variables_secret_manager_name(self) -> None:
        os.environ["RECORDER_NAME"] = "default"

        spy = MagicMock(wraps=self.handler.lambda_response)
        self.handler.lambda_response = spy

        with self.assertRaisesRegex(
            ValueError, "SECRET_MANAGER_NAME environment variable is required"
        ):
            self.handler.lambda_handler({}, None)

        spy.assert_called()
        args, _kwargs = spy.call_args
        self.assertEqual(args[0], "error")

    def test_failed_to_load_configuration(self) -> None:
        os.environ["RECORDER_NAME"] = "default"
        os.environ["SECRET_MANAGER_NAME"] = "desired/config"

        self.handler.load_configuration = MagicMock(
            side_effect=ValueError("failed to load configuration")
        )
        self.handler.get_recorder = MagicMock()
        self.handler.merge_configurations = MagicMock()
        self.handler.list_accounts = MagicMock(return_value={})

        spy = MagicMock(wraps=self.handler.lambda_response)
        self.handler.lambda_response = spy

        with self.assertRaisesRegex(ValueError, "failed to load configuration"):
            self.handler.lambda_handler({}, None)

        spy.assert_called()
        args, _kwargs = spy.call_args
        self.assertEqual(args[0], "error")
        self.assertEqual(args[1], "default")

    def test_recorder_not_recording_returns_skipped(self) -> None:
        os.environ["RECORDER_NAME"] = "default"
        os.environ["SECRET_MANAGER_NAME"] = "desired/config"

        desired = __import__("config_types").DesiredConfig.load(
            {"filter": {"names": ["Dev"], "regions": ["eu-west-2"]}}
        )
        self.handler.load_configuration = MagicMock(
            return_value=__import__("config_types").AccountConfig(
                accounts={"dev": desired}
            )
        )
        self.handler.list_accounts = MagicMock(
            return_value={"Dev": MagicMock(id="123456789012", name="Dev", email="x@y")}
        )
        self.handler.get_config_client = MagicMock(return_value=self.handler._test_assumed_config_client)  # type: ignore[attr-defined]
        self.handler.get_recorder = MagicMock(
            return_value=(
                "arn:aws:iam::123:role/x",
                False,
                {"recordingGroup": {}, "recordingMode": {}},
            )
        )
        self.handler.merge_configurations = MagicMock()

        resp = self.handler.lambda_handler({}, None)
        self.assertEqual(resp["status"], "skipped")
        self.assertEqual(resp["recorder_name"], "default")
        self.assertIn("Recorder is not recording", resp.get("message", ""))

        self.handler.merge_configurations.assert_not_called()

    def test_no_changes_returns_skipped(self) -> None:
        os.environ["RECORDER_NAME"] = "default"
        os.environ["SECRET_MANAGER_NAME"] = "desired/config"

        desired = __import__("config_types").DesiredConfig.load(
            {"mode": "DAILY", "filter": {"names": ["Dev"], "regions": ["eu-west-2"]}}
        )
        self.handler.load_configuration = MagicMock(
            return_value=__import__("config_types").AccountConfig(
                accounts={"dev": desired}
            )
        )
        self.handler.list_accounts = MagicMock(
            return_value={"Dev": MagicMock(id="123456789012", name="Dev", email="x@y")}
        )
        self.handler.get_config_client = MagicMock(return_value=self.handler._test_assumed_config_client)  # type: ignore[attr-defined]
        self.handler.get_recorder = MagicMock(
            return_value=(
                "arn:aws:iam::123:role/x",
                True,
                {"recordingGroup": {}, "recordingMode": {}},
            )
        )
        self.handler.merge_configurations = MagicMock(
            return_value=(False, {"recordingGroup": {}, "recordingMode": {}})
        )

        resp = self.handler.lambda_handler({}, None)
        self.assertEqual(resp["status"], "skipped")
        self.assertEqual(resp["recorder_name"], "default")
        self.assertIn("did not change", resp.get("message", ""))

        self.handler._test_assumed_config_client.put_configuration_recorder.assert_not_called()  # type: ignore[attr-defined]

    def test_filter_regions_empty_uses_recorder_regions_env(self) -> None:
        """When filter.regions is null or [], iterate regions from RECORDER_REGIONS (module var.regions)."""
        os.environ["RECORDER_NAME"] = "default"
        os.environ["SECRET_MANAGER_NAME"] = "desired/config"
        os.environ["RECORDER_REGIONS"] = "us-east-1,eu-west-2"

        cfg = __import__("config_types")
        for filter_payload in (
            {"names": ["Dev"], "regions": None},
            {"names": ["Dev"], "regions": []},
        ):
            with self.subTest(filter_payload=filter_payload):
                desired = cfg.DesiredConfig.load({"filter": filter_payload})
                self.assertEqual(desired.filter.regions, [])

                self.handler.load_configuration = MagicMock(
                    return_value=cfg.AccountConfig(accounts={"dev": desired})
                )
                self.handler.list_accounts = MagicMock(
                    return_value={
                        "Dev": MagicMock(id="123456789012", name="Dev", email="x@y")
                    }
                )
                get_recorder = MagicMock(
                    return_value=(
                        "arn:aws:iam::123:role/x",
                        True,
                        {"recordingGroup": {}, "recordingMode": {}},
                    )
                )
                self.handler.get_config_client = MagicMock(
                    return_value=self.handler._test_assumed_config_client  # type: ignore[attr-defined]
                )
                self.handler.get_recorder = get_recorder
                self.handler.merge_configurations = MagicMock(
                    return_value=(False, {"recordingGroup": {}, "recordingMode": {}})
                )

                resp = self.handler.lambda_handler({}, None)
                self.assertEqual(resp["status"], "skipped")
                self.assertEqual(get_recorder.call_count, 2)

    def test_filter_regions_empty_does_not_leak_prior_account_regions(self) -> None:
        """Entries without filter.regions use base regions, not another entry's override."""
        os.environ["RECORDER_NAME"] = "default"
        os.environ["SECRET_MANAGER_NAME"] = "desired/config"
        os.environ["RECORDER_REGIONS"] = "us-east-1"

        cfg = __import__("config_types")
        first = cfg.DesiredConfig.load(
            {"filter": {"names": ["Dev"], "regions": ["eu-west-2"]}}
        )
        second = cfg.DesiredConfig.load({"filter": {"names": ["Prod"]}})

        self.handler.load_configuration = MagicMock(
            return_value=cfg.AccountConfig(accounts={"dev": first, "prod": second})
        )
        self.handler.list_accounts = MagicMock(
            return_value={
                "Dev": MagicMock(id="111111111111", name="Dev", email="a@b"),
                "Prod": MagicMock(id="222222222222", name="Prod", email="c@d"),
            }
        )
        get_recorder = MagicMock(
            return_value=(
                "arn:aws:iam::123:role/x",
                True,
                {"recordingGroup": {}, "recordingMode": {}},
            )
        )
        get_config = MagicMock(
            return_value=self.handler._test_assumed_config_client  # type: ignore[attr-defined]
        )
        self.handler.get_config_client = get_config
        self.handler.get_recorder = get_recorder
        self.handler.merge_configurations = MagicMock(
            return_value=(False, {"recordingGroup": {}, "recordingMode": {}})
        )

        resp = self.handler.lambda_handler({}, None)
        self.assertEqual(resp["status"], "skipped")
        self.assertEqual(get_recorder.call_count, 2)

        regions_touched = [c.kwargs.get("region") for c in get_config.call_args_list]
        self.assertEqual(regions_touched, ["eu-west-2", "us-east-1"])

    def test_empty_recorder_regions_falls_back_to_aws_region(self) -> None:
        """When var.regions is empty, RECORDER_REGIONS is empty and filter.regions is omitted, use AWS_REGION."""
        os.environ["RECORDER_NAME"] = "default"
        os.environ["SECRET_MANAGER_NAME"] = "desired/config"
        os.environ["RECORDER_REGIONS"] = ""
        os.environ["AWS_REGION"] = "ap-southeast-1"

        cfg = __import__("config_types")
        desired = cfg.DesiredConfig.load({"filter": {"names": ["Dev"]}})

        self.handler.load_configuration = MagicMock(
            return_value=cfg.AccountConfig(accounts={"dev": desired})
        )
        self.handler.list_accounts = MagicMock(
            return_value={"Dev": MagicMock(id="123456789012", name="Dev", email="x@y")}
        )
        get_recorder = MagicMock(
            return_value=(
                "arn:aws:iam::123:role/x",
                True,
                {"recordingGroup": {}, "recordingMode": {}},
            )
        )
        get_config = MagicMock(
            return_value=self.handler._test_assumed_config_client  # type: ignore[attr-defined]
        )
        self.handler.get_config_client = get_config
        self.handler.get_recorder = get_recorder
        self.handler.merge_configurations = MagicMock(
            return_value=(False, {"recordingGroup": {}, "recordingMode": {}})
        )

        resp = self.handler.lambda_handler({}, None)
        self.assertEqual(resp["status"], "skipped")
        self.assertEqual(get_recorder.call_count, 1)
        get_config.assert_called_once()
        self.assertEqual(get_config.call_args.kwargs.get("region"), "ap-southeast-1")

    def test_changes_with_diff_applies_update_and_returns_ok(self) -> None:
        os.environ["RECORDER_NAME"] = "default"
        os.environ["SECRET_MANAGER_NAME"] = "desired/config"

        desired = __import__("config_types").DesiredConfig.load(
            {
                "mode": "DAILY",
                "resources": ["AWS::S3::Bucket"],
                "filter": {"names": ["Dev"], "regions": ["eu-west-2"]},
            }
        )
        self.handler.load_configuration = MagicMock(
            return_value=__import__("config_types").AccountConfig(
                accounts={"dev": desired}
            )
        )
        self.handler.list_accounts = MagicMock(
            return_value={"Dev": MagicMock(id="123456789012", name="Dev", email="x@y")}
        )
        self.handler.get_config_client = MagicMock(return_value=self.handler._test_assumed_config_client)  # type: ignore[attr-defined]
        self.handler.get_recorder = MagicMock(
            return_value=(
                "arn:aws:iam::123:role/x",
                True,
                {"recordingGroup": {"resourceTypes": []}, "recordingMode": {}},
            )
        )
        merged = {
            "recordingGroup": {"resourceTypes": ["AWS::S3::Bucket"]},
            "recordingMode": {"recordingFrequency": "DAILY"},
        }
        self.handler.merge_configurations = MagicMock(return_value=(True, merged))

        resp = self.handler.lambda_handler({}, None)
        self.assertEqual(resp["status"], "ok")
        self.assertEqual(resp["recorder_name"], "default")
        self.assertIn("Successfully applied", resp.get("message", ""))

        self.handler._test_assumed_config_client.put_configuration_recorder.assert_called_once()  # type: ignore[attr-defined]
        _args, kwargs = self.handler._test_assumed_config_client.put_configuration_recorder.call_args  # type: ignore[attr-defined]
        sent = kwargs["ConfigurationRecorder"]
        self.assertEqual(sent["name"], "default")
        self.assertEqual(sent["roleARN"], "arn:aws:iam::123:role/x")
        self.assertEqual(sent["recordingGroup"], merged.get("recordingGroup"))
        self.assertEqual(sent["recordingMode"], merged.get("recordingMode"))

    def test_failed_to_update_recorder_raises_and_records_error_status(self) -> None:
        os.environ["RECORDER_NAME"] = "default"
        os.environ["SECRET_MANAGER_NAME"] = "desired/config"

        desired = __import__("config_types").DesiredConfig.load(
            {"mode": "DAILY", "filter": {"names": ["Dev"], "regions": ["eu-west-2"]}}
        )
        self.handler.load_configuration = MagicMock(
            return_value=__import__("config_types").AccountConfig(
                accounts={"dev": desired}
            )
        )
        self.handler.list_accounts = MagicMock(
            return_value={"Dev": MagicMock(id="123456789012", name="Dev", email="x@y")}
        )
        self.handler.get_config_client = MagicMock(return_value=self.handler._test_assumed_config_client)  # type: ignore[attr-defined]
        self.handler.get_recorder = MagicMock(
            return_value=(
                "arn:aws:iam::123:role/x",
                True,
                {"recordingGroup": {}, "recordingMode": {}},
            )
        )
        self.handler.merge_configurations = MagicMock(
            return_value=(True, {"recordingGroup": {}, "recordingMode": {}})
        )

        self.handler._test_assumed_config_client.put_configuration_recorder.side_effect = RuntimeError("update failed")  # type: ignore[attr-defined]

        spy = MagicMock(wraps=self.handler.lambda_response)
        self.handler.lambda_response = spy

        with self.assertRaisesRegex(RuntimeError, "update failed"):
            self.handler.lambda_handler({}, None)

        spy.assert_called()
        args, _kwargs = spy.call_args
        self.assertEqual(args[0], "error")
        self.assertEqual(args[1], "default")


if __name__ == "__main__":
    unittest.main()
