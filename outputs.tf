output "eventbridge_rule_name" {
  description = "Name of the EventBridge rule invoking the Lambda"
  value       = try(aws_cloudwatch_event_rule.schedule[0].name, null)
}

output "lambda_function_arn" {
  description = "ARN of the Lambda function"
  value       = module.lambda.lambda_function_arn
}

output "lambda_failure_alarm_arn" {
  description = "ARN of the CloudWatch alarm which triggers on Lambda errors"
  value       = try(aws_cloudwatch_metric_alarm.lambda_errors[0].arn, null)
}

output "secret_manager_name" {
  description = "Name of the Secret Manager secret holding the JSON configuration"
  value       = aws_secretsmanager_secret.config.name
}