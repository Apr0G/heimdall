# =============================================================================
# Cognito Custom Email Sender — routes ALL user-pool email (invites, password
# reset codes) through SMTP2GO as no-reply@heimdallclaims.com via a Lambda,
# bypassing SES entirely (production access denied 2026-08-24; Cognito's only
# native senders are its generic default and SES).
#
# GATED: nothing attaches to the user pool until cognito_custom_email_sender =
# true. Rollout order matters —
#   1. terraform apply                      (creates the KMS key + the Lambda
#                                            from a failing stub bundle)
#   2. run the deploy-email-sender workflow (builds + uploads the real bundle;
#                                            it npm-tests first)
#   3. verify heimdallclaims.com in SMTP2GO and set the
#      heimdall/smtp2go-api-key secret value (same prerequisites as mailer.py)
#   4. set cognito_custom_email_sender = true, terraform apply
#   5. invite a test user / run a password reset; watch the Lambda's log group
#
# ROLLBACK: flip the var back and apply. KNOWN PROVIDER BUG (hashicorp/aws
# #29048): removing custom_email_sender from lambda_config may not detach it on
# the live pool — if invites still route through the Lambda after the apply,
# detach manually:
#   aws cognito-idp update-user-pool --user-pool-id <pool-id> --lambda-config '{}'
# (then re-apply to restore any other pool settings the CLI call cleared).
#
# The trigger is ALL-or-nothing: once attached, every Cognito email depends on
# this Lambda. The alarm below pages heimdall-alerts on any Lambda error.
# =============================================================================

variable "cognito_custom_email_sender" {
  description = "Attach the SMTP2GO email-sender Lambda to the user pool. Flip only after the deploy-email-sender workflow has uploaded the real bundle AND the SMTP2GO domain + API-key secret are in place (see rollout order in cognito-email-sender.tf)."
  type        = bool
  default     = false
}

# Symmetric CMK Cognito uses to encrypt the temp password / code before
# invoking the Lambda (AWS Encryption SDK envelope). Dedicated key rather than
# reusing aws_kms_key.heimdall: the cognito-idp service principal needs Encrypt
# rights on it, and that grant should not widen the key protecting PHI secrets.
# No SourceArn condition on purpose — the pool's lambda_config references this
# key, so a key-policy condition on the pool ARN would be a dependency cycle;
# kms:ViaService + SourceAccount bound it to this account's Cognito use.
resource "aws_kms_key" "cognito_email" {
  description         = "Encrypts Cognito custom-email-sender payloads (temp passwords, codes)"
  enable_key_rotation = true
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AccountAdmin"
        Effect    = "Allow"
        Principal = { AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root" }
        Action    = "kms:*"
        Resource  = "*"
      },
      {
        Sid       = "CognitoEncrypt"
        Effect    = "Allow"
        Principal = { Service = "cognito-idp.amazonaws.com" }
        Action    = ["kms:CreateGrant", "kms:Encrypt", "kms:GenerateDataKey*", "kms:DescribeKey"]
        Resource  = "*"
        Condition = {
          StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }
        }
      },
    ]
  })
}

resource "aws_kms_alias" "cognito_email" {
  name          = "alias/heimdall-cognito-email"
  target_key_id = aws_kms_key.cognito_email.key_id
}

resource "aws_iam_role" "cognito_email_sender" {
  name = "heimdall-cognito-email-sender"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "cognito_email_sender_logs" {
  role       = aws_iam_role.cognito_email_sender.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "cognito_email_sender" {
  name = "decrypt-and-send"
  role = aws_iam_role.cognito_email_sender.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Decrypt the Encryption-SDK envelope Cognito hands us.
        Effect   = "Allow"
        Action   = "kms:Decrypt"
        Resource = aws_kms_key.cognito_email.arn
      },
      {
        # The SMTP2GO API key (shared with mailer.py); heimdall key decrypts it.
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue", "kms:Decrypt"]
        Resource = [aws_secretsmanager_secret.smtp2go_api_key.arn, aws_kms_key.heimdall.arn]
      },
    ]
  })
}

# The stub bundle only — the real, dependency-bearing bundle is uploaded by the
# deploy-email-sender workflow via update-function-code. Terraform never sees
# that drift (it compares the config hash against state, not the live code), so
# do not edit the stub after go-live: a changed hash would make the next apply
# revert the function to the stub.
data "archive_file" "cognito_email_sender_stub" {
  type        = "zip"
  source_file = "${path.module}/lambda/cognito-email-sender/stub/index.mjs"
  output_path = "${path.module}/lambda/cognito-email-sender/stub.zip"
}

resource "aws_lambda_function" "cognito_email_sender" {
  function_name    = "heimdall-cognito-email-sender"
  role             = aws_iam_role.cognito_email_sender.arn
  runtime          = "nodejs20.x"
  handler          = "index.handler"
  timeout          = 30
  memory_size      = 256
  filename         = data.archive_file.cognito_email_sender_stub.output_path
  source_code_hash = data.archive_file.cognito_email_sender_stub.output_base64sha256

  environment {
    variables = {
      KMS_KEY_ARN        = aws_kms_key.cognito_email.arn
      SMTP2GO_SECRET_ARN = aws_secretsmanager_secret.smtp2go_api_key.arn
      MAIL_FROM          = local.mail_from
      MAIL_REPLY_TO      = local.mail_reply_to
    }
  }
}

resource "aws_lambda_permission" "cognito_email_sender" {
  statement_id  = "AllowCognitoInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.cognito_email_sender.function_name
  principal     = "cognito-idp.amazonaws.com"
  source_arn    = aws_cognito_user_pool.heimdall.arn
}

# Any error here is an invite / password-reset outage — page immediately.
resource "aws_cloudwatch_metric_alarm" "cognito_email_sender_errors" {
  alarm_name          = "heimdall-cognito-email-sender-errors"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  dimensions          = { FunctionName = aws_lambda_function.cognito_email_sender.function_name }
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

# deploy-email-sender.yml updates the bundle through the existing OIDC role.
resource "aws_iam_role_policy" "gha_deploy_email_sender" {
  name = "heimdall-gha-email-sender"
  role = aws_iam_role.gha_deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "lambda:UpdateFunctionCode",
        "lambda:GetFunction",
        # `aws lambda wait function-updated` polls this; without it the
        # workflow's upload succeeds but the wait step fails (seen 2026-08-25).
        "lambda:GetFunctionConfiguration",
      ]
      Resource = aws_lambda_function.cognito_email_sender.arn
    }]
  })
}
