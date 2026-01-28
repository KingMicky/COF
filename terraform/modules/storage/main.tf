

variable "cloud_provider" {
  description = "Cloud provider: aws or azure"
  type        = string
  validation {
    condition     = contains(["aws", "azure"], var.cloud_provider)
    error_message = "Cloud provider must be either 'aws' or 'azure'."
  }
}

variable "bucket_name" {
  description = "Name of the storage bucket/container"
  type        = string
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
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

variable "versioning" {
  description = "Enable versioning for storage"
  type        = bool
  default     = true
}

variable "lifecycle_rules" {
  description = "Lifecycle rules for cost optimization"
  type = list(object({
    id      = string
    enabled = bool
    prefix  = optional(string)
    tags    = optional(map(string))
    transition = optional(list(object({
      days          = number
      storage_class = string
    })))
    expiration = optional(object({
      days = number
    }))
    noncurrent_version_expiration = optional(object({
      noncurrent_days = number
    }))
  }))
  default = [
    {
      id      = "cost-opt-transition"
      enabled = true
      transition = [
        {
          days          = 30
          storage_class = "STANDARD_IA"
        },
        {
          days          = 90
          storage_class = "GLACIER"
        }
      ]
      expiration = {
        days = 365
      }
      noncurrent_version_expiration = {
        noncurrent_days = 30
      }
    }
  ]
}


resource "aws_s3_bucket" "storage" {
  count  = var.cloud_provider == "aws" ? 1 : 0
  bucket = var.bucket_name

  tags = merge(var.tags, {
    ManagedBy = "cost-optimization-framework"
  })
}

resource "aws_s3_bucket_versioning" "storage" {
  count  = var.cloud_provider == "aws" ? 1 : 0
  bucket = aws_s3_bucket.storage[0].id

  versioning_configuration {
    status = var.versioning ? "Enabled" : "Suspended"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "storage" {
  count  = var.cloud_provider == "aws" ? 1 : 0
  bucket = aws_s3_bucket.storage[0].id

  dynamic "rule" {
    for_each = var.lifecycle_rules
    content {
      id     = rule.value.id
      status = rule.value.enabled ? "Enabled" : "Disabled"

      dynamic "filter" {
        for_each = rule.value.prefix != null ? [rule.value.prefix] : []
        content {
          prefix = filter.value
        }
      }

      dynamic "transition" {
        for_each = rule.value.transition != null ? rule.value.transition : []
        content {
          days          = transition.value.days
          storage_class = transition.value.storage_class
        }
      }

      dynamic "expiration" {
        for_each = rule.value.expiration != null ? [rule.value.expiration] : []
        content {
          days = expiration.value.days
        }
      }

      dynamic "noncurrent_version_expiration" {
        for_each = rule.value.noncurrent_version_expiration != null ? [rule.value.noncurrent_version_expiration] : []
        content {
          noncurrent_days = noncurrent_version_expiration.value.noncurrent_days
        }
      }
    }
  }
}

resource "aws_kms_key" "storage" {
  count                   = var.cloud_provider == "aws" ? 1 : 0
  description             = "KMS key for storage bucket"
  deletion_window_in_days = 10
  enable_key_rotation     = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "storage" {
  count  = var.cloud_provider == "aws" ? 1 : 0
  bucket = aws_s3_bucket.storage[0].id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.storage[0].arn
      sse_algorithm     = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "storage" {
  count  = var.cloud_provider == "aws" ? 1 : 0
  bucket = aws_s3_bucket.storage[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket" "logging" {
  count  = var.cloud_provider == "aws" ? 1 : 0
  bucket = "${var.bucket_name}-logs"

  tags = merge(var.tags, {
    ManagedBy = "cost-optimization-framework"
  })
}

resource "aws_s3_bucket_ownership_controls" "logging" {
  count  = var.cloud_provider == "aws" ? 1 : 0
  bucket = aws_s3_bucket.logging[0].id
  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

resource "aws_s3_bucket_acl" "logging" {
  count      = var.cloud_provider == "aws" ? 1 : 0
  bucket     = aws_s3_bucket.logging[0].id
  acl        = "log-delivery-write"
  depends_on = [aws_s3_bucket_ownership_controls.logging]
}

resource "aws_s3_bucket_versioning" "logging" {
  count  = var.cloud_provider == "aws" ? 1 : 0
  bucket = aws_s3_bucket.logging[0].id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "logging" {
  count  = var.cloud_provider == "aws" ? 1 : 0
  bucket = aws_s3_bucket.logging[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "logging" {
  count  = var.cloud_provider == "aws" ? 1 : 0
  bucket = aws_s3_bucket.logging[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_logging" "storage" {
  count  = var.cloud_provider == "aws" ? 1 : 0
  bucket = aws_s3_bucket.storage[0].id

  target_bucket = aws_s3_bucket.logging[0].id
  target_prefix = "log/"
}

resource "azurerm_storage_account" "storage" {
  count                    = var.cloud_provider == "azure" ? 1 : 0
  name                     = var.bucket_name
  resource_group_name      = var.resource_group_name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"

  tags = merge(var.tags, {
    ManagedBy = "cost-optimization-framework"
  })
}

variable "container_name" {
  description = "Name of the Azure storage container"
  type        = string
  default     = "cost-opt-container"
}

resource "azurerm_storage_container" "storage" {
  count                 = var.cloud_provider == "azure" ? 1 : 0
  name                  = var.container_name
  storage_account_name  = azurerm_storage_account.storage[0].name
  container_access_type = "private"
}


variable "azure_lifecycle_rules" {
  description = "Lifecycle rules for Azure storage"
  type = list(object({
    name    = string
    enabled = bool
    filters = object({
      prefix_match = list(string)
      blob_types   = list(string)
    })
    actions = object({
      base_blob = object({
        tier_to_cool_after_days_since_modification_greater_than    = optional(number)
        tier_to_archive_after_days_since_modification_greater_than = optional(number)
        delete_after_days_since_modification_greater_than          = optional(number)
      })
      snapshot = object({
        delete_after_days_since_creation_greater_than = optional(number)
      })
    })
  }))
  default = [
    {
      name    = "cost-opt-lifecycle"
      enabled = true
      filters = {
        prefix_match = ["cost-opt/"]
        blob_types   = ["blockBlob"]
      }
      actions = {
        base_blob = {
          tier_to_cool_after_days_since_modification_greater_than    = 30
          tier_to_archive_after_days_since_modification_greater_than = 90
          delete_after_days_since_modification_greater_than          = 365
        }
        snapshot = {
          delete_after_days_since_creation_greater_than = 30
        }
      }
    }
  ]
}

resource "azurerm_storage_management_policy" "storage" {
  count              = var.cloud_provider == "azure" ? 1 : 0
  storage_account_id = azurerm_storage_account.storage[0].id

  dynamic "rule" {
    for_each = var.azure_lifecycle_rules
    content {
      name    = rule.value.name
      enabled = rule.value.enabled

      filters {
        prefix_match = rule.value.filters.prefix_match
        blob_types   = rule.value.filters.blob_types
      }

      actions {
        base_blob {
          tier_to_cool_after_days_since_modification_greater_than    = rule.value.actions.base_blob.tier_to_cool_after_days_since_modification_greater_than
          tier_to_archive_after_days_since_modification_greater_than = rule.value.actions.base_blob.tier_to_archive_after_days_since_modification_greater_than
          delete_after_days_since_modification_greater_than          = rule.value.actions.base_blob.delete_after_days_since_modification_greater_than
        }

        snapshot {
          delete_after_days_since_creation_greater_than = rule.value.actions.snapshot.delete_after_days_since_creation_greater_than
        }
      }
    }
  }
}


output "aws_bucket_name" {
  description = "AWS S3 bucket name"
  value       = var.cloud_provider == "aws" ? aws_s3_bucket.storage[0].bucket : null
}

output "aws_bucket_arn" {
  description = "AWS S3 bucket ARN"
  value       = var.cloud_provider == "aws" ? aws_s3_bucket.storage[0].arn : null
}

output "azure_storage_account_name" {
  description = "Azure storage account name"
  value       = var.cloud_provider == "azure" ? azurerm_storage_account.storage[0].name : null
}

output "azure_container_name" {
  description = "Azure storage container name"
  value       = var.cloud_provider == "azure" ? azurerm_storage_container.storage[0].name : null
}
