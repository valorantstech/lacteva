# What the operator needs after `apply` (INF-001).

output "public_ipv4" {
  description = "Point the A record here. It survives server replacement."
  value       = hcloud_primary_ip.public_v4.ip_address
}

output "public_ipv6" {
  description = "Point the AAAA record here."
  value       = hcloud_primary_ip.public_v6.ip_address
}

output "server_id" {
  description = "Needed to detach the IP and volume during a host replacement."
  value       = hcloud_server.app.id
}

output "data_volume_id" {
  description = "The volume holding the database, backups and logs."
  value       = hcloud_volume.data.id
}

output "data_device_path" {
  description = "Stable device path cloud-init mounts at /var/lib/lacteva."
  value       = "/dev/disk/by-id/scsi-0HC_Volume_${hcloud_volume.data.id}"
}

output "ssh_command" {
  description = "First thing to run after apply."
  value       = "ssh lacteva@${hcloud_primary_ip.public_v4.ip_address}"
}

output "next_steps" {
  description = "Provisioning ends here; deployment is a separate step."
  value       = <<-EOT
    1. Point DNS at ${hcloud_primary_ip.public_v4.ip_address} (A) and ${hcloud_primary_ip.public_v6.ip_address} (AAAA).
    2. Wait for cloud-init: ssh lacteva@${hcloud_primary_ip.public_v4.ip_address} 'cloud-init status --wait'
    3. Copy .env.production to /etc/lacteva/ and issue TLS certificates.
    4. Deploy: /opt/lacteva/current/infra/deploy/deploy.sh <image-tag>
    Full sequence: INFRASTRUCTURE.md §Provisioning.
  EOT
}
