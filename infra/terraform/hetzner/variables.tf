# Inputs (INF-001). Every one either has a defensible default or no default at
# all — a variable that silently defaults to something wrong is worse than one
# that stops the plan.

variable "hcloud_token" {
  description = "Hetzner Cloud API token. Export HCLOUD_TOKEN rather than writing it down."
  type        = string
  sensitive   = true
}

variable "environment" {
  description = "Environment name. Used in every resource name and label, so two environments cannot collide in one project."
  type        = string
  default     = "production"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,20}$", var.environment))
    error_message = "environment must be lowercase alphanumeric with hyphens."
  }
}

variable "location" {
  description = "Hetzner location. Pick one close to the market being served — latency to a Kenyan collection center is dominated by distance."
  type        = string
  default     = "nbg1" # Nuremberg
}

variable "server_type" {
  description = <<-EOT
    Hetzner server type. The whole stack — API, PostgreSQL, Redis, Prometheus,
    Grafana, Loki — runs on this one machine, so it is sized for the database
    first. cpx41 (8 vCPU / 16 GB) is the smallest type where the documented
    PostgreSQL settings (512MB shared_buffers, 1GB maintenance_work_mem) leave
    room for everything else. Below cpx31 the monitoring stack alone will
    fight the database for page cache.
  EOT
  type        = string
  default     = "cpx41"
}

variable "image" {
  description = "Base image. Ubuntu LTS because cloud-init, unattended-upgrades and the Docker repository are all first-class there."
  type        = string
  default     = "ubuntu-24.04"
}

variable "ssh_public_keys" {
  description = <<-EOT
    Public keys allowed to log in, as a map of name => key material.
    Passwords are disabled entirely by cloud-init, so this list is the ONLY
    way onto the machine. An empty map produces a server nobody can reach.
  EOT
  type        = map(string)

  validation {
    condition     = length(var.ssh_public_keys) > 0
    error_message = "at least one SSH key is required — cloud-init disables password login."
  }
}

variable "ssh_allowed_cidrs" {
  description = <<-EOT
    Source ranges permitted to reach SSH. NOT 0.0.0.0/0.

    Exposing SSH to the internet is the single most common way a small
    deployment is compromised, and key-only auth reduces the risk without
    removing it — the daemon still parses attacker-controlled input from
    anywhere on earth. Use an office range, a VPN, or a bastion.
  EOT
  type        = list(string)

  validation {
    condition     = !contains(var.ssh_allowed_cidrs, "0.0.0.0/0")
    error_message = "refusing to open SSH to the whole internet. Use a VPN, a bastion, or an office range."
  }
}

variable "data_volume_size_gb" {
  description = <<-EOT
    Size of the separate data volume holding PostgreSQL, backups and logs.

    DBD-0001 models ~12 TB/year at full scale, which this topology does not
    address at all — see INFRASTRUCTURE.md §Scaling. 200 GB is a sensible
    first year for a single-tenant or pilot deployment, and the volume can be
    grown in place (Hetzner supports online resize; shrinking it cannot).
  EOT
  type        = number
  default     = 200

  validation {
    condition     = var.data_volume_size_gb >= 50
    error_message = "below 50 GB the backup retention policy cannot be satisfied."
  }
}

variable "enable_provider_snapshots" {
  description = <<-EOT
    Hetzner's own daily server backups (+20% of server cost).

    These are a SEPARATE line of defence from the platform's logical backups:
    they survive a mistake inside the machine (a bad migration, an rm -rf)
    that the on-volume backups would not, because those live on the volume.
    Keep them on unless backups are being shipped off-host by other means.
  EOT
  type        = bool
  default     = true
}

variable "domain" {
  description = "Public hostname, used for the reverse DNS record. TLS is issued against this name."
  type        = string
  default     = ""
}
