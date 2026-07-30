# =============================================================================
# ElastiCache Redis — a shared rate-limit store. In-memory limits are per-
# container, so when ECS runs >1 task the effective limit multiplies (weakening
# login brute-force + AI-cost caps). Redis makes the limit global and survives
# scaling. Wired as REDIS_URL on the backend (ecs-express.tf); the app already
# reads it (core/rate_limit.py). Reachable only from the backend tasks.
#
# Applying REDIS_URL updates the ECS service (a rolling redeploy) — run this
# apply alone (no concurrent GitHub deploy), same as the other service changes.
# =============================================================================

resource "aws_elasticache_subnet_group" "redis" {
  name       = "heimdall-redis"
  subnet_ids = data.aws_subnets.default.ids
}

resource "aws_security_group" "redis" {
  name        = "heimdall-redis"
  description = "Redis access for Heimdall - backend ECS tasks only"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description     = "Redis from the Heimdall backend tasks"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [data.aws_security_group.ecs_tasks.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# AUTH token. Not PHI-bearing (keys are `user:<cognito sub>` and `ip:<addr>`), but
# without a token ANYTHING that reaches port 6379 can FLUSHALL — which resets every
# login-throttle counter and silently reopens the brute-force window that
# rate_limit.py's fail-closed login peek exists to hold shut.
resource "random_password" "redis_auth" {
  length = 64
  # ElastiCache rejects several punctuation characters in an AUTH token; keep it
  # alphanumeric rather than discover which at apply time.
  special = false
}

resource "aws_secretsmanager_secret" "redis_auth" {
  name       = "heimdall/redis-auth-token"
  kms_key_id = aws_kms_key.heimdall.arn
}

resource "aws_secretsmanager_secret_version" "redis_auth" {
  secret_id     = aws_secretsmanager_secret.redis_auth.id
  secret_string = random_password.redis_auth.result
}

# A replication group rather than aws_elasticache_cluster: the single-node cluster
# resource supports NEITHER transit nor at-rest encryption, so there was no way to
# encrypt it in place.
#
# NOTE: this REPLACES the existing cluster. Enabling encryption is not an in-place
# change, and the rate-limit store is throwaway state — losing it resets counters,
# it does not lose data. Apply during a quiet window.
resource "aws_elasticache_replication_group" "redis" {
  # Deliberately NOT "heimdall-redis": the old standalone cluster still holds that
  # identifier, and ElastiCache cannot have both at once. Sharing the name would
  # force destroy-before-create, which means a window with no rate-limit store at
  # all — and `login_allowed` fails CLOSED, so that window blocks every new login.
  # A distinct name lets the new group exist alongside the old one, so the cutover
  # can be done without denying logins (see the two-step note in DEPLOY.md).
  replication_group_id = "heimdall-redis-tls"
  description          = "Heimdall rate-limit store (encrypted in transit + at rest)"
  engine               = "redis"
  engine_version       = "7.1"
  node_type            = "cache.t4g.micro" # smallest; ~$12/mo
  num_cache_clusters   = 1
  parameter_group_name = "default.redis7"
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.redis.name
  security_group_ids   = [aws_security_group.redis.id]

  # §164.312(e)(1) transmission security. Anything on the VPC path could
  # previously read this traffic in cleartext.
  transit_encryption_enabled = true
  at_rest_encryption_enabled = true
  kms_key_id                 = aws_kms_key.heimdall.arn
  auth_token                 = random_password.redis_auth.result
  auth_token_update_strategy = "ROTATE"

  apply_immediately = true
}

output "redis_endpoint" {
  description = <<-EOT
    Wired as REDIS_URL in ecs-express.tf. Note the `rediss://` scheme — TLS is now
    mandatory on this cluster, so a `redis://` URL will simply fail to connect.
  EOT
  value       = "rediss://${aws_elasticache_replication_group.redis.primary_endpoint_address}:6379"
}
