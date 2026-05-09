"""Unit tests for `config_types.py`."""

import importlib.util
import unittest

from tests.test_support import ensure_recorder_dir_on_path


def _load_recorder_config_types_module():
    """
    Load recorder/config_types.py as a module.
    """
    recorder_dir = ensure_recorder_dir_on_path()

    config_types_path = recorder_dir / "config_types.py"
    spec = importlib.util.spec_from_file_location(
        "recorder_config_types", config_types_path
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestOverride(unittest.TestCase):
    def test_override_load_success(self) -> None:
        t = _load_recorder_config_types_module()
        for override_type in ("CONTINUOUS", "DAILY"):
            with self.subTest(override_type=override_type):
                o = t.Override.load(
                    {"resources": ["AWS::S3::Bucket"], "override_type": override_type}
                )
                self.assertEqual(o.resources, ["AWS::S3::Bucket"])
                self.assertEqual(o.override_type, override_type)

    def test_override_load_validation_errors(self) -> None:
        t = _load_recorder_config_types_module()

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


class TestAccountFilter(unittest.TestCase):
    def test_account_filter_regions_null_or_missing_uses_empty_list(self) -> None:
        t = _load_recorder_config_types_module()
        for raw in (
            {"names": ["Dev"], "regions": None},
            {"names": ["Dev"]},
        ):
            with self.subTest(raw=raw):
                f = t.AccountFilter.load(raw)
                self.assertEqual(f.names, ["Dev"])
                self.assertEqual(f.regions, [])

    def test_account_filter_regions_empty_list(self) -> None:
        t = _load_recorder_config_types_module()
        f = t.AccountFilter.load({"names": ["Dev"], "regions": []})
        self.assertEqual(f.names, ["Dev"])
        self.assertEqual(f.regions, [])

    def test_account_filter_multiple_names(self) -> None:
        t = _load_recorder_config_types_module()
        f = t.AccountFilter.load({"names": ["Dev", "Staging"], "regions": ["eu-west-2"]})
        self.assertEqual(f.names, ["Dev", "Staging"])
        self.assertEqual(f.regions, ["eu-west-2"])

    def test_account_filter_names_invalid_type_raises(self) -> None:
        t = _load_recorder_config_types_module()
        with self.assertRaisesRegex(ValueError, "names must be a list of strings"):
            t.AccountFilter.load({"names": "Dev", "regions": []})
        with self.assertRaisesRegex(ValueError, "names must be a list of strings"):
            t.AccountFilter.load({"regions": []})

    def test_account_filter_regions_invalid_type_raises(self) -> None:
        t = _load_recorder_config_types_module()
        with self.assertRaisesRegex(ValueError, "regions must be a list of strings"):
            t.AccountFilter.load({"names": ["Dev"], "regions": "eu-west-2"})


class TestDesiredConfig(unittest.TestCase):
    def test_desired_config_load_success(self) -> None:
        t = _load_recorder_config_types_module()
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
        t = _load_recorder_config_types_module()

        cases = [
            (None, "configuration must be an object"),
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

    def test_desired_config_load_allows_partial_configuration(self) -> None:
        t = _load_recorder_config_types_module()
        dc = t.DesiredConfig.load({"overrides": []})
        self.assertIsNone(dc.mode)
        self.assertEqual(dc.resources, [])
        self.assertEqual(dc.exclude_resources, [])
        self.assertEqual(dc.overrides, [])


class TestAccountConfig(unittest.TestCase):
    def test_account_config_load_success(self) -> None:
        t = _load_recorder_config_types_module()
        cfg = t.AccountConfig.load(
            {
                "dev": {
                    "filter": {"names": ["Dev"], "regions": ["eu-west-2"]},
                    "mode": "DAILY",
                },
                "prod": {
                    "filter": {"names": ["Prod"], "regions": ["eu-west-2"]},
                    "resources": ["AWS::S3::Bucket"],
                },
            }
        )
        self.assertIn("dev", cfg.accounts)
        self.assertEqual(cfg.accounts["dev"].filter.names, ["Dev"])
        self.assertEqual(cfg.accounts["dev"].mode, "DAILY")
        self.assertIn("prod", cfg.accounts)
        self.assertEqual(cfg.accounts["prod"].filter.names, ["Prod"])
        self.assertEqual(cfg.accounts["prod"].resources, ["AWS::S3::Bucket"])

    def test_account_config_load_validation_errors(self) -> None:
        t = _load_recorder_config_types_module()
        with self.assertRaisesRegex(ValueError, "configuration must be an object"):
            t.AccountConfig.load(None)  # type: ignore[arg-type]
        with self.assertRaisesRegex(
            ValueError, "configuration entries must be objects"
        ):
            t.AccountConfig.load({"dev": "nope"})  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
