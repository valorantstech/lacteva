# Lacteva production host — AWS (INF-001, optional abstraction).
#
# The same topology as ../hetzner: one instance, one Elastic IP, one EBS
# volume, one security group. Deliberately thin — see README.md for what this
# is not, and why RDS belongs in its own work order.
#
# Everything above the machine (cloud-init, the filesystem standard, systemd,
# deploy.sh) is shared with the Hetzner path unchanged.

terraform {
  required_version = "~> 1.9"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}

provider "aws" {
  region = var.region
  # The platform's AWS account.
  profile = var.aws_profile
  default_tags {
    tags = local.tags
  }
}

locals {
  name = "lacteva-${var.environment}"

  # AWS Backup cannot select a resource without a role to assume, so asking for
  # snapshots without one produces a vault and a plan that back nothing up.
  # Requiring both makes the failure "you did not ask for snapshots" instead of
  # "your snapshots silently do not exist".
  provider_snapshots = var.enable_provider_snapshots && var.backup_role_arn != ""
  tags = {
    Project     = "lacteva"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }
}

resource "aws_key_pair" "admin" {
  for_each   = var.ssh_public_keys
  key_name   = "${local.name}-${each.key}"
  public_key = each.value
}

# --- perimeter -------------------------------------------------------------
resource "aws_security_group" "app" {
  name        = "${local.name}-sg"
  description = "Lacteva: 80/443 from anywhere, SSH from known ranges only"
  vpc_id      = var.vpc_id

  # AWS-001: AWS restricts security-group descriptions to a subset of ASCII
  # (^[0-9A-Za-z_ .:/()#,@\[\]+=&;{}!$*-]*$). An em dash is refused, and the
  # refusal happens at PLAN time, so this configuration could never have been
  # planned — the same class of defect DEPLOY-001 found in the Hetzner config,
  # in the file next to it. Hyphens here, prose everywhere else.
  ingress {
    description = "HTTP - ACME and the redirect to HTTPS"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "SSH - validated to reject 0.0.0.0/0 in variables.tf"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.ssh_allowed_cidrs
  }

  # Unrestricted, for the same reason as the Hetzner path: image pulls, OS
  # updates, ACME, and eventually an SMS gateway. An egress rule that must be
  # edited whenever a dependency moves is one that gets disabled mid-incident.
  egress {
    description = "all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle {
    create_before_destroy = true
  }
}

# --- storage ---------------------------------------------------------------
resource "aws_ebs_volume" "data" {
  availability_zone = var.availability_zone
  size              = var.data_volume_size_gb
  type              = "gp3"
  iops              = var.data_volume_iops
  throughput        = var.data_volume_throughput
  encrypted         = true # not optional: this volume holds PII and bank details

  tags = { Name = "${local.name}-data" }

  lifecycle {
    prevent_destroy = true
    ignore_changes  = [size] # grow in place; never let a smaller number plan a replace
  }
}

resource "aws_volume_attachment" "data" {
  device_name = "/dev/xvdf"
  volume_id   = aws_ebs_volume.data.id
  instance_id = aws_instance.app.id
  # Detaching a mounted volume corrupts it. Stopping the instance first is the
  # documented server-replacement procedure, not something Terraform should do
  # on its own.
  stop_instance_before_detaching = true
}

# --- the host --------------------------------------------------------------
resource "aws_instance" "app" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  availability_zone      = var.availability_zone
  subnet_id              = var.subnet_id
  vpc_security_group_ids = [aws_security_group.app.id]
  key_name               = values(aws_key_pair.admin)[0].key_name

  root_block_device {
    volume_size = 40
    volume_type = "gp3"
    encrypted   = true
  }

  metadata_options {
    # IMDSv2 only. IMDSv1 turns any SSRF in the application into instance
    # credentials, which is the single most valuable thing on the machine.
    http_tokens                 = "required"
    http_endpoint               = "enabled"
    http_put_response_hop_limit = 1 # containers cannot reach it
  }

  user_data = templatefile("${path.module}/../../cloud-init/lacteva.yaml", {
    hostname = local.name
    # AWS-001: NOT "/dev/xvdf". Every instance type this platform would use is
    # a Nitro type, and Nitro ignores the device name in the attachment and
    # exposes the volume as an NVMe device (`/dev/nvme1n1`) whose number
    # depends on attach order. cloud-init waited 60s for a device that was
    # never going to appear, then tried to mkfs it and aborted the whole
    # bootstrap — the host came up with no Docker.
    #
    # `/dev/disk/by-id/nvme-Amazon_Elastic_Block_Store_<volume-id>` is the
    # stable path AWS guarantees, and it names THIS volume rather than
    # whichever NVMe device happened to enumerate second.
    data_device     = "/dev/disk/by-id/nvme-Amazon_Elastic_Block_Store_${replace(aws_ebs_volume.data.id, "-", "")}"
    timezone        = "UTC"
    admin_user      = "lacteva"
    ssh_public_keys = values(var.ssh_public_keys)
  })

  tags = { Name = local.name }

  lifecycle {
    ignore_changes = [ami, user_data]
  }
}

resource "aws_eip" "public" {
  domain   = "vpc"
  instance = aws_instance.app.id
  tags     = { Name = "${local.name}-ip" }

  lifecycle {
    prevent_destroy = true
  }
}

# --- backups ---------------------------------------------------------------
# Snapshots of the whole volume, independent of the platform's own logical
# backups. Two lines of defence: this one survives a mistake INSIDE the
# machine, which the on-volume backups would not.
#
# AWS-001: `backup_role_arn` says "Empty disables the plan rather than creating
# a role this module should not own", and nothing implemented it. With the
# default (`enable_provider_snapshots = true`, `backup_role_arn = ""`) the
# vault and plan were created and the SELECTION failed on `IAM Role is null` —
# a half-built backup plan that snapshots nothing, left behind by a failed
# apply. `local.provider_snapshots` makes the documented contract true.
resource "aws_backup_vault" "main" {
  count = local.provider_snapshots ? 1 : 0
  name  = "${local.name}-vault"
}

resource "aws_backup_plan" "daily" {
  count = local.provider_snapshots ? 1 : 0
  name  = "${local.name}-daily"

  rule {
    rule_name         = "daily"
    target_vault_name = aws_backup_vault.main[0].name
    schedule          = "cron(30 1 * * ? *)" # before the platform's 02:15 logical backup
    lifecycle {
      delete_after = var.snapshot_retention_days
    }
  }
}

resource "aws_backup_selection" "data" {
  count        = local.provider_snapshots ? 1 : 0
  name         = "${local.name}-data"
  plan_id      = aws_backup_plan.daily[0].id
  iam_role_arn = var.backup_role_arn
  resources    = [aws_ebs_volume.data.arn]
}
