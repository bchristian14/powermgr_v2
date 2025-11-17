"""
Thermostat Controller Lambda Function
Adjusts thermostat temperatures based on battery levels and analytics
"""
import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional

# Import from Lambda Layer
from powermgr.config import get_config
from powermgr.tesla_client import TeslaClient
from powermgr.honeywell_client import HoneywellClient
from powermgr.state_manager import StateManager, AnalyticsManager
from powermgr.adjustment_engine import ThermostatAdjustmentEngine
from powermgr.notifications import NotificationManager

# Set up logging
logger = logging.getLogger()
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logger.setLevel(getattr(logging, log_level))

# Initialize clients (reused across invocations)
config = None
tesla_client = None
honeywell_client = None
state_manager = None
analytics_manager = None
adjustment_engine = None
notification_manager = None


def init_clients():
    """Initialize clients on cold start"""
    global config, tesla_client, honeywell_client, state_manager, analytics_manager, adjustment_engine, notification_manager

    if config is None:
        config = get_config()
        tesla_client = TeslaClient(config)
        honeywell_client = HoneywellClient(config)
        state_manager = StateManager()
        analytics_manager = AnalyticsManager()
        adjustment_engine = ThermostatAdjustmentEngine(config)
        notification_manager = NotificationManager(config)

    return config, tesla_client, honeywell_client, state_manager, analytics_manager, adjustment_engine, notification_manager


def lambda_handler(event, context):
    """
    Lambda handler for thermostat control

    Triggered every 15 minutes during peak hours to adjust thermostats
    based on battery level and/or analytics predictions

    Args:
        event: EventBridge scheduled event
        context: Lambda context

    Returns:
        Response dictionary
    """
    try:
        logger.info("Starting thermostat controller")

        # Initialize clients
        cfg, tesla, honeywell, state_mgr, analytics_mgr, adj_engine, notif_mgr = init_clients()

        # Check if in dry-run mode
        if cfg.dry_run:
            logger.warning("=" * 60)
            logger.warning("DRY-RUN MODE ENABLED - No actual thermostat changes will be made")
            logger.warning("=" * 60)

        # Get current battery status from Tesla
        logger.info("Getting current battery status from Tesla")
        status = tesla.get_live_status()
        battery_pct = status.get('percentage_charged', 0)
        grid_power = status.get('grid_power', 0)

        logger.info(f"Current battery: {battery_pct}%")

        # Check for unexpected grid usage
        if grid_power > 500:
            logger.warning(f"GRID USAGE DETECTED: {grid_power}W")
            notif_mgr.send_warning(
                subject="Grid Usage Alert",
                message=f"Unexpected grid usage detected: {grid_power}W\nBattery: {battery_pct}%"
            )

        # Get current battery status (state)
        current_status = state_mgr.get_state('battery_status')
        battery_status = current_status.get('status_level', 0) if current_status else 0

        logger.info(f"Current battery status level: {battery_status}")

        # Get latest analytics if in predictive mode
        analytics = None
        if cfg.adjustment_mode == 'predictive':
            logger.info("Predictive mode enabled - getting latest analytics")
            analytics = analytics_mgr.get_latest_analytics()

            if analytics:
                logger.info(f"Analytics: projected {analytics.get('projected_battery_at_peak_end', 0):.1f}% at peak end, "
                           f"recommendation: {analytics.get('recommended_temp_adjustment', 0)}°F")
            else:
                logger.warning("No analytics available - will use fixed mode as fallback")

        # Calculate adjustment using adjustment engine
        adjustment_result = adj_engine.calculate_adjustment(
            current_battery_pct=battery_pct,
            current_status=battery_status,
            analytics=analytics
        )

        logger.info(f"Adjustment calculation: {adjustment_result}")

        temp_adjustment = adjustment_result.get('adjustment', 0)
        new_status = adjustment_result.get('new_status', battery_status)
        mode_used = adjustment_result.get('mode_used', 'none')

        # Apply adjustment if needed
        if temp_adjustment != 0:
            logger.info(f"Adjusting thermostats by {temp_adjustment}°F (mode: {mode_used})")

            # Build notification message
            message = f"Battery: {battery_pct}%\n"
            message += f"Adjusting thermostats by {temp_adjustment}°F\n"
            message += f"Mode: {mode_used}\n"

            if analytics and mode_used == 'predictive':
                message += f"\nProjected battery at peak end: {analytics.get('projected_battery_at_peak_end', 0):.1f}%\n"
                message += f"Urgency: {analytics.get('urgency', 'N/A')}\n"
                message += f"Reason: {analytics.get('reason', 'N/A')}"

            # Adjust all thermostats
            results = honeywell.adjust_all_thermostats(temp_adjustment)

            # Add device details to message
            message += "\n\nThermostat adjustments:\n"
            for result in results:
                message += f"Device {result['device_id']}: {result['old_temp']}°F → {result['new_temp']}°F\n"

            # Update battery status state
            state_mgr.set_state('battery_status', {
                'status_level': new_status,
                'battery_percentage': battery_pct,
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'adjustment_made': temp_adjustment,
                'mode_used': mode_used
            })

            logger.info(f"Updated battery status to level {new_status}")

            # Send notification
            notif_mgr.send_info(
                subject="Thermostat Adjustment",
                message=message
            )

            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Thermostats adjusted successfully',
                    'battery_percentage': battery_pct,
                    'adjustment': temp_adjustment,
                    'mode': mode_used,
                    'new_status_level': new_status,
                    'devices_adjusted': len(results)
                })
            }
        else:
            logger.info("No adjustment needed")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'No adjustment needed',
                    'battery_percentage': battery_pct,
                    'status_level': battery_status,
                    'mode': mode_used
                })
            }

    except Exception as e:
        logger.exception(f"Thermostat controller failed: {e}")

        try:
            notif_mgr.send_warning(
                subject="Thermostat Controller Error",
                message=f"Failed to control thermostats:\n{str(e)}"
            )
        except:
            pass

        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Thermostat control failed',
                'message': str(e)
            })
        }
