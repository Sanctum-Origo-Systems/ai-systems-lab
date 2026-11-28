#!/usr/bin/env bash
# Create the Terraform state bucket once, by hand, before the first `terraform init`.
# Usage: AWS_PROFILE=lab deploy/terraform/bootstrap-state.sh <bucket-name> [region]
#
# The bucket gets:
#   - all four Block Public Access settings
#   - ACLs disabled (BucketOwnerEnforced)
#   - versioning, so a bad apply can be rolled back
#   - default encryption (SSE-S3, AES256)
#   - a bucket policy that denies any request not made over TLS
# Locking uses Terraform's S3 native lockfile (use_lockfile = true), so there's no DynamoDB table.
# Safe to re-run: every step is a put of the desired state.
set -euo pipefail

bucket="${1:?usage: bootstrap-state.sh <bucket-name> [region]}"
region="${2:-us-east-1}"

if aws s3api head-bucket --bucket "$bucket" 2>/dev/null; then
  echo "bucket $bucket exists; re-applying settings"
elif [ "$region" = "us-east-1" ]; then
  aws s3api create-bucket --bucket "$bucket" --region "$region"
else
  aws s3api create-bucket --bucket "$bucket" --region "$region" \
    --create-bucket-configuration "LocationConstraint=$region"
fi

aws s3api put-public-access-block --bucket "$bucket" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

aws s3api put-bucket-ownership-controls --bucket "$bucket" \
  --ownership-controls 'Rules=[{ObjectOwnership=BucketOwnerEnforced}]'

aws s3api put-bucket-versioning --bucket "$bucket" --versioning-configuration Status=Enabled

aws s3api put-bucket-encryption --bucket "$bucket" --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"},"BucketKeyEnabled":true}]}'

aws s3api put-bucket-policy --bucket "$bucket" --policy "$(cat <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyInsecureTransport",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": ["arn:aws:s3:::${bucket}", "arn:aws:s3:::${bucket}/*"],
      "Condition": {"Bool": {"aws:SecureTransport": "false"}}
    }
  ]
}
JSON
)"

aws s3api put-bucket-tagging --bucket "$bucket" \
  --tagging 'TagSet=[{Key=project,Value=ai-systems-lab},{Key=workstream,Value=base},{Key=ttl,Value=none}]'

echo "state bucket $bucket ready in $region"
