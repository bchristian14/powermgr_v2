"""
Data Collector Lambda Function
Collects battery, solar, and grid metrics from Tesla API and stores in DynamoDB
Architecture: Forever-free AWS tier using DynamoDB only (no S3 costs)
"""
import json
import logging
import os
from datetime import datetime
from typing import Dict, Any

# Import from Lambda Layer
from powermgr.config import get_config
from powermgr.tesla_client import TeslaClient, TeslaAPIError
from powermgr.state_manager import MetricsManager
from powermgr.notifications import NotificationManager

# Set up logging
logger = logging.getLogger()
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logger.setLevel(getattr(logging, log_level))

# Initialize clients (reused across invocations)
config = None
tesla_client = None
metrics_manager = None
notification_manager = None


def init_clients():
    """Initialize clients on cold start"""
    global config, tesla_client, metrics_manager, notification_manager

    if config is None:
        config = get_config()
        tesla_client = TeslaClient(config)
        metrics_manager = MetricsManager()
        notification_manager = NotificationManager(config)

    return config, tesla_client, metrics_manager, notification_manager


def calculate_solar_factor(timestamp: datetime, latitude: float, longitude: float) -> float:
    """
    Calculate solar output factor based on time until sunset
    Returns 1.0 during full sun, decreasing to 0.0 at sunset

    Args:
        timestamp: Current time
        latitude: Site latitude
        longitude: Site longitude

    Returns:
        Solar factor (0.0 to 1.0)
    """
    try:
        # Simple calculation - in production, could use astral or similar library
        # For now, use a simple approximation based on time of day
        hour = timestamp.hour
        minute = timestamp.minute
        time_decimal = hour + minute / 60.0

        # Assume sunset around 18:00 (6 PM) - should be enhanced with actual sunset calculation
        # Solar starts degrading 2 hours before sunset
        sunset_time = 18.0
        degradation_start = sunset_time - 2.0

        if time_decimal < degradation_start:
            return 1.0
        elif time_decimal >= sunset_time:
            return 0.0
        else:
            # Linear degradation from 1.0 to 0.0 over 2 hours
            return 1.0 - ((time_decimal - degradation_start) / 2.0)

    except Exception as e:
        logger.warning(f"Failed to calculate solar factor: {e}")
        return 1.0  # Default to full sun if calculation fails


def get_peak_period(timestamp: datetime, config) -> str:
    """
    Determine current peak period

    Args:
        timestamp: Current time
        config: Configuration object

    Returns:
        Peak period string (e.g., 'summer_peak', 'winter_morning_peak', 'off_peak')
    """
    month = timestamp.month
    hour = timestamp.hour
    weekday = timestamp.weekday()  # 0 = Monday, 6 = Sunday

    # Check if weekend
    if weekday >= 5:  # Saturday or Sunday
        return 'off_peak_weekend'

    # Check if holiday
    date_str = timestamp.date().isoformat()
    if date_str in config.holidays:
        return 'off_peak_holiday'

    # Determine season and peak period
    if config.summer_first_month <= month <= config.summer_last_month:
        # Summer season
        if config.summer_peak_start <= hour < config.summer_peak_end:
            return 'summer_peak'
        else:
            return 'summer_off_peak'
    else:
        # Winter season
        if config.winter_morning_peak_start <= hour < config.winter_morning_peak_end:
            return 'winter_morning_peak'
        elif config.winter_evening_peak_start <= hour < config.winter_evening_peak_end:
            return 'winter_evening_peak'
        else:
            return 'winter_off_peak'


def calculate_minutes_until_peak_end(timestamp: datetime, peak_period: str, config) -> int:
    """
    Calculate minutes until current peak period ends

    Args:
        timestamp: Current time
        peak_period: Current peak period string
        config: Configuration object

    Returns:
        Minutes until peak end (0 if off-peak)
    """
    if 'off_peak' in peak_period or 'weekend' in peak_period or 'holiday' in peak_period:
        return 0

    hour = timestamp.hour
    minute = timestamp.minute
    current_minutes = hour * 60 + minute

    if peak_period == 'summer_peak':
        peak_end_minutes = config.summer_peak_end * 60
    elif peak_period == 'winter_morning_peak':
        peak_end_minutes = config.winter_morning_peak_end * 60
    elif peak_period == 'winter_evening_peak':
        peak_end_minutes = config.winter_evening_peak_end * 60
    else:
        return 0

    minutes_remaining = peak_end_minutes - current_minutes
    return max(0, minutes_remaining)


def enrich_metrics(raw_metrics: Dict[str, Any], config) -> Dict[str, Any]:
    """
    Enrich raw Tesla metrics with calculated fields

    Args:
        raw_metrics: Raw metrics from Tesla API
        config: Configuration object

    Returns:
        Enriched metrics dictionary
    """
    timestamp = datetime.fromisoformat(raw_metrics['timestamp'].replace('Z', '+00:00'))

    # Calculate additional fields
    peak_period = get_peak_period(timestamp, config)
    minutes_until_peak_end = calculate_minutes_until_peak_end(timestamp, peak_period, config)

    # Calculate solar factor (simplified - could be enhanced with actual sunset time)
    solar_factor = calculate_solar_factor(timestamp, config.latitude, config.longitude)

    # Add calculated fields
    enriched = raw_metrics.copy()
    enriched['peak_period'] = peak_period
    enriched['minutes_until_peak_end'] = minutes_until_peak_end
    enriched['solar_output_factor'] = solar_factor

    # Calculate approximate minutes until sunset (simplified)
    # In production, use astral or similar library
    hour = timestamp.hour
    estimated_sunset_hour = 18  # 6 PM approximation
    minutes_until_sunset = max(0, (estimated_sunset_hour - hour) * 60 - timestamp.minute)
    enriched['minutes_until_sunset'] = minutes_until_sunset

    return enriched


def lambda_handler(event, context):
    """
    Lambda handler for data collection

    Args:
        event: EventBridge scheduled event
        context: Lambda context

    Returns:
        Response dictionary
    """
    try:
        logger.info("Starting data collection")

        # Initialize clients
        cfg, tesla, metrics_mgr, notif_mgr = init_clients()

        # Collect metrics from Tesla API
        logger.info("Fetching battery metrics from Tesla API")
        raw_metrics = tesla.get_battery_metrics()

        # Enrich with calculated fields
        enriched_metrics = enrich_metrics(raw_metrics, cfg)

        logger.info(f"Collected metrics: Battery={enriched_metrics['battery_percentage']}%, "
                   f"Solar={enriched_metrics['solar_power']}W, "
                   f"Grid={enriched_metrics['grid_power']}W, "
                   f"Peak={enriched_metrics['peak_period']}")

        # Store in DynamoDB (with 1-year retention)
        logger.info("Storing metrics in DynamoDB")
        metrics_mgr.save_metrics(enriched_metrics)

        # Check for abnormal conditions
        check_for_alerts(enriched_metrics, cfg, notif_mgr)

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Data collection successful',
                'timestamp': enriched_metrics['timestamp'],
                'battery_percentage': enriched_metrics['battery_percentage'],
                'peak_period': enriched_metrics['peak_period']
            })
        }

    except TeslaAPIError as e:
        logger.error(f"Tesla API error: {e}")

        # Send notification for critical errors
        try:
            notif_mgr.send_warning(
                subject="Data Collection Failed - Tesla API Error",
                message=f"Failed to collect data from Tesla API:\n{str(e)}"
            )
        except:
            pass

        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Tesla API error',
                'message': str(e)
            })
        }

    except Exception as e:
        logger.exception(f"Unexpected error in data collection: {e}")

        # Send notification
        try:
            notif_mgr.send_warning(
                subject="Data Collection Failed - Unexpected Error",
                message=f"Data collection failed with unexpected error:\n{str(e)}"
            )
        except:
            pass

        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Internal error',
                'message': str(e)
            })
        }


def check_for_alerts(metrics: Dict[str, Any], config, notif_mgr: NotificationManager):
    """
    Check metrics for conditions that require alerts

    Args:
        metrics: Current metrics
        config: Configuration
        notif_mgr: Notification manager
    """
    try:
        # Check for unexpected grid usage during peak hours
        if 'peak' in metrics['peak_period'] and metrics['grid_power'] > 500:
            logger.warning(f"Grid usage detected during peak: {metrics['grid_power']}W")
            notif_mgr.send_warning(
                subject="Grid Usage During Peak Period",
                message=f"Grid usage detected: {metrics['grid_power']}W\n"
                       f"Battery: {metrics['battery_percentage']}%\n"
                       f"Solar: {metrics['solar_power']}W\n"
                       f"Time: {metrics['timestamp']}"
            )

        # Check for low battery during peak
        if 'peak' in metrics['peak_period'] and metrics['battery_percentage'] < 15:
            logger.warning(f"Low battery during peak: {metrics['battery_percentage']}%")
            notif_mgr.send_warning(
                subject="Low Battery During Peak Period",
                message=f"Battery critically low: {metrics['battery_percentage']}%\n"
                       f"Grid power: {metrics['grid_power']}W\n"
                       f"Time: {metrics['timestamp']}"
            )

    except Exception as e:
        logger.error(f"Failed to check for alerts: {e}")
        # Don't raise - alert checking failure shouldn't fail data collection
