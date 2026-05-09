"""AWS Organizations helpers used by the Lambda function."""

from dataclasses import dataclass

import boto3

from logger import logger


@dataclass(frozen=True)
class Account:
    # The account id
    id: str
    # The account name
    name: str
    # The account email
    email: str


def list_accounts(
    client: boto3.client,
) -> dict[str, Account]:
    """
    Get all the accounts from the AWS Organizations API

    Args:
        client: The AWS Organizations client

    Returns:
        A map of Account objects by account id

    Raises:
        Exception: If the accounts cannot be listed
    """

    accounts: dict[str, Account] = {}

    try:
        # List the accounts and account ids
        paginator = client.get_paginator("list_accounts")
        for page in paginator.paginate():
            for record in page.get("Accounts", []):
                if record.get("Status") != "ACTIVE":
                    continue

                acct = Account(
                    id=str(record.get("Id", "")),
                    name=str(record.get("Name", "")),
                    email=str(record.get("Email", "")),
                )
                # Key by name because configuration targets accounts by name
                accounts[acct.name] = acct

        # Next we need to get the account details for each account id
        logger.debug(
            "Accounts retrieved",
            extra={
                "action": "list_accounts",
                "accounts": accounts,
            },
        )

        return accounts

    except Exception as e:
        logger.error(
            "Error listing accounts",
            extra={
                "action": "list_accounts",
                "error": str(e),
            },
        )
        raise e
