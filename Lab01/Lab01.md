# Lab 01 — Cloud Development Environment Setup

**Course:** Cloud Computing Technologies  
**Course Code:** ITMO-444 | ITMO-544  
**Semester:** Fall 2026  

---

# Step 01 — AWS Account, IAM User, MFA, and Access Keys

## Overview

In Step 01, I created and secured my AWS environment for use throughout the course. I secured the AWS root account with multi-factor authentication (MFA), created an IAM user for regular lab activities, enabled MFA for the IAM user, configured the required permissions, and generated an access key for programmatic access.

---

## 1. Root User MFA Enabled

The following screenshot confirms that MFA is enabled on the AWS root user.

![Root User MFA Enabled](screenshots/Step01-pic1.png)

---

## 2. IAM User Created

The following screenshot shows the IAM Users list and confirms that the lab IAM user was successfully created.

![IAM Users List](screenshots/Step01-pic2.png)

---

## 3. IAM User MFA Enabled

The following screenshot confirms that MFA is enabled for the IAM lab user.

![IAM User MFA Enabled](screenshots/Step01-pic3.png)

---

## 4. Access Key Confirmation

Access key successfully created for the IAM lab user.

**Access Key ID:** `AKIAW24GPJVZJ3R5XXXX`

> The Secret Access Key is intentionally not included for security reasons.

---

## 5. Security Reflection

Root user MFA is important because the root account has unrestricted access to all AWS resources, billing information, and security settings. Enabling MFA adds an extra layer of protection beyond the password and reduces the risk of unauthorized access. Using a least-privilege IAM user for everyday tasks is also important because it limits the permissions available to only those needed for the work being performed. This reduces the potential damage if the IAM user's credentials are compromised and helps protect the overall AWS environment.

---

## Step 01 Completion

Step 01 was successfully completed. The AWS root account and IAM user were secured with MFA, and an IAM access key was created for use with the AWS CLI in later steps.
