

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
  default     = "0 18 * * 1-5"
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


variable "admin_password" {
  description = "Azure VM admin password"
  type        = string
  sensitive   = true
  default     = null
}

variable "vpc_id" {
  description = "VPC ID for AWS resources"
  type        = string
  default     = null
}

variable "subnet_ids" {
  description = "Subnet IDs for AWS resources"
  type        = list(string)
  default     = null
}

resource "aws_instance" "compute" {
  count         = var.cloud_provider == "aws" ? var.instance_count : 0
  ami           = data.aws_ami.amazon_linux[0].id
  instance_type = var.instance_type
  subnet_id     = var.subnet_ids[count.index % length(var.subnet_ids)]

  tags = merge(var.tags, {
    Name         = "cost-opt-compute-${count.index}"
    AutoShutdown = var.auto_shutdown ? "true" : "false"
    ManagedBy    = "cost-optimization-framework"
  })

  metadata_options {
    http_tokens   = "required"
    http_endpoint = "enabled"
  }

  root_block_device {
    encrypted = true
  }

  lifecycle {
    ignore_changes = [
      tags["LastModified"],
    ]
  }
}

data "aws_ami" "amazon_linux" {
  count       = var.cloud_provider == "aws" ? 1 : 0
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["amzn2-ami-hvm-2.0.*-x86_64-gp2"]
  }
}


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

  admin_username                  = "azureuser"
  admin_password                  = var.admin_password
  disable_password_authentication = false

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
  content                 = var.runbook_content
}

variable "runbook_content" {
  description = "Content of the Azure Automation runbook"
  type        = string
  default     = <<-EOF
    param(
      [string]$ResourceGroupName,
      [string]$VmssName
    )

    Stop-AzVmss -ResourceGroupName $ResourceGroupName -VMScaleSetName $VmssName -Force
    EOF
}


resource "azurerm_automation_schedule" "auto_shutdown" {
  count                   = var.cloud_provider == "azure" && var.auto_shutdown ? 1 : 0
  name                    = "auto-shutdown-compute"
  resource_group_name     = var.resource_group_name
  automation_account_name = azurerm_automation_account.cost_opt[0].name
  frequency               = "Week"
  interval                = 1
  timezone                = "UTC"
  start_time              = formatdate("YYYY-MM-DD'T'hh:mm:ssZ", timestamp())
  description             = "Auto-shutdown compute instances on weekdays"
}


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
