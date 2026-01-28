

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  required_version = ">= 1.0"
}

provider "aws" {
  region = var.aws_region

  endpoints {
    ec2        = var.aws_endpoint_url
    s3         = var.aws_endpoint_url
    rds        = var.aws_endpoint_url
    cloudwatch = var.aws_endpoint_url
    iam        = var.aws_endpoint_url
    sns        = var.aws_endpoint_url
    sts        = var.aws_endpoint_url
    kms        = var.aws_endpoint_url
  }

  default_tags {
    tags = {
      Project     = "cost-optimization-framework"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}


variable "aws_endpoint_url" {
  description = "AWS Endpoint URL for LocalStack"
  type        = string
  default     = null
}





variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "dev"
}

variable "owner" {
  description = "Resource owner"
  type        = string
  default     = "cost-optimization-team"
}

variable "cost_center" {
  description = "Cost center"
  type        = string
  default     = "engineering"
}

variable "vpc_id" {
  description = "VPC ID for resources"
  type        = string
}

variable "subnet_ids" {
  description = "Subnet IDs for resources"
  type        = list(string)
}


# NOTE: This policy can only be applied to the master account of an AWS Organization.
resource "aws_organizations_policy" "tagging_policy" {
  name        = "cost-optimization-tagging-policy"
  description = "Enforce cost optimization tagging"

  content = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Deny"
        Action = [
          "ec2:RunInstances",
          "rds:CreateDBInstance",
          "s3:CreateBucket"
        ]
        Resource = "*"
        Condition = {
          StringNotEquals = {
            "aws:RequestTag/Owner" : var.owner
            "aws:RequestTag/Environment" : var.environment
            "aws:RequestTag/CostCenter" : var.cost_center
          }
        }
      }
    ]
  })
}


module "compute" {
  source = "../modules/compute"

  cloud_provider       = "aws"
  instance_count       = 2
  instance_type        = "t3.micro"
  auto_shutdown        = true
  shutdown_schedule    = "0 18 * * 1-5"
  location             = var.aws_region
  lambda_function_name = "cost-opt-auto-shutdown"
  vpc_id               = var.vpc_id
  subnet_ids           = var.subnet_ids

  tags = {
    Owner       = var.owner
    Environment = var.environment
    CostCenter  = var.cost_center
  }
}


module "storage" {
  source = "../modules/storage"

  cloud_provider = "aws"
  bucket_name    = "cost-opt-storage-${var.environment}-${random_string.bucket_suffix.result}"

  tags = {
    Owner       = var.owner
    Environment = var.environment
    CostCenter  = var.cost_center
  }
}

resource "random_string" "bucket_suffix" {
  length  = 8
  lower   = true
  upper   = false
  numeric = true
  special = false
}


module "database" {
  source = "../modules/database"

  cloud_provider          = "aws"
  db_name                 = "costoptdb"
  db_username             = "admin"
  db_password             = var.db_password
  db_instance_class       = "db.t3.micro"
  db_engine               = "mysql"
  db_allocated_storage    = 20
  backup_retention_period = 7
  auto_shutdown           = var.environment != "prod"
  db_subnet_group_name    = aws_db_subnet_group.database.name
  vpc_id                  = var.vpc_id

  tags = {
    Owner       = var.owner
    Environment = var.environment
    CostCenter  = var.cost_center
  }
}

variable "db_password" {
  description = "Database password"
  type        = string
  sensitive   = true
}








resource "aws_db_subnet_group" "database" {
  name       = "cost-opt-db-subnet-group"
  subnet_ids = var.subnet_ids

  tags = {
    Name = "Cost Optimization DB Subnet Group"
  }
}



resource "aws_budgets_budget" "monthly_budget" {
  name         = "cost-optimization-monthly-budget"
  budget_type  = "COST"
  limit_amount = "1000"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "TagKeyValue"
    values = ["Environment$${var.environment}"]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }
}

variable "alert_email" {
  description = "Email for budget alerts"
  type        = string
}


resource "aws_cloudwatch_metric_alarm" "high_cpu" {
  for_each            = toset(module.compute.aws_instance_ids)
  alarm_name          = "cost-opt-high-cpu-${each.key}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = "300"
  statistic           = "Average"
  threshold           = "80"
  alarm_description   = "High CPU utilization - consider right-sizing"
  alarm_actions       = [aws_sns_topic.cost_alerts.arn]

  dimensions = {
    InstanceId = each.key
  }
}

resource "aws_kms_key" "sns" {
  description             = "KMS key for SNS alerts"
  deletion_window_in_days = 10
  enable_key_rotation     = true
}

resource "aws_sns_topic" "cost_alerts" {
  name              = "cost-optimization-alerts"
  kms_master_key_id = aws_kms_key.sns.arn
}


output "compute_instance_ids" {
  description = "EC2 instance IDs"
  value       = module.compute.aws_instance_ids
}

output "storage_bucket_name" {
  description = "S3 bucket name"
  value       = module.storage.aws_bucket_name
}

output "database_endpoint" {
  description = "RDS endpoint"
  value       = module.database.aws_db_endpoint
}

output "budget_id" {
  description = "Budget ID"
  value       = aws_budgets_budget.monthly_budget.id
}
