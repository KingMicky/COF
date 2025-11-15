# Reusable Compute Module for AWS EC2 and Azure VM Scale Sets

variable "cloud_provider" {
  description = "Cloud provider: aws or azure"
  type        = string
  validation {
    condition     = contains(["aws", "azure"], var.cloud_provider)
    error_message = "Cloud provider must be either 'aws' or 'azure'."
  }
}

variable "instance_count" {
  description = "Number of instances to create"
  type        = number
  default     = 1
}

variable "instance_type" {
  description = "Instance type/size"
  type        = string
  default     = "t3.micro"
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}

variable "auto_shutdown" {
  description = "Enable auto-shutdown scheduling"
  type        = bool
  default     = false
}

variable "shutdown_schedule" {
  description = "Cron schedule for auto-shutdown (UTC)"
  type        = string
  default     = "0 18 * * 1-5"  # 6 PM weekdays
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

variable "subnet_id" {
  description = "Azure subnet ID"
  type        = string
  default     = ""
}

variable "automation_account_name" {
  description = "Azure Automation account name"
  type        = string
  default     = ""
}

variable "lambda_function_name" {
  description = "AWS Lambda function name for auto-shutdown"
  type        = string
  default     = ""
}

# AWS Resources
resource "aws_instance" "compute" {
  count         = var.cloud_provider == "aws" ? var.instance_count : 0
  ami           = data.aws_ami.amazon_linux.id
  instance_type = var.instance_type

  tags = merge(var.tags, {
    Name         = "cost-opt-compute-${count.index}"
    AutoShutdown = var.auto_shutdown ? "true" : "false"
    ManagedBy    = "cost-optimization-framework"
  })

  lifecycle {
    ignore_changes = [
      tags["LastModified"],
    ]
  }
}

data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["amzn2-ami-hvm-*-x86_64-gp2"]
  }
}

# Auto-shutdown CloudWatch Event Rule for AWS
resource "aws_cloudwatch_event_rule" "auto_shutdown" {
  count               = var.cloud_provider == "aws" && var.auto_shutdown ? 1 : 0
  name                = "auto-shutdown-compute"
  description         = "Auto-shutdown compute instances"
  schedule_expression = "cron(${var.shutdown_schedule})"
}

data "aws_caller_identity" "current" {
  count = var.cloud_provider == "aws" ? 1 : 0
}

resource "aws_cloudwatch_event_target" "auto_shutdown" {
  count     = var.cloud_provider == "aws" && var.auto_shutdown ? 1 : 0
  rule      = aws_cloudwatch_event_rule.auto_shutdown[0].name
  target_id = "AutoShutdownCompute"
  arn       = "arn:aws:lambda:${var.location}:${data.aws_caller_identity.current[0].account_id}:function:${var.lambda_function_name}"
}

# Azure Resources
resource "azurerm_linux_virtual_machine_scale_set" "compute" {
  count               = var.cloud_provider == "azure" ? 1 : 0
  name                = "cost-opt-compute-vmss"
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = var.instance_type
  instances           = var.instance_count

  source_image_reference {
    publisher = "Canonical"
    offer     = "UbuntuServer"
    sku       = "18.04-LTS"
    version   = "latest"
  }

  os_disk {
    storage_account_type = "Standard_LRS"
    caching              = "ReadWrite"
  }

  admin_username = "azureuser"

  network_interface {
    name    = "cost-opt-nic"
    primary = true

    ip_configuration {
      name      = "internal"
      primary   = true
      subnet_id = var.subnet_id
    }
  }

  tags = merge(var.tags, {
    AutoShutdown = var.auto_shutdown ? "true" : "false"
    ManagedBy    = "cost-optimization-framework"
  })
}

# Azure Automation Account (required for schedules)
resource "azurerm_automation_account" "cost_opt" {
  count               = var.cloud_provider == "azure" && var.auto_shutdown ? 1 : 0
  name                = var.automation_account_name
  location            = var.location
  resource_group_name = var.resource_group_name
  sku_name            = "Basic"

  tags = {
    ManagedBy = "cost-optimization-framework"
  }
}

# Azure Runbook for auto-shutdown (placeholder - would contain actual PowerShell script)
resource "azurerm_automation_runbook" "auto_shutdown" {
  count                   = var.cloud_provider == "azure" && var.auto_shutdown ? 1 : 0
  name                    = "auto-shutdown-compute"
  location                = var.location
  resource_group_name     = var.resource_group_name
  automation_account_name = azurerm_automation_account.cost_opt[0].name
  log_verbose             = "true"
  log_progress            = "true"
  description             = "Auto-shutdown compute instances"
  runbook_type            = "PowerShell"

  publish_content_link {
    uri = "https://raw.githubusercontent.com/Azure/azure-quickstart-templates/master/101-automation-runbook-getvms/runbooks/Get-VMs.ps1"
  }
}

# Azure Automation Schedule for auto-shutdown
resource "azurerm_automation_schedule" "auto_shutdown" {
  count                   = var.cloud_provider == "azure" && var.auto_shutdown ? 1 : 0
  name                    = "auto-shutdown-compute"
  resource_group_name     = var.resource_group_name
  automation_account_name = azurerm_automation_account.cost_opt[0].name
  frequency               = "Week"
  interval                = 1
  timezone                = "UTC"
  start_time              = "2024-01-01T18:00:00Z"
  description             = "Auto-shutdown compute instances on weekdays"
}

# Outputs
output "aws_instance_ids" {
  description = "AWS instance IDs"
  value       = var.cloud_provider == "aws" ? aws_instance.compute[*].id : []
}

output "azure_vmss_id" {
  description = "Azure VM Scale Set ID"
  value       = var.cloud_provider == "azure" ? azurerm_linux_virtual_machine_scale_set.compute[0].id : null
}

output "auto_shutdown_enabled" {
  description = "Whether auto-shutdown is enabled"
  value       = var.auto_shutdown
}
