output "alb_dns_name" {
  description = "The load balancer's address."
  value       = aws_lb.main.dns_name
}

output "weather_url" {
  value = "http://${aws_lb.main.dns_name}:${local.tiers.weather.listener_port}"
}

output "advisor_url" {
  value = "http://${aws_lb.main.dns_name}:${local.tiers.advisor.listener_port}"
}

output "gemini_parameter_name" {
  description = "Where to store your Gemini key."
  value       = aws_ssm_parameter.gemini.name
}

output "weather_table_name" {
  value = aws_dynamodb_table.weather.name
}
