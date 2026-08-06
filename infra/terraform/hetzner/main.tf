# Lacteva production host — Hetzner Cloud (INF-001).
#
# One machine, one volume, one static IP, one firewall. That is the whole
# topology, and it is a deliberate choice rather than a first draft: the
# platform is a modular monolith with a single database, so a single host is
# the honest shape for it. Scaling out means changing the platform's
# architecture, not this file — INFRASTRUCTURE.md §Scaling says what breaks
# first and in what order.
#
# What this file does NOT do: install anything. Provisioning is cloud-init's
# job (../../cloud-init/lacteva.yaml), and deployment is deploy.sh's. Keeping
# the three separate means a server can be replaced without redeploying, and
# redeployed without reprovisioning.

locals {
  name = "lacteva-${var.environment}"

  labels = {
    project     = "lacteva"
    environment = var.environment
    managed_by  = "terraform"
  }
}

# --- access ----------------------------------------------------------------

resource "hcloud_ssh_key" "admin" {
  for_each   = var.ssh_public_keys
  name       = "${local.name}-${each.key}"
  public_key = each.value
  labels     = local.labels
}

# --- addressing ------------------------------------------------------------

# A primary IP that outlives the server it is attached to. This is the whole
# server-replacement story: build a new machine, detach the IP, attach it,
# and DNS never changes — no propagation wait, no stale resolver cache, no
# certificate reissue. Without it, replacing a host is a DNS event with a TTL
# attached to it.
resource "hcloud_primary_ip" "public_v4" {
  name          = "${local.name}-ipv4"
  type          = "ipv4"
  datacenter    = "${var.location}-dc3"
  assignee_type = "server"
  auto_delete   = false # survives `terraform destroy` of the server
  labels        = local.labels

  lifecycle {
    # Losing the address means every client, DNS record and certificate is
    # pointing at somebody else's machine.
    prevent_destroy = true
  }
}

resource "hcloud_primary_ip" "public_v6" {
  name          = "${local.name}-ipv6"
  type          = "ipv6"
  datacenter    = "${var.location}-dc3"
  assignee_type = "server"
  auto_delete   = false
  labels        = local.labels

  lifecycle {
    prevent_destroy = true
  }
}

# --- storage ---------------------------------------------------------------

# Everything that must survive the machine lives here: the database, the
# backups, the logs. The server is then genuinely disposable — which is what
# makes "replace the host" a routine operation rather than a recovery.
#
# Formatting is deliberately NOT done by Terraform. cloud-init formats it only
# if it has no filesystem, because a `format` attribute here would let a
# `terraform apply` after a state mishap reformat a volume holding production
# data. That is a footgun with no upside.
resource "hcloud_volume" "data" {
  name     = "${local.name}-data"
  size     = var.data_volume_size_gb
  location = var.location
  labels   = local.labels

  lifecycle {
    prevent_destroy = true
    # Growing is fine and online; shrinking is impossible, and Terraform would
    # otherwise plan a destroy-and-recreate to satisfy a smaller number.
    ignore_changes = [size]
  }
}

resource "hcloud_volume_attachment" "data" {
  volume_id = hcloud_volume.data.id
  server_id = hcloud_server.app.id
  automount = false # cloud-init mounts it, with the right options
}

# --- the host --------------------------------------------------------------

resource "hcloud_server" "app" {
  name        = local.name
  server_type = var.server_type
  image       = var.image
  location    = var.location
  ssh_keys    = [for key in hcloud_ssh_key.admin : key.id]
  labels      = local.labels

  # Provider-level daily snapshots of the whole machine. A second, independent
  # line of defence: these survive a mistake INSIDE the machine that the
  # on-volume backups would not, because those live on the volume.
  backups = var.enable_provider_snapshots

  firewall_ids = [hcloud_firewall.app.id]

  public_net {
    ipv4_enabled = true
    ipv4         = hcloud_primary_ip.public_v4.id
    ipv6_enabled = true
    ipv6         = hcloud_primary_ip.public_v6.id
  }

  user_data = templatefile("${path.module}/../../cloud-init/lacteva.yaml", {
    hostname       = local.name
    data_device    = "/dev/disk/by-id/scsi-0HC_Volume_${hcloud_volume.data.id}"
    timezone       = "UTC"
    admin_user     = "lacteva"
    ssh_public_keys = values(var.ssh_public_keys)
  })

  lifecycle {
    # A change to user_data must NOT recreate a running production server —
    # cloud-init only runs on first boot anyway, so replacing the machine to
    # apply it would destroy data and change nothing.
    ignore_changes = [user_data, image]
  }
}

# --- reverse DNS -----------------------------------------------------------
# Mail and TLS tooling both care. Skipped when no domain is configured.

resource "hcloud_rdns" "v4" {
  count      = var.domain == "" ? 0 : 1
  server_id  = hcloud_server.app.id
  ip_address = hcloud_primary_ip.public_v4.ip_address
  dns_ptr    = var.domain
}

resource "hcloud_rdns" "v6" {
  count      = var.domain == "" ? 0 : 1
  server_id  = hcloud_server.app.id
  ip_address = hcloud_primary_ip.public_v6.ip_address
  dns_ptr    = var.domain
}
