terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
  # State is kept locally (in CloudShell's home folder). For a team, move it to an
  # S3 backend with locking; see docs/aws-deployment.md.
}

provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project   = "blinkhub-procurement-intelligence"
      Purpose   = "candidate-prototype-demo"
      ManagedBy = "terraform"
    }
  }
}
