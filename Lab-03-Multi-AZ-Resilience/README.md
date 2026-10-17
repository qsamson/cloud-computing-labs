# Lab 03 — Multi-AZ Resilience

## Overview

In this lab, I changed the previous EC2 setup to use an Application Load Balancer and Auto Scaling Groups.

The uploader and viewer applications still use the same S3 file, but they are now reached through the load balancer. Each application has its own target group and Auto Scaling Group.

The main goal was to test how long the applications take to recover when an EC2 instance fails.

---

## 1. Application Stack Created

The `create_app_stack.sh` script created the load balancer, target groups, listeners, and Auto Scaling Groups.

The uploader used port `8080` and the viewer used port `8081`.

![Create App Stack](Sc1-lab3.png)

---

## 2. Applications Working Through the ALB

I uploaded a text file using the uploader application.

![Uploader Success](Sc2A-lab3.png)

The viewer application was able to read and display the same file.

![Viewer Content](Sc2B-lab3.png)

---

## 3. Target Group Health

Both the uploader and viewer target groups showed their EC2 instances as `healthy`.

![Healthy Target Groups](Sc3-lab3.png)

---

## 4. Recovery Test — PASS

I ran the chaos test on the uploader with a recovery SLO of **180 seconds**.

The running uploader instance was terminated through the Auto Scaling Group. The Auto Scaling Group then created a new instance automatically.

The application recovered in:

**82.2 seconds**

Since 82.2 seconds is less than the 180-second SLO, the test passed.

![Uploader PASS Test](Sc4-lab3.png)

CSV log:

[chaos_test_uploader_10761.csv](csv/chaos_test_uploader_10761.csv)

---

## 5. Recovery Test — FAIL

I ran the uploader test again, but this time I changed the SLO to **60 seconds**.

The application recovered in:

**82.6 seconds**

Since 82.6 seconds is more than the 60-second SLO, the test failed.

![Uploader FAIL Test](Sc5-lab3.png)

CSV log:

[chaos_test_uploader_11385.csv](csv/chaos_test_uploader_11385.csv)

---

## 6. Viewer Recovery Test

I also tested the viewer Auto Scaling Group.

The viewer recovered in:

**79.4 seconds**

The SLO was 180 seconds, so the test passed.

![Viewer PASS Test](Viewer-Test-Passed.png)

CSV log:

[chaos_test_viewer_12033.csv](csv/chaos_test_viewer_12033.csv)

---

## 7. What Affected the Recovery Time?

The uploader recovered in about **82 seconds**, while the viewer recovered in about **79 seconds**.

The main reason for the wait is that each Auto Scaling Group had only one running instance. When the instance was terminated, AWS had to start a new EC2 instance. The new instance had to finish its setup, start the application, join the target group, and pass the health checks before the load balancer could send traffic to it.

This is why the 180-second SLO passed, but the 60-second SLO failed. Using another running instance or making the startup process faster could reduce the recovery time.

---

## 8. Changes to the Create and Delete Scripts

In the previous lab, `run-instances` was used to start EC2 instances directly.

In this lab, `run-instances` was replaced by **Auto Scaling Groups**. The Auto Scaling Groups use the launch templates to create and manage the EC2 instances.

This allows AWS to automatically replace an instance when it fails.

The `create_app_stack.sh` script also creates the Application Load Balancer, target groups, listeners, security group rules, and Auto Scaling Groups.

The `delete_app_stack.sh` script removes the Auto Scaling Groups, load balancer, target groups, security group, IAM resources, and S3 resources.

---

## 9. Cleanup

After completing the tests, I ran `delete_app_stack.sh`.

Both Auto Scaling Groups were deleted and their EC2 instances were terminated. The load balancer, target groups, security group, IAM resources, and S3 bucket were also removed.

The final checks showed that no lab Auto Scaling Groups or running EC2 instances remained.

![Cleanup Complete](Sc6-lab3.png)

---

## CSV Recovery Logs

The recovery test CSV files are stored in the `csv` folder:

- [Uploader PASS — 82.2 seconds](csv/chaos_test_uploader_10761.csv)
- [Uploader FAIL — 82.6 seconds](csv/chaos_test_uploader_11385.csv)
- [Viewer PASS — 79.4 seconds](csv/chaos_test_viewer_12033.csv)
