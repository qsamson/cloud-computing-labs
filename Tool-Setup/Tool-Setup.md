# Step 01 — AWS Account, IAM User, MFA, and Access Keys

## Root User MFA Enabled

![Root User MFA Enabled](screenshots/step01-pic1.png)

## IAM User Created

![IAM Users List](screenshots/step01-pic2.png)

## IAM User MFA Enabled

![IAM User MFA Enabled](screenshots/step01-pic3.png)

## Access Key Confirmation

Access key successfully created for the IAM lab user.

**Access Key:** `AKIA****…**** (last 4 chars: XXXX)`

## Security Reflection

Root user MFA is important because the root account has unrestricted access to all AWS resources, billing information, and security settings. Enabling MFA adds an extra layer of protection beyond the password and reduces the risk of unauthorized access. Using a least-privilege IAM user for everyday tasks is also important because it limits the permissions available to only those needed for the work being performed. This reduces the potential damage if the IAM user's credentials are compromised and helps protect the overall AWS environment.
