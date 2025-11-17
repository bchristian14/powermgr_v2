"""
End of Day Status Lambda Function
Sends daily status email with battery metrics and monitors for unexpected usage
"""
import json
import logging
import os
import time
from datetime import datetime
from typing import Dict, Any

# Import from Lambda Layer
from powermgr.config import get_config
from powermgr.tesla_client import TeslaClient
from powermgr.notifications import NotificationManager

# Set up logging
logger = logging.getLogger()
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logger.setLevel(getattr(logging, log_level))

# Initialize clients (reused across invocations)
config = None
tesla_client = None
notification_manager = None


def init_clients():
    """Initialize clients on cold start"""
    global config, tesla_client, notification_manager

    if config is None:
        config = get_config()
        tesla_client = TeslaClient(config)
        notification_manager = NotificationManager(config)

    return config, tesla_client, notification_manager


def lambda_handler(event, context):
    """
    Lambda handler for end-of-day status report

    Runs once daily (e.g., 9pm) to send status email with:
    - Current battery percentage
    - Backup reserve setting
    - Battery discharge rate
    - Follow-up check if high discharge detected

    Args:
        event: EventBridge scheduled event
        context: Lambda context

    Returns:
        Response dictionary
    """
    try:
        logger.info("Starting EOD status check")

        # Initialize clients
        cfg, tesla, notif_mgr = init_clients()

        # Get current status
        logger.info("Getting EOD battery status from Tesla")
        status = tesla.get_live_status()
        battery_pct = status.get('percentage_charged', 0)
        battery_power = status.get('battery_power', 0)  # Negative = discharging

        logger.info(f"EOD Charge: {battery_pct}%")
        logger.info(f"EOD Battery Power: {battery_power}W")

        # Get site info for reserve setting
        site_info = tesla.get_site_info()
        reserve_pct = site_info.get('backup_reserve_percent', 0)

        logger.info(f"EOD Reserve Setting: {reserve_pct}%")

        # Build status message
        message = f"End of Day Status:\n\n"
        message += f"Battery Charge: {battery_pct}%\n"
        message += f"Reserve Setting: {reserve_pct}%\n"
        message += f"Battery Power: {battery_power}W\n"

        # Add interpretation
        if battery_power < -1000:
            message += f"\n⚠ High discharge rate detected ({abs(battery_power)}W)"
        elif battery_power > 1000:
            message += f"\n✓ Battery is charging ({battery_power}W)"
        elif battery_power < 0:
            message += f"\n→ Battery is discharging (normal off-peak)"
        else:
            message += f"\n→ Battery is idle"

        # Send EOD status email
        notif_mgr.send_info(
            subject="Powerwall EOD Status",
            message=message
        )

        logger.info("EOD status email sent")

        # Check if battery discharge is unexpectedly high (> 1000W)
        if battery_power < -1000:
            logger.warning(f"Unexpected high battery usage detected: {abs(battery_power)}W")
            logger.info("Waiting 5 minutes for follow-up check...")

            # Wait 5 minutes
            time.sleep(300)

            # Re-check battery power
            logger.info("Performing 5-minute follow-up check")
            status_followup = tesla.get_live_status()
            battery_power_followup = status_followup.get('battery_power', 0)
            battery_pct_followup = status_followup.get('percentage_charged', 0)

            logger.info(f"Follow-up Battery Power: {battery_power_followup}W")
            logger.info(f"Follow-up Battery Charge: {battery_pct_followup}%")

            # Send follow-up email
            followup_message = f"5-Minute Follow-up Check:\n\n"
            followup_message += f"Initial discharge: {abs(battery_power)}W\n"
            followup_message += f"Follow-up discharge: {abs(battery_power_followup)}W\n"
            followup_message += f"Battery level: {battery_pct_followup}%\n\n"

            if battery_power_followup < -1000:
                followup_message += "⚠ High discharge continues - investigate usage"
            elif battery_power_followup < 0:
                followup_message += "→ Discharge reduced to normal level"
            else:
                followup_message += "✓ Discharge stopped"

            notif_mgr.send_info(
                subject="Powerwall Follow-up Check",
                message=followup_message
            )

            logger.info("Follow-up check email sent")

            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'EOD status sent with follow-up check',
                    'battery_percentage': battery_pct,
                    'reserve_percent': reserve_pct,
                    'battery_power': battery_power,
                    'followup_battery_power': battery_power_followup,
                    'followup_battery_percentage': battery_pct_followup
                })
            }
        else:
            logger.info("No follow-up check needed")

            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'EOD status sent',
                    'battery_percentage': battery_pct,
                    'reserve_percent': reserve_pct,
                    'battery_power': battery_power
                })
            }

    except Exception as e:
        logger.exception(f"EOD status check failed: {e}")

        try:
            notif_mgr.send_warning(
                subject="EOD Status Check Error",
                message=f"Failed to get EOD status:\n{str(e)}"
            )
        except:
            pass

        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'EOD status check failed',
                'message': str(e)
            })
        }
