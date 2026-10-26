# Application secrets in SSM Parameter Store, encrypted (SecureString, AWS
# managed key: free). The server reads them at deploy time; they never appear
# in Git, in a container image, or in the pipeline logs.

resource "random_password" "jwt" {
  length  = 48
  special = false
}

locals {
  secrets_all = {
    JWT_SECRET_KEY        = random_password.jwt.result
    MONGO_URI             = var.mongo_uri
    GROQ_API_KEY          = var.groq_api_key
    OPENAI_API_KEY        = var.openai_api_key
    GITHUB_TOKEN          = var.github_token
    CLOUDINARY_CLOUD_NAME = var.cloudinary_cloud_name
    CLOUDINARY_API_KEY    = var.cloudinary_api_key
    CLOUDINARY_API_SECRET = var.cloudinary_api_secret
  }
  # Parameter Store does not accept empty values: skip the unset optional ones.
  secrets = { for k, v in local.secrets_all : k => v if v != "" }
}

resource "aws_ssm_parameter" "secret" {
  for_each = nonsensitive(toset(keys(local.secrets)))
  name     = "/docling/${each.key}"
  type     = "SecureString"
  value    = local.secrets[each.key]
  tier     = "Standard" # free
}
