variable "region" {
  description = "AWS region. Mumbai is closest for India."
  type        = string
  default     = "ap-south-1"
}

variable "instance_type" {
  description = "EC2 size. t3.micro (2 vCPU, 1 GB RAM + 2 GB swap) is the cheapest size that runs both APIs."
  type        = string
  default     = "t3.micro"
}

variable "disk_gb" {
  description = "Server disk size (OS + container images + swap)."
  type        = number
  default     = 20
}

variable "github_repository" {
  description = "GitHub repository (owner/name) allowed to deploy, via OIDC."
  type        = string
  default     = "vdt1905/ManuscriptOS"
}

variable "create_github_oidc_provider" {
  description = "Create the GitHub OIDC identity provider. Set false if the account already has one."
  type        = bool
  default     = true
}

variable "alert_email" {
  description = "Email that gets an alert if AWS spending passes $1 (empty = no budget alarm)."
  type        = string
  default     = ""
}

# ── Application secrets (stored encrypted in SSM Parameter Store) ───────────
# Put values in terraform.tfvars (gitignored).

variable "mongo_uri" {
  description = "MongoDB connection string, e.g. MongoDB Atlas free tier (M0)."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.mongo_uri) > 0
    error_message = "mongo_uri is required (the EC2 instance is too small to also run MongoDB)."
  }
}

variable "groq_api_key" {
  description = "Groq API key for the AI features."
  type        = string
  default     = ""
  sensitive   = true
}

variable "openai_api_key" {
  type      = string
  default   = ""
  sensitive = true
}

variable "github_token" {
  description = "Optional GitHub token used by the AI service."
  type        = string
  default     = ""
  sensitive   = true
}

variable "cloudinary_cloud_name" {
  type    = string
  default = ""
}

variable "cloudinary_api_key" {
  type      = string
  default   = ""
  sensitive = true
}

variable "cloudinary_api_secret" {
  type      = string
  default   = ""
  sensitive = true
}
