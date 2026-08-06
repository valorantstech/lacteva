# Provider pinning (INF-001).
#
# Pinned to a minor version, not a range. An infrastructure definition that
# resolves differently on Tuesday than it did on Monday is not a definition —
# and the failure shows up as "terraform plan wants to replace the server",
# which is the most alarming diff there is.
terraform {
  required_version = "~> 1.9"

  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.48"
    }
  }

  # State holds the server id, the volume id, and the IP. Losing it means
  # Terraform no longer knows what it created — which is recoverable by
  # import, but only if someone wrote down what to import.
  #
  # Local state is the DEFAULT here on purpose: a remote backend needs a
  # bucket that this configuration does not create, and a half-configured
  # backend fails in a way that is hard to read. Uncomment and fill in before
  # a second person touches this.
  #
  # backend "s3" {
  #   bucket  = "lacteva-terraform-state"
  #   key     = "production/hetzner.tfstate"
  #   region  = "eu-west-1"
  #   encrypt = true
  #   profile = "ibs"
  #   use_lockfile = true
  # }
}

provider "hcloud" {
  # Never in a .tf file. Export HCLOUD_TOKEN, or use a tfvars file that is
  # git-ignored. See INFRASTRUCTURE.md §Secrets.
  token = var.hcloud_token
}
