output "app_url" {
  description = "The application, through the Ingress."
  value       = "http://localhost:${var.http_port}"
}

output "cluster_name" {
  value = kind_cluster.this.name
}

output "kubeconfig_path" {
  description = "Kubeconfig for this cluster (or run: kind export kubeconfig --name <cluster_name>)."
  value       = kind_cluster.this.kubeconfig_path
}

output "next_steps" {
  value = <<-EOT
    kind export kubeconfig --name ${kind_cluster.this.name}
    docker build -t docling/frontend:local frontend
    docker build -t docling/auth-service:local backend
    docker build -t docling/ai-service:local backend_ai
    kind load docker-image docling/frontend:local docling/auth-service:local docling/ai-service:local --name ${kind_cluster.this.name}
    kubectl apply -k k8s
  EOT
}
