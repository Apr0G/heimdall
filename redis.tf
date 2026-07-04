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

resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "heimdall-redis"
  engine               = "redis"
  engine_version       = "7.1"
  node_type            = "cache.t4g.micro" # smallest; ~$12/mo
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.redis.name
  security_group_ids   = [aws_security_group.redis.id]
}

output "redis_endpoint" {
  description = "Set as REDIS_URL on the backend (already wired in ecs-express.tf)."
  value       = "redis://${aws_elasticache_cluster.redis.cache_nodes[0].address}:6379"
}
