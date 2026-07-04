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
        StringEquals = { "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com" }
        StringLike   = { "token.actions.githubusercontent.com:sub" = "repo:${var.github_repo}:*" }
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
        # Run one-off DB migration tasks (alembic upgrade head) inside the VPC.
        Effect   = "Allow"
        Action   = "ecs:RunTask"
        Resource = "arn:aws:ecs:us-east-1:${data.aws_caller_identity.current.account_id}:task-definition/default-heimdall-api:*"
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
        # PassRole is needed so run-task can hand the migration task its roles.
        Effect   = "Allow"
        Action   = "iam:PassRole"
        Resource = [aws_iam_role.ecs_execution.arn, aws_iam_role.app.arn]
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
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue", "kms:Decrypt"]
      Resource = [aws_secretsmanager_secret.database_url.arn, aws_kms_key.heimdall.arn]
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
              { Name = "LOG_LEVEL", Value = "INFO" },
            ]
            Secrets = [
              { Name = "DATABASE_URL", ValueFrom = aws_secretsmanager_secret.database_url.arn },
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
