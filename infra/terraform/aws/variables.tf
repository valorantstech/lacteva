variable "aws_profile" {
  description = "AWS CLI profile. This platform deploys with `ibs`."
  type        = string
  default     = "ibs"
}

variable "region" {
  type    = string
  default = "eu-west-1"
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
  description = "Sized for PostgreSQL first — the whole stack shares this machine. m6i.2xlarge is the Hetzner cpx41 equivalent."
  type        = string
  default     = "m6i.2xlarge"
}

variable "ssh_public_keys" {
  type = map(string)
  validation {
    condition     = length(var.ssh_public_keys) > 0
    error_message = "at least one SSH key is required — cloud-init disables password login."
  }
}

variable "ssh_allowed_cidrs" {
  description = "NOT 0.0.0.0/0. Use a VPN, a bastion, or an office range."
  type        = list(string)
  validation {
    condition     = !contains(var.ssh_allowed_cidrs, "0.0.0.0/0")
    error_message = "refusing to open SSH to the whole internet."
  }
}

variable "data_volume_size_gb" {
  type    = number
  default = 200
  validation {
    condition     = var.data_volume_size_gb >= 50
    error_message = "below 50 GB the backup retention policy cannot be satisfied."
  }
}

variable "data_volume_iops" {
  description = "gp3 baseline is 3000. PostgreSQL under the modelled write load wants more."
  type        = number
  default     = 6000
}

variable "data_volume_throughput" {
  type    = number
  default = 250
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
