# Lab 07: Infrastructure as Code with Terraform

## Overview

This lab rebuilds the two-tier Weather Advisor application using Terraform instead of imperative infrastructure scripts.

The infrastructure includes an Application Load Balancer, Weather and Advisor Auto Scaling Groups, EC2 launch templates, DynamoDB, IAM roles, security groups, AWS Systems Manager Parameter Store, and automated instance refresh behavior.

The Weather service retrieves forecast information and stores recent results in DynamoDB. The Advisor service calls the Weather service and attempts to use Gemini to generate clothing recommendations. If Gemini is unavailable, the application uses a rule-based fallback so the service continues working.

## Project Structure

```text
lab07-Terraform/
├── advisor-app/
│   ├── app.js
│   └── package.json
├── weather-app/
│   ├── app.js
│   └── package.json
├── testing/
│   └── app_smoke_test.py
├── submission-evidence/
├── alb.tf
├── compute.tf
├── iam.tf
├── locals.tf
├── network.tf
├── outputs.tf
├── storage.tf
├── variables.tf
├── versions.tf
├── user-data.sh.tftpl
├── terraform.tfvars.example
├── .terraform.lock.hcl
└── .gitignore
```

## Terraform Workflow

The configuration was validated using:

```bash
terraform init
terraform fmt
terraform validate
terraform plan
terraform apply
```

The initial deployment created 24 AWS resources.

```text
Plan: 24 to add, 0 to change, 0 to destroy.
```

A later Terraform plan with no configuration changes reported:

```text
No changes. Your infrastructure matches the configuration.
```

This demonstrates Terraform's idempotent behavior.

## Imperative vs. Declarative Infrastructure

My Lab06 Python infrastructure contained 3,081 total infrastructure lines and 2,501 nonblank and noncomment code lines.

Lab07 contained 418 Terraform and template lines and 349 nonblank and noncomment code lines.

Lab06 also contained 100 lines of delete scripts. Terraform required no separate deletion script because the infrastructure could be removed using:

```bash
terraform destroy
```

Terraform also reduced the need for manual resource ordering, existence checks, retry logic, and separate cleanup scripts.

## Terraform Dependency Graph

The dependency graph included:

```text
aws_launch_template.tier -> aws_lb.main
```

The Advisor launch template depends on the load balancer because the Advisor uses the load balancer DNS name in its Weather service URL.

Terraform determines this dependency automatically from references in the configuration.

## Rolling Instance Refresh

The Weather cache duration was changed from 600 seconds to 60 seconds.

Terraform reported:

```text
Plan: 0 to add, 2 to change, 0 to destroy.
```

The Weather launch template and Auto Scaling Group were updated.

The Auto Scaling instance refresh completed successfully:

```text
Successful    100
```

The updated launch template contained:

```text
Environment="CACHE_SECONDS=60"
```

## Drift Detection

The Weather target group health check was manually changed from:

```text
/
```

to:

```text
/nope
```

Terraform detected the drift and proposed restoring the configured value:

```text
/nope -> /
Plan: 0 to add, 1 to change, 0 to destroy.
```

The Advisor listener was also manually deleted.

Terraform detected that the declared listener was missing:

```text
Plan: 1 to add, 0 to change, 0 to destroy.
```

Applying the plan recreated only the missing listener.

This demonstrates a major difference between Terraform and simple imperative existence checks. Terraform compares the actual resource configuration with the desired configuration instead of only checking whether a resource exists.

## Least Privilege IAM Testing

The AWS IAM policy simulator produced the following results:

| Role | Action | Result |
|---|---|---|
| Weather role | `dynamodb:PutItem` | allowed |
| Weather role | `ssm:GetParameter` | implicitDeny |
| Advisor role | `ssm:GetParameter` | allowed |
| Advisor role | `dynamodb:GetItem` | implicitDeny |

The Weather tier can access the DynamoDB table but cannot retrieve the Gemini parameter.

The Advisor tier can retrieve the Gemini parameter but cannot directly access the Weather DynamoDB table.

This limits the permissions available to each application tier.

## Secret Handling

The Gemini API key is stored in AWS Systems Manager Parameter Store as a `SecureString`.

The Terraform SSM configuration was updated to use a write-only value and a sensitive ephemeral variable so the real key is not stored in Terraform state.

Verification showed:

```text
grep -c 'AQ\.' terraform.tfstate
0
```

A later Terraform plan also returned:

```text
No changes.
```

Terraform state files, variable files, private keys, and API keys are excluded from this repository.

## Application Smoke Test

The smoke test checked the following functionality:

Weather forecast retrieval  
DynamoDB cache hits  
Weather lookup history  
Invalid ZIP validation  
Unknown ZIP handling  
Advisor recommendations  
Gemini recommendation source  
Advisor ZIP validation  
Advisor home page

The final result was:

```text
8 of 9 checks passed
```

All application and AWS infrastructure checks passed except the requirement that the recommendation come directly from Gemini.

The Advisor returned:

```text
source=fallback
```

A direct Gemini API request from the lab environment returned HTTP 400 with a generic HTML response. The application therefore demonstrated graceful degradation by continuing to provide a useful clothing recommendation instead of failing.

## Graceful Degradation

When Gemini is unavailable, the Advisor returns a rule-based recommendation and labels the source as `fallback`.

This keeps the application available when an external dependency fails.

A disadvantage of silent fallback is that users may not realize that the AI service has failed unless application logs or monitoring are reviewed.

## EC2 Advisor vs. AWS Lambda

The EC2 implementation requires a launch template, Auto Scaling Group, instance refresh configuration, EC2 instance profile, operating system initialization, Node.js installation, systemd service configuration, security group access, and health checks.

If the Advisor were converted to Lambda, many of these EC2-specific resources would disappear.

The Lambda version would instead require an `aws_lambda_function`, a Lambda execution role, an `aws_lambda_permission` allowing the Application Load Balancer to invoke the function, and application code capable of handling Lambda and ALB events.

Terraform and Lambda remove different kinds of work.

Terraform manages infrastructure creation, dependency ordering, updates, drift detection, and destruction.

Lambda removes much of the server and operating system management required by EC2.

Lambda would also introduce concerns such as cold starts, execution limits, deployment packaging, and different application testing requirements.

## Terraform and Lambda

Terraform and Lambda both allow a platform to handle repetitive work around something provided by the developer.

The important difference is that Terraform is an infrastructure deployment tool. It calls cloud APIs, records infrastructure state, and exits.

AWS Lambda is a runtime service that executes application code when an event occurs.

## What Terraform Did Not Make Easier

Terraform introduced new concepts including HCL, state management, provider versions, dependency graphs, plan interpretation, and protection of sensitive state.

Secret handling and provider behavior also required additional debugging.

## Destroy

At the end of the lab, the infrastructure was removed using Terraform.

```text
Destroy complete! Resources: 24 destroyed.
```

This replaced the separate ordered deletion scripts required by the previous imperative implementation.

## Security

The following files are intentionally excluded from GitHub:

```text
terraform.tfstate
terraform.tfstate.*
terraform.tfvars
tfplan
.terraform/
*.pem
.env
API keys
```

Only `terraform.tfvars.example` is committed so the expected configuration format can be reproduced without exposing credentials.

## Conclusion

This lab demonstrated how Terraform can declaratively manage a multi-tier AWS application.

The major advantages observed were automatic dependency management, idempotence, drift detection, predictable change plans, controlled rolling updates, least-privilege IAM configuration, and complete infrastructure cleanup using a single Terraform command.
