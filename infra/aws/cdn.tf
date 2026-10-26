# Public entry point: CloudFront (always-free tier: 1 TB/month, 10M requests).
#   /*                                   -> S3 bucket with the built React app
#   /api/auth*, /api/projects*           -> EC2 :8001  auth-service
#   /api/v2*, /deepscan*, /files*, /toolkit* -> EC2 :8000  ai-service
# Gives a free HTTPS address: https://<id>.cloudfront.net

# ── Frontend files ──────────────────────────────────────────────────────────
# Trivy exceptions:
#   AWS-0089 access logging would need a second bucket; not needed for a static site
#   AWS-0090 versioning adds nothing: every deploy re-uploads the site from Git
#trivy:ignore:AWS-0089
#trivy:ignore:AWS-0090
resource "aws_s3_bucket" "frontend" {
  bucket_prefix = "docling-frontend-"
  force_destroy = true # lets `terraform destroy` remove it with its files
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# Trivy exception AWS-0132: a customer-managed KMS key costs $1/month, so the
# free S3-managed encryption (SSE-S3, AES-256) is used. The files are public
# website files anyway.
#trivy:ignore:AWS-0132
resource "aws_s3_bucket_server_side_encryption_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Only this CloudFront distribution may read the bucket (it stays private).
resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowCloudFrontRead"
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.frontend.arn}/*"
      Condition = { StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.app.arn } }
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.frontend]
}

resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "docling-frontend"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# Single-page app: a path like /dashboard is not a file; serve index.html and
# let React Router show the page. Runs only for the S3 (default) behaviour,
# so real API 404s are never rewritten.
resource "aws_cloudfront_function" "spa_routes" {
  name    = "docling-spa-routes"
  runtime = "cloudfront-js-2.0"
  publish = true
  code    = <<-EOT
    function handler(event) {
      var request = event.request;
      if (request.uri.indexOf('.') === -1) {
        request.uri = '/index.html';
      }
      return request;
    }
  EOT
}

locals {
  # AWS managed policies (fixed IDs, documented by AWS)
  caching_optimized = "658327ea-f89d-4fab-a63d-7e88639e58f6"
  caching_disabled  = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
  all_viewer        = "216adef6-5c7f-47e4-b989-5492eafa07d3" # forwards Authorization etc.
  security_headers  = "67f7725c-6f97-4210-82d7-5512b31e9d03"
  api_paths_auth    = ["/api/auth*", "/api/projects*"]
  api_paths_ai      = ["/api/v2*", "/deepscan*", "/files*", "/toolkit*"]
  server_origin_dns = aws_eip.server.public_dns
}

# Trivy exceptions:
#   AWS-0010 access logs would need another bucket; CloudFront's free metrics are used
#   AWS-0011 AWS WAF is a paid service ($5+/month); the APIs accept CloudFront traffic only
#trivy:ignore:AWS-0010
#trivy:ignore:AWS-0011
resource "aws_cloudfront_distribution" "app" {
  enabled             = true
  comment             = "Docling AI"
  default_root_object = "index.html"
  price_class         = "PriceClass_200" # includes edge locations in India
  http_version        = "http2and3"

  origin {
    origin_id                = "frontend"
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  origin {
    origin_id   = "auth-service"
    domain_name = local.server_origin_dns
    custom_origin_config {
      http_port                = 8001
      https_port               = 443
      origin_protocol_policy   = "http-only"
      origin_ssl_protocols     = ["TLSv1.2"]
      origin_read_timeout      = 60
      origin_keepalive_timeout = 5
    }
  }

  origin {
    origin_id   = "ai-service"
    domain_name = local.server_origin_dns
    custom_origin_config {
      http_port                = 8000
      https_port               = 443
      origin_protocol_policy   = "http-only"
      origin_ssl_protocols     = ["TLSv1.2"]
      origin_read_timeout      = 60 # deep-scan streams progress every 5 s
      origin_keepalive_timeout = 5
    }
  }

  # Website: cached at the edge.
  default_cache_behavior {
    target_origin_id           = "frontend"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD", "OPTIONS"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = local.caching_optimized
    response_headers_policy_id = local.security_headers

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.spa_routes.arn
    }
  }

  # APIs: never cached, every header (including Authorization) forwarded.
  dynamic "ordered_cache_behavior" {
    for_each = concat(
      [for p in local.api_paths_auth : { path = p, origin = "auth-service" }],
      [for p in local.api_paths_ai : { path = p, origin = "ai-service" }],
    )
    content {
      path_pattern               = ordered_cache_behavior.value.path
      target_origin_id           = ordered_cache_behavior.value.origin
      viewer_protocol_policy     = "redirect-to-https"
      allowed_methods            = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
      cached_methods             = ["GET", "HEAD"]
      compress                   = false # keeps streamed progress events unbuffered
      cache_policy_id            = local.caching_disabled
      origin_request_policy_id   = local.all_viewer
      response_headers_policy_id = local.security_headers
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}
