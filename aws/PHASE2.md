# Phase 2: Analytics & Prediction Engine

This phase implements intelligent battery depletion prediction and proactive thermostat adjustment recommendations.

## Overview

**Status:** ✅ Complete and ready to deploy

The Analytics function runs every 15 minutes during peak hours to:
1. Query last 60 minutes of metrics from DynamoDB
2. Calculate battery depletion rate (kWh/hour)
3. Factor in sunset timing (solar degradation)
4. Project battery level at peak period end
5. Generate thermostat adjustment recommendations
6. Store results in PowerAnalyticsTable

---

## What's New in Phase 2

### **AnalyticsFunction Lambda**
- **Location:** `functions/analytics/handler.py`
- **Trigger:** EventBridge every 15 minutes during peak hours
- **Input:** Queries PowerMetricsTable for last 60 minutes
- **Output:** Stores analytics in PowerAnalyticsTable

### **Key Calculations**

#### 1. Battery Depletion Rate
```python
depletion_rate = (battery_start_kwh - battery_end_kwh) / hours_elapsed

Example:
- Start: 20 kWh (60 min ago)
- End: 17 kWh (now)
- Elapsed: 1 hour
- Rate: (20 - 17) / 1 = 3 kWh/hour
```

#### 2. Sunset Impact
```python
# Solar currently offsetting battery drain
solar_contribution = current_solar_power / 1000  # Convert W to kW

# After sunset, battery will drain faster by this amount
additional_drain = solar_contribution * hours_after_sunset

Example:
- Current solar: 2000W = 2 kWh/hour offset
- Sunset in 1 hour
- Peak ends in 3 hours
- Hours after sunset: 2 hours
- Additional drain: 2 kWh/hr * 2 hr = 4 kWh
```

#### 3. Battery Projection
```python
# Base projection using current rate
base_projection = current_battery - (depletion_rate * hours_remaining)

# Adjusted for sunset
adjusted_projection = base_projection - sunset_additional_drain

Example:
- Current: 18 kWh (50%)
- Depletion: 2 kWh/hr
- Hours remaining: 3
- Base: 18 - (2 * 3) = 12 kWh
- Sunset impact: -4 kWh
- Adjusted: 12 - 4 = 8 kWh (22%)
```

#### 4. Recommendation Logic
```python
deficit = target_minimum - projected_battery_pct

If deficit > 10%:   +4°F (CRITICAL)
If deficit > 5%:    +2°F (HIGH)
If deficit > 0%:    +2°F (MEDIUM)
If surplus > 10%:   -2°F (can restore comfort)
Else:               0°F (on target)
```

---

## Deployment

### Prerequisites

**Phase 1 must be deployed first:**
- DynamoDB tables created
- DataCollector running and collecting data
- At least 1 hour of metrics in PowerMetricsTable

### Deploy Phase 2

```bash
cd aws

# Build (includes new Analytics function)
sam build

# Deploy
sam deploy

# Verify deployment
aws lambda get-function --function-name PowerMgr-Analytics-prod
```

### Verify Analytics Function

```bash
# Manually invoke (must be during peak hours for meaningful results)
make invoke-analytics

# Expected output:
{
  "statusCode": 200,
  "body": {
    "message": "Analytics calculation successful",
    "timestamp": "2025-11-16T15:30:00Z",
    "projected_battery": 23.5,
    "recommendation": 2,
    "urgency": "MEDIUM"
  }
}

# View logs
make logs-analytics

# Tail logs in real-time
make tail-analytics
```

---

## Testing & Validation

### Test 1: Verify Data Collection (1 hour)

After deploying, wait 1 hour for data to accumulate:

```bash
# Check metrics count
aws dynamodb scan \
  --table-name PowerMetrics-prod \
  --select COUNT

# Should see 12+ items from last hour (5-min intervals during peak)
```

### Test 2: Manual Analytics Run

```bash
# Invoke analytics
make invoke-analytics

# Check PowerAnalyticsTable
aws dynamodb query \
  --table-name PowerAnalytics-prod \
  --key-condition-expression 'analysis_date = :date' \
  --expression-attribute-values '{":date": {"S": "'$(date +%Y-%m-%d)'"}}'
```

**Expected fields in result:**
- `depletion_rate_kwh_per_hour`
- `projected_battery_at_peak_end`
- `recommended_temp_adjustment`
- `confidence_score`
- `urgency`

### Test 3: Validate Predictions (1 day)

Run analytics for one full day, then compare:

```bash
# Export today's analytics
make export-json START=$(date +%Y-%m-%d) END=$(date +%Y-%m-%d) FILE=analytics.json

# Compare projected vs actual battery at peak end
python3 scripts/validate_predictions.py analytics.json
```

### Test 4: Different Scenarios

**Sunny Day (High Solar):**
- Depletion rate should be lower
- Sunset impact should be significant
- Projections optimistic early, then adjust after 6 PM

**Cloudy Day (Low Solar):**
- Depletion rate higher
- Sunset impact minimal
- Projections more pessimistic throughout

**Weekend/Holiday:**
- Analytics should skip (off-peak pricing)
- No recommendations needed

---

## Monitoring

### CloudWatch Metrics

```bash
# Invocation count (should be ~4 per hour during peak)
make lambda-stats

# Error rate (should be 0%)
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=PowerMgr-Analytics-prod \
  --start-time $(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 86400 \
  --statistics Sum
```

### Notification Alerts

Analytics sends alerts for:
- **CRITICAL urgency** - Projected battery < 10% below target
- **Function errors** - Any exception during calculation

### Confidence Scoring

Each analytics result includes a `confidence_score` (0.0 to 1.0):

- **0.0-0.3:** Low confidence (< 4 samples, high variance)
- **0.4-0.7:** Medium confidence (4-8 samples, moderate variance)
- **0.8-1.0:** High confidence (12+ samples, stable rate)

**Action:** Only trust recommendations with confidence > 0.6

---

## Configuration

### Adjustment Mode

Phase 2 analytics is ready but **not yet acting**. To use predictions:

```bash
# Still in fixed mode (Phase 1)
aws ssm get-parameter \
  --name /powermgr/config/adjustment_mode \
  --query 'Parameter.Value' --output text

# Returns: {"mode": "fixed", ...}
```

**Phase 3 will use these analytics** when ThermostatController is deployed.

For now, analytics runs and stores results but doesn't control thermostats yet.

### Target Battery Minimum

```bash
# Default: 20%
# Adjust if needed:
aws ssm put-parameter \
  --name '/powermgr/config/adjustment_mode' \
  --value '{"mode": "fixed", "target_battery_minimum": 25, "enable_predictive_override": false}' \
  --overwrite
```

This affects analytics recommendations (higher target = more aggressive recommendations).

---

## Sample Analytics Result

```json
{
  "timestamp": "2025-11-16T15:30:00Z",

  "current_battery_pct": 45.5,
  "current_battery_kwh": 16.4,
  "current_solar_power": 2500.0,
  "minutes_until_peak_end": 270,
  "minutes_until_sunset": 90,

  "depletion_rate_kwh_per_hour": 2.3,
  "depletion_rate_percent_per_hour": 6.4,
  "avg_battery_power": -2300.0,
  "avg_solar_power": 2450.0,
  "sample_count": 12,
  "confidence_score": 0.87,

  "solar_contribution_kwh_per_hour": 2.5,
  "additional_drain_after_sunset_kwh": 7.5,
  "solar_factor": 0.75,

  "projected_battery_at_peak_end": 18.2,
  "projected_battery_base": 25.7,
  "deficit_from_target": 1.8,

  "recommended_temp_adjustment": 2,
  "urgency": "MEDIUM",
  "reason": "Projected 18.2% is slightly below target",
  "target_battery_minimum": 20
}
```

**Interpretation:**
- Currently 45.5% battery
- Draining at 2.3 kWh/hr
- Solar contributing 2.5 kWh/hr (offsetting drain)
- Sunset in 90 min will add 7.5 kWh extra drain
- **Without sunset:** Would end at 25.7%
- **With sunset:** Will end at 18.2%
- **Recommendation:** +2°F to reduce drain slightly
- **Confidence:** 87% (high - trust this)

---

## Troubleshooting

### "No metrics available for analysis"

**Cause:** DynamoDB has no recent data

**Fix:**
```bash
# Check data exists
aws dynamodb scan --table-name PowerMetrics-prod --select COUNT

# If 0, DataCollector isn't running
make invoke  # Manually trigger collection
make logs    # Check for errors
```

### "Not in peak period, skipping analysis"

**Cause:** Running during off-peak hours

**Fix:** This is normal. Analytics only runs during peak hours when management is needed.

### "Sample count too low, confidence 0.2"

**Cause:** Not enough historical data (< 4 samples)

**Fix:** Wait longer. Need at least 20-30 minutes of data at 5-min intervals.

### Projected battery seems wrong

**Cause:** Unusual conditions or insufficient data

**Debug:**
```bash
# Check raw metrics
make export-csv START=$(date +%Y-%m-%d) END=$(date +%Y-%m-%d) FILE=debug.csv

# Look for:
# - Gaps in data collection
# - Sudden battery jumps
# - Negative solar (shouldn't happen)
# - Grid charging during peak (unusual)
```

### Critical alerts every 15 minutes

**Cause:** Target minimum set too high, or genuinely low battery

**Fix:**
```bash
# Lower target from 20% to 15%
aws ssm put-parameter \
  --name '/powermgr/config/adjustment_mode' \
  --value '{"mode": "fixed", "target_battery_minimum": 15, "enable_predictive_override": false}' \
  --overwrite

# Or investigate why battery is draining so fast
make export-csv START=$(date +%Y-%m-%d) END=$(date +%Y-%m-%d) FILE=investigation.csv
```

---

## Performance Expectations

### Accuracy

After 1 week of operation, projections should be accurate within:
- **±2%** on stable sunny days
- **±5%** on variable cloudy days
- **±8%** on unusual weather conditions

### Resource Usage

**Lambda:**
- Invocations: ~80-100/day (4 per hour × 5 peak hours)
- Duration: ~1-2 seconds per invocation
- Memory: < 128 MB
- Cost: $0 (well within free tier)

**DynamoDB:**
- PowerAnalytics writes: ~80-100/day
- PowerMetrics reads: ~12 items per analytics run
- Cost: $0 (within free tier)

---

## Next Steps

### Phase 3: Control (Use These Analytics!)

Once Phase 2 is validated:
1. Build ThermostatController (uses analytics recommendations)
2. Switch to predictive mode
3. Automate thermostat adjustments based on projections

### Phase 4: Reporting

- Weekly reports with prediction accuracy
- Trend analysis of depletion rates
- Sunset impact visualization

---

## FAQ

**Q: Why does analytics skip off-peak hours?**
A: No need to manage battery during off-peak (cheap electricity). Analytics only runs when it matters.

**Q: Can I run analytics more frequently than every 15 minutes?**
A: Yes, but not recommended. Needs 60 min of data for accurate calculations. Running every 5 min would just repeat with same data.

**Q: What if sunset time is wrong?**
A: Currently uses simplified 6 PM sunset. Phase 2.1 could add astral library for actual sunset times based on lat/lon.

**Q: Does this cost money?**
A: No! Analytics function is well within Lambda free tier (1M requests/month). Uses ~3K requests/month.

**Q: Can I test analytics during off-peak?**
A: Yes, via manual invocation (`make invoke-analytics`), but it will skip analysis. For real testing, invoke during actual peak hours.

---

## Success Criteria

Phase 2 is successful when:
- ✅ Analytics runs automatically every 15 min during peak
- ✅ Projections stored in DynamoDB
- ✅ Confidence scores consistently > 0.6
- ✅ Predictions within ±5% of actual battery at peak end
- ✅ No critical errors in CloudWatch logs
- ✅ Ready for Phase 3 (ThermostatController can query these results)

---

## Summary

**Phase 2 Status:** ✅ Complete

**What Works:**
- Battery depletion rate calculation
- Sunset-aware projections
- Recommendation generation
- Confidence scoring
- Automatic scheduling during peaks

**What's Next:**
- Deploy Phase 1 if not already done
- Wait 1-2 days for data collection
- Deploy Phase 2
- Validate predictions for 3-5 days
- Proceed to Phase 3 (ThermostatController)

**Cost:** $0/month (forever free)

Ready to deploy! 🚀
