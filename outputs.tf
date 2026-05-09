output "eventbridge_rule_name" {
  description = "Name of the EventBridge rule invoking the Lambda"
  value       = try(aws_cloudwatch_event_rule.schedule[0].name, null)
}

output "lambda_function_arn" {
  description = "ARN of the Lambda function"
  value       = module.lambda.lambda_function_arn
}

output "ssm_parameter_name" {
  description = "Name of the SSM parameter holding the JSON configuration"
  value       = aws_ssm_parameter.recorder_config.name
}