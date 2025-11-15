# Azure Cost Optimization Framework Infrastructure

terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }

  required_version = ">= 1.0"
}

provider "azurerm" {
  features {}
}

# Variables
variable "subscription_id" {
  description = "Azure subscription ID"
  type        = string
}

variable "location" {
  description = "Azure location"
  type        = string
  default     = "East US"
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

variable "resource_group_name" {
  description = "Resource group name"
  type        = string
  default     = "cost-opt-rg"
}

variable "vnet_name" {
  description = "Virtual network name"
  type        = string
  default     = "cost-opt-vnet"
}

variable "subnet_name" {
  description = "Subnet name"
  type        = string
  default     = "cost-opt-subnet"
}

variable "automation_account_name" {
  description = "Azure Automation account name"
  type        = string
  default     = "cost-opt-automation"
}

# Resource Group
resource "azurerm_resource_group" "cost_opt" {
  name     = var.resource_group_name
  location = var.location

  tags = {
    Environment = var.environment
    Owner       = var.owner
    CostCenter  = var.cost_center
    ManagedBy   = "cost-optimization-framework"
  }
}

# Virtual Network
resource "azurerm_virtual_network" "cost_opt" {
  name                = var.vnet_name
  location            = azurerm_resource_group.cost_opt.location
  resource_group_name = azurerm_resource_group.cost_opt.name
  address_space       = ["10.0.0.0/16"]

  tags = {
    Environment = var.environment
    Owner       = var.owner
    CostCenter  = var.cost_center
    ManagedBy   = "cost-optimization-framework"
  }
}

# Subnet
resource "azurerm_subnet" "cost_opt" {
  name                 = var.subnet_name
  resource_group_name  = azurerm_resource_group.cost_opt.name
  virtual_network_name = azurerm_virtual_network.cost_opt.name
  address_prefixes     = ["10.0.1.0/24"]
}

# Tagging Policy (Azure Policy)
resource "azurerm_policy_definition" "tagging_policy" {
  name         = "cost-optimization-tagging-policy"
  policy_type  = "Custom"
  mode         = "All"
  display_name = "Cost Optimization Tagging Policy"

  policy_rule = jsonencode({
    if = {
      allOf = [
        {
          field  = "type"
          equals = "Microsoft.Compute/virtualMachines"
        },
        {
          anyOf = [
            {
              field     = "tags.Owner"
              exists    = false
            },
            {
              field     = "tags.Environment"
              exists    = false
            },
            {
              field     = "tags.CostCenter"
              exists    = false
            }
          ]
        }
      ]
    }
    then = {
      effect = "deny"
    }
  })
}

resource "azurerm_subscription_policy_assignment" "tagging_policy" {
  name                 = "cost-opt-tagging-assignment"
  policy_definition_id = azurerm_policy_definition.tagging_policy.id
  subscription_id      = var.subscription_id
}

# Compute Resources (VM Scale Sets)
module "compute" {
  source = "../modules/compute"

  cloud_provider     = "azure"
  instance_count     = 2
  instance_type      = "Standard_B1s"
  auto_shutdown      = true
  shutdown_schedule  = "0 18 * * 1-5"  # 6 PM weekdays

  resource_group_name     = azurerm_resource_group.cost_opt.name
  location               = azurerm_resource_group.cost_opt.location
  subnet_id              = azurerm_subnet.cost_opt.id
  automation_account_name = var.automation_account_name

  tags = {
    Owner       = var.owner
    Environment = var.environment
    CostCenter  = var.cost_center
  }
}

# Storage Resources (Blob Storage)
module "storage" {
  source = "../modules/storage"

  cloud_provider     = "azure"
  bucket_name        = "costoptstorage${random_string.bucket_suffix.result}"
  resource_group_name = azurerm_resource_group.cost_opt.name
  location           = azurerm_resource_group.cost_opt.location

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

# Database Resources (Azure SQL)
module "database" {
  source = "../modules/database"

  cloud_provider     = "azure"
  db_name            = "costoptdb"
  db_username        = "adminuser"
  db_password        = var.db_password
  db_instance_class  = "Basic"
  db_engine          = "sqlserver"
  auto_shutdown      = var.environment != "prod"

  resource_group_name = azurerm_resource_group.cost_opt.name
  location           = azurerm_resource_group.cost_opt.location

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

# Cost Management Budget
resource "azurerm_consumption_budget_resource_group" "monthly_budget" {
  name              = "cost-opt-monthly-budget"
  resource_group_id = azurerm_resource_group.cost_opt.id
  amount            = 1000
  time_grain        = "Monthly"

  time_period {
    start_date = "2024-01-01T00:00:00Z"
    end_date   = "2024-12-31T23:59:59Z"
  }

  notification {
    enabled        = true
    threshold      = 80.0
    operator       = "EqualTo"
    contact_emails = [var.alert_email]
  }
}

variable "alert_email" {
  description = "Email for budget alerts"
  type        = string
}

# Azure Monitor Alerts for Cost Optimization
resource "azurerm_monitor_metric_alert" "high_cpu" {
  name                = "cost-opt-high-cpu"
  resource_group_name = azurerm_resource_group.cost_opt.name
  scopes              = [module.compute.azure_vmss_id]
  description         = "High CPU utilization - consider right-sizing"

  criteria {
    metric_namespace = "Microsoft.Compute/virtualMachineScaleSets"
    metric_name      = "Percentage CPU"
    aggregation      = "Average"
    operator         = "GreaterThan"
    threshold        = 80
  }

  action {
    action_group_id = azurerm_monitor_action_group.cost_alerts.id
  }
}

resource "azurerm_monitor_action_group" "cost_alerts" {
  name                = "cost-opt-action-group"
  resource_group_name = azurerm_resource_group.cost_opt.name
  short_name          = "costalerts"

  email_receiver {
    name          = "cost-alerts"
    email_address = var.alert_email
  }
}

# Outputs
output "resource_group_name" {
  description = "Resource group name"
  value       = azurerm_resource_group.cost_opt.name
}

output "vmss_id" {
  description = "VM Scale Set ID"
  value       = module.compute.azure_vmss_id
}

output "storage_account_name" {
  description = "Storage account name"
  value       = module.storage.azure_storage_account_name
}

output "sql_server_fqdn" {
  description = "SQL Server FQDN"
  value       = module.database.azure_sql_server_fqdn
}

output "budget_id" {
  description = "Budget ID"
  value       = azurerm_consumption_budget_resource_group.monthly_budget.id
}
