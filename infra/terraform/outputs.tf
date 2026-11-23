output "url" {
  description = "Open this once the server has finished building (about 10 minutes)"
  value       = "https://${local.domain}"
}

output "api_docs" {
  value = "https://${local.domain}/docs"
}

output "instance_id" {
  value = aws_instance.web.id
}

output "documents_bucket" {
  value = aws_s3_bucket.documents.bucket
}

output "connect" {
  description = "Open a shell on the server without SSH"
  value       = "EC2 console -> Instances -> ${aws_instance.web.id} -> Connect -> Session Manager"
}

output "github_deploy_role_arn" {
  description = "Set as the AWS_DEPLOY_ROLE_ARN repository variable to enable the Deploy workflow"
  value       = var.github_repo == "" ? null : aws_iam_role.github_deploy[0].arn
}
