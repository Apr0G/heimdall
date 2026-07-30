# =============================================================================
# Stage 2 (revised) — Backend on Amazon ECS Express Mode.
#
# App Runner stopped accepting new customers (Apr 2026), so we use its AWS-
# recommended successor. Express Mode auto-provisions the load balancer, target
# groups, security groups, auto-scaling and HTTPS from one resource.
#
# The Terraform-native resource needs AWS provider v6.23+; to avoid a v5->v6
# major upgrade of the whole stack, we create the Express service via
# CloudFormation (AWS's native path for it) wrapped in an aws_cloudformation_stack.
#
# LEAN: reaches RDS over its existing (TLS) endpoint — no DB-network change here.
# Two-phase apply (see DEPLOY.md): first apply builds ECR + roles; push the image
# via the deploy-backend workflow; then set deploy_backend_service=true and apply.
# =============================================================================

variable "bedrock_model_id" {
  description = "Bedrock inference-profile id (starts with 'us.'), same as local .env.local."
  type        = string
}

variable "frontend_url" {
  description = "Public Vercel URL, for CORS. Set in Stage 4; localhost is a safe placeholder."
  type        = string
  default     = "http://localhost:3000"
}

variable "github_repo" {
  description = "owner/name of the repo allowed to push images via GitHub OIDC."
  type        = string
  default     = "Apr0G/heimdall"
}

variable "destructive_environment" {
  description = <<-EOT
    GitHub Environment name that the irreversible workflows (wipe-test-data,
    dispose-practice) run under, so they can carry required reviewers. Must be
    created by hand in the repo settings with at least one required reviewer —
    Terraform only widens the OIDC trust policy to accept its `sub` claim; it
    cannot create the environment or its protection rules.
  EOT
  type        = string
  default     = "production-destructive"
}

variable "deploy_backend_service" {
  description = "Phase gate: false = create ECR + roles only; true = also create the Express service (do this after the first image is pushed to ECR)."
  type        = bool
  default     = false
}

# --- Full DB connection string, stored as a secret, injected masked -----------
resource "aws_secretsmanager_secret" "database_url" {
  name        = "heimdall/database-url"
  description = "SQLAlchemy asyncpg connection string for the backend."
  kms_key_id  = aws_kms_key.heimdall.arn
}

resource "aws_secretsmanager_secret_version" "database_url" {
  secret_id = aws_secretsmanager_secret.database_url.id
  secret_string = format(
    "postgresql+asyncpg://%s:%s@%s:5432/%s?ssl=require",
    aws_db_instance.heimdall.username,
    var.db_password,
    aws_db_instance.heimdall.address,
    aws_db_instance.heimdall.db_name,
  )
}

# --- ECR repository for the backend image ------------------------------------
resource "aws_ecr_repository" "backend" {
  name                 = "heimdall-backend"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
}

# --- GitHub OIDC: keyless image pushes from GitHub Actions --------------------
resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

resource "aws_iam_role" "gha_deploy" {
  name = "heimdall-gha-deploy"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        # Two accepted subjects, no wider than before:
        #
        #   ref:refs/heads/main            — deploy, migrate, export, integrity.
        #   environment:<destructive env>  — wipe-test-data and dispose-practice.
        #
        # A GitHub `environment:` REPLACES the ref in the sub claim, which is why
        # the destructive workflows could not previously have required-reviewer
        # gates: adding one broke role assumption outright. Listing both subjects
        # removes that forced tradeoff. This does NOT loosen the branch
        # restriction — a workflow run from a non-main branch without the
        # environment still matches neither pattern.
        #
        # ORDERING: apply this BEFORE the workflows start requesting the
        # environment, and create the environment (with required reviewers) in the
        # repo settings, or the destructive workflows will fail to assume the role.
        StringLike = {
          "token.actions.githubusercontent.com:sub" = [
            "repo:${var.github_repo}:ref:refs/heads/main",
            "repo:${var.github_repo}:environment:${var.destructive_environment}",
          ]
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "gha_deploy" {
  name = "heimdall-gha-deploy-ecr"
  role = aws_iam_role.gha_deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:PutImage",
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
          # deploy-backend's `deploy-only` mode reports which image :latest
          # actually points at before restarting onto it — that mode ships an
          # image built by an earlier run, so the workflow's own SHA is not
          # necessarily what goes live.
          "ecr:DescribeImages",
        ]
        Resource = aws_ecr_repository.backend.arn
      },
      {
        # Redeploy the running service so it pulls the freshly pushed image.
        Effect   = "Allow"
        Action   = ["ecs:UpdateService", "ecs:DescribeServices"]
        Resource = "arn:aws:ecs:us-east-1:${data.aws_caller_identity.current.account_id}:service/default/heimdall-api"
      },
      {
        # Run one-off tasks (migrations, export, wipe, verify) inside the VPC.
        Effect = "Allow"
        Action = "ecs:RunTask"
        Resource = [
          "arn:aws:ecs:us-east-1:${data.aws_caller_identity.current.account_id}:task-definition/default-heimdall-api:*",
          "arn:aws:ecs:us-east-1:${data.aws_caller_identity.current.account_id}:task-definition/heimdall-migrate:*",
          "arn:aws:ecs:us-east-1:${data.aws_caller_identity.current.account_id}:task-definition/heimdall-dispose:*",
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "ecs:DescribeTasks",
          "ecs:DescribeTaskDefinition",
          "ec2:DescribeVpcs",
          "ec2:DescribeSubnets",
          "ec2:DescribeSecurityGroups",
        ]
        Resource = "*"
      },
      {
        # PassRole is needed so run-task can hand each task its roles.
        Effect = "Allow"
        Action = "iam:PassRole"
        Resource = [
          aws_iam_role.ecs_execution.arn,
          aws_iam_role.app.arn,
          aws_iam_role.migrate_exec.arn,
          aws_iam_role.dispose_exec.arn,
          aws_iam_role.dispose_task.arn,
        ]
      },
    ]
  })
}

# --- ECS execution role: pull image + write logs + read the injected secret ---
resource "aws_iam_role" "ecs_execution" {
  name = "heimdall-ecs-execution"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution_managed" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "ecs_execution_secrets" {
  name = "read-database-url-secret"
  role = aws_iam_role.ecs_execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["secretsmanager:GetSecretValue", "kms:Decrypt"]
      # When the least-privilege role is active the app may read ONLY its limited
      # URL — never the admin URL (which migrations use).
      Resource = [
        var.app_db_role_active ? aws_secretsmanager_secret.app_database_url.arn : aws_secretsmanager_secret.database_url.arn,
        aws_secretsmanager_secret.redis_auth.arn,
        aws_secretsmanager_secret.phi_hash_pepper.arn,
        aws_kms_key.heimdall.arn,
      ]
    }]
  })
}

# --- ECS infrastructure role: lets Express manage ALB/target groups/etc. ------
resource "aws_iam_role" "ecs_infra" {
  name = "heimdall-ecs-infrastructure"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_infra_managed" {
  role       = aws_iam_role.ecs_infra.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices"
}

# --- API log group -----------------------------------------------------------
# Declared in Terraform so retention is MANAGED. The ExpressGatewayService block
# below carries no logConfiguration, so AWS auto-created this group at the default
# "Never Expire" — and this is the group carrying request paths, case UUIDs and
# exception text, i.e. the most PHI-adjacent log stream we have.
# HIPAA-SERVICE-INVENTORY.md asserted "90-day retention" for it, unhedged, which
# was not true of anything in the repo.
resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/ecs/heimdall-api"
  retention_in_days = 90
  kms_key_id        = aws_kms_key.heimdall.arn
}

# --- The Express service (via CloudFormation) --------------------------------
# Created only once the image exists in ECR (deploy_backend_service=true).
resource "aws_cloudformation_stack" "express" {
  count = var.deploy_backend_service ? 1 : 0
  name  = "heimdall-api-express"

  template_body = jsonencode({
    Resources = {
      Api = {
        Type = "AWS::ECS::ExpressGatewayService"
        Properties = {
          ServiceName           = "heimdall-api"
          Cpu                   = "1024"
          Memory                = "2048"
          HealthCheckPath       = "/healthz"
          ExecutionRoleArn      = aws_iam_role.ecs_execution.arn
          InfrastructureRoleArn = aws_iam_role.ecs_infra.arn
          TaskRoleArn           = aws_iam_role.app.arn
          PrimaryContainer = {
            Image         = "${aws_ecr_repository.backend.repository_url}:latest"
            ContainerPort = 8080
            # Point at the Terraform-managed group above rather than letting AWS
            # auto-create one with never-expire retention.
            LogConfiguration = {
              LogDriver = "awslogs"
              Options = {
                "awslogs-group"         = aws_cloudwatch_log_group.api.name
                "awslogs-region"        = "us-east-1"
                "awslogs-stream-prefix" = "api"
              }
            }
            Environment = [
              { Name = "APP_ENV", Value = "production" },
              { Name = "AWS_REGION", Value = "us-east-1" },
              { Name = "S3_BUCKET_NAME", Value = aws_s3_bucket.documents.bucket },
              { Name = "KMS_KEY_ALIAS", Value = aws_kms_alias.heimdall.name },
              { Name = "COGNITO_USER_POOL_ID", Value = aws_cognito_user_pool.heimdall.id },
              { Name = "COGNITO_CLIENT_ID", Value = aws_cognito_user_pool_client.heimdall.id },
              { Name = "COGNITO_REGION", Value = "us-east-1" },
              { Name = "BEDROCK_MODEL_ID", Value = var.bedrock_model_id },
              { Name = "FRONTEND_URL", Value = var.frontend_url },
              { Name = "LEADS_TOPIC_ARN", Value = aws_sns_topic.leads.arn },
              # rediss:// — transit encryption is enforced on the cluster, and the
              # AUTH token arrives separately via Secrets (below) so it never
              # appears in the task definition's plaintext environment.
              { Name = "REDIS_URL", Value = "rediss://${aws_elasticache_replication_group.redis.primary_endpoint_address}:6379" },
              { Name = "LOG_LEVEL", Value = "INFO" },
              # verify-full DB TLS: verify the RDS server cert + hostname against the
              # global CA bundle baked into the image. Verified to connect via a
              # one-off in-VPC task (2026-07-11) before enabling. §164.312(e)(1).
              { Name = "DB_SSL_CA_BUNDLE", Value = "/app/rds-ca.pem" },
            ]
            Secrets = [
              # heimdall_app (limited) once cut over; heimdall_admin until then.
              { Name = "DATABASE_URL", ValueFrom = var.app_db_role_active ? aws_secretsmanager_secret.app_database_url.arn : aws_secretsmanager_secret.database_url.arn },
              { Name = "REDIS_AUTH_TOKEN", ValueFrom = aws_secretsmanager_secret.redis_auth.arn },
              # Pepper for the keyed identifier hashes (member_id_hash, corpus
              # claim_ref). Without it those degrade to omitted/failing rather
              # than writing an offline-brute-forceable digest.
              { Name = "PHI_HASH_PEPPER", ValueFrom = aws_secretsmanager_secret.phi_hash_pepper.arn },
            ]
          }
        }
      }
    }
    Outputs = {
      Endpoint = { Value = { "Fn::GetAtt" = ["Api", "Endpoint"] } }
    }
  })
}

output "ecr_repository_url" {
  description = "Push the backend image here (the deploy-backend workflow does this)."
  value       = aws_ecr_repository.backend.repository_url
}

output "backend_endpoint" {
  description = "Public HTTPS endpoint of the backend once deploy_backend_service=true."
  value = var.deploy_backend_service ? try(
    aws_cloudformation_stack.express[0].outputs["Endpoint"],
    "(endpoint pending — check the ECS console)",
  ) : "(set deploy_backend_service=true and apply after pushing the image)"
}
