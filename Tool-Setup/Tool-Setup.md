# Step 01 — AWS Account, IAM User, MFA, and Access Keys

## Root User MFA Enabled

![Root User MFA Enabled](step01-pic1.png)

## IAM User Created

![IAM Users List](step01-pic2.png)

## IAM User MFA Enabled

![IAM User MFA Enabled](step01-pic3.png)

## Access Key Confirmation

Access key successfully created for the IAM lab user.

**Access Key:(AKIAW24GPJVZJ3R5XXXX)

## Security Reflection

Root user MFA is important because the root account has unrestricted access to all AWS resources, billing information, and security settings. Enabling MFA adds an extra layer of protection beyond the password and reduces the risk of unauthorized access. Using a least-privilege IAM user for everyday tasks is also important because it limits the permissions available to only those needed for the work being performed. This reduces the potential damage if the IAM user's credentials are compromised and helps protect the overall AWS environment.

---

# Step 02 — Docker and Ubuntu Linux Container Setup

## Docker Version

![Docker Version](step02-pic1.png)

## Hello World Container

![Hello World Container](step02-pic2.png)

## Ubuntu Container Verification

![Ubuntu OS Release](step02-pic3.png)

## Docker Containers Before Removing `my-ubuntu`

![Docker Containers Before Removal](step02-pic4.png)

## Docker Containers After Removing `my-ubuntu`

![Docker Containers After Removal](step02-pic5.png)

## Docker Image vs. Docker Container

A Docker image is like a blueprint or template that contains the files and software needed to create a container. The image itself does not run; it is used to create containers. A Docker container is an actual running or stopped instance created from that image. Containers are lightweight and isolated from the main operating system, which makes them useful for running applications consistently on different computers.
