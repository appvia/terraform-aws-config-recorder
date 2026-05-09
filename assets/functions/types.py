"""
Types for the AWS Config recorder configurator Lambda function.
"""

from dataclasses import dataclass, field
from typing import Any
from utils import is_string_list, is_list, is_frequency
from logger import logger


@dataclass(frozen=True)
class Override:
    # A human-readable description of the override
    description: str = "Override for resource types"
    # The type of override to apply to the recorder
    resources: list[str] = field(default_factory=list)
    # The frequency to apply when type is frequency
    override_type: str = "DAILY"

    @classmethod
    def load(cls, raw: dict[str, Any]) -> "Override":
        """
        Load the override from the raw configuration

        Args:
            raw: The raw configuration to parse

        Returns:
            An Override object
        """

        # Ensure the resource is a string
        if not is_string_list(raw.get("resources")):
            raise ValueError("resources must be a list of strings")

        # Ensure the override type is a string
        if not is_frequency(raw.get("override_type")):
            raise ValueError("override_type must be a frequency")

        return cls(
            description=str(raw.get("description", cls.description)),
            override_type=str(raw.get("override_type")),
            resources=[str(r) for r in raw.get("resources")],
        )


@dataclass(frozen=True)
class DesiredConfig:
    # The mode to apply to the recorder
    mode: str = "CONTINUOUS"
    # The mode to apply to the recorder (i.e specific resource types or all resources)
    resources: list[str] = field(default_factory=list)
    # Resource to exclude from the recorder
    exclude_resources: list[str] = field(default_factory=list)
    # The overrides to apply to the recorder
    overrides: list[Override] = field(default_factory=list)

    def is_recording_mode(self, value: str) -> bool:
        """
        Check if a value is a recording mode

        Args:
            value: The value to check

        Returns:
            True if the value is a recording mode, False otherwise
        """

        return is_frequency(value)

    @classmethod
    def load(cls, raw: dict[str, Any]) -> "DesiredConfig":
        """
        Load the desired configuration from the raw configuration

        Args:
            raw: The raw configuration to parse

        Returns:
            A DesiredConfig object
        """

        logger.debug(
            "Loading DesiredConfig from raw configuration",
            extra={
                "action": "DesiredConfig.load",
                "raw": raw,
            },
        )

        if not isinstance(raw, dict):
            raise ValueError("configuration must be an object")

        mode = raw.get("mode")
        resources = raw.get("resources")
        exclude_resources = raw.get("exclude_resources")
        overrides_raw = raw.get("overrides")

        # Ensure the mode is a string
        if not cls().is_recording_mode(mode):
            raise ValueError("resource_filter.mode must be a recording mode")

        # Ensure the resources is a list of strings
        if not is_string_list(resources):
            raise ValueError("resources must be a list")

        # Ensure the exclude_resources is a list of strings
        if not is_string_list(exclude_resources):
            raise ValueError("exclude_resources must be a list")

        # Ensure the overrides is a list of objects
        if not is_list(overrides_raw):
            raise ValueError("overrides must be a list")

        overrides: list[Override] = []
        for o in overrides_raw:
            if not isinstance(o, dict):
                raise ValueError("override entries must be objects")
            overrides.append(Override.load(o))

        return cls(
            exclude_resources=[str(r) for r in exclude_resources],
            mode=str(mode),
            overrides=[Override.load(o) for o in overrides_raw],
            resources=[str(r) for r in resources],
        )
