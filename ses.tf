# =============================================================================
# Transactional email identity: lets Cognito send invites and password-reset
# codes from no-reply@heimdallclaims.com instead of AWS's generic
# no-reply@verificationemail.com (50/day cap, spam-prone, looks like phishing).
#
# DNS lives at Wix, not Route53, so the DKIM CNAMEs below are added by hand —
# see `terraform output ses_dkim_records`. No mailbox exists for no-reply@: SES
# signs and sends directly; nothing touches Google Workspace. Replies go to info@.
#
# Two-step rollout (see DEPLOY.md, "Email sender"): the identity is created
# first; Cognito is switched to it ONLY once (a) the domain shows verified and
# (b) the SES account is out of the sandbox — in the sandbox SES refuses mail to
# unverified recipients, which would silently break invites and resets.
# =============================================================================

variable "cognito_email_from_ses" {
  description = "Send Cognito email via SES as no-reply@heimdallclaims.com. Flip to true only after the SES domain is verified AND the account has production access; otherwise invites/resets fail for unverified recipients."
  type        = bool
  default     = false
}

locals {
  mail_domain   = "heimdallclaims.com"
  mail_from     = "Heimdall <no-reply@heimdallclaims.com>"
  mail_reply_to = "info@heimdallclaims.com"
}

resource "aws_ses_domain_identity" "heimdall" {
  domain = local.mail_domain
}

resource "aws_ses_domain_dkim" "heimdall" {
  domain = aws_ses_domain_identity.heimdall.domain
}

# Cognito sends *as* this identity, so the identity must authorise the Cognito
# service principal — scoped to this account's pool, not any pool anywhere.
resource "aws_ses_identity_policy" "cognito" {
  identity = aws_ses_domain_identity.heimdall.arn
  name     = "heimdall-cognito-send"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "CognitoSend"
      Effect    = "Allow"
      Principal = { Service = "cognito-idp.amazonaws.com" }
      Action    = ["ses:SendEmail", "ses:SendRawEmail"]
      Resource  = aws_ses_domain_identity.heimdall.arn
      Condition = {
        StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }
        ArnLike      = { "aws:SourceArn" = aws_cognito_user_pool.heimdall.arn }
      }
    }]
  })
}

output "ses_dkim_records" {
  description = "Add these three CNAMEs at the DNS host (Wix). Host = <token>._domainkey, value = <token>.dkim.amazonses.com."
  value = [
    for t in aws_ses_domain_dkim.heimdall.dkim_tokens :
    { host = "${t}._domainkey", type = "CNAME", value = "${t}.dkim.amazonses.com" }
  ]
}

# Bounces and complaints land in the existing alerts topic (email to the
# founder). Volume is tiny, so a human reading each one IS the suppression
# process: a bounced invite means a typo'd address to fix in Cognito.
resource "aws_ses_identity_notification_topic" "bounce" {
  identity                 = aws_ses_domain_identity.heimdall.domain
  notification_type        = "Bounce"
  topic_arn                = aws_sns_topic.alerts.arn
  include_original_headers = false
}

resource "aws_ses_identity_notification_topic" "complaint" {
  identity                 = aws_ses_domain_identity.heimdall.domain
  notification_type        = "Complaint"
  topic_arn                = aws_sns_topic.alerts.arn
  include_original_headers = false
}
