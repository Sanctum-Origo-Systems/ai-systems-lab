terraform {
  # Pinned to the CI version's minor line. S3 native state locking (use_lockfile) needs >= 1.10.
  required_version = "~> 1.17.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Partial configuration: bucket, key and region come from an uncommitted backend.hcl
  # (copy backend.hcl.example), so no account-specific name is committed.
  backend "s3" {
    encrypt      = true
    use_lockfile = true
  }
}
