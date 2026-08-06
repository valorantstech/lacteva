# AWS — the optional abstraction

Hetzner is the primary target (`../hetzner`). This directory exists because
the work order asked for an AWS path, and because the topology is portable:
one VM, one static IP, one data volume, one firewall.

**It is deliberately a thin equivalent, not a parallel product.** Two
half-maintained infrastructure definitions are worse than one maintained one —
the second is always the one that has not been applied since March, and
discovering that during a migration is exactly the wrong time.

## What it provisions

| Hetzner | AWS |
| --- | --- |
| `hcloud_server` | `aws_instance` |
| `hcloud_primary_ip` | `aws_eip` |
| `hcloud_volume` | `aws_ebs_volume` + attachment |
| `hcloud_firewall` | `aws_security_group` |
| `hcloud_ssh_key` | `aws_key_pair` |
| `backups = true` | AWS Backup plan (daily, 30-day retention) |

Same cloud-init file, same filesystem standard, same systemd units, same
`deploy.sh`. Everything above the machine is identical, which is the point of
keeping provisioning and deployment separate.

## What it does NOT do

- **No RDS.** Moving PostgreSQL to RDS is the right long-term answer — it
  brings failover, PITR and replicas together and removes most of
  INFRASTRUCTURE.md §Disaster-recovery. But it changes the topology rather
  than the provider, so it belongs in its own work order.
- **No VPC creation.** It attaches to an existing VPC and subnet, because a
  VPC is usually an account-level decision made once, not per application.
- **No load balancer, no auto-scaling group.** The platform is a modular
  monolith with a single database; adding an ASG would produce N machines
  fighting over one PostgreSQL.

## Credentials

Uses the **`ibs`** AWS profile. Set `profile = "ibs"` in the provider (already
the default in `variables.tf`) or export `AWS_PROFILE=ibs`.

## Status

**Written, never applied.** Neither this nor the Hetzner configuration has been
run — there is no Terraform binary and no cloud account in the environment
where they were authored. Treat the first `terraform plan` as a review step,
not a formality.
