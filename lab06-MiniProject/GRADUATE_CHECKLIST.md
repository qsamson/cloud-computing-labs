# Lab 06 - Graduate Python Checklist

## Python Implementation

This lab was implemented in Python using boto3 and builds on the Python infrastructure package from Lab 05. The database is created and deleted with `create_database.py` and `delete_database.py`, while the application infrastructure is created and deleted with `create_weather_stack.py` and `delete_weather_stack.py`.

The Python implementation creates the private PostgreSQL RDS database, database security group, DB subnet group, SSM SecureString password, IAM roles and instance profiles, least-privilege policies, ALB security group, target groups, Application Load Balancer, listeners, launch templates, and Auto Scaling Groups.

The create operations are idempotent, and the delete operations tolerate resources that have already been removed. Configuration values are loaded from `.env` through the Python configuration module. Secrets are not stored in `.env`, source files, user-data, logs, or screenshots.

## Test Results

- Unit tests with Moto: **9 passed**
- Integration tests against real AWS: **7 passed**
- Chaos tests: **2 passed**
- `pytest -m "not integration and not chaos"`: **9 passed**

The unit tests verify the required RDS configuration, database security-group rule, cleanup behavior, least-privilege IAM policies, ALB-first ordering, user-data contents and size, and idempotent creation.

The integration tests verify healthy target groups, PostgreSQL cache miss and hit behavior, saved history, ZIP-code error handling, advisor responses, ALB-only application access, private database access, and IAM policy simulation.

The chaos tests verify that the weather service continues operating when PostgreSQL becomes unreachable and that the weather tier recovers after its EC2 instance is terminated.

## What Moto Could Not Prove

Moto was useful for testing the structure and behavior of the boto3 infrastructure code without creating real AWS resources. It proved that the database request used `db.t4g.micro`, 20 GB of storage, encryption, `BackupRetentionPeriod=0`, `MultiAZ=False`, and `PubliclyAccessible=False`. It also verified that the database security group allowed PostgreSQL port 5432 from the application security group rather than from a public CIDR range. Moto allowed the IAM policies, idempotent creation, cleanup behavior, launch-template data, and user-data size to be tested quickly.

However, Moto could not prove several behaviors that depend on real AWS infrastructure. It could not prove that an RDS endpoint was actually private and unreachable from my computer, that the Application Load Balancer could route traffic to healthy EC2 targets, or that an Auto Scaling Group could replace a terminated instance. It also could not prove the real network behavior of security groups, the actual IAM Policy Simulator results, or that the weather application could make a verified TLS connection to the real RDS PostgreSQL service.

The real AWS integration tests covered these gaps. The target-group test proved that both application tiers became healthy behind the ALB. The network tests proved that port 3000 on an application instance was not directly reachable and that the PostgreSQL endpoint could not be reached from my computer. The IAM simulator integration test proved that the weather role could read only the database password parameter and the advisor role could read only the Gemini key parameter. The weather, history, and cache tests proved that the application could communicate with the real PostgreSQL database. Finally, the chaos tests proved real failure and recovery behavior by removing database access and by terminating the weather EC2 instance and measuring its recovery.

## Python Compared with Bash

The Python version required more code than the equivalent Bash commands, especially for creating the database, checking whether resources already existed, handling AWS exceptions, and waiting for resources to become available. Bash was shorter for simple AWS CLI commands, but it was also easier to hide failures with patterns such as redirecting errors or using `|| true`. Python made error handling more explicit because individual `ClientError` codes could be checked and only expected conditions could be ignored. Python was also much easier to test because the resource-creation functions could be called directly from pytest and Moto. This made it possible to verify configuration values, least-privilege policies, idempotency, cleanup, and generated user-data before deploying anything to real AWS. For this lab, Bash was shorter, but Python provided stronger testing, clearer error handling, and more reusable infrastructure code.
