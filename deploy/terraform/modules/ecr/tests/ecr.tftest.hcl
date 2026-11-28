# Offline tests: the mocked AWS provider needs no credentials and makes no AWS calls.
# Run with: terraform -chdir=deploy/terraform/modules/ecr init -backend=false && terraform -chdir=deploy/terraform/modules/ecr test

mock_provider "aws" {}

variables {
  repositories = ["lab-api", "lab-worker"]
}

run "defaults" {
  command = apply

  assert {
    condition     = toset(keys(aws_ecr_repository.this)) == toset(["lab-api", "lab-worker"])
    error_message = "One repository must be created per name in var.repositories."
  }

  assert {
    condition     = alltrue([for r in aws_ecr_repository.this : r.image_tag_mutability == "IMMUTABLE"])
    error_message = "Image tags must be immutable."
  }

  assert {
    condition     = alltrue([for r in aws_ecr_repository.this : r.image_scanning_configuration[0].scan_on_push])
    error_message = "Every repository must scan on push."
  }

  assert {
    condition     = alltrue([for r in aws_ecr_repository.this : r.force_delete])
    error_message = "Every repository must set force_delete so teardown is one command."
  }

  assert {
    condition     = alltrue([for r in aws_ecr_repository.this : r.encryption_configuration[0].encryption_type == "AES256"])
    error_message = "Encryption must default to AES256."
  }

  assert {
    condition     = toset(keys(aws_ecr_lifecycle_policy.this)) == toset(["lab-api", "lab-worker"])
    error_message = "Every repository must have a lifecycle policy."
  }

  assert {
    condition = alltrue([
      for name, p in aws_ecr_lifecycle_policy.this :
      p.repository == name &&
      jsondecode(p.policy).rules[0].selection.countType == "imageCountMoreThan" &&
      jsondecode(p.policy).rules[0].selection.countNumber == 10 &&
      jsondecode(p.policy).rules[0].selection.tagStatus == "any" &&
      jsondecode(p.policy).rules[0].action.type == "expire"
    ])
    error_message = "Lifecycle policy must expire all but the newest 10 images by default."
  }

  assert {
    condition     = toset(keys(output.repository_urls)) == toset(["lab-api", "lab-worker"])
    error_message = "repository_urls must map every repository name to its URL."
  }

  assert {
    condition     = alltrue([for name, url in output.repository_urls : url == aws_ecr_repository.this[name].repository_url])
    error_message = "repository_urls values must be the repository URLs."
  }
}

run "keep_images_override" {
  command = apply

  variables {
    keep_images = 3
  }

  assert {
    condition     = alltrue([for p in aws_ecr_lifecycle_policy.this : jsondecode(p.policy).rules[0].selection.countNumber == 3])
    error_message = "Lifecycle policy must use var.keep_images."
  }
}

run "kms_encryption" {
  command = apply

  variables {
    encryption_type = "KMS"
    # A placeholder account id built at test time, so no literal account id is committed.
    kms_key_arn = format("arn:aws:kms:us-east-1:%s:key/test", join("", [for i in range(12) : "1"]))
  }

  assert {
    condition     = alltrue([for r in aws_ecr_repository.this : r.encryption_configuration[0].encryption_type == "KMS"])
    error_message = "encryption_type KMS must reach every repository."
  }

  assert {
    condition     = alltrue([for r in aws_ecr_repository.this : r.encryption_configuration[0].kms_key == var.kms_key_arn])
    error_message = "kms_key_arn must reach every repository when encryption_type is KMS."
  }
}

run "rejects_unknown_encryption_type" {
  command = plan

  variables {
    encryption_type = "NONE"
  }

  expect_failures = [var.encryption_type]
}

run "rejects_zero_keep_images" {
  command = plan

  variables {
    keep_images = 0
  }

  expect_failures = [var.keep_images]
}
