#!/bin/bash
set -e

# Load environment variables
export $(grep -v '^#' .env | xargs)

echo "Launching $INSTANCE_COUNT instance(s) in $AWS_REGION..."

OUTPUT=$(aws ec2 run-instances \
--image-id "$AMI_ID" \
--instance-type "$INSTANCE_TYPE" \
--key-name "$KEY_NAME" \
--security-group-ids "$SECURITY_GROUP_ID" \
--count "$INSTANCE_COUNT" \
--tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME_TAG}]" \
--region "$AWS_REGION" \
--query "Instances[*].InstanceId" \
--output text)

echo "Launched instance IDs:"
echo "$OUTPUT"

echo "$OUTPUT" | tr '\t' '\n' > instance_ids.txt

echo "Instance IDs saved to instance_ids.txt"
