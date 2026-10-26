output "app_url" {
  description = "The public link."
  value       = "https://${aws_cloudfront_distribution.app.domain_name}"
}

output "server_public_ip" {
  description = "Add this IP to MongoDB Atlas -> Network Access."
  value       = aws_eip.server.public_ip
}

output "github_variables" {
  description = "Set these as GitHub repository variables (Settings -> Secrets and variables -> Actions -> Variables)."
  value = {
    AWS_REGION                 = var.region
    AWS_ROLE_ARN               = aws_iam_role.github_deploy.arn
    EC2_INSTANCE_ID            = aws_instance.server.id
    FRONTEND_BUCKET            = aws_s3_bucket.frontend.bucket
    CLOUDFRONT_DISTRIBUTION_ID = aws_cloudfront_distribution.app.id
    APP_URL                    = "https://${aws_cloudfront_distribution.app.domain_name}"
  }
}

output "server_shell" {
  description = "Open a shell on the server (no SSH needed)."
  value       = "aws ssm start-session --target ${aws_instance.server.id} --region ${var.region}"
}
