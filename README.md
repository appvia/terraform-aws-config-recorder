## terraform-aws-config-recorder

### Introduction
AWS Control Tower establishes an AWS Config baseline in enrolled accounts (including creating/enabling a configuration recorder), but it **does not provide a central way to consistently configure that recorder across accounts**.

The practical impact is that accounts can drift back to a “record everything, continuously” posture (or simply remain there), which can create **unexpectedly high AWS Config costs** at scale—especially in large organizations with many accounts and regions.

### Intent
This module provides a repeatable way to **enforce a desired AWS Config recorder configuration in an account** (typically an account enrolled in Control Tower), without attempting to replace the Control Tower baseline.

In short, it helps you:

- **Standardize** recorder settings across accounts
- **Reduce cost exposure** by switching to daily recording, excluding resource types, or applying overrides
- **Continuously remediate drift** (on a schedule) rather than relying on one-time manual changes

### How it works
At a high level the module:

- Stores your desired recorder configuration (as JSON) in **SSM Parameter Store**
- Deploys a small **Lambda** that reads that parameter and applies it to an **existing** AWS Config recorder via the AWS Config APIs
- Invokes the Lambda on an **EventBridge schedule** to keep the recorder aligned over time

### Usage examples

#### Example 1: Record daily, exclude noisy resource types

```hcl
module "config_recorder" {
  source = "appvia/config-recorder/aws"

  name                = "aws-config-recorder"
  recorder_name       = "aws-controltower-BaselineConfigRecorder"
  schedule_expression = "cron(0 2 * * ? *)"
  ssm_parameter_name  = "/org/aws-config/recorder/config"

  config = {
    enable = true
    mode   = "DAILY"

    exclude_resources = [
      "AWS::CloudTrail::Trail",
      "AWS::Config::ResourceCompliance",
    ]
  }
}
```

#### Example 2: Record only specific resource types (continuous)

```hcl
module "config_recorder" {
  source = "appvia/config-recorder/aws"

  name                = "aws-config-recorder"
  recorder_name       = "aws-controltower-BaselineConfigRecorder"
  schedule_expression = "rate(6 hours)"
  ssm_parameter_name  = "/org/aws-config/recorder/config"

  config = {
    enable    = true
    mode      = "CONTINUOUS"
    resources = [
      "AWS::S3::Bucket",
      "AWS::EC2::Instance",
    ]
  }
}
```

#### Example 3: Stop the recorder (temporarily disable)

```hcl
module "config_recorder" {
  source = "appvia/config-recorder/aws"

  name                = "aws-config-recorder"
  recorder_name       = "aws-controltower-BaselineConfigRecorder"
  schedule_expression = "rate(1 day)"
  ssm_parameter_name  = "/org/aws-config/recorder/config"

  config = {
    enable = false
  }
}
```

### Notes / assumptions
- **Existing recorder required**: this module configures a recorder that already exists (e.g. created by Control Tower). It does not create the recorder or delivery channel.
- **Apply scope**: deploy this module per account (and per region if you operate multi-region Config) using your preferred account vending / pipeline approach.

<!-- BEGIN_TF_DOCS -->
## Providers

| Name | Version |
|------|---------|
| <a name="provider_aws"></a> [aws](#provider\_aws) | >= 6.0.0 |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_schedule_expression"></a> [schedule\_expression](#input\_schedule\_expression) | The EventBridge schedule expression used to invoke the Lambda | `string` | n/a | yes |
| <a name="input_config"></a> [config](#input\_config) | The configuration JSON (as an object) to store in SSM and apply to the recorder | <pre>object({<br/>    # Indicates if the configuration is enabled (controls the schedule nothing else)<br/>    enable = optional(bool, true)<br/>    # The mode to apply to the recorder (i.e. DAILY or CONTINUOUS)<br/>    mode = optional(string, "CONTINUOUS")<br/>    # The resources to include in the recorder<br/>    resources = optional(list(string), [])<br/>    # The resources to exclude from the recorder<br/>    exclude_resources = optional(list(string), [])<br/>    # The overrides to apply to the recorder<br/>    overrides = optional(list(object({<br/>      # A human-readable description of the override<br/>      description = optional(string, "Override for resource types")<br/>      # The resource to apply the override to<br/>      resources = list(string)<br/>      # The type of override to apply (DAILY or CONTINUOUS)<br/>      override_type = optional(string, "DAILY")<br/>    })), [])<br/>  })</pre> | `{}` | no |
| <a name="input_lambda_memory_size"></a> [lambda\_memory\_size](#input\_lambda\_memory\_size) | The amount of memory in MB for the Lambda | `number` | `256` | no |
| <a name="input_lambda_runtime"></a> [lambda\_runtime](#input\_lambda\_runtime) | The runtime for the Lambda | `string` | `"python3.14"` | no |
| <a name="input_lambda_timeout"></a> [lambda\_timeout](#input\_lambda\_timeout) | The timeout in seconds for the Lambda | `number` | `120` | no |
| <a name="input_name"></a> [name](#input\_name) | The base name used for resources | `string` | `"lz-config-recorder"` | no |
| <a name="input_recorder_name"></a> [recorder\_name](#input\_recorder\_name) | Name of the existing AWS Config recorder to manage | `string` | `"aws-controltower-BaselineConfigRecorder"` | no |
| <a name="input_ssm_parameter_name"></a> [ssm\_parameter\_name](#input\_ssm\_parameter\_name) | The name of the SSM parameter to store the recorder configuration JSON | `string` | `"/lz/aws-config/recorder/config"` | no |
| <a name="input_tags"></a> [tags](#input\_tags) | A collection of tags to apply to resources | `map(string)` | `{}` | no |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_eventbridge_rule_name"></a> [eventbridge\_rule\_name](#output\_eventbridge\_rule\_name) | Name of the EventBridge rule invoking the Lambda |
| <a name="output_lambda_function_arn"></a> [lambda\_function\_arn](#output\_lambda\_function\_arn) | ARN of the Lambda function |
| <a name="output_ssm_parameter_name"></a> [ssm\_parameter\_name](#output\_ssm\_parameter\_name) | Name of the SSM parameter holding the JSON configuration |
<!-- END_TF_DOCS -->
