variable "region" {
  description = "AWS region. af-south-1 (Cape Town) keeps data in South Africa (POPIA); it must be enabled first. eu-west-1 works without enabling."
  type        = string
  default     = "af-south-1"
}

variable "repo_url" {
  description = "Public Git URL the server clones"
  type        = string
  default     = "https://github.com/DayDay0308/blinkhub-procurement-intelligence.git"
}

variable "branch" {
  type    = string
  default = "main"
}

variable "instance_type" {
  description = "t3.small (2 vCPU, 2 GB) is Free Tier eligible and enough for the demo with swap"
  type        = string
  default     = "t3.small"
}

variable "alert_email" {
  description = "Where budget alerts go"
  type        = string
}

variable "monthly_budget_usd" {
  description = "Alert at 50%, 80% and 100% of this, and when the forecast passes it"
  type        = number
  default     = 20
}

variable "domain" {
  description = "Leave empty to use <ip>.sslip.io (works without buying a domain)"
  type        = string
  default     = ""
}

variable "anthropic_api_key" {
  description = "Optional. Stored as an encrypted SSM parameter, never in the server's user data"
  type        = string
  default     = ""
  sensitive   = true
}

variable "github_repo" {
  description = "Optional owner/name. Creates a role GitHub Actions can assume (OIDC, no stored keys) to deploy"
  type        = string
  default     = ""
}
variable "github_oidc_subject" {
  description = "Exact identity GitHub sends (now includes owner and repo IDs). Copy it from CloudTrail."
  type        = string
  default     = ""
}