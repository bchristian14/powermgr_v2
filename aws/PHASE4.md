# Phase 4: Weekly Reporting & Analytics

Phase 4 implements comprehensive weekly reporting with cost savings calculations, performance metrics, and actionable insights.

## Overview

Phase 4 adds the **WeeklyReportFunction** that analyzes 7 days of data and sends a detailed performance report covering:

- 💰 **Cost Savings** - Grid energy avoided, estimated dollar savings
- 🔋 **Battery Performance** - Average levels, threshold events, usage patterns
- 🌡️ **Thermostat Adjustments** - Frequency, urgency breakdown, effectiveness
- ✅ **Peak Period Compliance** - Grid usage incidents, charging patterns

## Prerequisites

**Required:**
- Phase 1 deployed and collecting data for at least 7 days
- Phase 2 deployed and generating analytics (for adjustment insights)
- Phase 3 deployed (for complete system metrics)
- SNS subscription configured for email delivery

**Recommended:**
- At least 1-2 weeks of data collection for meaningful reports
- System running in production mode (not testing)

## Deployment

### 1. Deploy Phase 4 Function

```bash
cd aws
make deploy
```

This deploys the WeeklyReportFunction with its weekly schedule.

### 2. Verify Deployment

```bash
# Check function deployment
aws lambda get-function --function-name PowerMgr-WeeklyReport-prod

# View function configuration
make stack-outputs | grep Weekly
```

### 3. Manual Test (Optional)

```bash
# Manually trigger weekly report
make invoke-weekly

# View execution logs
make logs-weekly
```

**Note:** Manual test will generate a report based on current data, even if it's only a few days.

## Function Details

### WeeklyReportFunction

**Purpose:** Generates and sends comprehensive weekly performance report

**Schedule:** Weekly on Sunday night at 11:00pm EST (04:00 UTC Monday)

**Timeout:** 5 minutes (to process 7 days of data)

**Data Sources:**
- PowerMetrics table (battery, solar, grid readings)
- PowerAnalytics table (projections and recommendations)
- PowerState table (battery status, thermostat state)

**Calculations:**

#### 1. Cost Savings
```python
# Grid energy avoided during peak periods
grid_avoided_kwh = battery_kwh + solar_kwh

# Estimated savings (assuming $0.45/kWh peak rate)
savings = grid_avoided_kwh * 0.45

# Actual cost (minimal grid usage)
actual_cost = grid_usage_kwh * 0.45

# Net savings
net_savings = savings - actual_cost
```

#### 2. Battery Performance
```python
# Average battery level over week
avg_battery = sum(all_readings) / count

# Threshold event counting
times_below_20 = count(readings < 20%)
times_below_35 = count(readings < 35%)

# Battery range
min_level = min(all_readings)
max_level = max(all_readings)
```

#### 3. Thermostat Adjustments
```python
# Count adjustments by urgency
critical_adjustments = count(urgency == 'CRITICAL')  # +4°F
high_adjustments = count(urgency == 'HIGH')          # +2°F
medium_adjustments = count(urgency == 'MEDIUM')      # +2°F

# Average battery deficit from target
avg_deficit = avg(target - projected)
```

#### 4. Peak Compliance
```python
# Grid usage compliance
peak_compliance = (peak_periods - grid_incidents) / peak_periods * 100

# Charging effectiveness
charging_rate = charging_periods / off_peak_periods * 100
```

## Sample Report

```
POWER MANAGEMENT WEEKLY REPORT
2025-11-10 to 2025-11-17

═══════════════════════════════════════════════════════════════

💰 COST SAVINGS SUMMARY

Grid Energy Avoided:     145.32 kWh
  - Battery Usage:       98.45 kWh
  - Solar Generation:    46.87 kWh

Estimated Savings:       $65.39
  - Would-be Cost:       $65.39 (@ $0.45/kWh)
  - Actual Grid Cost:    $0.00

Peak Periods Tracked:    420

═══════════════════════════════════════════════════════════════

🔋 BATTERY PERFORMANCE

Average Battery Level:   67.3%
Battery Range:           18.2% - 98.5%

Threshold Events:
  - Below 20%:           3 times
  - Below 35%:           24 times

Total Readings:          2,016

═══════════════════════════════════════════════════════════════

🌡️  THERMOSTAT ADJUSTMENTS

Total Adjustments:       18
  - CRITICAL:            2 (+4°F)
  - HIGH:                7 (+2°F)
  - MEDIUM:              9 (+2°F)

Avg Battery Deficit:     3.2% from target
Analytics Runs:          84

═══════════════════════════════════════════════════════════════

✅ PEAK PERIOD COMPLIANCE

Peak Periods:            420
Grid Usage Incidents:    0
Peak Compliance:         100.0%

Off-Peak Periods:        1,596
Charging Periods:        1,234
Charging Rate:           77.3%

═══════════════════════════════════════════════════════════════

📊 WEEKLY INSIGHTS

✨ Excellent savings this week! System is performing optimally.
✓ Perfect peak period compliance - zero grid usage!

═══════════════════════════════════════════════════════════════

Report generated: 2025-11-18 04:00:15 UTC
```

## Commands

```bash
# Manually generate weekly report
make invoke-weekly

# View report generation logs (last 2 hours)
make logs-weekly

# Real-time log monitoring
make tail-weekly

# Check function status
aws lambda get-function --function-name PowerMgr-WeeklyReport-prod
```

## Customizing the Report

### Adjusting Electricity Rates

Edit `aws/functions/weekly_report/handler.py`:

```python
def calculate_cost_savings(metrics: List[Dict[str, Any]], cfg) -> Dict[str, Any]:
    # Update these rates to match your utility
    peak_rate_per_kwh = 0.45      # Your peak rate
    off_peak_rate_per_kwh = 0.12  # Your off-peak rate

    # ... rest of function
```

### Changing Report Schedule

Edit `aws/template.yaml`:

```yaml
WeeklyReportSchedule:
  Type: Schedule
  Properties:
    # Run Monday morning instead of Sunday night
    Schedule: cron(0 13 ? * MON *)  # 8am EST Monday
    Description: Generate and send weekly performance report
    Enabled: true
```

**Timezone Conversion:**
- EST to UTC: Add 5 hours (standard) or 4 hours (DST)
- PST to UTC: Add 8 hours (standard) or 7 hours (DST)

### Adding Custom Metrics

Add new calculation functions to `handler.py`:

```python
def analyze_custom_metric(metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Your custom analysis"""
    # Process metrics
    return {
        'custom_value': calculated_value,
        'custom_count': count
    }

# Call in lambda_handler
custom_stats = analyze_custom_metric(all_metrics)

# Include in format_report_email
```

## Monitoring

### Email Notifications

Weekly reports are sent via SNS to all subscribed email addresses.

**Verify Subscription:**
```bash
aws sns list-subscriptions-by-topic \
  --topic-arn $(aws cloudformation describe-stacks \
    --stack-name powermgr-prod \
    --query 'Stacks[0].Outputs[?OutputKey==`NotificationTopicArn`].OutputValue' \
    --output text)
```

**Add Subscription:**
```bash
aws sns subscribe \
  --topic-arn YOUR_TOPIC_ARN \
  --protocol email \
  --notification-endpoint your-email@example.com
```

### CloudWatch Metrics

Monitor function performance:

```bash
# View invocation count
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=PowerMgr-WeeklyReport-prod \
  --start-time $(date -u -d '30 days ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 604800 \
  --statistics Sum

# View execution duration
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=PowerMgr-WeeklyReport-prod \
  --start-time $(date -u -d '30 days ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 604800 \
  --statistics Average,Maximum
```

## Troubleshooting

### Report Not Received

**Check:**
1. Function executed successfully
2. SNS subscription confirmed
3. Email not in spam folder

**Debug:**
```bash
# Check recent invocations
make logs-weekly

# Check for errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/PowerMgr-WeeklyReport-prod \
  --filter-pattern "ERROR"

# Verify SNS topic
aws sns get-topic-attributes --topic-arn YOUR_TOPIC_ARN
```

### Missing Data in Report

**Check:**
1. Data collection running for full week
2. DynamoDB tables have data
3. Function timeout (increase if needed)

**Debug:**
```bash
# Check metrics table
aws dynamodb scan \
  --table-name PowerMetrics-prod \
  --select COUNT

# Check analytics table
aws dynamodb scan \
  --table-name PowerAnalytics-prod \
  --select COUNT

# Query specific date
aws dynamodb query \
  --table-name PowerMetrics-prod \
  --key-condition-expression "metric_date = :date" \
  --expression-attribute-values '{":date":{"S":"2025-11-17"}}'
```

### Calculation Errors

**Check:**
1. Data format consistency
2. Decimal/float conversions
3. Division by zero handling

**Debug:**
```bash
# View detailed execution logs
make tail-weekly

# Check for warnings
aws logs filter-log-events \
  --log-group-name /aws/lambda/PowerMgr-WeeklyReport-prod \
  --filter-pattern "WARNING"
```

## Cost Analysis

**Phase 4 Lambda Invocations (Monthly):**
- WeeklyReportFunction: ~4 (weekly)
- Average duration: ~30 seconds (data processing)

**Total Phase 4 cost: $0/month** (well within Lambda free tier)

**Combined System Cost (All Phases):**
- Lambda: ~5,764 invocations/month vs 1,000,000 free tier
- CloudWatch Logs: ~200MB/month vs 5GB free tier
- DynamoDB: ~425MB storage vs 25GB free tier
- SNS: ~50 emails/month vs 1,000 free tier

**Forever-Free Architecture: $0/month**

## Interpreting Report Insights

### Cost Savings

**Good Performance:**
- Net savings > $20/week
- Grid usage incidents = 0
- Charging rate > 70%

**Needs Attention:**
- Net savings < $10/week - Review battery usage patterns
- Grid usage incidents > 0 - Investigate peak period breaches
- Charging rate < 50% - Check off-peak charging logic

### Battery Performance

**Good Performance:**
- Average level > 60%
- Times below 20% < 5
- Min level > 15%

**Needs Attention:**
- Average level < 50% - Battery may be undersized
- Times below 20% > 10 - Adjust thresholds or increase reserve
- Min level < 10% - Risk of complete discharge

### Thermostat Adjustments

**Good Performance:**
- Critical adjustments < 5
- High adjustments < 15
- Average deficit < 5%

**Needs Attention:**
- Critical adjustments > 10 - Battery struggling to meet demand
- Average deficit > 10% - Consider increasing target reserve
- Too many adjustments - Review predictive model accuracy

### Peak Compliance

**Perfect:**
- Peak compliance = 100%
- Grid incidents = 0

**Needs Improvement:**
- Peak compliance < 95% - Review PeakManager schedules
- Grid incidents > 0 - Check battery capacity and usage

## Related Documentation

- [Phase 1: Data Collection](../QUICKSTART.md)
- [Phase 2: Analytics](PHASE2.md)
- [Phase 3: Control Functions](PHASE3.md)
- [Forever Free Architecture](FOREVER_FREE.md)
- [Configuration Guide](README.md#configuration)

## Next Steps

After Phase 4 deployment:

1. **Wait for First Report** - Arrives Sunday night/Monday morning
2. **Review Performance** - Analyze savings and compliance metrics
3. **Tune System** - Adjust thresholds based on actual performance
4. **Monitor Trends** - Compare week-over-week performance
5. **Optimize Settings** - Fine-tune for maximum savings

**Production Recommendations:**
- Review weekly reports consistently
- Track month-over-month trends
- Adjust seasonal settings (summer vs winter)
- Document any manual interventions
- Celebrate your energy savings! 🎉
