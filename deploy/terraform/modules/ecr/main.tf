terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

# ---------------------------------------------------------------------------
# Variables
# ---------------------------------------------------------------------------

variable "repositories" {
  description = "Names of the private ECR repositories to create, one per image."
  type        = set(string)
}

variable "keep_images" {
  description = "Number of newest images kept per repository; older images expire."
  type        = number
  default     = 10

  validation {
    condition     = var.keep_images >= 1 && floor(var.keep_images) == var.keep_images
    error_message = "keep_images must be a whole number of at least 1."
  }
}

variable "encryption_type" {
  description = "Encryption at rest for every repository: AES256 (AWS-managed) or KMS."
  type        = string
  default     = "AES256"

  validation {
    condition     = contains(["AES256", "KMS"], var.encryption_type)
    error_message = "encryption_type must be AES256 or KMS."
  }
}

variable "kms_key_arn" {
  description = "Customer-managed KMS key ARN, used only when encryption_type is KMS. Null uses the AWS-managed ECR key."
  type        = string
  default     = null
}

# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

# No aws_ecr_repository_policy is created, so only principals in this account
# with IAM permissions can pull or push. There is no cross-account access.
resource "aws_ecr_repository" "this" {
  #checkov:skip=CKV_AWS_136:Decided: AWS-managed encryption (AES256) instead of a customer-managed KMS key. A lab stack torn down after every demo gains little from its own key; KMS stays opt-in through encryption_type.
  for_each = var.repositories

  name                 = each.value
  image_tag_mutability = "IMMUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = var.encryption_type
    kms_key         = var.encryption_type == "KMS" ? var.kms_key_arn : null
  }
}

resource "aws_ecr_lifecycle_policy" "this" {
  for_each = aws_ecr_repository.this

  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep only the newest ${var.keep_images} images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = var.keep_images
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "repository_urls" {
  description = "Map from repository name to repository URL, for make push."
  value       = { for name, repo in aws_ecr_repository.this : name => repo.repository_url }
}
