# =============================================================================
# WAF on the backend load balancer (the ECS Express ALB). AWS managed rule sets
# (common attacks, known-bad inputs, bad-IP reputation) + a per-IP rate limit.
#
# ENFORCING: the managed rule groups use `override_action { none {} }` and the
# rate rule `action { block {} }`, and the ACL is associated with the ALB. A
# managed-rule false positive therefore hard-blocks a real user — check the
# WAF sampled requests before tightening further. (Flipped from COUNT after a
# day of clean samples; a dormant CLOUDFRONT-scoped ACL that used to live in
# security.tf was destroyed 2026-08-20.)
# =============================================================================

variable "alb_arn" {
  # ECS Express creates the ALB inside its CloudFormation stack and exports
  # only the endpoint, so the ARN (random suffix included) has to be supplied.
  # If Express ever replaces the ALB this must be updated or the new ALB is
  # unprotected — `aws elbv2 describe-load-balancers` is the check.
  description = "ARN of the ECS Express application load balancer to protect."
  type        = string
  default     = "arn:aws:elasticloadbalancing:us-east-1:000000000000:loadbalancer/app/ecs-express-gateway-alb-00000000/0000000000000000"
}

resource "aws_wafv2_web_acl" "alb" {
  name        = "heimdall-alb-waf"
  description = "Heimdall backend WAF - enforcing block mode"
  scope       = "REGIONAL"

  default_action {
    allow {}
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "heimdall-alb-waf"
    sampled_requests_enabled   = true
  }

  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 1
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesCommonRuleSet"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "common"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "AWSManagedRulesKnownBadInputsRuleSet"
    priority = 2
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "bad-inputs"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "AWSManagedRulesAmazonIpReputationList"
    priority = 3
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesAmazonIpReputationList"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "ip-reputation"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "RateLimitPerIp"
    priority = 4
    action {
      block {}
    }
    statement {
      rate_based_statement {
        limit              = 2000
        aggregate_key_type = "IP"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "rate-limit"
      sampled_requests_enabled   = true
    }
  }
}

resource "aws_wafv2_web_acl_association" "alb" {
  resource_arn = var.alb_arn
  web_acl_arn  = aws_wafv2_web_acl.alb.arn
}
