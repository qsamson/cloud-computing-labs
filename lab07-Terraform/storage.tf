resource "aws_dynamodb_table" "weather" {
  name         = "${var.name_prefix}-weather-lookups"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "zip"

  attribute {
    name = "zip"
    type = "S"
  }

  ttl {
    attribute_name = "expiresAt"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = false
  }
}

resource "aws_ssm_parameter" "gemini" {
  name  = "/${var.name_prefix}/gemini-api-key"
  type  = "SecureString"
  value_wo         = var.gemini_api_key
  value_wo_version = 1
}
