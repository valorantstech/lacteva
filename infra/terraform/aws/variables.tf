variable "aws_profile" {
  description = "AWS CLI profile. This platform deploys with `ibs`."
  type        = string
  default     = "ibs"
}

variable "region" {
  # WO-48: NO DEFAULT, deliberately. It used to default to `eu-west-1` while
  # the platform runs in `ap-south-1`, so `terraform plan` in this directory
  # looked in Ireland, found nothing, and reported that every resource —
  # instance, EIP, security group, data volume — "has been deleted". Applying
  # that would have written an empty state and then built a second, parallel
  # deployment in the wrong continent, leaving production running and
  # unmanaged. A default that is wrong everywhere it is used is worse than no
  # default: no default is a question, and this was a confident wrong answer.
  description = "The region this deployment lives in. Stated, never inherited."
  type        = string
}

variable "environment" {
  type    = string
  default = "production"
}

variable "vpc_id" {
  description = "Existing VPC. A VPC is an account-level decision, not a per-application one."
  type        = string
}

variable "subnet_id" {
  description = "Public subnet in `availability_zone`. The instance needs a route to the internet for image pulls and ACME."
  type        = string
}

variable "availability_zone" {
  description = "Must match the subnet. An EBS volume can only attach to an instance in its own AZ."
  type        = string
}

variable "instance_type" {
  description = <<-EOT
    COST-001: the default is a DEVELOPMENT size, not a production one.

    Measured on the AWS-001 deployment, with all twelve containers running:
    the whole stack uses ~850 MB of container memory (api 417 MB, rabbitmq
    120 MB, postgres 111 MB, everything else under 50 MB each) and idles
    near zero CPU. t3.medium's 4 GB is ample for development, internal
    testing and demos, and costs less than half of m7i-flex.large.

    The one thing 4 GB will NOT do is BUILD the portal image on the host —
    `npm run build` needed more than 8 GB would give it while the stack was
    running. Build in CI and pull from ECR, which is the intended path.

    ACCOUNT CONSTRAINT, found by execution: the AWS-001 account is on a free
    plan, which refuses `RunInstances` for any type not on the free-tier
    list — t3.medium among them. `--dry-run` does NOT evaluate that
    restriction, so it reports success and the real call fails; and
    `ModifyInstanceAttribute` is blocked outright, so an instance cannot be
    resized in place, only replaced. The free-tier list here is t3.micro,
    t3.small, t4g.micro, t4g.small, c7i-flex.large and m7i-flex.large, so
    c7i-flex.large (2 vCPU, 4 GiB) is the t3.medium equivalent this account
    can actually launch — same memory, ~$62/month against m7i-flex.large's
    ~$74. On an unrestricted account, set t3.medium (~$33/month).

    Production sizing is a separate decision and wants PostgreSQL memory
    first: m6i.2xlarge is the Hetzner cpx41 equivalent. Set it explicitly
    when there is a production to size for — a default that costs
    $200+/month is a foot-gun for an environment with no customers.
  EOT
  type        = string
  default     = "t3.medium"
}

variable "ssh_public_keys" {
  type = map(string)
  validation {
    condition     = length(var.ssh_public_keys) > 0
    error_message = "at least one SSH key is required — cloud-init disables password login."
  }
}

variable "ssh_allowed_cidrs" {
  # WO-48. These are reconciled with the live security group; a rule added by
  # hand and not recorded here is a rule the next `apply` deletes. The values
  # live in `terraform.tfvars`, which is gitignored, because they are the
  # operators' own addresses and do not belong in a repository.
  description = "NOT 0.0.0.0/0. Use a VPN, a bastion, or an office range."
  type        = list(string)
  validation {
    condition     = !contains(var.ssh_allowed_cidrs, "0.0.0.0/0")
    error_message = "refusing to open SSH to the whole internet."
  }
}

variable "data_volume_size_gb" {
  # COST-001: 50 GB, the floor the retention check allows. The AWS-001
  # deployment used 40 KB of the 200 GB provisioned — Docker's volumes
  # (pgdata, backups, WAL) live on the ROOT volume, so this one holds only
  # what is explicitly placed under /var/lib/lacteva. Grow it when there is
  # data to justify it; gp3 grows online, and shrinking needs a replacement.
  type    = number
  default = 50
  validation {
    condition     = var.data_volume_size_gb >= 50
    error_message = "below 50 GB the backup retention policy cannot be satisfied."
  }
}

variable "data_volume_iops" {
  # COST-001: 3000 is gp3's INCLUDED baseline; every IOPS above it is billed
  # separately (~$0.005/IOPS-month, so the old 6000 default was ~$15/month
  # for provisioned IOPS alone, on a volume holding 40 KB).
  description = "gp3 baseline is 3000 and is free. Raise it for production write load, knowing it bills."
  type        = number
  default     = 3000
}

variable "data_volume_throughput" {
  # COST-001: 125 MB/s is gp3's included baseline; above it bills per MB/s.
  type    = number
  default = 125
}

variable "enable_provider_snapshots" {
  type    = bool
  default = true
}

variable "snapshot_retention_days" {
  type    = number
  default = 30
}

variable "backup_role_arn" {
  description = "IAM role AWS Backup assumes. Empty disables the plan rather than creating a role this module should not own."
  type        = string
  default     = ""
}
