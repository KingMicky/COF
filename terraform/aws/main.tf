# AWS Cost Optimization Framework Infrastructure

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

  default_tags {
    tags = {
      Project     = "cost-optimization-framework"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# Variables
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

# Tagging Policy Enforcement
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

# Compute Resources (EC2)
module "compute" {
  source = "../modules/compute"

  cloud_provider   = "aws"
  instance_count   = 2
  instance_type    = "t3.micro"
  auto_shutdown    = true
  shutdown_schedule = "0 18 * * 1-5"  # 6 PM weekdays

  tags = {
    Owner       = var.owner
    Environment = var.environment
    CostCenter  = var.cost_center
  }
}

# Storage Resources (S3)
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

# Database Resources (RDS)
module "database" {
  source = "../modules/database"

  cloud_provider         = "aws"
  db_name                = "costoptdb"
  db_username            = "admin"
  db_password            = var.db_password
  db_instance_class      = "db.t3.micro"
  db_engine              = "mysql"
  db_allocated_storage   = 20
  backup_retention_period = 7
  auto_shutdown          = var.environment != "prod"

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

# Cost Allocation Tags (Note: These are configured in AWS Cost Allocation Tags console)
# The following tags are activated for cost allocation:
# - Owner
# - Environment
# - CostCenter

# Budgets and Alerts
resource "aws_budgets_budget" "monthly_budget" {
  name         = "cost-optimization-monthly-budget"
  budget_type  = "COST"
  limit_amount = "1000"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "TagKeyValue"
    values = ["Environment$prod"]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }
}

variable "alert_email" {
  description = "Email for budget alerts"
  type        = string
}

# CloudWatch Alarms for Cost Optimization
resource "aws_cloudwatch_metric_alarm" "high_cpu" {
  alarm_name          = "cost-opt-high-cpu"
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
    InstanceId = module.compute.aws_instance_ids[0]
  }
}

resource "aws_sns_topic" "cost_alerts" {
  name = "cost-optimization-alerts"
}

# Outputs
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
