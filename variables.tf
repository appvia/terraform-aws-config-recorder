variable "config" {
  description = <<-EOT
    Desired recorder settings per logical block, stored as JSON in Secrets Manager. Each map entry is applied
    to the member account whose Organizations account name matches `filter.name` (see README).
  EOT
  type = map(object({
    # The account filter to filter the accounts to apply the configuration to
    filter = object({
      # Name of the account
      names = list(string)
      # If set, only these regions; if null or [], use var.regions (or Lambda region when var.regions is empty)
      regions = optional(list(string), [])
    })
    # Include we set all supported resources in the recorder
    enable_all_supported = optional(bool, true)
    # Indicates whether global resources should be recorded
    enable_global = optional(bool, true)
    # The mode to apply to the recorder (i.e. DAILY or CONTINUOUS)
    mode = optional(string, "CONTINUOUS")
    # The resources to include in the recorder
    resources = optional(list(string), [])
    # The resources to exclude from the recorder
    exclude_resources = optional(list(string), [])
    # The overrides to apply to the recorder
    overrides = optional(list(object({
      # A human-readable description of the override
      description = string
      # The resource to apply the override to
      resources = list(string)
      # The type of override to apply (DAILY or CONTINUOUS)
      override_type = string
    })), [])
  }))
  default = {}
}

variable "enable" {
  description = "Whether to enable the config recorder configuration"
  type        = bool
  default     = true
}

variable "enable_debug" {
  description = "Whether to enable debug mode (which will print debug logs to the CloudWatch logs)"
  type        = bool
  default     = false
}

variable "enable_dry_run" {
  description = "Whether to enable dry run mode (which will not make any changes to the recorder configuration)"
  type        = bool
  default     = false
}

variable "schedule_expression" {
  description = "The EventBridge schedule expression used to invoke the Lambda"
  type        = string
}

variable "lambda_memory_size" {
  description = "The amount of memory in MB for the Lambda"
  type        = number
  default     = 256
}

variable "lambda_runtime" {
  description = "The runtime for the Lambda"
  type        = string
  default     = "python3.13"
}

variable "lambda_timeout" {
  description = "The timeout in seconds for the Lambda"
  type        = number
  default     = 120
}

variable "name" {
  description = "The base name used for resources"
  type        = string
  default     = "lz-config-recorder"
}

variable "recorder_name" {
  description = "Name of the existing AWS Config recorder to manage"
  type        = string
  default     = "aws-controltower-BaselineConfigRecorder"
}

variable "regions" {
  description = <<-EOT
    Default region list for every `config` entry whose `filter.regions` is omitted or empty. Passed to the
    Lambda as `RECORDER_REGIONS`. When empty, the function uses the Lambda runtime region (`AWS_REGION`).
  EOT
  type        = list(string)
  default     = []
}

variable "secret_manager_name" {
  description = "Name of the Secrets Manager secret that stores the recorder configuration JSON"
  type        = string
  default     = "/lz/aws-config/config"
}

variable "sns_topic_arn" {
  description = "Optional SNS topic ARN to notify when the Lambda alarm fires"
  type        = string
  default     = null
}

variable "tags" {
  description = "A collection of tags to apply to resources"
  type        = map(string)
  default     = {}
}

variable "trigger_on_package_timestamp" {
  description = "Whether to trigger the Lambda on the package timestamp"
  type        = bool
  default     = false
}