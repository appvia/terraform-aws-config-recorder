"""
Handler for the AWS Config recorder configurator Lambda function.
"""

from __future__ import annotations

import copy
import json
import os
from typing import Any, Literal

import boto3

from client import get_config_client
from config_types import AccountConfig, DesiredConfig
from logger import logger
from organizations import list_accounts

# Initialize the AWS clients
secretsmanager = boto3.client("secretsmanager")  # pylint: disable=no-member
# Initialize the AWS Config client
config = boto3.client("config")  # pylint: disable=no-member
# Initialize the AWS Organizations client
organizations_client = boto3.client("organizations")  # pylint: disable=no-member


def merge_configurations(
    desired: DesiredConfig,
    existing: dict[str, Any],
) -> tuple[bool, dict[str, Any]]:
    """
    Merge the desired configuration with the existing configuration

    Args:
        desired: The desired configuration
        existing: The existing configuration

    Returns:
        A tuple containing a boolean indicating if the configuration changed,
        and the merged configuration
    """

    # Make a copy of the existing configuration
    merged = copy.deepcopy(existing)
    # Set the recording frequency in the merged configuration (only if provided)
    recording_mode = merged.setdefault("recordingMode", {})
    # Set the recording group in the merged configuration
    recording_group = merged.setdefault("recordingGroup", {})
    # Set the recording strategy in the merged configuration
    recording_strategy = recording_group.setdefault("recordingStrategy", {})
    # Set the exclusion by resource types in the merged configuration
    exclusion_by_type = recording_group.setdefault("exclusionByResourceTypes", {})

    # Set the recording group scope
    recording_group["allSupported"] = desired.enable_all_supported
    recording_group["includeGlobalResourceTypes"] = desired.enable_global_resources
    recording_group["resourceTypes"] = desired.resources
    # If the desired configuration excludes resources, then set the recording strategy
    # to exclusion by resource types
    if len(desired.exclude_resources) > 0:
        exclusion_by_type["resourceTypes"] = desired.exclude_resources
        recording_strategy["useOnly"] = "EXCLUSION_BY_RESOURCE_TYPES"
    else:
        exclusion_by_type["resourceTypes"] = []
        recording_strategy["useOnly"] = "ALL_SUPPORTED_RESOURCE_TYPES"

    # Set the recording mode (frequency only when provided)
    if desired.mode is not None:
        recording_mode["recordingFrequency"] = desired.mode
    recording_mode["recordingModeOverrides"] = desired.get_overrides()

    # Check if the merged configuration is different from the existing configuration
    changed = merged != existing
    if changed:
        logger.info(
            "Configuration has changes to apply",
            extra={
                "action": "merge_configurations",
                "current": existing,
                "desired": merged,
            },
        )

    return changed, merged


def load_configuration(
    secret_manager_name: str,
) -> AccountConfig:
    """
    Load the desired configuration from Secret Manager and parse it
    into a DesiredConfig object

    Args:
        secret_manager_name: The name of the Secret Manager secret to
        load the configuration from.

    Returns:
        An AccountConfig object containing the desired configuration.
    """

    logger.info(
        "Loading desired configuration from Secret Manager",
        extra={
            "action": "load_configuration",
            "secret_manager_name": secret_manager_name,
        },
    )

    # Get the parameter from Secret Manager
    param = secretsmanager.get_secret_value(SecretId=secret_manager_name)
    # Get the raw value from the Secret Manager secret
    raw_value = param["SecretString"]
    # Load the raw configuration into a DesiredConfig object
    return AccountConfig.load(json.loads(raw_value))


def get_recorder(
    client: boto3.client,
    recorder_name: str,
) -> tuple[str, bool, dict[str, Any]]:
    """
    Get the recorder configuration from AWS Config

    Args:
        client:        The Boto3 client to use to get the recorder configuration
        recorder_name: The name of the recorder

    Returns:
        A tuple containing the recorder arn and the status

    """

    try:
        logger.info(
            "Getting recorder configuration",
            extra={
                "action": "get_recorder",
                "recorder_name": recorder_name,
            },
        )

        # List the existing recorders
        recorders = client.describe_configuration_recorders(
            ConfigurationRecorderNames=[recorder_name]
        ).get("ConfigurationRecorders", [])
        if not recorders:
            raise ValueError(f"Recorder not found: {recorder_name}")

        # Get the existing recorder configuration
        existing = recorders[0]
        # Get the role ARN from the existing recorder configuration
        role_arn = existing.get("roleARN")
        # Ensure the role ARN is set
        if not role_arn:
            raise ValueError(
                "Existing recorder has no roleARN; cannot update recorder safely"
            )

        # Get the status of the existing recorder
        status = client.describe_configuration_recorder_status(
            ConfigurationRecorderNames=[recorder_name]
        ).get("ConfigurationRecordersStatus", [])
        recording = bool(status and status[0].get("recording"))

        logger.debug(
            "Recorder configuration retrieved",
            extra={
                "action": "get_recorder",
                "recorder_name": recorder_name,
                "recording": recording,
                "role_arn": role_arn,
                "configuration": existing,
            },
        )

        # Return the role ARN, recording status, and existing configuration
        return role_arn, recording, existing

    except Exception as e:
        logger.error(
            "Error getting recorder configuration",
            extra={
                "action": "get_recorder",
                "recorder_name": recorder_name,
                "error": str(e),
            },
        )
        raise e


def lambda_response(
    status: Literal["ok", "skipped", "error"],
    recorder_name: str,
    message: str | None = None,
) -> dict[str, Any]:
    """
    Build the response for the Lambda function

    Args:
        status: The status of the Lambda function
        recorder_name: The name of the recorder
        message: The message to include in the response

    Returns:
        A dictionary representing the response
    """

    response: dict[str, Any] = {
        "status": status,
        "recorder_name": recorder_name,
    }
    if message:
        response["message"] = message

    return response


def lambda_handler(event: dict[str, Any], _: Any) -> dict[str, Any]:
    """
    Handler for the AWS Config recorder configurator Lambda function.

    This function is responsible for:
    - Loading the desired configuration from Secrets Manager
    - Applying the configuration to the AWS Config recorder in member accounts
    """

    # Get the recorder name from the environment variable
    recorder_name = os.environ.get("RECORDER_NAME", "").strip()
    # Get the log level from the event or environment variable
    log_level = (
        event.get("log_level") or os.environ.get("LOG_LEVEL") or "INFO"
    ).upper()
    # Get the dry run mode from the environment variable
    dry_run = (
        event.get("dry_run")
        or os.environ.get("ENABLE_DRY_MODE", "false").upper() == "TRUE"
    )
    regions_raw = event.get("regions")
    if regions_raw:
        regions = [str(r).strip() for r in regions_raw]
    else:
        regions = [
            r.strip()
            for r in os.environ.get("RECORDER_REGIONS", "").split(",")
            if r.strip()
        ]
    if not regions:
        fallback = os.environ.get("AWS_REGION", "").strip()
        if fallback:
            regions = [fallback]

    # Get the Secret Manager name from the environment variable
    secret_manager_name = os.environ.get("SECRET_MANAGER_NAME", "").strip()

    try:
        logger.info(
            "Starting Lambda handler",
            extra={
                "action": "lambda_handler",
                "dry_run": dry_run,
                "event": event,
                "log_level": log_level,
                "recorder_name": recorder_name,
                "regions": regions,
                "secret_manager_name": secret_manager_name,
            },
        )
        # Set the log level
        logger.setLevel(log_level)
        # Ensure the recorder name and secret name are set
        if not recorder_name:
            raise ValueError("RECORDER_NAME environment variable is required")
        if not secret_manager_name:
            raise ValueError("SECRET_MANAGER_NAME environment variable is required")

        # Get the desired configuration from Secret Manager
        desired_config = load_configuration(secret_manager_name)
        # Load all the accounts from the AWS Organizations API
        accounts = list_accounts(client=organizations_client)

        any_applied = False
        skipped_not_recording = False
        skipped_no_change = False

        # Iterate over the accounts and apply the configuration to the recorder
        for _, desired in desired_config.accounts.items():
            for account_name in desired.filter.names:
                # Get the effective regions to apply the configuration to
                effective_regions = desired.filter.regions or regions
                # Iterate over the regions and apply the configuration to the recorder
                for region in effective_regions:
                    logger.info(
                        "Ensuring recorder configuration is applied to account",
                        extra={
                            "action": "lambda_handler",
                            "account_name": account_name,
                            "region": region,
                        },
                    )

                    # Get the account from the AWS Organizations API
                    account = accounts.get(account_name)
                    if not account:
                        logger.warning(
                            "Account not found, skipping configuration",
                            extra={
                                "action": "lambda_handler",
                                "account_name": account_name,
                                "region": region,
                            },
                        )
                        continue

                    # Assume into the AWSControlTowerExecution role for the account, and
                    # return a config boto3 client
                    config_client = get_config_client(
                        account_id=account.id,
                        role_arn=f"arn:aws:iam::{account.id}:role/AWSControlTowerExecution",
                        region=region,
                    )

                    # Get the existing recorder configuration (role ARN, recording status, and configuration)
                    role_arn, recording, configuration = get_recorder(
                        client=config_client,
                        recorder_name=recorder_name,
                    )
                    # If the recorder is not recording, then we ignore configuration changes
                    if not recording:
                        logger.warning(
                            "Recorder is not recording, ignoring configuration changes",
                            extra={
                                "action": "lambda_handler",
                                "recorder_name": recorder_name,
                            },
                        )
                        logger.warning(
                            "Recorder is not recording, ignoring configuration changes",
                            extra={
                                "action": "lambda_handler",
                                "account_name": account_name,
                                "recorder_name": recorder_name,
                                "region": region,
                            },
                        )
                        skipped_not_recording = True
                        continue

                    # Merge the desired configuration with the current configuration
                    changed, merged = merge_configurations(desired, configuration)

                    # If the configuration did not change, then we skip the configuration
                    if not changed:
                        logger.info(
                            "Configuration did not change, skipping configuration changes",
                            extra={
                                "action": "lambda_handler",
                                "recorder_name": recorder_name,
                            },
                        )

                        logger.info(
                            "Configuration did not change, skipping configuration changes",
                            extra={
                                "action": "lambda_handler",
                                "account_name": account_name,
                                "recorder_name": recorder_name,
                                "region": region,
                            },
                        )

                        skipped_no_change = True
                        continue

                    # Apply the recorder configuration
                    logger.info(
                        "Changes detected, applying recorder configuration",
                        extra={
                            "action": "lambda_handler",
                            "recorder_name": recorder_name,
                            "merged": merged,
                        },
                    )

                    if not dry_run:
                        # Put the recorder configuration
                        config_client.put_configuration_recorder(
                            ConfigurationRecorder={
                                "name": recorder_name,
                                "roleARN": role_arn,
                                "recordingGroup": merged.get("recordingGroup"),
                                "recordingMode": merged.get("recordingMode"),
                            }
                        )
                        any_applied = True
                        logger.info(
                            "Successfully applied recorder configuration",
                            extra={
                                "action": "lambda_handler",
                                "account_name": account_name,
                                "dry_run": dry_run,
                                "recorder_name": recorder_name,
                                "region": region,
                            },
                        )
                    else:
                        logger.info(
                            "Dry run mode enabled, skipping recorder configuration",
                            extra={
                                "action": "lambda_handler",
                                "current": configuration,
                                "desired": merged,
                                "recorder_name": recorder_name,
                                "region": region,
                            },
                        )

                    logger.info(
                        "Successfully applied recorder configuration with region",
                        extra={
                            "action": "lambda_handler",
                            "account_name": account_name,
                            "recorder_name": recorder_name,
                            "region": region,
                        },
                    )

        if any_applied:
            return lambda_response(
                message="Successfully applied recorder configuration to all regions",
                recorder_name=recorder_name,
                status="ok",
            )

        if skipped_not_recording and not skipped_no_change:
            return lambda_response(
                message="Recorder is not recording, ignoring configuration changes",
                recorder_name=recorder_name,
                status="skipped",
            )

        if skipped_no_change:
            return lambda_response(
                message="Configuration did not change, skipping configuration changes",
                recorder_name=recorder_name,
                status="skipped",
            )

        return lambda_response(
            message="No applicable configuration changes",
            recorder_name=recorder_name,
            status="skipped",
        )

    except Exception as e:
        logger.error(
            "Error applying recorder configuration",
            extra={
                "action": "lambda_handler",
                "recorder_name": recorder_name,
                "error": str(e),
            },
        )
        lambda_response("error", recorder_name, str(e))

        raise e
