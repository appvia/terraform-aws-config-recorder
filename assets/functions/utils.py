"""
Utility functions for the AWS Config recorder configurator Lambda function.
"""

from typing import Any


def is_frequency(value: Any) -> bool:
    """
    Check if a value is a frequency

    Args:
        value: The value to check
    """
    if not is_string(value):
        return False

    return str(value) in ("CONTINUOUS", "DAILY")


def is_list(value: Any) -> bool:
    """
    Check if a value is an array

    Args:
        value: The value to check

    Returns:
        True if the value is an array, False otherwise
    """

    return isinstance(value, list)


def is_string(value: Any) -> bool:
    """
    Check if a value is a string

    Args:
        value: The value to check

    Returns:
        True if the value is a string, False otherwise
    """
    return isinstance(value, str)


def is_string_list(value: Any) -> bool:
    """
    Check if a value is a list

    Args:
        value: The value to check

    Returns:
        True if the value is a list, False otherwise

    Returns:
        True if the value is a list, False otherwise
    """

    if value is None:
        return False

    if not is_list(value):
        return False

    if not all(isinstance(x, str) for x in value):
        return False

    return True
