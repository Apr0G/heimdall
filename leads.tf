# =============================================================================
# "Get started" lead intake — the public form posts to /api/leads, which
# publishes to this SNS topic, emailing the founder. No PHI (prospect contact
# info only). Confirm the email subscription after apply.
# =============================================================================

resource "aws_sns_topic" "leads" {
  name = "heimdall-leads"
}

resource "aws_sns_topic_subscription" "leads_email" {
  topic_arn = aws_sns_topic.leads.arn
  protocol  = "email"
  endpoint  = var.alert_email # alerts@example.com (shared with alerts)
}
