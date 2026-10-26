# =============================================================================
# Infrastructure as Code for Docling AI
#
#   terraform init
#   terraform apply
#
# creates, from nothing:
#   1. a Kubernetes cluster (kind, running in Docker Desktop)
#   2. Traefik, the Ingress controller: the single entry point on :8080
#   3. metrics-server, so the HorizontalPodAutoscalers can see CPU usage
#   4. the "docling" namespace and the Secret holding every credential
#
# The application itself is then deployed with `kubectl apply -k k8s`.
# `terraform destroy` removes all of it again.
# =============================================================================

# ── 1. Cluster ───────────────────────────────────────────────────────────────
resource "kind_cluster" "this" {
  name           = var.cluster_name
  wait_for_ready = true
  # Written next to this file instead of into ~/.kube/config.
  # Use `kind export kubeconfig --name docling` to point kubectl at it.
  kubeconfig_path = "${path.module}/${var.cluster_name}.kubeconfig"

  kind_config {
    kind        = "Cluster"
    api_version = "kind.x-k8s.io/v1alpha4"

    node {
      role = "control-plane"

      # Traffic to localhost:<http_port> on this machine reaches port 30080
      # inside the cluster, where Traefik listens.
      extra_port_mappings {
        container_port = 30080
        host_port      = var.http_port
        listen_address = "127.0.0.1"
        protocol       = "TCP"
      }
    }
  }
}

locals {
  cluster_auth = {
    host                   = kind_cluster.this.endpoint
    client_certificate     = kind_cluster.this.client_certificate
    client_key             = kind_cluster.this.client_key
    cluster_ca_certificate = kind_cluster.this.cluster_ca_certificate
  }
}

provider "helm" {
  kubernetes = local.cluster_auth
}

provider "kubernetes" {
  host                   = local.cluster_auth.host
  client_certificate     = local.cluster_auth.client_certificate
  client_key             = local.cluster_auth.client_key
  cluster_ca_certificate = local.cluster_auth.cluster_ca_certificate
}

# ── 2. Ingress controller ────────────────────────────────────────────────────
resource "helm_release" "traefik" {
  name             = "traefik"
  repository       = "https://traefik.github.io/charts"
  chart            = "traefik"
  version          = "42.1.3"
  namespace        = "traefik"
  create_namespace = true
  wait             = true
  timeout          = 600

  values = [yamlencode({
    service = { spec = { type = "NodePort" } }
    ports = {
      web       = { nodePort = 30080 } # matches the kind port mapping
      websecure = { expose = { default = false } }
    }
    ingressClass = { enabled = true, isDefaultClass = true }
    resources = {
      requests = { cpu = "50m", memory = "64Mi" }
      limits   = { cpu = "500m", memory = "256Mi" }
    }
  })]
}

# ── 3. Metrics for autoscaling ───────────────────────────────────────────────
resource "helm_release" "metrics_server" {
  name       = "metrics-server"
  repository = "https://kubernetes-sigs.github.io/metrics-server/"
  chart      = "metrics-server"
  version    = "3.14.0"
  namespace  = "kube-system"
  wait       = true
  timeout    = 600

  values = [yamlencode({
    # kind's kubelets use self-signed certificates.
    args = ["--kubelet-insecure-tls"]
  })]
}

# ── 4. Namespace and secrets ─────────────────────────────────────────────────
resource "kubernetes_namespace_v1" "docling" {
  metadata {
    name = var.namespace
  }
}

resource "random_password" "mongo_root" {
  length  = 24
  special = false
}

resource "random_password" "jwt" {
  length  = 48
  special = false
}

locals {
  in_cluster_mongo_uri = "mongodb://root:${random_password.mongo_root.result}@mongo:27017/hackamined?authSource=admin"
}

resource "kubernetes_secret_v1" "docling" {
  metadata {
    name      = "docling-secrets"
    namespace = kubernetes_namespace_v1.docling.metadata[0].name
  }

  data = {
    JWT_SECRET_KEY        = var.jwt_secret != "" ? var.jwt_secret : random_password.jwt.result
    MONGO_ROOT_USERNAME   = "root"
    MONGO_ROOT_PASSWORD   = random_password.mongo_root.result
    MONGO_URI             = var.mongo_uri != "" ? var.mongo_uri : local.in_cluster_mongo_uri
    GROQ_API_KEY          = var.groq_api_key
    OPENAI_API_KEY        = var.openai_api_key
    GITHUB_TOKEN          = var.github_token
    CLOUDINARY_CLOUD_NAME = var.cloudinary_cloud_name
    CLOUDINARY_API_KEY    = var.cloudinary_api_key
    CLOUDINARY_API_SECRET = var.cloudinary_api_secret
  }
}
