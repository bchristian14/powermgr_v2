# Quick Start Guide - Phase 1 Deployment

This guide will get your Power Management System running on AWS in approximately 30 minutes.

## 🎉 **FOREVER FREE** - $0/month

This system runs **completely free on AWS forever**, not just for 12 months. See [FOREVER_FREE.md](FOREVER_FREE.md) for details.

---

## Prerequisites Checklist

- [ ] AWS Account with admin access
- [ ] AWS CLI installed and configured (`aws configure`)
- [ ] AWS SAM CLI installed (`sam --version`)
- [ ] Python 3.11+ installed
- [ ] Existing `tesla.token` file
- [ ] Tesla Energy Site ID
- [ ] Honeywell credentials and thermostat IDs
- [ ] OpenWeatherMap API key
- [ ] Email addresses for notifications

---

## 5-Step Deployment

### Step 1: Build (2 minutes)

```bash
cd aws
sam build
```

**Expected output:** "Build Succeeded"

---

### Step 2: Deploy (3-5 minutes)

```bash
sam deploy --guided
```

**Prompts - accept defaults or customize:**
- Stack Name: `powermgr-prod` ✓
- AWS Region: `us-east-1` (or your preference)
- Parameter Environment: `prod` ✓
- Confirm changes: `Y` ✓
- Allow IAM role creation: `Y` ✓
- Save configuration: `Y` ✓

**Wait for:** "Successfully created/updated stack"

---

### Step 3: Configure Secrets (5-10 minutes)

#### Quick Setup Script:

```bash
# Install Python dependencies
pip install boto3

# Create all parameters with defaults
python3 scripts/setup_parameters.py --setup-all
```

#### Update Critical Parameters:

```bash
# 1. Tesla Site ID (REQUIRED)
aws ssm put-parameter \
  --name '/powermgr/config/tesla/energy_site_id' \
  --value 'YOUR_SITE_ID_HERE' \
  --type String \
  --overwrite

# 2. Your Location (REQUIRED for weather)
aws ssm put-parameter \
  --name '/powermgr/config/precool_settings' \
  --value '{"temp": 67, "threshold": 90, "lat": YOUR_LAT, "lon": YOUR_LON, "forecast_threshold": 105}' \
  --type String \
  --overwrite

# 3. Thermostat IDs (REQUIRED)
aws ssm put-parameter \
  --name '/powermgr/config/thermostat_settings' \
  --value '{"ids": [123456, 123457], "base_url": "https://www.mytotalconnectcomfort.com/portal"}' \
  --type String \
  --overwrite

# 4. Notification Emails (REQUIRED)
aws ssm put-parameter \
  --name '/powermgr/config/notification_emails' \
  --value '["your.email@example.com"]' \
  --type String \
  --overwrite

# 5. Honeywell Credentials (REQUIRED)
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

# 6. OpenWeather API Key (REQUIRED)
aws ssm put-parameter \
  --name '/powermgr/secrets/openweather/api_key' \
  --value 'YOUR_API_KEY' \
  --type SecureString \
  --overwrite
```

#### Verify Configuration:

```bash
python3 scripts/setup_parameters.py --verify
```

**Expected:** All parameters show ✓ Configured

---

### Step 4: Initialize Tesla Token (2 minutes)

```bash
# Import token from file
python3 scripts/init_tesla_token.py ../tesla.token --verify
```

**Expected output:**
```
✓ Token loaded successfully
✓ Tesla token stored in DynamoDB table: PowerState-prod
✓ Token verification successful
```

---

### Step 5: Subscribe to Notifications (2 minutes)

```bash
# Get SNS Topic ARN
TOPIC_ARN=$(aws cloudformation describe-stacks \
  --stack-name powermgr-prod \
  --query 'Stacks[0].Outputs[?OutputKey==`NotificationTopicArn`].OutputValue' \
  --output text)

# Subscribe your email
aws sns subscribe \
  --topic-arn $TOPIC_ARN \
  --protocol email \
  --notification-endpoint your.email@example.com
```

**Check your email and click the confirmation link!**

---

## Validation & Testing

### Test Data Collection

```bash
# Manually invoke the function
aws lambda invoke \
  --function-name PowerMgr-DataCollector-prod \
  --log-type Tail \
  response.json

# View response
cat response.json | python3 -m json.tool
```

**Expected response:**
```json
{
    "statusCode": 200,
    "body": "{\"message\": \"Data collection successful\", ...}"
}
```

### View Logs

```bash
# Watch real-time logs
aws logs tail /aws/lambda/PowerMgr-DataCollector-prod --follow
```

### Check Data Storage

```bash
# Check DynamoDB (wait 5-10 minutes for first scheduled run)
aws dynamodb scan \
  --table-name PowerMetrics-prod \
  --limit 1
```

**Expected:** Returns at least one item with battery metrics

### Check S3 Historical Storage

```bash
# List recent data (update ACCOUNT_ID)
aws s3 ls s3://powermgr-historical-prod-ACCOUNT_ID/metrics/ --recursive | tail -5
```

---

## What Happens Next?

### Automatic Data Collection

The system now automatically collects data:
- **Every 5 minutes** during peak hours
- **Every 15 minutes** during off-peak hours

### Data Retention

- **DynamoDB:** Last 14 days (rolling)
- **S3:** Permanent (archived to Glacier after 1 year)

### Monitoring

View Lambda executions in CloudWatch:
```bash
# Count invocations in last hour
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=PowerMgr-DataCollector-prod \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Sum
```

---

## Troubleshooting

### Common Issues

**Issue:** "Parameter not found" error

**Solution:**
```bash
# Verify parameter exists
aws ssm get-parameter --name /powermgr/config/tesla/energy_site_id

# If missing, create it with proper value
```

**Issue:** Tesla API 401 error

**Solution:**
```bash
# Check token in DynamoDB
aws dynamodb get-item \
  --table-name PowerState-prod \
  --key '{"state_key": {"S": "tesla_token"}}'

# Reinitialize if needed
python3 scripts/init_tesla_token.py ../tesla.token --verify
```

**Issue:** No data in DynamoDB after 30 minutes

**Solution:**
```bash
# Check Lambda errors
aws lambda get-function \
  --function-name PowerMgr-DataCollector-prod

# View detailed logs
aws logs tail /aws/lambda/PowerMgr-DataCollector-prod --since 1h

# Manually invoke to see error
aws lambda invoke \
  --function-name PowerMgr-DataCollector-prod \
  --log-type Tail \
  response.json
```

---

## Next Steps

### After 24-48 Hours

1. **Validate Data Collection:**
   ```bash
   # Count total metrics collected
   aws dynamodb scan \
     --table-name PowerMetrics-prod \
     --select COUNT
   ```

   **Expected:** 200-500+ items

2. **Query Historical Data with Athena:**
   - Go to AWS Console → Athena
   - Select database: `powermgmt_prod`
   - Run query:
     ```sql
     SELECT * FROM metrics
     WHERE year = '2025'
     LIMIT 10;
     ```

3. **Review Costs:**
   - Go to AWS Console → Cost Explorer
   - Should be $0.00 with free tier

### Proceed to Phase 2

Once Phase 1 is validated, you're ready for:
- **Phase 2:** Analytics and prediction engine
- **Phase 3:** Smart thermostat control
- **Phase 4:** Weekly reports and dashboards

See main [README.md](README.md) for full documentation.

---

## Cost Summary

**Monthly Cost:**
- **Forever:** $0.00 ✅
- Uses only AWS always-free tier services
- 1-year data retention within DynamoDB 25GB free tier
- No S3 costs, no Athena costs, no surprises

**See [FOREVER_FREE.md](FOREVER_FREE.md) for complete breakdown.**

---

## Getting Help

**Check logs first:**
```bash
aws logs tail /aws/lambda/PowerMgr-DataCollector-prod --since 2h
```

**Verify configuration:**
```bash
python3 scripts/setup_parameters.py --verify
```

**View all stack resources:**
```bash
aws cloudformation describe-stack-resources --stack-name powermgr-prod
```

---

## Success Indicators

✅ **You're successful if:**
- Lambda function executes without errors
- DynamoDB has metrics with current timestamp
- S3 has JSON files in dated partitions
- CloudWatch shows regular invocations
- No error emails received

🎉 **Congratulations! Your Power Management System is now running on AWS!**
