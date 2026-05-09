"""Unit tests for `handler.py`."""

import importlib.util
import os
import sys
import types as stdlib_types
import unittest
from pathlib import Path
from unittest.mock import MagicMock


def _load_module_from_path(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_recorder_handler_module():
    """
    Load recorder/handler.py as a module, while ensuring:
    - local recorder `types.py` shadows stdlib `types` for handler imports
    - boto3 is mocked so no AWS calls happen at import time
    """
    recorder_dir = Path(__file__).resolve().parents[1]
    if str(recorder_dir) not in sys.path:
        sys.path.insert(0, str(recorder_dir))

    # Load local types.py as a module we can temporarily map to name "types"
    local_types_mod = _load_module_from_path(
        "recorder_types", recorder_dir / "types.py"
    )

    # Provide a mocked boto3 module so handler module init doesn't create real clients
    ssm_client = MagicMock(name="ssm_client")
    config_client = MagicMock(name="config_client")
    boto3_mod = MagicMock(name="boto3")

    def _client(service_name: str):
        if service_name == "ssm":
            return ssm_client
        if service_name == "config":
            return config_client
        raise AssertionError(f"Unexpected boto3 client requested: {service_name}")

    boto3_mod.client.side_effect = _client

    # Temporarily override sys.modules for handler imports.
    saved_types = sys.modules.get("types")
    saved_boto3 = sys.modules.get("boto3")
    try:
        sys.modules["types"] = local_types_mod
        sys.modules["boto3"] = boto3_mod

        handler_mod = _load_module_from_path(
            "recorder_handler", recorder_dir / "handler.py"
        )
        # Attach the mocks so tests can access them easily
        handler_mod._test_ssm_client = ssm_client  # type: ignore[attr-defined]
        handler_mod._test_config_client = config_client  # type: ignore[attr-defined]
        return handler_mod
    finally:
        # Restore modules (keep stdlib `types` intact)
        if saved_types is not None:
            sys.modules["types"] = saved_types
        else:
            sys.modules.pop("types", None)
            sys.modules["types"] = stdlib_types

        if saved_boto3 is not None:
            sys.modules["boto3"] = saved_boto3
        else:
            sys.modules.pop("boto3", None)


class TestLambdaHandler(unittest.TestCase):
    def setUp(self) -> None:
        self.handler = _load_recorder_handler_module()

        # Ensure a clean env for each test
        self._saved_env = dict(os.environ)
        os.environ.pop("RECORDER_NAME", None)
        os.environ.pop("SSM_PARAMETER_NAME", None)
        os.environ.pop("LOG_LEVEL", None)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._saved_env)

    def test_missing_environment_variables_recorder_name(self) -> None:
        os.environ["SSM_PARAMETER_NAME"] = "/desired/config"

        spy = MagicMock(wraps=self.handler.lambda_response)
        self.handler.lambda_response = spy

        with self.assertRaisesRegex(
            ValueError, "RECORDER_NAME environment variable is required"
        ):
            self.handler.lambda_handler({}, None)

        spy.assert_called()
        args, _kwargs = spy.call_args
        self.assertEqual(args[0], "error")

    def test_missing_environment_variables_ssm_parameter_name(self) -> None:
        os.environ["RECORDER_NAME"] = "default"

        spy = MagicMock(wraps=self.handler.lambda_response)
        self.handler.lambda_response = spy

        with self.assertRaisesRegex(
            ValueError, "SSM_PARAMETER_NAME environment variable is required"
        ):
            self.handler.lambda_handler({}, None)

        spy.assert_called()
        args, _kwargs = spy.call_args
        self.assertEqual(args[0], "error")

    def test_failed_to_load_configuration(self) -> None:
        os.environ["RECORDER_NAME"] = "default"
        os.environ["SSM_PARAMETER_NAME"] = "/desired/config"

        self.handler.load_configuration = MagicMock(
            side_effect=ValueError("failed to load configuration")
        )
        self.handler.get_recorder = MagicMock()
        self.handler.merge_configurations = MagicMock()

        spy = MagicMock(wraps=self.handler.lambda_response)
        self.handler.lambda_response = spy

        with self.assertRaisesRegex(ValueError, "failed to load configuration"):
            self.handler.lambda_handler({}, None)

        spy.assert_called()
        args, _kwargs = spy.call_args
        self.assertEqual(args[0], "error")
        self.assertEqual(args[1], "default")

    def test_missing_recorder(self) -> None:
        os.environ["RECORDER_NAME"] = "missing"
        os.environ["SSM_PARAMETER_NAME"] = "/desired/config"

        self.handler.load_configuration = MagicMock(
            return_value=MagicMock(name="desired")
        )
        self.handler.get_recorder = MagicMock(
            side_effect=ValueError("Recorder not found: missing")
        )

        spy = MagicMock(wraps=self.handler.lambda_response)
        self.handler.lambda_response = spy

        with self.assertRaisesRegex(ValueError, "Recorder not found: missing"):
            self.handler.lambda_handler({}, None)

        spy.assert_called()
        args, _kwargs = spy.call_args
        self.assertEqual(args[0], "error")
        self.assertEqual(args[1], "missing")

    def test_recorder_not_recording_returns_skipped(self) -> None:
        os.environ["RECORDER_NAME"] = "default"
        os.environ["SSM_PARAMETER_NAME"] = "/desired/config"

        self.handler.load_configuration = MagicMock(
            return_value=MagicMock(name="desired")
        )
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
        os.environ["SSM_PARAMETER_NAME"] = "/desired/config"

        self.handler.load_configuration = MagicMock(
            return_value=MagicMock(name="desired")
        )
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

        self.handler._test_config_client.put_configuration_recorder.assert_not_called()  # type: ignore[attr-defined]

    def test_changes_with_diff_applies_update_and_returns_ok(self) -> None:
        os.environ["RECORDER_NAME"] = "default"
        os.environ["SSM_PARAMETER_NAME"] = "/desired/config"

        self.handler.load_configuration = MagicMock(
            return_value=MagicMock(name="desired")
        )
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

        self.handler._test_config_client.put_configuration_recorder.assert_called_once()  # type: ignore[attr-defined]
        _args, kwargs = self.handler._test_config_client.put_configuration_recorder.call_args  # type: ignore[attr-defined]
        sent = kwargs["ConfigurationRecorder"]
        self.assertEqual(sent["name"], "default")
        self.assertEqual(sent["roleARN"], "arn:aws:iam::123:role/x")
        self.assertEqual(sent["recordingGroup"], merged.get("recordingGroup"))
        self.assertEqual(sent["recordingMode"], merged.get("recordingMode"))

    def test_failed_to_update_recorder_raises_and_records_error_status(self) -> None:
        os.environ["RECORDER_NAME"] = "default"
        os.environ["SSM_PARAMETER_NAME"] = "/desired/config"

        self.handler.load_configuration = MagicMock(
            return_value=MagicMock(name="desired")
        )
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

        self.handler._test_config_client.put_configuration_recorder.side_effect = RuntimeError("update failed")  # type: ignore[attr-defined]

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
