# Lab 03 – Two-Tier File Upload and Display with EC2, S3, and IAM Roles

This lab implements a two-tier application using two EC2 instances and Amazon S3. The uploader instance writes a text file to S3, while the viewer instance reads and displays the file using separate least-privilege IAM roles.

## Screenshot 1 – Local Application Structure

![Screenshot 1](screenshots/screenshot-01-folder-structure.png)

This screenshot shows the local `lab03` directory containing the uploader and viewer applications, with an `app.js` and `package.json` file for each application.

## Screenshot 2 – Successful File Upload

![Screenshot 2](screenshots/screenshot-02-upload-success.png)

This screenshot confirms that a valid `.txt` file was successfully uploaded through the uploader application.

## Screenshot 3 – File Size Validation

![Screenshot 3](screenshots/screenshot-03-large-file-rejected.png)

This screenshot shows the uploader rejecting a `.txt` file larger than the allowed 1 MB limit.

## Screenshot 4 – File Type Validation

![Screenshot 4](screenshots/screenshot-04-non-txt-rejected.png)

This screenshot demonstrates the server-side validation rejecting a non-`.txt` file.

## Screenshot 5 – Viewer Displays Uploaded File

![Screenshot 5](screenshots/screenshot-05-viewer-first-file.png)

This screenshot shows the viewer application successfully retrieving and displaying the uploaded text file from Amazon S3.

## Screenshot 6 – Viewer Displays Updated File

![Screenshot 6](screenshots/screenshot-06-viewer-updated-file.png)

This screenshot shows that after uploading a second text file and refreshing the viewer, the displayed content updates to the new file.

## Screenshot 7 – Launch Templates

![Screenshot 7](screenshots/screenshot-07-launch-templates.png)

This screenshot shows the uploader and viewer EC2 launch templates created for the two application tiers.

## Screenshot 8 – Launch Template Versions

![Screenshot 8](screenshots/screenshot-08-template-versions.png)

This screenshot shows multiple versions of the uploader launch template after the stack creation script was run again with updated application code.

## Screenshot 9 – IAM Role Policies

![Screenshot 9](screenshots/screenshot-09-iam-policies.png)

This screenshot shows the least-privilege IAM policies: the uploader can only write `shared.txt`, while the viewer can read the object and list the S3 bucket.

## Screenshot 10 – Application Stack Creation

![Screenshot 10](screenshots/screenshot-10-create-stack.png)

This screenshot shows `create_app_stack.sh` successfully launching both the uploader and viewer EC2 instances and displaying their public IP addresses.

## Screenshot 11 – Stack Cleanup

![Screenshot 11](screenshots/screenshot-11-cleanup.png)

This screenshot shows `delete_app_stack.sh` completing successfully after removing the EC2, IAM, launch template, and S3 resources.

## Extra Evidence – Updated Uploader

![Extra Evidence](screenshots/extra-uploader-version2.png)

This additional screenshot shows `Uploader Version 2`, confirming that the updated local application code was embedded into a new launch template version and deployed on a new EC2 instance.

## IAM Role Design

The uploader and viewer use separate IAM roles to follow the principle of least privilege. The uploader only needs permission to write `shared.txt` to S3, while the viewer only needs permission to read the file and list the bucket. Using separate roles prevents either instance from receiving permissions it does not need and reduces the impact if one instance is compromised.

## User-Data Code Deployment

Embedding the application code directly in EC2 user-data means that each instance already receives its application code when it launches. The instance does not need Git credentials, S3 credentials, or another code-download mechanism just to retrieve its own application, which simplifies the deployment process and avoids storing additional credentials on the instance.
