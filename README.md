# Terraform AWS Config Recorder

### Introduction

AWS Control Tower establishes an AWS Config baseline in enrolled accounts (including creating/enabling a configuration recorder), but it **does not provide a central way to consistently configure that recorder across accounts**.

The practical impact is that accounts can drift back to a “record everything, continuously” posture (or simply remain there), which can create **unexpectedly high AWS Config costs** at scale—especially in large organizations with many accounts and regions.

### Intent

This module provides a repeatable way to **enforce a desired AWS Config recorder configuration across member accounts** enrolled in Control Tower, from the **organization management account**, without replacing the Control Tower baseline.

It helps you:

- **Standardize** recorder settings across accounts
- **Reduce cost exposure** by switching to daily recording, excluding resource types, or applying overrides
- **Continuously remediate drift** (on a schedule) rather than relying on one-time manual changes

### Deployment model

Deploy this module in the **AWS Organizations management account** (the account that owns the organization).

The Lambda runs there so it can call `organizations:ListAccounts` and resolve member accounts by name. For each configured entry, the function **assumes the Control Tower execution role** in the target account. That role is named **`AWSControlTowerExecution`** in every enrolled account.

Cross-account access is constrained in two ways:

1. **Lambda execution role** (`main.tf`): `sts:AssumeRole` is allowed only for `arn:aws:iam::*:role/AWSControlTowerExecution`.
2. **AssumeRole session policy** (`assets/functions/client.py`): each `sts:AssumeRole` call attaches an inline session policy that can only *reduce* privileges. It limits the session to `config:DescribeConfigurationRecorders`, `config:DescribeConfigurationRecorderStatus`, and `config:PutConfigurationRecorder`.

### How it works

- The desired configuration is stored as JSON in **AWS Secrets Manager** (`secret_manager_name`).
- A **Lambda** reads the secret, lists accounts in Organizations, and for each matching member account and region updates the **existing** baseline recorder (`recorder_name`) via the Config API using credentials from the assumed `AWSControlTowerExecution` role.
- **Amazon EventBridge** invokes the Lambda on `schedule_expression`.

### Account filters and regions

The `config` input is a map. Each value describes how to tune the recorder for **one Organizations member account**:

- **`filter.name`** (required): must match the **account name** returned by Organizations (`ListAccounts`), not the account ID.
- **`filter.regions`** (optional): when set to a **non-empty** list, the Lambda applies that block **only** in those regions and **does not** use `var.regions` for that entry. When omitted, null, or `[]`, that entry uses the module default regions below.

The **top-level keys** in `config` (for example `devops`, `workloads`) are arbitrary labels for Terraform and become keys in the JSON secret; they are not sent to AWS.

#### `var.regions` vs `filter.regions`

| Input | Role |
|--------|------|
| **`var.regions`** | Default region list for every `config` entry that does not set `filter.regions`. Passed to the Lambda as `RECORDER_REGIONS` (comma-separated). If you leave it as the default `[]`, the function uses the **Lambda runtime region** (`AWS_REGION`) for those entries—typically the region where you deploy the stack. |
| **`filter.regions`** | Per-entry override: **replaces** `var.regions` for that map entry only, so you can target one region for one account and a broader list for another. |

### Usage examples

#### Example 1: Daily recording and exclusions (shared default regions)

```hcl
module "config_recorder" {
  source = "appvia/config-recorder/aws"

  name                = "aws-config-recorder"
  recorder_name       = "aws-controltower-BaselineConfigRecorder"
  schedule_expression = "cron(0 2 * * ? *)"
  secret_manager_name = "/org/aws-config/recorder/config"

  regions = ["eu-west-2", "us-east-1"]

  config = {
    workloads = {
      filter = {
        name = "Workloads" # Must match the Organizations account name
      }
      mode = "DAILY"
      exclude_resources = [
        "AWS::CloudTrail::Trail",
        "AWS::Config::ResourceCompliance",
      ]
    }
  }
}
```

#### Example 2: Continuous recording for specific resource types — `filter.regions` overrides `var.regions`

For this entry only, the recorder is updated in `eu-west-2` even if `var.regions` lists additional regions.

```hcl
module "config_recorder" {
  source = "appvia/config-recorder/aws"

  name                = "aws-config-recorder"
  recorder_name       = "aws-controltower-BaselineConfigRecorder"
  schedule_expression = "rate(6 hours)"
  secret_manager_name = "/org/aws-config/recorder/config"

  regions = ["eu-west-2", "us-east-1"]

  config = {
    security = {
      filter = {
        name    = "Security"
        regions = ["eu-west-2"]
      }
      mode      = "CONTINUOUS"
      resources = [
        "AWS::S3::Bucket",
        "AWS::EC2::Instance",
      ]
    }
  }
}
```

#### Example 3: Multiple member accounts

```hcl
module "config_recorder" {
  source = "appvia/config-recorder/aws"

  name                = "aws-config-recorder"
  recorder_name       = "aws-controltower-BaselineConfigRecorder"
  schedule_expression = "rate(1 day)"
  secret_manager_name = "/org/aws-config/recorder/config"

  regions = ["eu-west-2"]

  config = {
    development = {
      filter = { name = "Development" }
      mode   = "DAILY"
    }
    production = {
      filter = {
        name    = "Production"
        regions = ["eu-west-2", "us-east-1"]
      }
      mode = "DAILY"
    }
  }
}
```

### Notes / assumptions

- **Management account**: required so Organizations APIs and the intended assume-role pattern align with Control Tower landing zones.
- **Existing recorder**: the module does not create the recorder or delivery channel; it updates the existing Control Tower baseline recorder.
- **Pause scheduled runs**: set **`enable = false`** on the module to skip creating the EventBridge schedule (the Lambda and secret can remain for ad-hoc use).

<!-- BEGIN_TF_DOCS -->
## Providers

| Name | Version |
|------|---------|
| <a name="provider_aws"></a> [aws](#provider\_aws) | >= 6.0.0 |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_schedule_expression"></a> [schedule\_expression](#input\_schedule\_expression) | The EventBridge schedule expression used to invoke the Lambda | `string` | n/a | yes |
| <a name="input_config"></a> [config](#input\_config) | Desired recorder settings per logical block, stored as JSON in Secrets Manager. Each map entry is applied<br/>to the member account whose Organizations account name matches `filter.name` (see README). | <pre>map(object({<br/>    # The account filter to filter the accounts to apply the configuration to<br/>    filter = object({<br/>      # Name of the account<br/>      name = string<br/>      # If set, only these regions; if null or [], use var.regions (or Lambda region when var.regions is empty)<br/>      regions = optional(list(string), null)<br/>    })<br/>    # The mode to apply to the recorder (i.e. DAILY or CONTINUOUS)<br/>    mode = optional(string, null)<br/>    # The resources to include in the recorder<br/>    resources = optional(list(string), null)<br/>    # The resources to exclude from the recorder<br/>    exclude_resources = optional(list(string), null)<br/>    # The overrides to apply to the recorder<br/>    overrides = optional(list(object({<br/>      # A human-readable description of the override<br/>      description = string<br/>      # The resource to apply the override to<br/>      resources = list(string)<br/>      # The type of override to apply (DAILY or CONTINUOUS)<br/>      override_type = string<br/>    })), null)<br/>  }))</pre> | `{}` | no |
| <a name="input_enable"></a> [enable](#input\_enable) | Whether to enable the config recorder configuration | `bool` | `true` | no |
| <a name="input_enable_debug"></a> [enable\_debug](#input\_enable\_debug) | Whether to enable debug mode (which will print debug logs to the CloudWatch logs) | `bool` | `false` | no |
| <a name="input_enable_dry_run"></a> [enable\_dry\_run](#input\_enable\_dry\_run) | Whether to enable dry run mode (which will not make any changes to the recorder configuration) | `bool` | `false` | no |
| <a name="input_lambda_memory_size"></a> [lambda\_memory\_size](#input\_lambda\_memory\_size) | The amount of memory in MB for the Lambda | `number` | `256` | no |
| <a name="input_lambda_runtime"></a> [lambda\_runtime](#input\_lambda\_runtime) | The runtime for the Lambda | `string` | `"python3.13"` | no |
| <a name="input_lambda_timeout"></a> [lambda\_timeout](#input\_lambda\_timeout) | The timeout in seconds for the Lambda | `number` | `120` | no |
| <a name="input_name"></a> [name](#input\_name) | The base name used for resources | `string` | `"lz-config-recorder"` | no |
| <a name="input_recorder_name"></a> [recorder\_name](#input\_recorder\_name) | Name of the existing AWS Config recorder to manage | `string` | `"aws-controltower-BaselineConfigRecorder"` | no |
| <a name="input_regions"></a> [regions](#input\_regions) | Default region list for every `config` entry whose `filter.regions` is omitted or empty. Passed to the<br/>Lambda as `RECORDER_REGIONS`. When empty, the function uses the Lambda runtime region (`AWS_REGION`). | `list(string)` | `[]` | no |
| <a name="input_secret_manager_name"></a> [secret\_manager\_name](#input\_secret\_manager\_name) | Name of the Secrets Manager secret that stores the recorder configuration JSON | `string` | `"/lz/aws-config/config"` | no |
| <a name="input_sns_topic_arn"></a> [sns\_topic\_arn](#input\_sns\_topic\_arn) | Optional SNS topic ARN to notify when the Lambda alarm fires | `string` | `null` | no |
| <a name="input_tags"></a> [tags](#input\_tags) | A collection of tags to apply to resources | `map(string)` | `{}` | no |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_eventbridge_rule_name"></a> [eventbridge\_rule\_name](#output\_eventbridge\_rule\_name) | Name of the EventBridge rule invoking the Lambda |
| <a name="output_lambda_failure_alarm_arn"></a> [lambda\_failure\_alarm\_arn](#output\_lambda\_failure\_alarm\_arn) | ARN of the CloudWatch alarm which triggers on Lambda errors |
| <a name="output_lambda_function_arn"></a> [lambda\_function\_arn](#output\_lambda\_function\_arn) | ARN of the Lambda function |
| <a name="output_secret_manager_name"></a> [secret\_manager\_name](#output\_secret\_manager\_name) | Name of the Secret Manager secret holding the JSON configuration |
<!-- END_TF_DOCS -->
