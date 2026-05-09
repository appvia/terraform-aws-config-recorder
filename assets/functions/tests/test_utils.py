"""Unit tests for `utils.py`."""

import sys
import unittest
from pathlib import Path

recorder_dir = Path(__file__).resolve().parents[1]
if str(recorder_dir) not in sys.path:
    sys.path.insert(0, str(recorder_dir))

from utils import (
    is_boolean,
    is_frequency,
    is_list,
    is_string,
    is_string_list,
)


class TestIsFrequency(unittest.TestCase):
    def test_true_for_valid_frequency_values(self) -> None:
        self.assertTrue(is_frequency("CONTINUOUS"))
        self.assertTrue(is_frequency("DAILY"))

    def test_false_for_invalid_frequency_values(self) -> None:
        self.assertFalse(is_frequency("WEEKLY"))
        self.assertFalse(is_frequency(""))
        self.assertFalse(is_frequency("daily"))
        self.assertFalse(is_frequency("continuous"))

    def test_false_for_non_string_values(self) -> None:
        self.assertFalse(is_frequency(None))
        self.assertFalse(is_frequency(True))
        self.assertFalse(is_frequency(1))
        self.assertFalse(is_frequency([]))
        self.assertFalse(is_frequency({}))


class TestIsBoolean(unittest.TestCase):
    def test_true_for_bool_values(self) -> None:
        self.assertTrue(is_boolean(True))
        self.assertTrue(is_boolean(False))

    def test_false_for_non_bool_values(self) -> None:
        self.assertFalse(is_boolean(1))
        self.assertFalse(is_boolean(0))
        self.assertFalse(is_boolean("true"))
        self.assertFalse(is_boolean(None))
        self.assertFalse(is_boolean([]))
        self.assertFalse(is_boolean({}))


class TestIsList(unittest.TestCase):
    def test_true_for_list(self) -> None:
        self.assertTrue(is_list([]))
        self.assertTrue(is_list(["a", "b"]))

    def test_false_for_non_list(self) -> None:
        self.assertFalse(is_list("not-a-list"))
        self.assertFalse(is_list(("tuple",)))
        self.assertFalse(is_list({"a": 1}))
        self.assertFalse(is_list(None))


class TestIsString(unittest.TestCase):
    def test_true_for_str(self) -> None:
        self.assertTrue(is_string(""))
        self.assertTrue(is_string("abc"))

    def test_false_for_non_str(self) -> None:
        self.assertFalse(is_string(123))
        self.assertFalse(is_string(True))
        self.assertFalse(is_string(None))
        self.assertFalse(is_string([]))


class TestIsStringList(unittest.TestCase):
    def test_true_for_list_of_strings(self) -> None:
        self.assertTrue(is_string_list([]))
        self.assertTrue(is_string_list(["a", "b", "c"]))

    def test_false_for_non_list(self) -> None:
        self.assertFalse(is_string_list("a"))
        self.assertFalse(is_string_list(("a", "b")))
        self.assertFalse(is_string_list(None))

    def test_false_for_list_with_non_string_elements(self) -> None:
        self.assertFalse(is_string_list(["a", 1]))
        self.assertFalse(is_string_list([True]))
        self.assertFalse(is_string_list([{"k": "v"}]))


if __name__ == "__main__":
    unittest.main()
