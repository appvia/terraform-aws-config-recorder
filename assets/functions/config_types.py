"""
Types for the AWS Config recorder configurator Lambda function.
"""

from dataclasses import dataclass, field
from typing import Any
from utils import is_string_list, is_list, is_frequency
from logger import logger


@dataclass
class Override:
    # A human-readable description of the override
    description: str = "Override for resource types"
    # The type of override to apply to the recorder
    resources: list[str] = field(default_factory=list)
    # The frequency to apply when type is frequency
    override_type: str = "DAILY"

    def get_override(self) -> dict[str, Any]:
        """
        Get the override entry for the override

        Returns:
            A dictionary containing the override entry
        """

        return {
            "description": self.description,
            "recordingFrequency": self.override_type,
            "resourceTypes": self.resources,
        }

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


@dataclass
class AccountFilter:
    # Name of the account
    name: str = field(default_factory=str)
    # Non-empty: only these regions; empty: use module/env default regions (RECORDER_REGIONS / AWS_REGION)
    regions: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, raw: dict[str, Any]) -> "AccountFilter":
        """
        Load the account filter from the raw configuration

        Args:
            raw: The raw configuration to parse

        Returns:
            An AccountFilter object
        """

        if raw is None:
            return cls()
        if not isinstance(raw, dict):
            raise ValueError("filter must be an object")

        regions_raw = raw.get("regions")
        # Omitted or null (e.g. Terraform optional) means use module/event regions
        if regions_raw is None:
            regions_raw = []
        elif not is_string_list(regions_raw):
            raise ValueError("regions must be a list of strings")

        return cls(
            name=str(raw.get("name", "")),
            regions=[str(r) for r in regions_raw],
        )


@dataclass
class DesiredConfig:
    # The mode to apply to the recorder
    mode: str | None = None
    # The mode to apply to the recorder (i.e specific resource types or all resources)
    resources: list[str] = field(default_factory=list)
    # Resource to exclude from the recorder
    exclude_resources: list[str] = field(default_factory=list)
    # The overrides to apply to the recorder
    overrides: list[Override] = field(default_factory=list)
    # The account filter to apply the configuration to
    filter: AccountFilter = field(default_factory=AccountFilter)

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

        # Get the mode, resources, exclude_resources, and overrides from the raw configuration
        mode = raw.get("mode")
        resources_raw = raw.get("resources")
        exclude_resources_raw = raw.get("exclude_resources")
        overrides_raw = raw.get("overrides")
        filter_raw = raw.get("filter")

        desired_filter = AccountFilter.load(filter_raw)
        desired_mode: str | None = None
        desired_resources: list[str] = []
        desired_exclude_resources: list[str] = []
        desired_overrides: list[Override] = []

        # Ensure the mode is a valid frequency when provided
        if mode:
            if not is_frequency(mode):
                # Preserve existing error message expected by tests/users
                raise ValueError("resource_filter.mode must be a recording mode")
            desired_mode = str(mode)

        # Ensure the resources is a list of strings
        if resources_raw:
            if not is_string_list(resources_raw):
                raise ValueError("resources must be a list")
            desired_resources = [str(r) for r in resources_raw]

        # Ensure the exclude_resources is a list of strings
        if exclude_resources_raw:
            if not is_string_list(exclude_resources_raw):
                raise ValueError("exclude_resources must be a list")
            desired_exclude_resources = [str(r) for r in exclude_resources_raw]

        if overrides_raw:
            if not is_list(overrides_raw):
                raise ValueError("overrides must be a list")
            for o in overrides_raw:
                if not isinstance(o, dict):
                    raise ValueError("override entries must be objects")
                desired_overrides.append(Override.load(o))

        return cls(
            mode=desired_mode,
            resources=desired_resources,
            exclude_resources=desired_exclude_resources,
            overrides=desired_overrides,
            filter=desired_filter,
        )


@dataclass
class AccountConfig:
    # A map of DesiredConfig objects by key
    accounts: dict[str, DesiredConfig] = field(default_factory=dict)

    @classmethod
    def load(cls, raw: dict[str, Any]) -> "AccountConfig":
        """
        Load the account configuration from the raw configuration

        Args:
            raw: The raw configuration to parse

        Returns:
            An AccountConfig object
        """

        if not isinstance(raw, dict):
            raise ValueError("configuration must be an object")

        accounts: dict[str, DesiredConfig] = {}
        for key, value in raw.items():
            if not isinstance(value, dict):
                raise ValueError("configuration entries must be objects")
            accounts[str(key)] = DesiredConfig.load(value)

        return cls(accounts=accounts)
