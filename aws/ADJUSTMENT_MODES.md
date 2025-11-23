# Thermostat Adjustment Modes

The power management system supports two modes for determining thermostat adjustments:

## Mode Comparison

| Feature | Fixed Mode | Predictive Mode |
|---------|-----------|-----------------|
| **Decision Basis** | Current battery % | Projected battery at peak end |
| **Complexity** | Simple | Advanced |
| **Data Required** | Current battery only | 60 min of historical data |
| **Response Time** | Immediate | 15-minute lag (needs analytics) |
| **Accuracy** | Fixed thresholds | Dynamic based on conditions |
| **Best For** | Stable conditions | Variable solar/weather |
| **Status** | ✅ Available (Phase 1) | 🚧 Coming in Phase 2 |

---

## Fixed Mode (Current)

### How It Works

Uses three fixed battery percentage thresholds:

```
Battery Level    Action           Total Adjustment
───────────────────────────────────────────────────
> 50%           No adjustment    0°F
≤ 50%           +2°F             +2°F
≤ 35%           +2°F more        +4°F
≤ 20%           +4°F more        +8°F (critical)
```

### Pros
- ✅ Simple and predictable
- ✅ No dependency on analytics
- ✅ Works immediately
- ✅ Battle-tested (from Pi implementation)

### Cons
- ⚠️ Reactive (waits for battery to drop)
- ⚠️ Doesn't account for depletion rate
- ⚠️ Ignores sunset timing
- ⚠️ May adjust too late on fast drain days

### Configuration

```json
{
  "mode": "fixed",
  "target_battery_minimum": 20,
  "enable_predictive_override": false
}
```

**Battery Thresholds** (in `config/battery_thresholds`):
```json
{
  "first": 50,
  "second": 35,
  "third": 20
}
```

---

## Predictive Mode (Phase 2+)

### How It Works

Uses analytics to project battery level at peak end, then adjusts proactively:

```
1. Query last 60 minutes of metrics
2. Calculate battery depletion rate (kWh/hour)
3. Factor in sunset time (solar will stop contributing)
4. Project battery % at peak period end
5. Compare to target minimum (default: 20%)
6. Adjust thermostat based on deficit/surplus
```

### Decision Logic

```
Projected Battery    Deficit    Action
──────────────────────────────────────────────
> 30% (target +10%)  None      -2°F (restore comfort)
21-30%               0-10%     No change
15-20%               5-10%     +2°F
< 15%                > 10%     +4°F (aggressive)
```

### Pros
- ✅ Proactive (adjusts before battery drops)
- ✅ Accounts for depletion rate
- ✅ Factors in sunset timing
- ✅ Can restore comfort if projection improves
- ✅ More efficient battery usage

### Cons
- ⚠️ Requires 60 minutes of data
- ⚠️ More complex (can have bugs)
- ⚠️ Depends on analytics accuracy
- ⚠️ 15-minute lag (analytics cycle)

### Configuration

```json
{
  "mode": "predictive",
  "target_battery_minimum": 20,
  "enable_predictive_override": true
}
```

**With Override Enabled:**
- Uses predictive logic by default
- Falls back to fixed thresholds if predictive says "no adjustment"
- Provides safety net for edge cases

---

## Switching Between Modes

### Via AWS CLI

```bash
# Switch to fixed mode
aws ssm put-parameter \
  --name '/powermgr/config/adjustment_mode' \
  --value '{"mode": "fixed", "target_battery_minimum": 20, "enable_predictive_override": false}' \
  --type String \
  --overwrite

# Switch to predictive mode
aws ssm put-parameter \
  --name '/powermgr/config/adjustment_mode' \
  --value '{"mode": "predictive", "target_battery_minimum": 20, "enable_predictive_override": true}' \
  --type String \
  --overwrite

# Force Lambda to reload config
aws lambda invoke \
  --function-name PowerMgr-ThermostatController-prod \
  response.json
```

### Via AWS Console

1. Go to **AWS Systems Manager** → **Parameter Store**
2. Find `/powermgr/config/adjustment_mode`
3. Click **Edit**
4. Update JSON value
5. Save

Changes take effect on next Lambda invocation (within 15 minutes).

---

## Hybrid Mode (Predictive with Override)

Best of both worlds - recommended for most users:

```json
{
  "mode": "predictive",
  "target_battery_minimum": 20,
  "enable_predictive_override": true
}
```

**Behavior:**
1. Uses predictive logic primarily
2. If predictive says "no adjustment needed"...
3. But fixed thresholds say "adjust now"...
4. Apply the fixed threshold adjustment as safety measure

**Use Case:** You want smart predictions but don't trust them completely yet.

---

## Configuration Parameters

### `mode`
- **Type:** String
- **Options:** `"fixed"` or `"predictive"`
- **Default:** `"fixed"`
- **Description:** Primary adjustment mode

### `target_battery_minimum`
- **Type:** Number
- **Range:** 0-100
- **Default:** 20
- **Description:** Target minimum battery % at peak end
- **Used By:** Predictive mode only

### `enable_predictive_override`
- **Type:** Boolean
- **Default:** false
- **Description:** Allow fixed thresholds to override predictive decisions
- **Used By:** Predictive mode only

---

## Example Scenarios

### Scenario 1: Stable Sunny Day

**Fixed Mode:**
- 3:00 PM: Battery 60% → No adjustment
- 4:00 PM: Battery 48% → +2°F
- 5:00 PM: Battery 33% → +2°F more (+4°F total)
- 6:00 PM: Battery 18% → +4°F more (+8°F total) 😰

**Predictive Mode:**
- 3:00 PM: Battery 60%, projected 25% → No adjustment
- 4:00 PM: Battery 48%, projected 22% → No adjustment
- 5:00 PM: Battery 33%, projected 21% → No adjustment
- 6:00 PM: Battery 21%, projected 20% → Success! 🎉

**Winner:** Predictive (no adjustments needed, maintained comfort)

---

### Scenario 2: Cloudy Day (Fast Drain)

**Fixed Mode:**
- 3:00 PM: Battery 65% → No adjustment
- 4:00 PM: Battery 45% → +2°F (too late!)
- 5:00 PM: Battery 25% → +2°F more
- 6:00 PM: Battery 10% → Using grid! 😱

**Predictive Mode:**
- 3:00 PM: Battery 65%, projected 12% → +4°F immediately
- 4:00 PM: Battery 52%, projected 18% → +2°F more
- 5:00 PM: Battery 35%, projected 19% → No change
- 6:00 PM: Battery 22% → Success! 🎉

**Winner:** Predictive (proactive adjustment prevented grid usage)

---

### Scenario 3: Analytics Failure

**Fixed Mode:**
- Works normally (doesn't use analytics)

**Predictive Mode (without override):**
- Falls back to current battery % (degraded mode)
- Logs warning about missing analytics

**Predictive Mode (with override):**
- Falls back to fixed thresholds automatically
- Best safety net

**Winner:** Hybrid mode (predictive + override)

---

## Recommendations

### During Phase 1 (Data Collection Only)
```json
{"mode": "fixed", "target_battery_minimum": 20, "enable_predictive_override": false}
```
**Reason:** Predictive mode not yet implemented

### During Phase 2 Testing
```json
{"mode": "predictive", "target_battery_minimum": 20, "enable_predictive_override": true}
```
**Reason:** Test predictive with safety net

### After Phase 2 Validation
```json
{"mode": "predictive", "target_battery_minimum": 18, "enable_predictive_override": false}
```
**Reason:** Trust predictive, lower target for more comfort

### Conservative Users
```json
{"mode": "fixed", "target_battery_minimum": 25, "enable_predictive_override": false}
```
**Reason:** Prefer proven approach, higher safety margin

---

## Monitoring Mode Performance

### Check Current Mode

```bash
# View current configuration
aws ssm get-parameter \
  --name /powermgr/config/adjustment_mode \
  --query 'Parameter.Value' \
  --output text | jq .
```

### Analyze Performance

```bash
# Export last week's data
make export-csv START=2025-11-09 END=2025-11-16 FILE=performance.csv

# Look for:
# - Grid usage events (should be 0)
# - Battery % at peak end (should be > target)
# - Thermostat adjustments (fewer = better comfort)
```

### Compare Modes

1. Run **fixed mode** for 1 week
2. Export data: `make export-csv ...`
3. Switch to **predictive mode**
4. Run for 1 week
5. Export data: `make export-csv ...`
6. Compare:
   - Grid usage events
   - Average battery at peak end
   - Total temperature adjustments
   - Comfort (lower adjustments = better)

---

## Tuning Parameters

### Target Battery Minimum

**Conservative:** 25%
- More safety margin
- More frequent adjustments
- Less comfort

**Balanced:** 20% (default)
- Good balance
- Tested with Pi implementation

**Aggressive:** 15%
- Maximum comfort
- Less safety margin
- Requires accurate predictions

### Fixed Thresholds

**Default:** 50%, 35%, 20%

**For faster drain scenarios:**
- First: 60%
- Second: 45%
- Third: 30%

**For slower drain scenarios:**
- First: 40%
- Second: 25%
- Third: 15%

---

## Future Enhancements (Phase 4+)

### Machine Learning Mode
- Train model on historical performance
- Predict optimal adjustments based on:
  - Weather patterns
  - Day of week
  - Time of year
  - Home usage patterns

### Adaptive Mode
- Automatically tune thresholds
- Learn from performance
- Adjust target based on success rate

### Weather-Aware Mode
- Integrate weather forecast directly
- Preemptively adjust for cloudy days
- Reduce adjustments on optimal solar days

---

## Troubleshooting

### Predictive mode not working

1. Check analytics are running:
```bash
aws dynamodb query \
  --table-name PowerAnalytics-prod \
  --key-condition-expression 'analysis_date = :date' \
  --expression-attribute-values '{":date": {"S": "'$(date +%Y-%m-%d)'"}}'
```

2. Check for errors in AnalyticsFunction logs

3. Temporarily enable override:
```bash
aws ssm put-parameter \
  --name '/powermgr/config/adjustment_mode' \
  --value '{"mode": "predictive", "target_battery_minimum": 20, "enable_predictive_override": true}' \
  --overwrite
```

### Too many adjustments

- Increase `target_battery_minimum` to 25%
- Or switch to predictive mode (more efficient)

### Not enough adjustments (using grid)

- Decrease `target_battery_minimum` to 15%
- Or switch to fixed mode with higher thresholds

---

## Summary

- **Phase 1 (Now):** Use `fixed` mode
- **Phase 2 Testing:** Use `predictive` with `override` enabled
- **Phase 2 Production:** Use `predictive` with `override` disabled
- **Always:** Monitor weekly reports and tune as needed

The configuration is designed to be flexible - switch anytime without code changes! 🎉
