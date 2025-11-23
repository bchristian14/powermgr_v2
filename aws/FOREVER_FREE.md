# Forever-Free AWS Architecture 🎉

This power management system is designed to run **completely free on AWS forever** - not just for 12 months.

## Cost Breakdown

| Service | Monthly Usage | Free Tier Limit | Forever Free? | Cost |
|---------|--------------|-----------------|---------------|------|
| **Lambda** | 35,000 invocations | 1M requests/month | ✅ Yes | $0 |
| **Lambda Compute** | ~150 GB-seconds | 400K GB-seconds/month | ✅ Yes | $0 |
| **DynamoDB Storage** | <1 GB (1 year data) | 25 GB | ✅ Yes | $0 |
| **DynamoDB R/W** | ~50 units | 25 RCU + 25 WCU | ✅ Yes | $0 |
| **Parameter Store** | 25 parameters | 10,000 standard params | ✅ Yes | $0 |
| **EventBridge** | 3 scheduled rules | Unlimited | ✅ Yes | $0 |
| **SNS Email** | ~150 emails/month | 1,000 emails/month | ✅ Yes | $0 |
| **CloudWatch Logs** | ~0.5 GB/month | 5 GB/month | ✅ Yes | $0 |
| **TOTAL** | | | ✅ **Yes** | **$0/month** |

---

## Architecture Changes for Forever-Free

### What We Removed

1. **S3 Historical Storage** ❌
   - Originally: 5GB free for 12 months only
   - After 12 months: ~$0.10-0.50/month
   - **Solution:** Use DynamoDB with 1-year TTL instead

2. **Athena/Glue** ❌
   - Not needed for our query patterns
   - **Solution:** Query DynamoDB directly or use local scripts

3. **Extra CloudWatch Retention** ⚠️
   - Reduced from 30 days to 7 days
   - Stays under 5GB free tier limit

### What We Kept (All Forever-Free)

1. **DynamoDB** ✅
   - 25GB storage (forever free)
   - Our 1-year retention: ~420 MB (1.68% of limit)
   - Room for 59 years of data!

2. **Lambda** ✅
   - 1M requests/month forever
   - We use ~35K/month (3.5% of limit)

3. **All other services** ✅
   - Parameter Store, EventBridge, SNS - all forever free

---

## Data Retention Strategy

### Storage Calculation

```
Single metric: ~1 KB JSON
Monthly readings: 35,000 (peak + off-peak)
Monthly data: 35 KB × 35,000 = 35 MB

1 year retention: 35 MB × 12 = 420 MB
DynamoDB free tier: 25,000 MB
Usage: 420 MB / 25,000 MB = 1.68% ✅
```

### TTL Configuration

- **Metrics Table:** 365 days (1 year)
- **Analytics Table:** 365 days (1 year)
- **State Table:** No TTL (small, persistent state)

### Automatic Cleanup

DynamoDB TTL automatically deletes expired items:
- No manual cleanup needed
- No cost for deletions
- Gradual, background process

---

## Historical Data Analysis

Without S3/Athena, how do we analyze historical data?

### Option 1: DynamoDB Queries (Built-in)

```python
# Query last 30 days directly from DynamoDB
from datetime import datetime, timedelta
import boto3

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('PowerMetrics-prod')

# Query specific date
response = table.query(
    KeyConditionExpression=Key('metric_date').eq('2025-11-16')
)
```

**Pros:**
- Free (no S3 costs)
- Fast queries
- Works immediately

**Cons:**
- Need to query each date individually
- Not as powerful as SQL

### Option 2: Local Analytics Script (Included)

We provide `scripts/analyze_metrics.py` for local analysis:

```bash
# Generate weekly report
make report

# Export to JSON for analysis
make export-json START=2025-11-01 END=2025-11-30 FILE=november.json

# Export to CSV for Excel/spreadsheets
make export-csv START=2025-11-01 END=2025-11-30 FILE=november.csv
```

**Pros:**
- Completely free
- Export to JSON/CSV for any tool (Excel, Python pandas, etc.)
- Weekly reports built-in

**Cons:**
- Requires local Python environment
- Must download data first

### Option 3: Manual S3 Export (When Needed)

DynamoDB offers **free** periodic exports to S3:

```bash
# Export to S3 (free operation)
aws dynamodb export-table-to-point-in-time \
  --table-arn arn:aws:dynamodb:region:account:table/PowerMetrics-prod \
  --s3-bucket my-temporary-bucket \
  --export-format DYNAMODB_JSON

# Analyze with Athena
# Delete from S3 when done (avoid storage costs)
```

**Pros:**
- Use Athena for complex SQL queries
- One-time deep dives

**Cons:**
- Manual process
- Remember to delete S3 data after analysis

---

## Monitoring Free Tier Usage

### Check DynamoDB Storage

```bash
# Via AWS CLI
aws dynamodb describe-table \
  --table-name PowerMetrics-prod \
  --query 'Table.TableSizeBytes' \
  --output text

# Convert bytes to MB
# Result should be < 25,000 MB (25 GB)
```

### Check Lambda Invocations

```bash
# Last 30 days
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=PowerMgr-DataCollector-prod \
  --start-time $(date -u -d '30 days ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 2592000 \
  --statistics Sum

# Should be < 1,000,000 per month
```

### Check CloudWatch Logs

```bash
# Via AWS Console
# CloudWatch → Log groups → /aws/lambda/PowerMgr-DataCollector-prod
# Should be < 5 GB ingested per month
```

### Set Up Billing Alerts (Recommended)

```bash
# Create SNS topic for billing alerts
aws sns create-topic --name BillingAlerts

# Subscribe your email
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:ACCOUNT:BillingAlerts \
  --protocol email \
  --notification-endpoint your@email.com

# Create billing alarm (triggers if > $1)
aws cloudwatch put-metric-alarm \
  --alarm-name UnexpectedAWSCharges \
  --alarm-description "Alert if AWS bill exceeds $1" \
  --metric-name EstimatedCharges \
  --namespace AWS/Billing \
  --statistic Maximum \
  --period 21600 \
  --evaluation-periods 1 \
  --threshold 1.0 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions arn:aws:sns:us-east-1:ACCOUNT:BillingAlerts
```

---

## What If I Exceed Free Tier?

### DynamoDB (25 GB limit)

If you somehow exceed 25 GB:
- Cost: $0.25/GB/month
- 30 GB total = ~$1.25/month

**Prevention:**
- Monitor table size monthly
- Current usage: < 2% of limit
- Would take 59+ years to exceed

### Lambda (1M requests/month)

If you exceed 1M requests:
- Cost: $0.20 per 1M requests
- 2M requests = ~$0.20/month

**Prevention:**
- Current: 35K requests/month (3.5%)
- Would need 28x more collection frequency

### CloudWatch Logs (5 GB/month)

If you exceed 5 GB ingestion:
- Cost: $0.50/GB
- 6 GB total = ~$0.50/month

**Prevention:**
- Reduced retention to 7 days
- Estimated: 0.5 GB/month (10% of limit)

---

## Comparison: AWS vs Other Clouds

| Feature | AWS (Forever Free) | GCP (Forever Free) | Azure (12 mo free) |
|---------|-------------------|--------------------|--------------------|
| **Compute** | Lambda 1M req/mo | Functions 2M req/mo | Functions 1M req/mo (12mo) |
| **Database** | DynamoDB 25GB | Firestore 1GB | Cosmos 1000 RU/s (12mo) |
| **Storage** | ❌ (not free) | 5GB forever ✅ | 5GB (12mo) |
| **Logging** | 5GB/month | 50GB/month ✅ | Limited (12mo) |
| **Total Cost** | **$0/month** | **$0/month** | ~$2+/month after 12mo |

**Winner for this use case:** Tie between AWS and GCP
- AWS: Better if you prefer DynamoDB over Firestore
- GCP: Better if you want built-in storage and more logging

---

## Best Practices for Staying Free

1. **Monitor monthly**
   - Check billing dashboard
   - Set up $1 billing alarm

2. **Don't over-collect**
   - Current schedule is optimal
   - Don't reduce collection interval unnecessarily

3. **Clean up logs**
   - 7-day retention is sufficient
   - Download important logs before deletion

4. **Export data periodically**
   - Use `make export-csv` monthly
   - Store locally or in personal cloud storage

5. **Review annually**
   - Update holidays configuration
   - Check for AWS free tier policy changes

---

## Conclusion

This architecture is designed to run **$0/month forever** by:
- Using only forever-free AWS services
- Staying well within all free tier limits
- Providing 1 year of data retention
- Including local analytics tools

You can run this system indefinitely without any AWS charges!

**Current usage: <2% of free tier limits across all services** ✅
