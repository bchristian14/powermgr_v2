# Power Management System v2.0 - AWS Deployment

This is the AWS serverless implementation of the Power Management System, migrated from Raspberry Pi cronjobs to AWS Lambda with historical data tracking and predictive analytics.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Prerequisites](#prerequisites)
- [Phase 1: Foundation Setup](#phase-1-foundation-setup)
- [Phase 2-4: Future Enhancements](#future-phases)
- [Cost Analysis](#cost-analysis)
- [Troubleshooting](#troubleshooting)

---

## Architecture Overview

### Components

**Data Storage:**
- **DynamoDB Tables:**
  - `PowerMetrics` - Recent metrics (14-day TTL)
  - `PowerAnalytics` - Analytics results (14-day TTL)
  - `PowerState` - System state (battery status, tokens, etc.)

- **S3 Buckets:**
  - Historical data storage (partitioned by date)
  - Athena query results

**Compute:**
- **Lambda Functions:**
  - `DataCollectorFunction` - Collects metrics from Tesla API every 5-15 minutes
  - Additional functions for analytics, control, and reporting (Phase 2+)

**Configuration:**
- **AWS Systems Manager Parameter Store:**
  - Configuration values (peak hours, thresholds, etc.)
  - Encrypted secrets (Tesla tokens, API keys, credentials)

**Scheduling:**
- **Amazon EventBridge** - Cron-based triggers for Lambda functions

**Analytics:**
- **AWS Glue** - Data catalog for Athena
- **Amazon Athena** - SQL queries on historical data

**Notifications:**
- **Amazon SNS** - Email notifications

---

## Prerequisites

### AWS Account Setup

1. **AWS Account** with appropriate permissions
2. **AWS CLI** installed and configured
   ```bash
   aws configure
   ```
3. **AWS SAM CLI** installed
   ```bash
   # macOS
   brew install aws-sam-cli

   # Linux
   pip install aws-sam-cli

   # Verify installation
   sam --version
   ```

### Required Data

Before deployment, gather the following:

- **Tesla:**
  - Energy Site ID
  - Valid access token and refresh token (from existing `tesla.token` file)

- **Honeywell:**
  - Total Connect username and password
  - Thermostat IDs

- **Weather:**
  - OpenWeatherMap API key (free tier available)
  - Your latitude and longitude

- **Notifications:**
  - Email addresses for notifications
  - Gmail username and app password (if using Gmail for notifications)

---

## Phase 1: Foundation Setup

Phase 1 establishes the core infrastructure and data collection.

### Step 1: Prepare Configuration

1. Navigate to the AWS directory:
   ```bash
   cd aws
   ```

2. Review and customize the SAM template if needed:
   ```bash
   # Edit template.yaml to adjust any settings
   nano template.yaml
   ```

### Step 2: Build the SAM Application

```bash
# Build the Lambda functions and layers
sam build
```

This will:
- Package the Lambda Layer with common utilities
- Package the DataCollector Lambda function
- Prepare for deployment

### Step 3: Deploy to AWS

```bash
# Deploy with guided prompts
sam deploy --guided
```

**Deployment prompts:**
- Stack Name: `powermgr-prod` (or your choice)
- AWS Region: Your preferred region (e.g., `us-east-1`)
- Parameter Environment: `prod` (or `dev`/`staging`)
- Confirm changes before deploy: Y
- Allow SAM CLI IAM role creation: Y
- Save arguments to configuration file: Y

This creates:
- DynamoDB tables
- S3 buckets
- Lambda functions
- IAM roles
- EventBridge schedules
- CloudWatch log groups
- Glue database and tables

**Deployment takes approximately 3-5 minutes.**

### Step 4: Configure Parameter Store

#### Option A: Interactive Setup (Recommended)

```bash
# Install dependencies for setup script
pip install boto3

# Setup all parameters with defaults
python3 scripts/setup_parameters.py --setup-all

# Migrate values from existing config.py (optional)
python3 scripts/setup_parameters.py --migrate-from-config ../config.py
```

#### Option B: Manual Configuration via AWS CLI

**Configuration Parameters:**

```bash
# Tesla Energy Site ID
aws ssm put-parameter \
  --name '/powermgr/config/tesla/energy_site_id' \
  --value 'YOUR_SITE_ID' \
  --type String \
  --overwrite

# Thermostat IDs (JSON array)
aws ssm put-parameter \
  --name '/powermgr/config/thermostat_settings' \
  --value '{"ids": [123456, 123457], "base_url": "https://www.mytotalconnectcomfort.com/portal"}' \
  --type String \
  --overwrite

# Precool settings (update lat/lon)
aws ssm put-parameter \
  --name '/powermgr/config/precool_settings' \
  --value '{"temp": 67, "threshold": 90, "lat": 40.71, "lon": -74.00, "forecast_threshold": 105}' \
  --type String \
  --overwrite

# Notification emails (JSON array)
aws ssm put-parameter \
  --name '/powermgr/config/notification_emails' \
  --value '["email@example.com", "email2@example.com"]' \
  --type String \
  --overwrite
```

**Secret Parameters (Encrypted):**

```bash
# Honeywell credentials
aws ssm put-parameter \
  --name '/powermgr/secrets/honeywell/username' \
  --value 'YOUR_USERNAME' \
  --type SecureString \
  --overwrite

aws ssm put-parameter \
  --name '/powermgr/secrets/honeywell/password' \
  --value 'YOUR_PASSWORD' \
  --type SecureString \
  --overwrite

# OpenWeather API key
aws ssm put-parameter \
  --name '/powermgr/secrets/openweather/api_key' \
  --value 'YOUR_API_KEY' \
  --type SecureString \
  --overwrite

# Gmail credentials (if using direct email)
aws ssm put-parameter \
  --name '/powermgr/secrets/gmail/username' \
  --value 'your.email@gmail.com' \
  --type SecureString \
  --overwrite

aws ssm put-parameter \
  --name '/powermgr/secrets/gmail/password' \
  --value 'YOUR_APP_PASSWORD' \
  --type SecureString \
  --overwrite
```

#### Verify Parameters

```bash
# Verify all parameters are configured
python3 scripts/setup_parameters.py --verify
```

### Step 5: Initialize Tesla Token

The Tesla token must be stored in DynamoDB for the Lambda functions to access:

```bash
# Initialize from existing tesla.token file
python3 scripts/init_tesla_token.py ../tesla.token --verify
```

This stores the token in the `PowerStateTable` with the key `tesla_token`.

**Verify token storage:**

```bash
# Check DynamoDB directly
aws dynamodb get-item \
  --table-name PowerState-prod \
  --key '{"state_key": {"S": "tesla_token"}}' \
  --query 'Item.last_updated'
```

### Step 6: Subscribe to SNS Notifications

```bash
# Get SNS topic ARN from stack outputs
TOPIC_ARN=$(aws cloudformation describe-stacks \
  --stack-name powermgr-prod \
  --query 'Stacks[0].Outputs[?OutputKey==`NotificationTopicArn`].OutputValue' \
  --output text)

# Subscribe email addresses
aws sns subscribe \
  --topic-arn $TOPIC_ARN \
  --protocol email \
  --notification-endpoint your.email@example.com
```

**Check your email and confirm the subscription.**

### Step 7: Test Data Collection

Manually invoke the DataCollector function to test:

```bash
# Invoke the function
aws lambda invoke \
  --function-name PowerMgr-DataCollector-prod \
  --log-type Tail \
  --query 'LogResult' \
  --output text \
  response.json | base64 --decode

# Check the response
cat response.json | jq .
```

**Expected response:**
```json
{
  "statusCode": 200,
  "body": "{\"message\": \"Data collection successful\", \"timestamp\": \"2025-11-16T14:30:00Z\", \"battery_percentage\": 75.0, \"peak_period\": \"summer_peak\"}"
}
```

### Step 8: Verify Data Storage

#### Check DynamoDB

```bash
# Query recent metrics
aws dynamodb query \
  --table-name PowerMetrics-prod \
  --key-condition-expression 'metric_date = :date' \
  --expression-attribute-values '{":date": {"S": "'$(date +%Y-%m-%d)'"}}' \
  --scan-index-forward false \
  --limit 1
```

#### Check S3

```bash
# List recent S3 objects
aws s3 ls s3://powermgr-historical-prod-YOUR_ACCOUNT_ID/metrics/year=$(date +%Y)/month=$(date +%m)/day=$(date +%d)/ --recursive
```

#### Check CloudWatch Logs

```bash
# View recent logs
aws logs tail /aws/lambda/PowerMgr-DataCollector-prod --follow
```

### Step 9: Monitor Scheduled Execution

The DataCollector function runs automatically based on EventBridge schedules:

- **Every 5 minutes** during peak hours
- **Every 15 minutes** during off-peak hours

**View scheduled executions:**

```bash
# Check recent invocations
aws lambda get-function \
  --function-name PowerMgr-DataCollector-prod \
  --query 'Configuration.[LastModified,LastUpdateStatus]'

# Monitor CloudWatch metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=PowerMgr-DataCollector-prod \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum
```

---

## Phase 1 Validation

After 24-48 hours of operation, validate:

### Data Collection

1. **DynamoDB Metrics:**
   ```bash
   # Count metrics collected today
   aws dynamodb scan \
     --table-name PowerMetrics-prod \
     --filter-expression 'metric_date = :date' \
     --expression-attribute-values '{":date": {"S": "'$(date +%Y-%m-%d)'"}}' \
     --select COUNT
   ```

   **Expected:** 100-300 items (depending on peak vs off-peak)

2. **S3 Historical Data:**
   ```bash
   # Count S3 objects for today
   aws s3 ls s3://powermgr-historical-prod-YOUR_ACCOUNT_ID/metrics/year=$(date +%Y)/month=$(date +%m)/day=$(date +%d)/ --recursive | wc -l
   ```

   **Expected:** Similar count to DynamoDB

3. **Athena Query:**
   ```sql
   SELECT
     COUNT(*) as total_records,
     AVG(battery_percentage) as avg_battery,
     AVG(solar_power) as avg_solar,
     AVG(grid_power) as avg_grid
   FROM powermgmt_prod.metrics
   WHERE year = '2025'
     AND month = '11'
     AND day = '16';
   ```

### Lambda Performance

```bash
# Check error rate
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=PowerMgr-DataCollector-prod \
  --start-time $(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 86400 \
  --statistics Sum

# Check duration
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=PowerMgr-DataCollector-prod \
  --start-time $(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 86400 \
  --statistics Average,Maximum
```

**Expected:**
- Error rate: 0%
- Average duration: < 2000ms
- Max duration: < 5000ms

---

## Future Phases

### Phase 2: Analytics & Prediction (Weeks 2-3)

- Deploy `AnalyticsFunction` for depletion rate calculations
- Implement predictive battery forecasting
- Solar-aware adjustments

### Phase 3: Smart Control (Week 3)

- Deploy enhanced `ThermostatControllerFunction`
- Deploy `PeakManagerFunction`
- Deploy `PrecoolCheckFunction`
- Deploy `EODStatusFunction`
- Deploy `AuthRefreshFunction`

### Phase 4: Reporting (Week 4)

- Deploy `WeeklyReportFunction`
- Setup Athena queries for trend analysis
- Optional: QuickSight dashboard

---

## Cost Analysis

### Free Tier (First 12 Months)

| Service | Usage (Monthly) | Free Tier | Cost |
|---------|----------------|-----------|------|
| Lambda Requests | ~35,000 | 1M requests | $0 |
| Lambda Compute | ~150 GB-sec | 400K GB-sec | $0 |
| DynamoDB Storage | ~5 GB | 25 GB | $0 |
| DynamoDB R/W | ~50 RCU/WCU | 25 RCU/WCU | $0 |
| S3 Storage | ~2 GB/year | 5 GB | $0 |
| S3 Requests | ~10K PUT | 2K PUT free | ~$0.05 |
| Athena Scanned | ~5 GB | 1 TB | $0 |
| EventBridge | ~40 rules | Free | $0 |
| Parameter Store | ~25 params | 10K params | $0 |
| SNS Email | ~150/month | 1K emails | $0 |
| CloudWatch Logs | ~2 GB | 5 GB | $0 |
| **Total** | | | **~$0/month** |

### After Free Tier

- Lambda: ~$0.20/month
- DynamoDB: ~$1.25/month
- S3: ~$0.10/month
- **Total: ~$1.50/month**

---

## Maintenance

### Update Configuration

```bash
# Update any parameter
aws ssm put-parameter \
  --name '/powermgr/config/PARAMETER_NAME' \
  --value 'NEW_VALUE' \
  --overwrite

# Force Lambda to reload (invoke once)
aws lambda invoke \
  --function-name PowerMgr-DataCollector-prod \
  response.json
```

### Update Lambda Code

```bash
# Make code changes
# Rebuild and deploy
sam build
sam deploy
```

### Update Holidays Annually

```bash
# Update holidays for 2026
aws ssm put-parameter \
  --name '/powermgr/config/holidays' \
  --value '["2026-01-01", "2026-05-25", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25"]' \
  --type String \
  --overwrite
```

### Backup and Restore

**Backup DynamoDB:**
```bash
# Enable point-in-time recovery (already enabled in template)
aws dynamodb update-continuous-backups \
  --table-name PowerState-prod \
  --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true
```

**Export S3 Data:**
```bash
# Download historical data
aws s3 sync s3://powermgr-historical-prod-YOUR_ACCOUNT_ID/metrics/ ./backups/metrics/
```

---

## Troubleshooting

### Data Collection Issues

**Problem:** No data in DynamoDB

1. Check Lambda execution:
   ```bash
   aws logs tail /aws/lambda/PowerMgr-DataCollector-prod --since 1h
   ```

2. Check EventBridge schedules:
   ```bash
   aws events list-rules --name-prefix powermgr
   ```

3. Manually invoke:
   ```bash
   aws lambda invoke --function-name PowerMgr-DataCollector-prod response.json
   cat response.json
   ```

**Problem:** Tesla API errors

1. Check token expiration:
   ```bash
   aws dynamodb get-item \
     --table-name PowerState-prod \
     --key '{"state_key": {"S": "tesla_token"}}'
   ```

2. Refresh token manually if needed (will be automated in Phase 3)

**Problem:** S3 storage failures

1. Check bucket permissions:
   ```bash
   aws s3api get-bucket-policy --bucket powermgr-historical-prod-YOUR_ACCOUNT_ID
   ```

2. Verify Lambda has S3 write permissions

### Parameter Store Issues

**Problem:** Parameters not found

```bash
# List all parameters
aws ssm get-parameters-by-path --path /powermgr --recursive

# Check specific parameter
aws ssm get-parameter --name /powermgr/config/tesla/energy_site_id
```

### Permission Issues

**Problem:** Lambda execution failures due to permissions

1. Check Lambda execution role:
   ```bash
   aws lambda get-function-configuration \
     --function-name PowerMgr-DataCollector-prod \
     --query 'Role'
   ```

2. Review CloudWatch logs for specific permission errors

3. Update SAM template and redeploy if needed

---

## Cleanup / Deletion

To remove all AWS resources:

```bash
# Delete CloudFormation stack
aws cloudformation delete-stack --stack-name powermgr-prod

# Wait for deletion
aws cloudformation wait stack-delete-complete --stack-name powermgr-prod

# Manually delete S3 buckets (must be empty first)
aws s3 rb s3://powermgr-historical-prod-YOUR_ACCOUNT_ID --force
aws s3 rb s3://powermgr-athena-results-prod-YOUR_ACCOUNT_ID --force

# Delete Parameter Store parameters
aws ssm delete-parameters --names $(aws ssm get-parameters-by-path --path /powermgr --recursive --query 'Parameters[].Name' --output text)
```

---

## Support

For issues:
1. Check CloudWatch Logs
2. Review [AWS SAM documentation](https://docs.aws.amazon.com/serverless-application-model/)
3. Check original repository issues

---

## Next Steps

Once Phase 1 is validated:
1. Monitor for 3-5 days to ensure consistent data collection
2. Review data quality in Athena
3. Proceed to Phase 2: Analytics implementation
