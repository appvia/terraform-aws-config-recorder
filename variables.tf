variable "config" {
  description = "The configuration JSON (as an object) to store in SSM and apply to the recorder"
  type = object({
    # Indicates if the configuration is enabled (controls the schedule nothing else)
    enable = optional(bool, true)
    # The mode to apply to the recorder (i.e. DAILY or CONTINUOUS)
    mode = optional(string, "CONTINUOUS")
    # The resources to include in the recorder
    resources = optional(list(string), [])
    # The resources to exclude from the recorder
    exclude_resources = optional(list(string), [])
    # The overrides to apply to the recorder
    overrides = optional(list(object({
      # A human-readable description of the override
      description = optional(string, "Override for resource types")
      # The resource to apply the override to
      resources = list(string)
      # The type of override to apply (DAILY or CONTINUOUS)
      override_type = optional(string, "DAILY")
    })), [])
  })
  default = {}

  validation {
    condition     = contains(["CONTINUOUS", "DAILY"], var.config.mode)
    error_message = "mode must be either CONTINUOUS or DAILY"
  }
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
  default     = "python3.14"
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

variable "ssm_parameter_name" {
  description = "The name of the SSM parameter to store the recorder configuration JSON"
  type        = string
  default     = "/lz/aws-config/recorder/config"
}

variable "tags" {
  description = "A collection of tags to apply to resources"
  type        = map(string)
  default     = {}
}

