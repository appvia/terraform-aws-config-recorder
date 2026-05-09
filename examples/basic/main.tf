#####################################################################################
# Terraform module examples are meant to show an _example_ on how to use a module
# per use-case. The code below should not be copied directly but referenced in order
# to build your own root module that invokes this module
#####################################################################################

module "config_recorder" {
  source = "../../"

  name                = "aws-config-recorder"
  recorder_name       = "aws-config-recorder-basic"
  schedule_expression = "cron(0 2 * * ? *)"
  ssm_parameter_name  = "/lza/aws-config/recorder/config"

  config = {
    # Can be CONTINUOUS or DAILY - i.e record all resources continuously or record all resources daily
    mode = "CONTINUOUS"
    # List of resources to include in the recorder
    resources = [
      "AWS::S3::Bucket",
      "AWS::S3::BucketPolicy",
      "EC2::Instance",
    ]
    # Exclude resources from the recorder
    exclude_resources = [
      "AWS::S3::BucketPolicy",
    ]
    # A collection of overrides to apply to the recorder
    overrides = [
      {
        # A human-readable description of the override
        description = "Override for AWS::S3::Bucket"
        # The resource to apply the override to
        resources = [
          "AWS::S3::Bucket",
          "AWS::EC2::Instance",
        ]
        # The type of override to apply (DAILY or CONTINUOUS), i.e record daily or continuously instead
        override_type = "DAILY"
      }
    ]
  }
}