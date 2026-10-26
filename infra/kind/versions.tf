terraform {
  required_version = ">= 1.5.0"

  required_providers {
    # Creates the Kubernetes cluster (kind = "Kubernetes IN Docker").
    kind = {
      source  = "tehcyx/kind"
      version = "~> 0.13.0"
    }
    # Installs cluster add-ons from Helm charts (Traefik, metrics-server).
    helm = {
      source  = "hashicorp/helm"
      version = "~> 3.3"
    }
    # Creates plain Kubernetes objects (namespace, secret).
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 3.4"
    }
    # Generates passwords so nobody has to invent (or commit) them.
    random = {
      source  = "hashicorp/random"
      version = "~> 3.9"
    }
  }
}
