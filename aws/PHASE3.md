# Phase 3: Control Functions

Phase 3 implements the active control layer that manages Tesla Powerwall and Honeywell thermostats based on analytics and schedules.

## Overview

Phase 3 adds 5 Lambda functions that control your power management system:

1. **ThermostatController** - Adjusts thermostat temps based on battery levels
2. **PeakManager** - Manages Powerwall reserve (0% peak, 100% off-peak)
3. **PrecoolCheck** - Weather-based precooling decisions
4. **EODStatus** - Daily status reports with battery metrics
5. **AuthRefresh** - Automatic Tesla token refresh

## Prerequisites

**Required:**
- Phase 1 deployed and collecting data
- Phase 2 deployed and generating analytics (if using predictive mode)
- Honeywell credentials configured in Parameter Store
- OpenWeather API key configured (for precool function)

**Credentials Setup:**

```bash
# Add Honeywell credentials
aws ssm put-parameter \
  --name /powermgr/secrets/honeywell/username \
  --value "your_honeywell_username" \
  --type SecureString

aws ssm put-parameter \
  --name /powermgr/secrets/honeywell/password \
  --value "your_honeywell_password" \
  --type SecureString

# Add OpenWeather API key
aws ssm put-parameter \
  --name /powermgr/secrets/openweather/api_key \
  --value "your_openweather_api_key" \
  --type SecureString
```

## Deployment

### 1. Deploy Phase 3 Functions

```bash
cd aws
make deploy
```

This deploys all 5 Phase 3 functions along with their EventBridge schedules.

### 2. Verify Deployment

```bash
# Check stack outputs
make stack-outputs

# Test each function manually
make invoke-thermostat
make invoke-peak
make invoke-precool
make invoke-eod
make invoke-auth
```

### 3. Monitor Initial Runs

```bash
# Watch ThermostatController logs
make tail-thermostat

# Watch PeakManager logs
make tail-peak

# View all function logs
make logs-thermostat
make logs-peak
make logs-precool
make logs-eod
make logs-auth
```

## Function Details

### 1. ThermostatController

**Purpose:** Adjusts thermostat temperatures to reduce battery drain during peak periods

**Schedule:** Every 15 minutes during peak hours
- Summer: 2:00pm - 8:00pm (Mon-Fri)
- Winter: 5:00am - 9:00am, 5:00pm - 9:00pm (Mon-Fri)

**Mode Selection:**
- **Fixed Mode:** Uses battery threshold levels (50%, 35%, 20%)
- **Predictive Mode:** Uses analytics projections and recommendations

**Adjustment Logic (Fixed Mode):**
```
Battery ≤ 50% (first threshold):  +2°F adjustment
Battery ≤ 35% (second threshold): +2°F adjustment
Battery ≤ 20% (third threshold):  +4°F adjustment
```

**Adjustment Logic (Predictive Mode):**
```
Deficit > 10% from target: +4°F (CRITICAL)
Deficit > 5% from target:  +2°F (HIGH)
Deficit > 0% from target:  +2°F (MEDIUM)
Surplus > 10% from target: -2°F (restore comfort)
On target:                  0°F (no change)
```

**Commands:**
```bash
make invoke-thermostat  # Manual invocation
make logs-thermostat    # View logs (last 2 hours)
make tail-thermostat    # Real-time log monitoring
```

**Sample Response:**
```json
{
  "statusCode": 200,
  "body": {
    "message": "Thermostats adjusted successfully",
    "battery_percentage": 42.5,
    "adjustment": 2,
    "mode": "predictive",
    "new_status_level": 1,
    "devices_adjusted": 3
  }
}
```

### 2. PeakManager

**Purpose:** Manages Powerwall backup reserve based on time-of-use pricing

**Schedule:** Every 10 minutes (all day, every day)

**Reserve Logic:**
```
Peak Period:    0% reserve (allow full battery use)
Off-Peak:     100% reserve (charge battery, no discharge)
Holidays:     100% reserve (off-peak pricing)
Weekends:     100% reserve (off-peak pricing)
```

**Peak Hours:**
- **Summer (May-Oct):** 2:00pm - 8:00pm (Mon-Fri)
- **Winter Morning (Nov-Apr):** 5:00am - 9:00am (Mon-Fri)
- **Winter Evening (Nov-Apr):** 5:00pm - 9:00pm (Mon-Fri)

**Startup Buffer:** Starts 10 minutes before official peak period

**Commands:**
```bash
make invoke-peak     # Manual invocation
make logs-peak       # View logs
make tail-peak       # Real-time monitoring
```

**Sample Response:**
```json
{
  "statusCode": 200,
  "body": {
    "message": "Reserve changed successfully",
    "period": "ON-PEAK",
    "previous_reserve": 100,
    "new_reserve": 0
  }
}
```

### 3. PrecoolCheck

**Purpose:** Precools house before peak hours on hot days to reduce peak battery usage

**Schedule:** Daily at 7:00am local time

**Precool Conditions (OR logic):**
1. Forecasted high ≥ 105°F (configurable)
2. Battery level ≤ 90% (configurable)

**Action:** Sets all thermostats to 67°F (configurable) when conditions met

**Weather Source:** OpenWeather OneCall API (free tier: 1,000 calls/day)

**Commands:**
```bash
make invoke-precool  # Manual invocation
make logs-precool    # View logs
make tail-precool    # Real-time monitoring
```

**Sample Response:**
```json
{
  "statusCode": 200,
  "body": {
    "message": "Precool activated",
    "forecast_high": 107,
    "battery_percentage": 88,
    "precool_temp": 67,
    "reasons": [
      "Forecasted high of 107°F exceeds threshold of 105°F",
      "Battery level of 88% is below threshold of 90%"
    ],
    "devices_adjusted": 3
  }
}
```

### 4. EODStatus

**Purpose:** Sends daily status email and monitors for unexpected battery usage

**Schedule:** Daily at 9:00pm local time

**Status Report Includes:**
- Battery charge percentage
- Backup reserve setting
- Battery power (discharge/charge rate)
- Status interpretation

**Follow-up Check:**
If discharge > 1000W:
1. Wait 5 minutes
2. Re-check battery power
3. Send follow-up email with both readings

**Commands:**
```bash
make invoke-eod   # Manual invocation
make logs-eod     # View logs
make tail-eod     # Real-time monitoring
```

**Sample Email:**
```
Subject: Powerwall EOD Status

End of Day Status:

Battery Charge: 94%
Reserve Setting: 100%
Battery Power: -250W

→ Battery is discharging (normal off-peak)
```

**Sample Response:**
```json
{
  "statusCode": 200,
  "body": {
    "message": "EOD status sent",
    "battery_percentage": 94,
    "reserve_percent": 100,
    "battery_power": -250
  }
}
```

### 5. AuthRefresh

**Purpose:** Automatically refreshes Tesla authentication token before expiration

**Schedule:** Daily at 2:00am local time

**Refresh Threshold:** 15 days before expiration

**Process:**
1. Check token expiration from DynamoDB state
2. If < 15 days remaining: refresh using refresh_token
3. Store new token in DynamoDB
4. Send email notification (success or failure)

**Commands:**
```bash
make invoke-auth  # Manual invocation
make logs-auth    # View logs
make tail-auth    # Real-time monitoring
```

**Sample Response (No Refresh Needed):**
```json
{
  "statusCode": 200,
  "body": {
    "message": "Token still valid - no refresh needed",
    "expiry_date": "2025-12-15T10:30:00",
    "days_until_expiry": 28.5,
    "refresh_threshold_days": 15
  }
}
```

**Sample Response (Refreshed):**
```json
{
  "statusCode": 200,
  "body": {
    "message": "Token refreshed successfully",
    "old_expiry": "2025-12-05T10:30:00",
    "new_expiry": "2026-06-05T10:30:00",
    "days_until_expiry": 180
  }
}
```

## Configuration

### Adjustment Mode

Switch between fixed and predictive modes:

```bash
# Use fixed thresholds
aws ssm put-parameter \
  --name /powermgr/config/adjustment_mode \
  --value '{"mode": "fixed", "target_battery_minimum": 20, "enable_predictive_override": false}' \
  --type String \
  --overwrite

# Use predictive analytics
aws ssm put-parameter \
  --name /powermgr/config/adjustment_mode \
  --value '{"mode": "predictive", "target_battery_minimum": 20, "enable_predictive_override": false}' \
  --type String \
  --overwrite
```

### Precool Settings

```bash
aws ssm put-parameter \
  --name /powermgr/config/precool_settings \
  --value '{"temp": 67, "threshold": 90, "lat": 40.71, "lon": -74.00, "forecast_threshold": 105}' \
  --type String \
  --overwrite
```

### Timezone Adjustments

**IMPORTANT:** EventBridge schedules use UTC. Adjust cron schedules in `template.yaml` for your timezone.

Example for Pacific Time (UTC-8/-7):
```yaml
# 7am PST = 15:00 UTC (DST) or 14:00 UTC (standard)
Schedule: cron(0 15 * * ? *)  # Adjust for your timezone
```

## Monitoring & Alerts

### Email Notifications

Functions send SNS notifications for:

**Thermostat Controller:**
- Thermostat adjustments with details
- Grid usage alerts (> 500W)
- Errors

**Peak Manager:**
- Reserve changes (0% ↔ 100%)
- Verification failures
- Errors

**Precool Check:**
- Precool activation with reasons
- Weather API failures
- Errors

**EOD Status:**
- Daily status (always sent)
- Follow-up checks (if high discharge)
- Errors

**Auth Refresh:**
- Token refresh success
- Token refresh failures
- Token expiration warnings

### SNS Topic Configuration

Subscribe to notifications:

```bash
aws sns subscribe \
  --topic-arn $(aws cloudformation describe-stacks \
    --stack-name powermgr-prod \
    --query 'Stacks[0].Outputs[?OutputKey==`NotificationTopicArn`].OutputValue' \
    --output text) \
  --protocol email \
  --notification-endpoint your-email@example.com
```

Confirm subscription via email link.

### CloudWatch Logs

All functions log to CloudWatch with 7-day retention:

```bash
# View all log groups
aws logs describe-log-groups --log-group-name-prefix /aws/lambda/PowerMgr

# Query for errors across all functions
aws logs filter-log-events \
  --log-group-name /aws/lambda/PowerMgr-ThermostatController-prod \
  --filter-pattern "ERROR"
```

## Troubleshooting

### Thermostat Not Adjusting

**Check:**
1. Honeywell credentials in Parameter Store
2. Thermostat IDs in config
3. Peak period detection logic
4. Battery status in DynamoDB state

**Debug:**
```bash
# Check if in peak period
make invoke-peak

# Check battery level and analytics
make invoke-analytics

# Manually test thermostat control
make invoke-thermostat

# View detailed logs
make logs-thermostat
```

### Reserve Not Changing

**Check:**
1. Tesla token validity
2. Peak/off-peak schedule alignment
3. Timezone settings in cron schedules

**Debug:**
```bash
# Check current reserve
aws lambda invoke --function-name PowerMgr-PeakManager-prod response.json
cat response.json | jq .

# View recent reserve changes
make logs-peak
```

### Precool Not Triggering

**Check:**
1. OpenWeather API key
2. Lat/lon coordinates
3. Forecast threshold settings
4. Schedule time (UTC conversion)

**Debug:**
```bash
# Manually test precool
make invoke-precool

# Check weather API response in logs
make logs-precool
```

### Token Refresh Failing

**Check:**
1. Token in DynamoDB state (state_key='tesla_token')
2. Refresh token validity
3. Tesla API availability

**Debug:**
```bash
# Check token status
aws dynamodb get-item \
  --table-name PowerState-prod \
  --key '{"state_key": {"S": "tesla_token"}}'

# Manually test refresh
make invoke-auth

# View error details
make logs-auth
```

## Cost Analysis

**Phase 3 Lambda Invocations (Monthly):**
- ThermostatController: ~1,350 (15 min during peak)
- PeakManager: ~4,320 (every 10 min)
- PrecoolCheck: ~30 (daily)
- EODStatus: ~30 (daily)
- AuthRefresh: ~30 (daily)

**Total: ~5,760 invocations/month**

**Forever-Free Tier:**
- Lambda: 1,000,000 requests/month FREE
- CloudWatch Logs: 5GB ingestion/month FREE (7-day retention)
- SNS: 1,000 email notifications/month FREE

**Actual Cost: $0/month** (well within free tier limits)

## Testing Phase 3

### 1. Test Each Function Independently

```bash
# Test thermostat control
make invoke-thermostat
# Verify: Check email notification and thermostat temps

# Test peak management
make invoke-peak
# Verify: Check Powerwall app for reserve change

# Test precool logic
make invoke-precool
# Verify: Check weather forecast used and decision

# Test EOD status
make invoke-eod
# Verify: Receive status email

# Test auth refresh
make invoke-auth
# Verify: Check token expiration in logs
```

### 2. Monitor Scheduled Runs

```bash
# Watch ThermostatController during peak hours
make tail-thermostat

# Watch PeakManager every 10 minutes
make tail-peak

# Check EOD email arrives at 9pm
# Check Precool email arrives at 7am (if conditions met)
```

### 3. Validate Integration

```bash
# Verify battery status updates
aws dynamodb get-item \
  --table-name PowerState-prod \
  --key '{"state_key": {"S": "battery_status"}}'

# Check analytics → thermostat control flow
make invoke-analytics
sleep 60
make invoke-thermostat
```

## Success Criteria

**Phase 3 is successful when:**

1. ✅ Powerwall reserve changes automatically (0% peak, 100% off-peak)
2. ✅ Thermostats adjust during peak hours when battery is low
3. ✅ Precool activates on hot forecast days (if configured)
4. ✅ Daily EOD status email arrives at scheduled time
5. ✅ Tesla token refreshes automatically before expiration
6. ✅ Email notifications received for all important events
7. ✅ No errors in CloudWatch logs
8. ✅ Total cost remains $0/month

## Next Steps

After Phase 3 is validated:

**Phase 4 (Optional):** Weekly reporting and deeper analytics
- WeeklyReportFunction
- Cost savings calculations
- Performance metrics
- Monthly summaries

**Production Optimization:**
- Fine-tune adjustment thresholds based on actual usage
- Adjust timezone cron schedules for DST changes
- Add CloudWatch alarms for function failures
- Create dashboard for system visibility

## Related Documentation

- [Phase 1: Data Collection](../QUICKSTART.md)
- [Phase 2: Analytics](PHASE2.md)
- [Adjustment Modes](ADJUSTMENT_MODES.md)
- [Forever Free Architecture](FOREVER_FREE.md)
- [Configuration Guide](README.md#configuration)
