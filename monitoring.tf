# =============================================================================
# Monitoring & alerting — detective controls (HIPAA §164.308(a)(1)(ii)(D)).
# Email alerts on DB health + suspicious account activity, the latter via
# CloudTrail -> CloudWatch Logs metric filters.
#
# After applying, CONFIRM the SNS subscription from the email AWS sends you.
# =============================================================================

variable "alert_email" {
  description = "Email that receives alarm notifications (confirm the SNS subscription from your inbox after apply)."
  type        = string
  default     = "alerts@example.com"
}

resource "aws_sns_topic" "alerts" {
  name = "heimdall-alerts"
}

resource "aws_sns_topic_subscription" "alerts_email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# --- CloudTrail -> CloudWatch Logs (needed to alarm on account events) --------
resource "aws_cloudwatch_log_group" "cloudtrail" {
  name              = "/heimdall/cloudtrail"
  retention_in_days = 365
  kms_key_id        = aws_kms_key.heimdall.arn
}

resource "aws_iam_role" "cloudtrail_cw" {
  name = "heimdall-cloudtrail-cw"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "cloudtrail.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "cloudtrail_cw" {
  name = "write-cloudwatch-logs"
  role = aws_iam_role.cloudtrail_cw.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "${aws_cloudwatch_log_group.cloudtrail.arn}:*"
    }]
  })
}

# --- Metric filters + alarms on suspicious account activity ------------------
locals {
  security_filters = {
    root-account-usage     = "{ $.userIdentity.type = \"Root\" && $.userIdentity.invokedBy NOT EXISTS && $.eventType != \"AwsServiceEvent\" }"
    unauthorized-api-calls = "{ ($.errorCode = \"*UnauthorizedOperation\") || ($.errorCode = \"AccessDenied*\") }"
    console-signin-no-mfa  = "{ $.eventName = \"ConsoleLogin\" && $.additionalEventData.MFAUsed != \"Yes\" && $.userIdentity.type = \"IAMUser\" }"
    iam-policy-changes     = "{ ($.eventName = Put*Policy) || ($.eventName = Delete*Policy) || ($.eventName = Attach*Policy) || ($.eventName = Detach*Policy) }"
  }
}

resource "aws_cloudwatch_log_metric_filter" "security" {
  for_each       = local.security_filters
  name           = each.key
  log_group_name = aws_cloudwatch_log_group.cloudtrail.name
  pattern        = each.value

  metric_transformation {
    name      = each.key
    namespace = "Heimdall/Security"
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "security" {
  for_each            = local.security_filters
  alarm_name          = "heimdall-${each.key}"
  namespace           = "Heimdall/Security"
  metric_name         = each.key
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# --- RDS health alarms -------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  alarm_name          = "heimdall-rds-cpu-high"
  namespace           = "AWS/RDS"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 3
  threshold           = 85
  comparison_operator = "GreaterThanThreshold"
  dimensions          = { DBInstanceIdentifier = aws_db_instance.heimdall.identifier }
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"
}

resource "aws_cloudwatch_metric_alarm" "rds_storage" {
  alarm_name          = "heimdall-rds-storage-low"
  namespace           = "AWS/RDS"
  metric_name         = "FreeStorageSpace"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 1
  threshold           = 2147483648 # 2 GB, in bytes
  comparison_operator = "LessThanThreshold"
  dimensions          = { DBInstanceIdentifier = aws_db_instance.heimdall.identifier }
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"
}
