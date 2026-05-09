locals {
  ## Name of the EventBridge rule
  event_rule_name = format("%s-schedule", var.name)

  ## Name of the CloudWatch alarm for Lambda errors
  lambda_error_alarm_name = format("%s-lambda-errors", var.name)
}

## Create the Secret Manager secret for the recorder configuration
resource "aws_secretsmanager_secret" "config" {
  name_prefix             = format("%s-", var.secret_manager_name)
  description             = "The desired recorder configuration for the AWS Config recorder"
  recovery_window_in_days = 7
  tags                    = merge(var.tags, { "Name" = var.secret_manager_name })
}

## Create the Secret Manager secret version for the recorder configuration
resource "aws_secretsmanager_secret_version" "config" {
  secret_id     = aws_secretsmanager_secret.config.id
  secret_string = jsonencode(var.config)
}

## Create the IAM policy document for the Lambda function
data "aws_iam_policy_document" "lambda_policy" {
  statement {
    sid    = "GetSecretValue"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
    ]
    resources = [
      aws_secretsmanager_secret.config.arn,
    ]
  }

  statement {
    sid    = "ListAccounts"
    effect = "Allow"
    actions = [
      "organizations:ListAccounts",
    ]
    resources = ["*"]
  }

  # Lambda code (assets/functions/client.py) always passes AssumeRole Policy:
  # an inline session policy limiting assumed credentials to Config recorder APIs.
  statement {
    sid    = "AssumeControlTowerExecutionRole"
    effect = "Allow"
    actions = [
      "sts:AssumeRole",
    ]
    resources = [
      "arn:aws:iam::*:role/AWSControlTowerExecution",
    ]
  }
}

## Lambda function for AWS Config recorder configuration
module "lambda" {
  source  = "terraform-aws-modules/lambda/aws"
  version = "8.8.0"

  architectures = ["arm64"]
  function_name = var.name
  memory_size   = var.lambda_memory_size
  function_tags = var.tags
  description   = "Used to configure the pre-existing AWS Config configuration recorder (e.g. Control Tower baseline)"
  handler       = "handler.lambda_handler"
  runtime       = var.lambda_runtime
  timeout       = var.lambda_timeout
  tags          = var.tags

  source_path = [
    {
      path = "${path.module}/assets/functions"
      patterns = [
        "!test_.*\\.py",
        "!__pycache__/",
        "!tests/",
      ]
    }
  ]

  environment_variables = {
    ENABLE_DRY_MODE     = var.enable_dry_run ? "true" : "false"
    LOG_LEVEL           = var.enable_debug ? "DEBUG" : "INFO"
    RECORDER_NAME       = var.recorder_name
    RECORDER_REGIONS    = join(",", var.regions)
    SECRET_MANAGER_NAME = aws_secretsmanager_secret.config.name
  }

  ## Lambda Role
  create_role                   = true
  role_force_detach_policies    = true
  role_maximum_session_duration = 3600
  role_name                     = var.name
  role_path                     = "/"
  role_permissions_boundary     = null
  role_tags                     = var.tags

  ## IAM Policy
  attach_cloudwatch_logs_policy = true
  attach_network_policy         = false
  attach_policy_json            = true
  attach_tracing_policy         = true
  policy_json                   = data.aws_iam_policy_document.lambda_policy.json
}

## CloudWatch alarm for Lambda failures (Errors > 0)
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  count = var.enable ? 1 : 0

  alarm_actions             = var.sns_topic_arn != null ? [var.sns_topic_arn] : []
  alarm_description         = "Alarm when the config recorder Lambda reports errors"
  alarm_name                = local.lambda_error_alarm_name
  comparison_operator       = "GreaterThanOrEqualToThreshold"
  evaluation_periods        = 1
  insufficient_data_actions = []
  metric_name               = "Errors"
  namespace                 = "AWS/Lambda"
  ok_actions                = var.sns_topic_arn != null ? [var.sns_topic_arn] : []
  period                    = 300
  statistic                 = "Sum"
  tags                      = merge(var.tags, { "Name" = local.lambda_error_alarm_name })
  threshold                 = 1
  treat_missing_data        = "notBreaching"

  dimensions = {
    FunctionName = module.lambda.lambda_function_name
  }
}

## EventBridge rule to trigger the Lambda on a schedule
resource "aws_cloudwatch_event_rule" "schedule" {
  count = var.enable ? 1 : 0

  name                = local.event_rule_name
  description         = "Invokes the config recorder configuration lambda on a schedule"
  schedule_expression = var.schedule_expression
  tags                = merge(var.tags, { "Name" = local.event_rule_name })
}

## Provision the cloudwatch event target to link the EventBridge rule to the Lambda function
resource "aws_cloudwatch_event_target" "schedule_target" {
  count = var.enable ? 1 : 0

  rule = aws_cloudwatch_event_rule.schedule[0].name
  arn  = module.lambda.lambda_function_arn
}

## Provide permissions for EventBridge to invoke the Lambda function
resource "aws_lambda_permission" "allow_eventbridge" {
  count = var.enable ? 1 : 0

  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda.lambda_function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule[0].arn
}
