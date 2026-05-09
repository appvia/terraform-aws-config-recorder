#####################################################################################
# Terraform module examples are meant to show an _example_ on how to use a module
# per use-case. The code below should not be copied directly but referenced in order
# to build your own root module that invokes this module
#
# Deploy from the AWS Organizations management account: the Lambda lists accounts and
# assumes AWSControlTowerExecution in each matching member account.
#####################################################################################

locals {
  tags = {
    Environment = "Testing"
    Owner       = "Engineering"
    Product     = "LandingZone"
    GitRepo     = "https://github.com/appvia/terraform-aws-config-recorder"
  }
}

module "config_recorder" {
  source = "../../"

  # The name of the config recorder
  name = "aws-config-recorder"
  # Whether to enable dry run mode (which will not make any changes to the recorder configuration)
  enable_dry_run = true
  # Whether to enable debug mode (which will print debug logs to the CloudWatch logs)
  enable_debug = true
  # The EventBridge schedule expression used to invoke the Lambda
  schedule_expression = "cron(0 2 * * ? *)"
  # The name of the Secret Manager secret holding the JSON configuration
  secret_manager_name = "/lza/aws-config/recorder/config"
  # Optional SNS topic ARN to notify when the Lambda alarm fires
  # sns_topic_arn = "arn:aws:sns:eu-west-2:123456789012:platform-alerts"
  # The tags to apply to the resources
  tags = local.tags
  # Default regions when a config entry omits filter.regions (see README)
  regions = ["eu-west-2", "us-east-1"]

  config = {
    devops = {
      filter = {
        # Must match the member account name in AWS Organizations
        name = "Devops"
      }
      overrides = [
        {
          # A human-readable description of the override
          description = "Overriding the following resource to be recorded daily instead of continuously"
          # The resource to apply the override to
          resources = [
            "AWS::EC2::Instance",
          ]
          # The type of override to apply (DAILY or CONTINUOUS)
          override_type = "DAILY"
        }
      ]
    }
  }
}

