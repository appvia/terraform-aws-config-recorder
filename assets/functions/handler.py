"""
Handler for the AWS Config recorder configurator Lambda function.
"""

from __future__ import annotations

import json
import os
from typing import Any, Literal

from types import DesiredConfig

import boto3
from logger import logger

# Initialize the AWS clients
ssm = boto3.client("ssm")  # pylint: disable=no-member
# Initialize the AWS Config client
config = boto3.client("config")  # pylint: disable=no-member


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
    merged = existing.copy()
    # Set the recording frequency in the merged configuration
    merged.get("recordingMode", {}).set("recordingFrequency", desired.mode)

    # If the desired configuration has resources, then set the resources in the merged configuration
    if desired.resources and len(desired.resources) > 0:
        merged.get("recordingGroup", {}).set("resourceTypes", desired.resources)
    if desired.exclude_resources and len(desired.exclude_resources) > 0:
        merged.get("recordingGroup", {}).get("exclusionByResourceTypes", {}).set(
            "resourceTypes", desired.exclude_resources
        )

    # If we have overrides, then set the overrides in the merged configuration
    if desired.overrides and len(desired.overrides) > 0:
        for override in desired.overrides:
            merged.get("recordingGroup", {}).get("overrides", {}).append(
                {
                    "description": override.description,
                    "recordingFrequency": override.override_type,
                    "resource": override.resource,
                }
            )

    # Get a json diff of the merged configuration and the existing configuration
    diff = json.dumps(merged, sort_keys=True) - json.dumps(existing, sort_keys=True)
    if diff:
        logger.info(
            "Configuration has changed",
            extra={
                "action": "merge_configurations",
                "diff": diff,
            },
        )

    # Check if the merged configuration is different from the existing configuration
    changed = merged != existing

    return changed, merged


def load_configuration(
    ssm_parameter_name: str,
) -> DesiredConfig:
    """
    Load the desired configuration from SSM and parse it into a DesiredConfig object

    Args:
        ssm_parameter_name: The name of the SSM parameter to load the configuration from

    Returns:
        A DesiredConfig object

    Raises:
        ValueError: If the SSM parameter is not found or is not a valid JSON object
    """

    logger.info(
        "Loading desired configuration from SSM",
        extra={
            "action": "load_configuration",
            "ssm_parameter_name": ssm_parameter_name,
        },
    )

    # Get the parameter from SSM
    param = ssm.get_parameter(Name=ssm_parameter_name)
    # Get the raw value from the parameter
    raw_value = param["Parameter"]["Value"]
    # Load the raw configuration into a DesiredConfig object
    return DesiredConfig.load(json.loads(raw_value))


def get_recorder(recorder_name: str) -> tuple[str, str, dict[str, Any]]:
    """
    Get the recorder configuration from AWS Config

    Args:
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
        recorders = config.describe_configuration_recorders(
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
        status = config.describe_configuration_recorder_status(
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

        # Return the role ARN, recording status, and existing recorder configuration
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
    - Loading the desired configuration from SSM
    - Applying the configuration to the AWS Config recorder
    - Starting or stopping the recorder based on the configuration
    """

    # Get the recorder name from the environment variable
    recorder_name = os.environ.get("RECORDER_NAME", "").strip()
    # Get the log level from the event or environment variable
    log_level = (
        event.get("log_level") or os.environ.get("LOG_LEVEL") or "INFO"
    ).upper()
    # Get the SSM parameter name from the environment variable
    ssm_parameter_name = os.environ.get("SSM_PARAMETER_NAME", "").strip()

    try:
        logger.info(
            "Starting Lambda handler",
            extra={
                "action": "lambda_handler",
                "event": event,
                "log_level": log_level,
                "recorder_name": recorder_name,
                "ssm_parameter_name": ssm_parameter_name,
            },
        )
        # Set the log level
        logger.setLevel(log_level)
        # Ensure the recorder name and SSM parameter name are set
        if not recorder_name:
            raise ValueError("RECORDER_NAME environment variable is required")
        if not ssm_parameter_name:
            raise ValueError("SSM_PARAMETER_NAME environment variable is required")

        # Get the desired configuration from SSM
        desired = load_configuration(ssm_parameter_name)

        # Get the existing recorder configuration (role ARN, recording status, and configuration)
        role_arn, recording, configuration = get_recorder(recorder_name)
        # If the recorder is not recording, then we ignore configuration changes
        if not recording:
            logger.warning(
                "Recorder is not recording, ignoring configuration changes",
                extra={
                    "action": "lambda_handler",
                    "recorder_name": recorder_name,
                },
            )

            return lambda_response(
                message="Recorder is not recording, ignoring configuration changes",
                recorder_name=recorder_name,
                status="skipped",
            )

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

            return lambda_response(
                message="Configuration did not change, skipping configuration changes",
                recorder_name=recorder_name,
                status="skipped",
            )

        # Apply the recorder configuration
        logger.info(
            "Changes detected, applying recorder configuration",
            extra={
                "action": "lambda_handler",
                "recorder_name": recorder_name,
                "merged": merged,
            },
        )

        # Put the recorder configuration
        config.put_configuration_recorder(
            ConfigurationRecorder={
                "name": recorder_name,
                "roleARN": role_arn,
                "recordingGroup": merged.get("recordingGroup"),
                "recordingMode": merged.get("recordingMode"),
            }
        )

        logger.info(
            "Successfully applied recorder configuration",
            extra={
                "action": "lambda_handler",
                "recorder_name": recorder_name,
            },
        )

        return lambda_response(
            message="Successfully applied recorder configuration",
            recorder_name=recorder_name,
            status="ok",
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
