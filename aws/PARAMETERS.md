# Power Management System - Parameter Reference

Complete list of all AWS Systems Manager Parameter Store parameters with examples.

## Quick Setup Commands

Copy these commands and replace the placeholder values with your actual data:

```bash
# Set AWS region for all commands
export AWS_DEFAULT_REGION=us-west-2

# ============================================
# Configuration Parameters (Non-Sensitive)
# ============================================

# Battery Thresholds - When to adjust thermostat based on battery level
aws ssm put-parameter \
  --name /powermgr/config/battery_thresholds \
  --value '{"first":50,"second":35,"third":20}' \
  --type String \
  --overwrite

# Peak Hours - When electricity rates are highest
aws ssm put-parameter \
  --name /powermgr/config/peak_hours \
  --value '{"summer":{"first_month":5,"last_month":10,"peak_start":14,"peak_end":20},"winter":{"morning_peak_start":5,"morning_peak_end":9,"evening_peak_start":17,"evening_peak_end":21}}' \
  --type String \
  --overwrite

# Holidays - Dates with off-peak pricing (update annually)
aws ssm put-parameter \
  --name /powermgr/config/holidays \
  --value '["2025-01-01","2025-05-26","2025-07-04","2025-09-01","2025-11-27","2025-12-25"]' \
  --type String \
  --overwrite

# Notification Emails - Where to send alerts
aws ssm put-parameter \
  --name /powermgr/config/notification_emails \
  --value '["your-email@example.com"]' \
  --type String \
  --overwrite

# Adjustment Mode - How thermostat adjustments are calculated
aws ssm put-parameter \
  --name /powermgr/config/adjustment_mode \
  --value '{"mode":"fixed","target_battery_minimum":20,"enable_predictive_override":false}' \
  --type String \
  --overwrite

# Dry-Run Mode - IMPORTANT: Start with "true" for testing!
aws ssm put-parameter \
  --name /powermgr/config/dry_run \
  --value "true" \
  --type String \
  --overwrite

# ============================================
# Secret Parameters (Encrypted/Sensitive)
# ============================================

# Tesla Access Token (get from Tesla API authentication)
aws ssm put-parameter \
  --name /powermgr/secrets/tesla/access_token \
  --value "YOUR_TESLA_ACCESS_TOKEN" \
  --type SecureString \
  --overwrite

# Tesla Refresh Token (get from Tesla API authentication)
aws ssm put-parameter \
  --name /powermgr/secrets/tesla/refresh_token \
  --value "YOUR_TESLA_REFRESH_TOKEN" \
  --type SecureString \
  --overwrite

# Honeywell Username
aws ssm put-parameter \
  --name /powermgr/secrets/honeywell/username \
  --value "your-honeywell-email@example.com" \
  --type SecureString \
  --overwrite

# Honeywell Password
aws ssm put-parameter \
  --name /powermgr/secrets/honeywell/password \
  --value "your-honeywell-password" \
  --type SecureString \
  --overwrite

# OpenWeather API Key (get from https://openweathermap.org/api)
aws ssm put-parameter \
  --name /powermgr/secrets/openweather/api_key \
  --value "YOUR_OPENWEATHER_API_KEY" \
  --type SecureString \
  --overwrite

# Gmail Username (optional, for email reports)
aws ssm put-parameter \
  --name /powermgr/secrets/gmail/username \
  --value "your-gmail@gmail.com" \
  --type SecureString \
  --overwrite

# Gmail App Password (optional, NOT your regular password)
# Generate at: https://myaccount.google.com/apppasswords
aws ssm put-parameter \
  --name /powermgr/secrets/gmail/password \
  --value "your-gmail-app-password" \
  --type SecureString \
  --overwrite
```

---

## Parameter Details

### Already Configured (You Set These)

#### `/powermgr/config/tesla/energy_site_id`
**Type:** String
**Example:** `"1234567890123"`
**Description:** Your Tesla Powerwall site ID from the Tesla app

#### `/powermgr/config/thermostat_settings`
**Type:** String (JSON)
**Example:**
```json
{
  "ids": ["12345678", "87654321"],
  "base_url": "https://www.mytotalconnectcomfort.com/portal"
}
```
**Description:** Honeywell thermostat device IDs and API URL

#### `/powermgr/config/precool_settings`
**Type:** String (JSON)
**Example:**
```json
{
  "temp": 67,
  "threshold": 90,
  "lat": 33.4484,
  "lon": -112.0740,
  "forecast_threshold": 105
}
```
**Description:**
- `temp`: Target temperature for precooling (°F)
- `threshold`: Start precooling when forecast reaches this temp (°F)
- `lat/lon`: Your location coordinates for weather forecasts
- `forecast_threshold`: Extreme heat threshold (°F)

---

### Need to Configure

#### `/powermgr/config/battery_thresholds`
**Type:** String (JSON)
**Example:**
```json
{
  "first": 50,
  "second": 35,
  "third": 20
}
```
**Description:** Battery percentage thresholds for thermostat adjustments
- `first` (50%): First threshold - slight adjustment
- `second` (35%): Second threshold - moderate adjustment
- `third` (20%): Third threshold - aggressive adjustment

---

#### `/powermgr/config/peak_hours`
**Type:** String (JSON)
**Example:**
```json
{
  "summer": {
    "first_month": 5,
    "last_month": 10,
    "peak_start": 14,
    "peak_end": 20
  },
  "winter": {
    "morning_peak_start": 5,
    "morning_peak_end": 9,
    "evening_peak_start": 17,
    "evening_peak_end": 21
  }
}
```
**Description:** When peak electricity rates apply
- Summer: May (5) through October (10), 2pm-8pm (14-20)
- Winter: 5am-9am and 5pm-9pm

**Customize for your utility:**
- Arizona (APS): Summer 3pm-8pm weekdays
- California (PG&E): 4pm-9pm all year
- Texas (various): Check your TOU plan

---

#### `/powermgr/config/holidays`
**Type:** String (JSON array)
**Example:**
```json
[
  "2025-01-01",
  "2025-05-26",
  "2025-07-04",
  "2025-09-01",
  "2025-11-27",
  "2025-12-25"
]
```
**Description:** Dates when off-peak rates apply all day (format: YYYY-MM-DD)
**Update annually** with your utility's holiday schedule

---

#### `/powermgr/config/notification_emails`
**Type:** String (JSON array)
**Example:**
```json
["you@example.com", "partner@example.com"]
```
**Description:** Email addresses to receive alerts and reports

---

#### `/powermgr/config/adjustment_mode`
**Type:** String (JSON)
**Example:**
```json
{
  "mode": "fixed",
  "target_battery_minimum": 20,
  "enable_predictive_override": false
}
```
**Description:** How thermostat adjustments are calculated
- `mode`: "fixed" (threshold-based) or "predictive" (ML-based)
- `target_battery_minimum`: Target battery % at end of peak period
- `enable_predictive_override`: Allow ML to override thresholds

**Recommendation:** Start with "fixed" mode, switch to "predictive" after 2+ weeks of data

---

#### `/powermgr/config/dry_run`
**Type:** String
**Example:** `"true"` or `"false"`
**Description:** Testing mode - logs actions without executing them
**IMPORTANT:** Always start with `"true"` for 24-48 hours of testing!

---

### Secret Parameters (Encrypted)

#### `/powermgr/secrets/tesla/access_token`
**Type:** SecureString
**How to get:** Use Tesla API authentication flow (see CREDENTIALS.md)
**Note:** Refreshed automatically by AuthRefresh Lambda

#### `/powermgr/secrets/tesla/refresh_token`
**Type:** SecureString
**How to get:** Use Tesla API authentication flow (see CREDENTIALS.md)
**Note:** Long-lived token for automatic refresh

#### `/powermgr/secrets/honeywell/username`
**Type:** SecureString
**Example:** `"your-email@example.com"`
**Description:** Your Honeywell Total Connect username

#### `/powermgr/secrets/honeywell/password`
**Type:** SecureString
**Description:** Your Honeywell Total Connect password

#### `/powermgr/secrets/openweather/api_key`
**Type:** SecureString
**How to get:**
1. Sign up at https://openweathermap.org/api
2. Free tier includes 1,000 calls/day (plenty for our needs)
3. Get API key from dashboard

#### `/powermgr/secrets/gmail/username` (Optional)
**Type:** SecureString
**Example:** `"yourname@gmail.com"`
**Note:** Only needed if using Gmail for weekly reports (SNS is recommended instead)

#### `/powermgr/secrets/gmail/password` (Optional)
**Type:** SecureString
**How to get:** Generate App Password at https://myaccount.google.com/apppasswords
**IMPORTANT:** Use App Password, NOT your regular Gmail password

---

## Verification

After setting parameters, verify they're all configured:

```bash
cd ~/git/powermgr_v2/aws
python3 scripts/setup_parameters.py --verify
```

Should show all parameters as "✓ Configured"

---

## Quick Fill Script

Want to set all missing parameters at once? Save this as `set-params.sh`:

```bash
#!/bin/bash
# Fill in your actual values below, then run: bash set-params.sh

export AWS_DEFAULT_REGION=us-west-2

# Required: Fill these in
TESLA_ACCESS_TOKEN="YOUR_TOKEN_HERE"
TESLA_REFRESH_TOKEN="YOUR_TOKEN_HERE"
HONEYWELL_USERNAME="your-email@example.com"
HONEYWELL_PASSWORD="your-password"
OPENWEATHER_API_KEY="your-api-key"
YOUR_EMAIL="your-email@example.com"

# Configuration parameters
aws ssm put-parameter --name /powermgr/config/battery_thresholds --value '{"first":50,"second":35,"third":20}' --type String --overwrite
aws ssm put-parameter --name /powermgr/config/peak_hours --value '{"summer":{"first_month":5,"last_month":10,"peak_start":14,"peak_end":20},"winter":{"morning_peak_start":5,"morning_peak_end":9,"evening_peak_start":17,"evening_peak_end":21}}' --type String --overwrite
aws ssm put-parameter --name /powermgr/config/holidays --value '["2025-01-01","2025-05-26","2025-07-04","2025-09-01","2025-11-27","2025-12-25"]' --type String --overwrite
aws ssm put-parameter --name /powermgr/config/notification_emails --value "[\"$YOUR_EMAIL\"]" --type String --overwrite
aws ssm put-parameter --name /powermgr/config/adjustment_mode --value '{"mode":"fixed","target_battery_minimum":20,"enable_predictive_override":false}' --type String --overwrite

# Secret parameters
aws ssm put-parameter --name /powermgr/secrets/tesla/access_token --value "$TESLA_ACCESS_TOKEN" --type SecureString --overwrite
aws ssm put-parameter --name /powermgr/secrets/tesla/refresh_token --value "$TESLA_REFRESH_TOKEN" --type SecureString --overwrite
aws ssm put-parameter --name /powermgr/secrets/honeywell/username --value "$HONEYWELL_USERNAME" --type SecureString --overwrite
aws ssm put-parameter --name /powermgr/secrets/honeywell/password --value "$HONEYWELL_PASSWORD" --type SecureString --overwrite
aws ssm put-parameter --name /powermgr/secrets/openweather/api_key --value "$OPENWEATHER_API_KEY" --type SecureString --overwrite

echo "✓ All parameters configured!"
echo "Run: python3 scripts/setup_parameters.py --verify"
```

---

## See Also

- `CREDENTIALS.md` - How to get Tesla API tokens
- `QUICKSTART.md` - Full setup guide
- `DRY_RUN.md` - Testing in dry-run mode
