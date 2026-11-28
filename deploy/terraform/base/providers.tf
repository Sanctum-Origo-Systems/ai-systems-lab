provider "aws" {
  region = var.region

  # Every resource is tagged through default_tags, so modules only set Name.
  default_tags {
    tags = {
      project    = "ai-systems-lab"
      workstream = "base"
      ttl        = var.ttl
    }
  }
}
