# Quick Recovery - Essential Commands

## 1. Add IAM Permissions (Choose One Method)

### Option A: AWS Console
Go to IAM → Users → powermgr-lambda-user → Add permissions → Attach these policies:
- AWSCloudFormationFullAccess
- IAMFullAccess
- AmazonS3FullAccess
- CloudWatchLogsFullAccess
- AWSLambda_FullAccess
- AmazonDynamoDBFullAccess
- AmazonSNSFullAccess
- AmazonEventBridgeFullAccess
- AmazonSSMFullAccess

### Option B: AWS CLI (Copy all at once)
```bash
aws iam attach-user-policy --user-name powermgr-lambda-user --policy-arn arn:aws:iam::aws:policy/AWSCloudFormationFullAccess
aws iam attach-user-policy --user-name powermgr-lambda-user --policy-arn arn:aws:iam::aws:policy/IAMFullAccess
aws iam attach-user-policy --user-name powermgr-lambda-user --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
aws iam attach-user-policy --user-name powermgr-lambda-user --policy-arn arn:aws:iam::aws:policy/CloudWatchLogsFullAccess
aws iam attach-user-policy --user-name powermgr-lambda-user --policy-arn arn:aws:iam::aws:policy/AWSLambda_FullAccess
aws iam attach-user-policy --user-name powermgr-lambda-user --policy-arn arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess
aws iam attach-user-policy --user-name powermgr-lambda-user --policy-arn arn:aws:iam::aws:policy/AmazonSNSFullAccess
aws iam attach-user-policy --user-name powermgr-lambda-user --policy-arn arn:aws:iam::aws:policy/AmazonEventBridgeFullAccess
aws iam attach-user-policy --user-name powermgr-lambda-user --policy-arn arn:aws:iam::aws:policy/AmazonSSMFullAccess
```

## 2. Clean Up Failed Stack

```bash
# Delete orphaned log groups
aws logs delete-log-group --log-group-name /aws/lambda/PowerMgr-DataCollector-prod --region us-west-2
aws logs delete-log-group --log-group-name /aws/lambda/PowerMgr-Analytics-prod --region us-west-2
aws logs delete-log-group --log-group-name /aws/lambda/PowerMgr-ThermostatController-prod --region us-west-2
aws logs delete-log-group --log-group-name /aws/lambda/PowerMgr-PeakManager-prod --region us-west-2
aws logs delete-log-group --log-group-name /aws/lambda/PowerMgr-PrecoolCheck-prod --region us-west-2
aws logs delete-log-group --log-group-name /aws/lambda/PowerMgr-EODStatus-prod --region us-west-2
aws logs delete-log-group --log-group-name /aws/lambda/PowerMgr-AuthRefresh-prod --region us-west-2
aws logs delete-log-group --log-group-name /aws/lambda/PowerMgr-WeeklyReport-prod --region us-west-2

# Delete failed stack
aws cloudformation delete-stack --stack-name powermgr-prod --region us-west-2

# Wait for deletion (takes 1-2 minutes)
aws cloudformation wait stack-delete-complete --stack-name powermgr-prod --region us-west-2
```

## 3. Rebuild and Deploy

```bash
cd /home/user/powermgr_v2/aws

# Build with container
sam build --use-container

# Deploy (will prompt for settings)
sam deploy --guided
```

**When prompted, use:**
- Stack Name: `powermgr-prod`
- AWS Region: `us-west-2`
- Parameter Environment: `prod`
- Allow IAM role creation: `Y`
- Save to config file: `Y`

## 4. Enable Dry-Run Mode

```bash
aws ssm put-parameter \
  --name /powermgr/config/dry_run \
  --value "true" \
  --type String \
  --region us-west-2
```

## 5. Test Functions

```bash
cd /home/user/powermgr_v2/aws

make invoke-collector && make logs-collector
make invoke-thermostat && make logs-thermostat
make invoke-peak && make logs-peak
```

Look for `[DRY-RUN]` messages in logs.

---

**See DEPLOYMENT_RECOVERY.md for complete guide**
