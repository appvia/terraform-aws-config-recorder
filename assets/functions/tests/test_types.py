"""Unit tests for `types.py`."""

import importlib.util
import sys
import unittest
from pathlib import Path


def _load_recorder_types_module():
    """
    Load recorder/types.py as a module without colliding with stdlib `types`.
    """
    recorder_dir = Path(__file__).resolve().parents[1]
    if str(recorder_dir) not in sys.path:
        sys.path.insert(0, str(recorder_dir))

    types_path = recorder_dir / "types.py"
    spec = importlib.util.spec_from_file_location("recorder_types", types_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestOverride(unittest.TestCase):
    def test_override_load_success(self) -> None:
        t = _load_recorder_types_module()
        for override_type in ("CONTINUOUS", "DAILY"):
            with self.subTest(override_type=override_type):
                o = t.Override.load(
                    {"resources": ["AWS::S3::Bucket"], "override_type": override_type}
                )
                self.assertEqual(o.resources, ["AWS::S3::Bucket"])
                self.assertEqual(o.override_type, override_type)

    def test_override_load_validation_errors(self) -> None:
        t = _load_recorder_types_module()

        cases = [
            ({}, "resources must be a list of strings"),
            (
                {"resources": 123, "override_type": "DAILY"},
                "resources must be a list of strings",
            ),
            ({"resources": ["AWS::S3::Bucket"]}, "override_type must be a frequency"),
            (
                {"resources": ["AWS::S3::Bucket"], "override_type": 1},
                "override_type must be a frequency",
            ),
            (
                {"resources": ["AWS::S3::Bucket"], "override_type": "NOPE"},
                "override_type must be a frequency",
            ),
            (
                {"resources": ["AWS::S3::Bucket"], "override_type": "EXCLUDE"},
                "override_type must be a frequency",
            ),
        ]

        for raw, err in cases:
            with self.subTest(raw=raw, err=err):
                with self.assertRaisesRegex(ValueError, err):
                    t.Override.load(raw)


class TestDesiredConfig(unittest.TestCase):
    def test_desired_config_is_frequency_and_mode_helpers(self) -> None:
        t = _load_recorder_types_module()
        dc = t.DesiredConfig()

        self.assertIs(t.is_frequency("CONTINUOUS"), True)
        self.assertIs(t.is_frequency("DAILY"), True)
        self.assertIs(t.is_frequency("weekly"), False)
        self.assertIs(t.is_frequency(None), False)

        self.assertIs(dc.is_recording_mode("CONTINUOUS"), True)
        self.assertIs(dc.is_recording_mode("DAILY"), True)
        self.assertIs(dc.is_recording_mode("weekly"), False)
        self.assertIs(dc.is_recording_mode(None), False)  # type: ignore[arg-type]

    def test_desired_config_load_success(self) -> None:
        t = _load_recorder_types_module()
        for override_type in ("CONTINUOUS", "DAILY"):
            with self.subTest(override_type=override_type):
                dc = t.DesiredConfig.load(
                    {
                        "mode": "CONTINUOUS",
                        "resources": ["AWS::S3::Bucket"],
                        "exclude_resources": [],
                        "overrides": [
                            {
                                "resources": ["AWS::S3::Bucket"],
                                "override_type": override_type,
                            }
                        ],
                    }
                )
                self.assertEqual(dc.mode, "CONTINUOUS")
                self.assertEqual(dc.resources, ["AWS::S3::Bucket"])
                self.assertEqual(dc.exclude_resources, [])
                self.assertEqual(len(dc.overrides), 1)
                self.assertEqual(dc.overrides[0].resources, ["AWS::S3::Bucket"])
                self.assertEqual(dc.overrides[0].override_type, override_type)

    def test_desired_config_load_validation_errors(self) -> None:
        t = _load_recorder_types_module()

        cases = [
            (None, "configuration must be an object"),
            ({}, "resource_filter.mode must be a recording mode"),
            (
                {
                    "mode": "WEEKLY",
                    "resources": [],
                    "exclude_resources": [],
                    "overrides": [],
                },
                "resource_filter.mode must be a recording mode",
            ),
            (
                {
                    "mode": "DAILY",
                    "resources": "nope",
                    "exclude_resources": [],
                    "overrides": [],
                },
                "resources must be a list",
            ),
            (
                {
                    "mode": "DAILY",
                    "resources": [],
                    "exclude_resources": "nope",
                    "overrides": "nope",
                },
                "exclude_resources must be a list",
            ),
            (
                {
                    "mode": "DAILY",
                    "resources": [],
                    "exclude_resources": [],
                    "overrides": ["not-an-object"],
                },
                "override entries must be objects",
            ),
            (
                {
                    "mode": "DAILY",
                    "resources": [],
                    "exclude_resources": [],
                    "overrides": [{"resources": "nope", "override_type": "DAILY"}],
                },
                "resources must be a list of strings",
            ),
        ]

        for raw, err in cases:
            with self.subTest(raw=raw, err=err):
                with self.assertRaisesRegex(ValueError, err):
                    t.DesiredConfig.load(raw)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
