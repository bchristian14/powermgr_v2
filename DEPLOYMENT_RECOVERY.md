# Deployment Recovery Guide

Your deployment failed due to IAM permission issues and the stack is now in `ROLLBACK_FAILED` state. This guide will help you recover and successfully deploy.

## Current Situation

**Stack Status:** ROLLBACK_FAILED
**User:** powermgr-lambda-user
**Account:** 260758034704
**Region:** us-west-2

**Problem:** Missing IAM permissions prevented CloudFormation from creating resources and then from cleaning up after failure.

## Recovery Steps

### Step 1: Add IAM Permissions

You need to add permissions to the `powermgr-lambda-user` IAM user. Choose one of these options:

#### Option A: AWS Console (Easiest)

1. Go to AWS Console → IAM → Users → powermgr-lambda-user
2. Click "Add permissions" → "Attach policies directly"
3. Search for and attach these managed policies:
   - `AWSCloudFormationFullAccess`
   - `IAMFullAccess`
   - `AmazonS3FullAccess`
   - `CloudWatchLogsFullAccess`
   - `AWSLambda_FullAccess`
   - `AmazonDynamoDBFullAccess`
   - `AmazonSNSFullAccess`
   - `AmazonEventBridgeFullAccess`
   - `AmazonSSMFullAccess`

4. Click "Add permissions"

#### Option B: AWS CLI (If you have admin access)

Run these commands from your local machine (not this environment):

```bash
# Attach CloudFormation permissions
aws iam attach-user-policy \
  --user-name powermgr-lambda-user \
  --policy-arn arn:aws:iam::aws:policy/AWSCloudFormationFullAccess

# Attach IAM permissions (needed to create Lambda execution roles)
aws iam attach-user-policy \
  --user-name powermgr-lambda-user \
  --policy-arn arn:aws:iam::aws:policy/IAMFullAccess

# Attach S3 permissions (SAM needs this for deployment artifacts)
aws iam attach-user-policy \
  --user-name powermgr-lambda-user \
  --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess

# Attach CloudWatch Logs permissions
aws iam attach-user-policy \
  --user-name powermgr-lambda-user \
  --policy-arn arn:aws:iam::aws:policy/CloudWatchLogsFullAccess

# Attach Lambda permissions
aws iam attach-user-policy \
  --user-name powermgr-lambda-user \
  --policy-arn arn:aws:iam::aws:policy/AWSLambda_FullAccess

# Attach DynamoDB permissions
aws iam attach-user-policy \
  --user-name powermgr-lambda-user \
  --policy-arn arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess

# Attach SNS permissions
aws iam attach-user-policy \
  --user-name powermgr-lambda-user \
  --policy-arn arn:aws:iam::aws:policy/AmazonSNSFullAccess

# Attach EventBridge permissions
aws iam attach-user-policy \
  --user-name powermgr-lambda-user \
  --policy-arn arn:aws:iam::aws:policy/AmazonEventBridgeFullAccess

# Attach Systems Manager permissions
aws iam attach-user-policy \
  --user-name powermgr-lambda-user \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMFullAccess
```

#### Option C: Request Admin Help

If you don't have admin access, send this to your AWS administrator:

```
Subject: IAM Permissions Request for Power Management Deployment

I need the following AWS managed policies attached to the 'powermgr-lambda-user' IAM user:
- AWSCloudFormationFullAccess
- IAMFullAccess
- AmazonS3FullAccess
- CloudWatchLogsFullAccess
- AWSLambda_FullAccess
- AmazonDynamoDBFullAccess
- AmazonSNSFullAccess
- AmazonEventBridgeFullAccess
- AmazonSSMFullAccess

These are needed to deploy a serverless power management application using AWS SAM.
```

### Step 2: Verify Permissions

Run this command to verify permissions were added:

```bash
aws iam list-attached-user-policies --user-name powermgr-lambda-user
```

You should see the policies listed.

### Step 3: Clean Up Failed Stack

Now that you have permissions, clean up the failed deployment:

```bash
# First, check stack status
aws cloudformation describe-stacks --stack-name powermgr-prod --region us-west-2

# Delete orphaned log groups (these failed to delete during rollback)
aws logs delete-log-group --log-group-name /aws/lambda/PowerMgr-DataCollector-prod --region us-west-2
aws logs delete-log-group --log-group-name /aws/lambda/PowerMgr-Analytics-prod --region us-west-2
aws logs delete-log-group --log-group-name /aws/lambda/PowerMgr-ThermostatController-prod --region us-west-2
aws logs delete-log-group --log-group-name /aws/lambda/PowerMgr-PeakManager-prod --region us-west-2
aws logs delete-log-group --log-group-name /aws/lambda/PowerMgr-PrecoolCheck-prod --region us-west-2
aws logs delete-log-group --log-group-name /aws/lambda/PowerMgr-EODStatus-prod --region us-west-2
aws logs delete-log-group --log-group-name /aws/lambda/PowerMgr-AuthRefresh-prod --region us-west-2
aws logs delete-log-group --log-group-name /aws/lambda/PowerMgr-WeeklyReport-prod --region us-west-2

# Delete the failed CloudFormation stack
aws cloudformation delete-stack --stack-name powermgr-prod --region us-west-2

# Wait for deletion to complete (takes 1-2 minutes)
aws cloudformation wait stack-delete-complete --stack-name powermgr-prod --region us-west-2

# Verify stack is gone (should show error "Stack with id powermgr-prod does not exist")
aws cloudformation describe-stacks --stack-name powermgr-prod --region us-west-2
```

### Step 4: Retry Deployment

Navigate to the aws directory and deploy:

```bash
cd /home/user/powermgr_v2/aws

# Build the application (use container to ensure correct Python version)
sam build --use-container

# Deploy with guided configuration
sam deploy --guided
```

**During `sam deploy --guided`, use these settings:**

```
Stack Name: powermgr-prod
AWS Region: us-west-2
Parameter Environment: prod
Confirm changes before deploy: Y
Allow SAM CLI IAM role creation: Y
Disable rollback: N
Save arguments to configuration file: Y
SAM configuration file: samconfig.toml
SAM configuration environment: default
```

### Step 5: Post-Deployment Configuration

Once deployment succeeds, you need to configure the system:

```bash
# Navigate to aws directory
cd /home/user/powermgr_v2/aws

# Set up initial parameters with default values
make setup-params

# Enable dry-run mode for safe testing
aws ssm put-parameter \
  --name /powermgr/config/dry_run \
  --value "true" \
  --type String \
  --region us-west-2

# Subscribe to email notifications
aws sns subscribe \
  --topic-arn $(aws cloudformation describe-stacks \
    --stack-name powermgr-prod \
    --query 'Stacks[0].Outputs[?OutputKey==`NotificationTopicArn`].OutputValue' \
    --output text \
    --region us-west-2) \
  --protocol email \
  --notification-endpoint YOUR_EMAIL@example.com \
  --region us-west-2

# Confirm email subscription (check your email and click confirmation link)
```

### Step 6: Add Credentials

You'll need to add your API credentials as secure parameters:

```bash
# Add Honeywell credentials
aws ssm put-parameter \
  --name /powermgr/honeywell/consumer_key \
  --value "YOUR_HONEYWELL_CONSUMER_KEY" \
  --type SecureString \
  --region us-west-2

aws ssm put-parameter \
  --name /powermgr/honeywell/consumer_secret \
  --value "YOUR_HONEYWELL_CONSUMER_SECRET" \
  --type SecureString \
  --region us-west-2

# Add OpenWeather API key
aws ssm put-parameter \
  --name /powermgr/openweather/api_key \
  --value "YOUR_OPENWEATHER_API_KEY" \
  --type SecureString \
  --region us-west-2

# Add Tesla credentials
aws ssm put-parameter \
  --name /powermgr/tesla/refresh_token \
  --value "YOUR_TESLA_REFRESH_TOKEN" \
  --type SecureString \
  --region us-west-2
```

**How to get Tesla refresh token:**
See `aws/CREDENTIALS.md` for detailed instructions on obtaining Tesla API credentials.

### Step 7: Test in Dry-Run Mode

Test each function manually while in dry-run mode:

```bash
cd /home/user/powermgr_v2/aws

# Test data collection
make invoke-collector
make logs-collector

# Test analytics
make invoke-analytics
make logs-analytics

# Test thermostat controller (should show [DRY-RUN] messages)
make invoke-thermostat
make logs-thermostat

# Test peak manager (should show [DRY-RUN] messages)
make invoke-peak
make logs-peak

# Test precool check (should show [DRY-RUN] messages)
make invoke-precool
make logs-precool
```

**Look for this in logs:**
```
============================================================
DRY-RUN MODE ENABLED - No actual thermostat changes will be made
============================================================

[DRY-RUN] Would set device 1234567 to 73°F (skipped)
```

### Step 8: Monitor for 24-48 Hours

Let the system run in dry-run mode for 1-2 days:

```bash
# Watch logs in real-time
make tail-thermostat
make tail-peak

# Review what actions would have been taken
aws logs filter-log-events \
  --log-group-name /aws/lambda/PowerMgr-ThermostatController-prod \
  --filter-pattern "[DRY-RUN]" \
  --region us-west-2
```

### Step 9: Go Live

Once you're confident the system is working correctly:

```bash
# Disable dry-run mode
aws ssm put-parameter \
  --name /powermgr/config/dry_run \
  --value "false" \
  --type String \
  --overwrite \
  --region us-west-2

# The system will pick up the change within 5 minutes
# Or redeploy to force immediate pickup
make deploy
```

## Troubleshooting

### If deployment still fails

1. Check you're using the correct AWS profile:
   ```bash
   aws sts get-caller-identity
   ```
   Should show: `arn:aws:iam::260758034704:user/powermgr-lambda-user`

2. Verify all permissions are attached:
   ```bash
   aws iam list-attached-user-policies --user-name powermgr-lambda-user
   ```

3. Check SAM configuration:
   ```bash
   cat samconfig.toml
   ```

### If log groups already exist

If you get "log group already exists" errors, delete them first:
```bash
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/PowerMgr" --region us-west-2
aws logs delete-log-group --log-group-name <LOG_GROUP_NAME> --region us-west-2
```

### If functions don't have credentials

Functions will fail if credentials aren't configured. Check:
```bash
aws ssm get-parameters \
  --names /powermgr/honeywell/consumer_key \
          /powermgr/honeywell/consumer_secret \
          /powermgr/openweather/api_key \
          /powermgr/tesla/refresh_token \
  --with-decryption \
  --region us-west-2
```

## Summary Checklist

- [ ] Add IAM permissions to powermgr-lambda-user
- [ ] Verify permissions with `aws iam list-attached-user-policies`
- [ ] Delete orphaned log groups
- [ ] Delete failed CloudFormation stack
- [ ] Run `sam build --use-container`
- [ ] Run `sam deploy --guided`
- [ ] Configure Parameter Store with `make setup-params`
- [ ] Enable dry-run mode
- [ ] Add API credentials to Parameter Store
- [ ] Subscribe to SNS email notifications
- [ ] Test all functions in dry-run mode
- [ ] Monitor logs for 24-48 hours
- [ ] Disable dry-run mode when ready
- [ ] Celebrate successful deployment! 🎉

## Cost Reminder

This entire system runs within AWS Free Tier limits:
- **Forever-Free: $0/month**
- No surprises, no charges
- All resources stay within free tier quotas

## Need Help?

See these files:
- `aws/README.md` - Complete AWS deployment guide
- `aws/DRY_RUN.md` - Dry-run mode documentation
- `aws/PHASE3.md` - Control functions guide
- `aws/PHASE4.md` - Weekly reporting guide
- `aws/CREDENTIALS.md` - How to get API credentials
