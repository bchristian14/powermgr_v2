# Dry-Run Mode

Dry-run mode allows you to safely test the power management system's decision-making logic **without actually controlling** your thermostats or Powerwall. All calculations, analytics, and control decisions run normally, but the actual API calls to change settings are skipped and logged instead.

## What Dry-Run Mode Does

When dry-run mode is enabled:

✅ **Still Happens:**
- Data collection from Tesla API (read-only)
- Battery status monitoring
- Analytics and projections
- Thermostat adjustment calculations
- Peak period detection
- Precool decision logic
- Weekly reports
- Email notifications

🚫 **Skipped (Logged Only):**
- Powerwall reserve changes (0% ↔ 100%)
- Thermostat temperature adjustments
- Precool temperature settings

## When to Use Dry-Run Mode

**Recommended for:**
- Initial system deployment and testing
- Verifying logic before going live
- Testing configuration changes
- Debugging issues without affecting comfort
- Understanding system behavior before trusting it
- Seasonal transitions (testing summer → winter logic)

**Not needed for:**
- Data collection and analytics (already read-only)
- Weekly reports (no control actions)

## Enabling Dry-Run Mode

### Option 1: Set via AWS CLI (Recommended)

```bash
aws ssm put-parameter \
  --name /powermgr/config/dry_run \
  --value "true" \
  --type String \
  --overwrite
```

### Option 2: Set via AWS Console

1. Open AWS Systems Manager Console
2. Navigate to **Parameter Store**
3. Create/Update parameter:
   - **Name:** `/powermgr/config/dry_run`
   - **Type:** String
   - **Value:** `true`

### Accepted Values

- **Enable:** `true`, `True`, `1`, `yes`, `Yes`
- **Disable:** `false`, `False`, `0`, `no`, `No`, or omit parameter

## Disabling Dry-Run Mode

When you're ready to let the system make actual changes:

```bash
aws ssm put-parameter \
  --name /powermgr/config/dry_run \
  --value "false" \
  --type String \
  --overwrite
```

**Or delete the parameter entirely:**

```bash
aws ssm delete-parameter --name /powermgr/config/dry_run
```

## Verifying Dry-Run Status

### Check Parameter Value

```bash
aws ssm get-parameter --name /powermgr/config/dry_run --query 'Parameter.Value' --output text
```

### Check in Logs

When dry-run mode is active, you'll see clear indicators in CloudWatch logs:

```
============================================================
DRY-RUN MODE ENABLED - No actual thermostat changes will be made
============================================================
```

And for each skipped action:

```
[DRY-RUN] Would set backup reserve to 0% (skipped)
[DRY-RUN] Payload would be: {"backup_reserve_percent": 0.0}
```

```
[DRY-RUN] Would set device 1234567 to 73°F (skipped)
[DRY-RUN] Data would be: {'SystemSwitch': None, 'CoolSetpoint': 73, ...}
```

## Testing Workflow

### 1. Initial Deployment

```bash
# Enable dry-run mode
aws ssm put-parameter \
  --name /powermgr/config/dry_run \
  --value "true" \
  --type String \
  --overwrite

# Deploy the system
cd aws
make deploy

# Test each control function
make invoke-thermostat
make invoke-peak
make invoke-precool
```

### 2. Monitor Logs

```bash
# Watch thermostat controller
make tail-thermostat

# Watch peak manager
make tail-peak

# You should see [DRY-RUN] messages instead of actual changes
```

### 3. Verify Logic

Check that the system makes the **right decisions**:

```bash
# View logs for decision logic
make logs-thermostat

# Look for:
# - Correct battery threshold detection
# - Appropriate temperature adjustments
# - Proper peak/off-peak detection
```

### 4. Let Run for 24-48 Hours

Monitor dry-run mode for a full day or two to see how the system would behave across different scenarios:

```bash
# Check what actions would have been taken
aws logs filter-log-events \
  --log-group-name /aws/lambda/PowerMgr-ThermostatController-prod \
  --filter-pattern "[DRY-RUN]" \
  --start-time $(date -u -d '24 hours ago' +%s)000
```

### 5. Disable and Go Live

Once confident in the system's decisions:

```bash
# Disable dry-run mode
aws ssm put-parameter \
  --name /powermgr/config/dry_run \
  --value "false" \
  --type String \
  --overwrite

# Functions will pick up the change on next invocation (< 5 minutes)
# OR force immediate reload by redeploying
make deploy
```

## Dry-Run Indicators by Function

### ThermostatController

**Dry-Run:**
```
[DRY-RUN] Would set device 1234567 to 75°F (skipped)
```

**Live:**
```
Setting device 1234567 to 75°F
Successfully set device 1234567 to 75°F
```

### PeakManager

**Dry-Run:**
```
[DRY-RUN] Would set backup reserve to 0% (skipped)
```

**Live:**
```
Setting backup reserve to 0%
Successfully set backup reserve to 0%
```

### PrecoolCheck

**Dry-Run:**
```
[DRY-RUN] Would set device 1234567 to 67°F (skipped)
```

**Live:**
```
Setting device 1234567 to 67°F
Successfully set device 1234567 to 67°F
```

## Impact on Other Functions

| Function | Affected by Dry-Run? | Notes |
|----------|---------------------|-------|
| DataCollector | ❌ No | Read-only data collection always runs |
| Analytics | ❌ No | Calculations always run normally |
| ThermostatController | ✅ Yes | Skips thermostat API calls |
| PeakManager | ✅ Yes | Skips reserve API calls |
| PrecoolCheck | ✅ Yes | Skips thermostat API calls |
| EODStatus | ❌ No | Read-only status reporting |
| AuthRefresh | ❌ No | Token refresh always runs |
| WeeklyReport | ❌ No | Read-only reporting |

## Troubleshooting

### Dry-Run Not Working (Still Making Changes)

**Check:**
1. Parameter value is exactly `true` (case-insensitive)
2. Parameter path is `/powermgr/config/dry_run`
3. Lambda functions have been invoked after parameter change
4. No typos in parameter name

**Debug:**
```bash
# Verify parameter
aws ssm get-parameter --name /powermgr/config/dry_run

# Check function logs
make logs-thermostat | grep -i "dry"

# Force reload by redeploying
make deploy
```

### Can't Find Dry-Run Messages in Logs

**Check:**
1. Dry-run mode is actually enabled
2. Control functions are being triggered (check schedules)
3. Conditions for actions are met (battery low, peak period, etc.)

**Debug:**
```bash
# Manually invoke to see dry-run messages
make invoke-thermostat
make logs-thermostat

# Look for the dry-run banner
make logs-thermostat | grep "DRY-RUN MODE ENABLED"
```

### Want to Test Specific Scenario

**Temporarily modify thresholds:**

```bash
# Lower battery threshold to trigger adjustments
aws ssm put-parameter \
  --name /powermgr/config/battery_thresholds \
  --value '{"first": 80, "second": 60, "third": 40}' \
  --type String \
  --overwrite

# Enable dry-run
aws ssm put-parameter \
  --name /powermgr/config/dry_run \
  --value "true" \
  --type String \
  --overwrite

# Invoke and watch logs
make invoke-thermostat
make logs-thermostat

# Restore original thresholds
aws ssm put-parameter \
  --name /powermgr/config/battery_thresholds \
  --value '{"first": 50, "second": 35, "third": 20}' \
  --type String \
  --overwrite
```

## Best Practices

1. **Always start with dry-run enabled** for new deployments
2. **Run for 24-48 hours** before going live to see full day/night cycle
3. **Check logs daily** during dry-run period
4. **Test edge cases** by temporarily adjusting thresholds
5. **Keep dry-run enabled** when making major configuration changes
6. **Document** when you disable dry-run mode
7. **Re-enable dry-run** if suspicious behavior occurs

## Performance Impact

Dry-run mode has **zero performance impact**:
- Same Lambda execution time
- Same number of invocations
- Same DynamoDB operations
- Same CloudWatch logs (slightly more verbose)
- Same cost ($0/month)

The only difference is skipping the final API call to Honeywell/Tesla.

## Examples

### Example 1: Initial Testing

```bash
# Day 1: Deploy with dry-run
aws ssm put-parameter --name /powermgr/config/dry_run --value "true" --type String
make deploy

# Day 1-2: Monitor logs
make tail-thermostat &
make tail-peak &

# Day 3: Review 48 hours of decisions
aws logs filter-log-events \
  --log-group-name /aws/lambda/PowerMgr-ThermostatController-prod \
  --filter-pattern "[DRY-RUN]" \
  --start-time $(date -u -d '48 hours ago' +%s)000

# Day 3: Go live if comfortable
aws ssm put-parameter --name /powermgr/config/dry_run --value "false" --type String --overwrite
```

### Example 2: Testing Configuration Change

```bash
# Enable dry-run before changing mode
aws ssm put-parameter --name /powermgr/config/dry_run --value "true" --type String --overwrite

# Change from fixed to predictive mode
aws ssm put-parameter \
  --name /powermgr/config/adjustment_mode \
  --value '{"mode": "predictive", "target_battery_minimum": 20, "enable_predictive_override": false}' \
  --type String \
  --overwrite

# Test for 24 hours
make tail-thermostat

# Verify predictive logic works as expected
make logs-analytics
make logs-thermostat

# Disable dry-run when confident
aws ssm put-parameter --name /powermgr/config/dry_run --value "false" --type String --overwrite
```

### Example 3: Debugging Issue

```bash
# Something went wrong - enable dry-run immediately
aws ssm put-parameter --name /powermgr/config/dry_run --value "true" --type String --overwrite

# Investigate logs without affecting house
make logs-thermostat
make logs-peak

# Make fixes, test with dry-run
make deploy
make invoke-thermostat

# Disable dry-run once fixed
aws ssm put-parameter --name /powermgr/config/dry_run --value "false" --type String --overwrite
```

## Related Documentation

- [Configuration Guide](README.md#configuration)
- [Phase 3: Control Functions](PHASE3.md)
- [Troubleshooting](PHASE3.md#troubleshooting)
- [Adjustment Modes](ADJUSTMENT_MODES.md)
