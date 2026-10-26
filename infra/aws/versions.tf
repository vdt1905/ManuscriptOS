terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.70"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.9"
    }
  }
}

provider "aws" {
  region = var.region

  # Every resource is tagged, so the AWS console's Tag Editor / Cost Explorer
  # can show exactly what this project created.
  default_tags {
    tags = {
      Project   = "docling"
      ManagedBy = "terraform"
    }
  }
}
