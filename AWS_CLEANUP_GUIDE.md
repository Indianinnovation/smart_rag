# AWS Cleanup Guide - Stay Under $5

## Step 1: Install Dependencies
```bash
pip install boto3
```

## Step 2: Configure AWS Credentials
```bash
aws configure
```
Enter your AWS Access Key ID and Secret Access Key

## Step 3: Run the Audit Tool
```bash
python aws_cleanup_tool.py
```

This will:
- Show your current month's cost
- Backup metadata of all resources
- Create a backup folder with JSON files
- Generate a cleanup script

## Step 4: Review the Backup
Check the generated backup folder (aws_backup_YYYYMMDD_HHMMSS/) for:
- s3_buckets.json - List of all S3 buckets and objects
- ec2_instances.json - EC2 instances
- rds_databases.json - RDS databases
- lambda_functions.json - Lambda functions
- dynamodb_tables.json - DynamoDB tables

## Step 5: Download Important Data from S3
```bash
# Download entire bucket
aws s3 sync s3://your-bucket-name ./local-backup/

# Or download specific files
aws s3 cp s3://your-bucket-name/important-file.txt ./
```

## Step 6: Delete Resources (Manual - Safest)

### Delete EC2 Instances
```bash
# Stop instance first
aws ec2 stop-instances --instance-ids i-xxxxx

# Then terminate
aws ec2 terminate-instances --instance-ids i-xxxxx
```

### Delete S3 Buckets
```bash
# Empty bucket first
aws s3 rm s3://bucket-name --recursive

# Then delete bucket
aws s3 rb s3://bucket-name
```

### Delete RDS Databases
```bash
aws rds delete-db-instance \
  --db-instance-identifier mydb \
  --skip-final-snapshot
```

### Delete Lambda Functions
```bash
aws lambda delete-function --function-name my-function
```

### Delete DynamoDB Tables
```bash
aws dynamodb delete-table --table-name my-table
```

## Step 7: Check for Hidden Costs

### EBS Volumes (often forgotten!)
```bash
# List volumes
aws ec2 describe-volumes --query 'Volumes[?State==`available`]'

# Delete unattached volumes
aws ec2 delete-volume --volume-id vol-xxxxx
```

### Elastic IPs (charged if not attached)
```bash
# List
aws ec2 describe-addresses

# Release
aws ec2 release-address --allocation-id eipalloc-xxxxx
```

### Snapshots
```bash
# List
aws ec2 describe-snapshots --owner-ids self

# Delete
aws ec2 delete-snapshot --snapshot-id snap-xxxxx
```

### Load Balancers
```bash
# List
aws elbv2 describe-load-balancers

# Delete
aws elbv2 delete-load-balancer --load-balancer-arn <arn>
```

### NAT Gateways (expensive!)
```bash
# List
aws ec2 describe-nat-gateways

# Delete
aws ec2 delete-nat-gateway --nat-gateway-id nat-xxxxx
```

## Step 8: Set Up Billing Alerts

1. Go to AWS Billing Console
2. Set up a budget alert for $5
3. Enable email notifications

Or use CLI:
```bash
aws budgets create-budget \
  --account-id <your-account-id> \
  --budget file://budget.json
```

## Step 9: Verify Cleanup
Wait 24 hours, then check:
```bash
python aws_cleanup_tool.py
```

Should show minimal resources and cost trending toward $0

## Step 10: Consider Closing Account
If you're done with AWS completely:
1. Go to AWS Console > Account Settings
2. Click "Close Account"
3. Follow the prompts

## Cost-Saving Tips
- Delete unused EBS volumes and snapshots
- Release unattached Elastic IPs
- Delete old CloudWatch logs
- Remove unused IAM users/roles
- Check all regions (resources in different regions cost money!)

## Emergency: Check All Regions
```bash
# List all regions
aws ec2 describe-regions --query 'Regions[].RegionName' --output text

# Check each region for EC2
for region in $(aws ec2 describe-regions --query 'Regions[].RegionName' --output text); do
  echo "Checking $region..."
  aws ec2 describe-instances --region $region
done
```

## Support
If you see unexpected charges:
1. Check AWS Cost Explorer
2. Contact AWS Support
3. Request a detailed billing report
