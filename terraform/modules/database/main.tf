

variable "cloud_provider" {
  description = "Cloud provider: aws or azure"
  type        = string
  validation {
    condition     = contains(["aws", "azure"], var.cloud_provider)
    error_message = "Cloud provider must be either 'aws' or 'azure'."
  }
}

variable "db_name" {
  description = "Database name"
  type        = string
}

variable "db_username" {
  description = "Database admin username"
  type        = string
  default     = "admin"
}

variable "db_password_secret_id" {
  description = "The ID of the Key Vault secret containing the database password"
  type        = string
  default     = null
}

variable "db_instance_class" {
  description = "Database instance class/size"
  type        = string
  default     = "db.t3.micro"
}

variable "db_engine" {
  description = "Database engine"
  type        = string
  default     = "mysql"
}

variable "db_allocated_storage" {
  description = "Allocated storage in GB"
  type        = number
  default     = 20
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}

variable "backup_retention_period" {
  description = "Backup retention period in days"
  type        = number
  default     = 7
}

variable "multi_az" {
  description = "Enable Multi-AZ deployment"
  type        = bool
  default     = false
}

variable "resource_group_name" {
  description = "Azure resource group name"
  type        = string
  default     = ""
}

variable "location" {
  description = "Azure location"
  type        = string
  default     = "East US"
}

variable "auto_shutdown" {
  description = "Enable auto-shutdown for dev/test environments"
  type        = bool
  default     = false
}

resource "aws_kms_key" "database" {
  count                   = var.cloud_provider == "aws" ? 1 : 0
  description             = "KMS key for database"
  deletion_window_in_days = 10
  enable_key_rotation     = true
}


variable "db_subnet_group_name" {
  description = "Name of the DB subnet group to use for the AWS RDS instance"
  type        = string
  default     = null
}

resource "aws_db_instance" "database" {
  count                = var.cloud_provider == "aws" ? 1 : 0
  identifier           = "${var.db_name}-cost-opt"
  engine               = var.db_engine
  engine_version       = var.db_engine == "mysql" ? "8.0" : "13.7"
  instance_class       = var.db_instance_class
  allocated_storage    = var.db_allocated_storage
  db_name              = var.db_name
  username             = var.db_username
  password             = var.db_password
  parameter_group_name = aws_db_parameter_group.database[0].name
  db_subnet_group_name = var.db_subnet_group_name
  skip_final_snapshot  = true

  backup_retention_period = var.backup_retention_period
  multi_az                = var.multi_az

  storage_encrypted                   = true
  kms_key_id                          = aws_kms_key.database[0].arn
  iam_database_authentication_enabled = true
  deletion_protection                 = true

  performance_insights_enabled          = true
  performance_insights_kms_key_id       = aws_kms_key.database[0].arn
  performance_insights_retention_period = 7

  tags = merge(var.tags, {
    AutoShutdown = var.auto_shutdown ? "true" : "false"
    ManagedBy    = "cost-optimization-framework"
  })

  lifecycle {
    ignore_changes = [
      password,
    ]
  }
}

resource "aws_db_parameter_group" "database" {
  count  = var.cloud_provider == "aws" ? 1 : 0
  family = var.db_engine == "mysql" ? "mysql8.0" : "postgres13"

  parameter {
    name  = "max_connections"
    value = "100"
  }

  tags = merge(var.tags, {
    ManagedBy = "cost-optimization-framework"
  })
}





data "azurerm_key_vault_secret" "db_password" {
  count        = var.cloud_provider == "azure" ? 1 : 0
  name         = "db-password"
  key_vault_id = var.db_password_secret_id
}

# NOTE: Using a plain text password for the database is a security risk.
# It is recommended to use a secret management tool like Azure Key Vault to store and retrieve the password.
resource "azurerm_mssql_server" "database" {
  count                         = var.cloud_provider == "azure" ? 1 : 0
  name                          = "${var.db_name}-cost-opt-sql"
  resource_group_name           = var.resource_group_name
  location                      = var.location
  version                       = "12.0"
  administrator_login           = var.db_username
  administrator_login_password  = data.azurerm_key_vault_secret.db_password[0].value
  minimum_tls_version           = "1.2"
  public_network_access_enabled = false

  tags = merge(var.tags, {
    AutoShutdown = var.auto_shutdown ? "true" : "false"
    ManagedBy    = "cost-optimization-framework"
  })
}

resource "azurerm_storage_account" "audit_logs" {
  count                    = var.cloud_provider == "azure" ? 1 : 0
  name                     = "auditlogs${substr(replace(var.db_name, "-", ""), 0, 15)}"
  resource_group_name      = var.resource_group_name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"

  tags = merge(var.tags, {
    ManagedBy = "cost-optimization-framework"
  })
}

resource "azurerm_mssql_server_extended_auditing_policy" "database" {
  count                                   = var.cloud_provider == "azure" ? 1 : 0
  server_id                               = azurerm_mssql_server.database[0].id
  storage_endpoint                        = azurerm_storage_account.audit_logs[0].primary_blob_endpoint
  storage_account_access_key              = azurerm_storage_account.audit_logs[0].primary_access_key
  storage_account_access_key_is_secondary = false
  retention_in_days                       = 91
}

resource "azurerm_mssql_database" "database" {
  count     = var.cloud_provider == "azure" ? 1 : 0
  name      = var.db_name
  server_id = azurerm_mssql_server.database[0].id
  collation = "SQL_Latin1_General_CP1_CI_AS"
  sku_name  = var.db_instance_class

  tags = merge(var.tags, {
    ManagedBy = "cost-optimization-framework"
  })
}


variable "elastic_pool_sku" {
  description = "SKU for the Azure SQL Elastic Pool"
  type        = string
  default     = "BasicPool"
}

resource "azurerm_mssql_elasticpool" "database" {
  count               = var.cloud_provider == "azure" && var.auto_shutdown ? 1 : 0
  name                = "${var.db_name}-cost-opt-pool"
  resource_group_name = var.resource_group_name
  location            = var.location
  server_name         = azurerm_mssql_server.database[0].name
  sku {
    name     = var.elastic_pool_sku
    tier     = "Basic"
    capacity = 50
  }

  per_database_settings {
    min_capacity = 0
    max_capacity = 5
  }
}


output "aws_db_endpoint" {
  description = "AWS RDS endpoint"
  value       = var.cloud_provider == "aws" ? aws_db_instance.database[0].endpoint : null
}

output "aws_db_instance_id" {
  description = "AWS RDS instance ID"
  value       = var.cloud_provider == "aws" ? aws_db_instance.database[0].id : null
}

output "azure_sql_server_fqdn" {
  description = "Azure SQL Server FQDN"
  value       = var.cloud_provider == "azure" ? azurerm_mssql_server.database[0].fully_qualified_domain_name : null
}

output "azure_sql_database_id" {
  description = "Azure SQL Database ID"
  value       = var.cloud_provider == "azure" ? azurerm_mssql_database.database[0].id : null
}

output "auto_shutdown_enabled" {
  description = "Whether auto-shutdown is enabled"
  value       = var.auto_shutdown
}
