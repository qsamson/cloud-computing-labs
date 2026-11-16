variable "aws_region" {
  description = "Region for everything in this lab."
  type        = string
  default     = "us-east-2"
}

variable "key_name" {
  description = "Name of the EC2 key pair you created in lab02."
  type        = string
}

variable "ssh_cidr" {
  description = "Your public address as x.x.x.x/32, to allow SSH to the instances. Leave empty to allow no SSH."
  type        = string
  default     = ""

  validation {
    condition     = var.ssh_cidr == "" || can(cidrhost(var.ssh_cidr, 0))
    error_message = "ssh_cidr must be empty or a CIDR block such as 203.0.113.7/32."
  }
}

variable "contact_email" {
  description = "Goes into the User-Agent header that the National Weather Service asks every client to send."
  type        = string
}

variable "instance_type" {
  description = "Instance type for both tiers."
  type        = string
  default     = "t3.micro"
}

variable "name_prefix" {
  description = "Start of every resource name."
  type        = string
  default     = "itmo-444-544-lab07"
}

variable "cache_seconds" {
  description = "How long the weather service reuses a saved forecast."
  type        = number
  default     = 600
}

variable "gemini_model" {
  description = "Gemini model name."
  type        = string
  default     = "gemini-3.1-flash-lite"
}

variable "key_cache_seconds" {
  description = "How long the advisor keeps the Gemini key in memory before reading it again."
  type        = number
  default     = 60
}

variable "gemini_api_key" {
  type      = string
  sensitive = true
  ephemeral = true
}
