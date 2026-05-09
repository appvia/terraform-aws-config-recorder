locals {
  ## Name of the EventBridge rule
  event_rule_name = format("%s-schedule", var.name)
}

## Store the desired recorder configuration in SSM as JSON
resource "aws_ssm_parameter" "recorder_config" {
  name  = var.ssm_parameter_name
  tags  = merge(var.tags, { "Name" = var.ssm_parameter_name })
  type  = "String"
  value = jsonencode(var.config)
}

## Create the IAM policy document for the Lambda function
data "aws_iam_policy_document" "lambda_policy" {
  statement {
    sid    = "ReadRecorderConfigurationFromSSM"
    effect = "Allow"
    actions = [
      "ssm:GetParameter",
    ]
    resources = [
      aws_ssm_parameter.recorder_config.arn,
    ]
  }

  statement {
    sid    = "ManageConfigRecorder"
    effect = "Allow"
    actions = [
      "config:DescribeConfigurationRecorders",
      "config:DescribeConfigurationRecorderStatus",
      "config:PutConfigurationRecorder",
      "config:StartConfigurationRecorder",
      "config:StopConfigurationRecorder",
    ]
    resources = ["*"]
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
      path = "${path.module}/assets/functions/recorder"
      patterns = [
        "!test_.*\\.py",
        "!__pycache__",
      ]
    }
  ]

  environment_variables = {
    LOG_LEVEL          = "INFO"
    RECORDER_NAME      = var.recorder_name
    SSM_PARAMETER_NAME = var.ssm_parameter_name
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

## EventBridge rule to trigger the Lambda on a schedule
resource "aws_cloudwatch_event_rule" "schedule" {
  count = var.config.enable ? 1 : 0

  name                = local.event_rule_name
  description         = "Invokes the config recorder configuration lambda on a schedule"
  schedule_expression = var.schedule_expression
  tags                = merge(var.tags, { "Name" = local.event_rule_name })
}

## Provision the cloudwatch event target to link the EventBridge rule to the Lambda function
resource "aws_cloudwatch_event_target" "schedule_target" {
  count = var.config.enable ? 1 : 0

  rule = aws_cloudwatch_event_rule.schedule[0].name
  arn  = module.lambda.lambda_function_arn
}

## Provide permissions for EventBridge to invoke the Lambda function
resource "aws_lambda_permission" "allow_eventbridge" {
  count = var.config.enable ? 1 : 0

  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda.lambda_function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule[0].arn
}
