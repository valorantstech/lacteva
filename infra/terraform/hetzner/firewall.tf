# The perimeter (INF-001).
#
# Hetzner's cloud firewall runs OUTSIDE the machine, so it holds even if the
# host's own nftables rules are wrong, the machine is mid-boot, or somebody
# has just flushed iptables while debugging. cloud-init configures ufw as
# well — two layers, and neither is load-bearing alone.
#
# Three ports in. Everything else — PostgreSQL, Redis, Prometheus, Grafana,
# Loki — is reachable only from inside the machine, where the compose network
# already confines it (DEP-001: only nginx publishes a port).

resource "hcloud_firewall" "app" {
  name   = "${local.name}-fw"
  labels = local.labels

  rule {
    description = "HTTP — ACME challenges and the redirect to HTTPS"
    direction   = "in"
    protocol    = "tcp"
    port        = "80"
    source_ips  = ["0.0.0.0/0", "::/0"]
  }

  rule {
    description = "HTTPS — the API and the admin portal"
    direction   = "in"
    protocol    = "tcp"
    port        = "443"
    source_ips  = ["0.0.0.0/0", "::/0"]
  }

  rule {
    description = "SSH — administration, from known ranges only"
    direction   = "in"
    protocol    = "tcp"
    port        = "22"
    # Validated in variables.tf to reject 0.0.0.0/0. Key-only auth reduces the
    # risk of exposing sshd to the internet; it does not remove it, because
    # the daemon still parses attacker-controlled input from anywhere.
    source_ips = var.ssh_allowed_cidrs
  }

  rule {
    description = "ICMP — being able to ping a host you cannot reach is how you find out why"
    direction   = "in"
    protocol    = "icmp"
    source_ips  = ["0.0.0.0/0", "::/0"]
  }

  # Outbound is deliberately unrestricted. The host must pull container
  # images, fetch OS updates, complete ACME challenges, and — once an adapter
  # exists — reach an SMS gateway. Egress filtering that has to be edited
  # every time a dependency moves gets disabled during the first incident,
  # and a rule everyone disables is worse than an honest absence.
}
