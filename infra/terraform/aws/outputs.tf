output "public_ip" {
  description = "Point DNS here. The EIP survives instance replacement."
  value       = aws_eip.public.public_ip
}

output "instance_id" {
  value = aws_instance.app.id
}

output "data_volume_id" {
  value = aws_ebs_volume.data.id
}

output "ssh_command" {
  value = "ssh lacteva@${aws_eip.public.public_ip}"
}
