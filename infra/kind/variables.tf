variable "cluster_name" {
  description = "Name of the kind cluster."
  type        = string
  default     = "docling"
}

variable "http_port" {
  description = "Port on this machine where the app is served (via the Ingress)."
  type        = number
  default     = 8080
}

variable "namespace" {
  description = "Kubernetes namespace for the application."
  type        = string
  default     = "docling"
}

# ── Application secrets ────────────────────────────────────────────────────
# Put real values in terraform.tfvars (gitignored), or pass them as
# TF_VAR_<name> environment variables (that is what CI does).

variable "groq_api_key" {
  description = "Groq API key used by the AI features. Empty = AI features return errors, everything else works."
  type        = string
  default     = ""
  sensitive   = true
}

variable "openai_api_key" {
  description = "Optional OpenAI key."
  type        = string
  default     = ""
  sensitive   = true
}

variable "github_token" {
  description = "Optional GitHub token used by the AI service."
  type        = string
  default     = ""
  sensitive   = true
}

variable "cloudinary_cloud_name" {
  description = "Optional Cloudinary account (profile pictures)."
  type        = string
  default     = ""
}

variable "cloudinary_api_key" {
  description = "Optional Cloudinary API key."
  type        = string
  default     = ""
  sensitive   = true
}

variable "cloudinary_api_secret" {
  description = "Optional Cloudinary API secret."
  type        = string
  default     = ""
  sensitive   = true
}

variable "jwt_secret" {
  description = "Key that signs login tokens. Empty = generate a random one."
  type        = string
  default     = ""
  sensitive   = true
}

variable "mongo_uri" {
  description = "Use an external MongoDB (e.g. Atlas). Empty = use the MongoDB inside the cluster."
  type        = string
  default     = ""
  sensitive   = true
}
