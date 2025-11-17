"""
Peak Manager Lambda Function
Manages Powerwall backup reserve based on peak/off-peak hours
"""
import json
import logging
import os
from datetime import datetime, timedelta
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


def is_peak_period(current_time: datetime, cfg) -> bool:
    """
    Determine if current time is in peak period

    Args:
        current_time: Current datetime
        cfg: Configuration object

    Returns:
        True if in peak period, False otherwise
    """
    # Check if it's a holiday
    date_str = current_time.strftime('%Y-%m-%d')
    if date_str in cfg.holidays:
        logger.info(f"Today ({date_str}) is a pricing holiday - OFF-PEAK")
        return False

    # Check if it's a weekday (Monday=0, Sunday=6)
    if current_time.weekday() >= 5:  # Saturday or Sunday
        logger.info("Weekend - OFF-PEAK")
        return False

    # Determine season
    current_month = current_time.month
    is_summer = cfg.summer_first_month <= current_month <= cfg.summer_last_month
    season = "summer" if is_summer else "winter"

    current_hour = current_time.hour
    current_minute = current_time.minute

    if is_summer:
        # Summer peak: 2pm-8pm (14:00-20:00)
        # Start 10 minutes early
        peak_start_hour = cfg.summer_peak_start
        peak_end_hour = cfg.summer_peak_end

        # Adjust for 10-minute early start
        start_time = datetime(current_time.year, current_time.month, current_time.day,
                             peak_start_hour, 0) - timedelta(minutes=10)
        end_time = datetime(current_time.year, current_time.month, current_time.day,
                           peak_end_hour, 0)

        is_peak = start_time.time() <= current_time.time() < end_time.time()

        logger.info(f"Season: SUMMER, Peak hours: {start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')}, "
                   f"Current: {current_time.strftime('%H:%M')}, Is Peak: {is_peak}")

        return is_peak

    else:
        # Winter has two peak periods:
        # Morning: 5am-9am (05:00-09:00)
        # Evening: 5pm-9pm (17:00-21:00)
        morning_start = cfg.winter_morning_peak_start
        morning_end = cfg.winter_morning_peak_end
        evening_start = cfg.winter_evening_peak_start
        evening_end = cfg.winter_evening_peak_end

        # Morning peak (start 10 minutes early)
        morning_start_time = datetime(current_time.year, current_time.month, current_time.day,
                                     morning_start, 0) - timedelta(minutes=10)
        morning_end_time = datetime(current_time.year, current_time.month, current_time.day,
                                   morning_end, 0)

        # Evening peak (start 10 minutes early)
        evening_start_time = datetime(current_time.year, current_time.month, current_time.day,
                                     evening_start, 0) - timedelta(minutes=10)
        evening_end_time = datetime(current_time.year, current_time.month, current_time.day,
                                   evening_end, 0)

        in_morning_peak = morning_start_time.time() <= current_time.time() < morning_end_time.time()
        in_evening_peak = evening_start_time.time() <= current_time.time() < evening_end_time.time()
        is_peak = in_morning_peak or in_evening_peak

        logger.info(f"Season: WINTER, Morning: {morning_start_time.strftime('%H:%M')}-{morning_end_time.strftime('%H:%M')}, "
                   f"Evening: {evening_start_time.strftime('%H:%M')}-{evening_end_time.strftime('%H:%M')}, "
                   f"Current: {current_time.strftime('%H:%M')}, Is Peak: {is_peak}")

        return is_peak


def lambda_handler(event, context):
    """
    Lambda handler for peak period management

    Runs every 10 minutes throughout the day to ensure Powerwall
    reserve is set correctly for peak/off-peak periods

    Args:
        event: EventBridge scheduled event
        context: Lambda context

    Returns:
        Response dictionary
    """
    try:
        logger.info("Starting peak manager")

        # Initialize clients
        cfg, tesla, notif_mgr = init_clients()

        # Check if in dry-run mode
        if cfg.dry_run:
            logger.warning("=" * 60)
            logger.warning("DRY-RUN MODE ENABLED - No actual reserve changes will be made")
            logger.warning("=" * 60)

        # Get current time
        current_time = datetime.utcnow()

        # Get current reserve setting
        logger.info("Getting current Powerwall reserve setting")
        site_info = tesla.get_site_info()
        current_reserve = site_info.get('backup_reserve_percent', -1)

        logger.info(f"Current reserve: {current_reserve}%")

        # Determine if we're in peak period
        in_peak = is_peak_period(current_time, cfg)

        # Determine desired reserve
        desired_reserve = 0.0 if in_peak else 100.0
        period_name = "ON-PEAK" if in_peak else "OFF-PEAK"

        logger.info(f"Period: {period_name}, Desired reserve: {desired_reserve}%")

        # Check if change is needed
        if current_reserve == desired_reserve:
            logger.info(f"Reserve already set to {desired_reserve}% - no action needed")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Reserve already set correctly',
                    'period': period_name,
                    'current_reserve': current_reserve,
                    'desired_reserve': desired_reserve
                })
            }

        # Set new reserve
        logger.info(f"Changing reserve from {current_reserve}% to {desired_reserve}%")

        try:
            tesla.set_backup_reserve(desired_reserve)

            # Verify the change
            new_site_info = tesla.get_site_info()
            actual_reserve = new_site_info.get('backup_reserve_percent', -1)

            if actual_reserve == desired_reserve:
                logger.info(f"Successfully set reserve to {desired_reserve}%")

                # Send info notification
                notif_mgr.send_info(
                    subject=f"Reserve Changed to {desired_reserve}%",
                    message=f"Period: {period_name}\n"
                           f"Previous reserve: {current_reserve}%\n"
                           f"New reserve: {actual_reserve}%\n"
                           f"Time: {current_time.strftime('%Y-%m-%d %H:%M:%S')} UTC"
                )

                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'message': 'Reserve changed successfully',
                        'period': period_name,
                        'previous_reserve': current_reserve,
                        'new_reserve': actual_reserve
                    })
                }
            else:
                logger.warning(f"Reserve set to {actual_reserve}% instead of {desired_reserve}%")

                notif_mgr.send_warning(
                    subject="Reserve Change Verification Failed",
                    message=f"Attempted to set reserve to {desired_reserve}%\n"
                           f"Actual reserve: {actual_reserve}%\n"
                           f"This may indicate an API issue."
                )

                return {
                    'statusCode': 500,
                    'body': json.dumps({
                        'error': 'Reserve verification failed',
                        'expected': desired_reserve,
                        'actual': actual_reserve
                    })
                }

        except Exception as e:
            logger.error(f"Failed to set reserve: {e}")

            notif_mgr.send_warning(
                subject="Powerwall Reserve Change Failed",
                message=f"Error setting battery reserve to {desired_reserve}%\n"
                       f"Manual update may be required!\n\n"
                       f"Period: {period_name}\n"
                       f"Current reserve: {current_reserve}%\n"
                       f"Error: {str(e)}"
            )

            raise

    except Exception as e:
        logger.exception(f"Peak manager failed: {e}")

        try:
            notif_mgr.send_warning(
                subject="Peak Manager Error",
                message=f"Failed to manage peak periods:\n{str(e)}"
            )
        except:
            pass

        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Peak management failed',
                'message': str(e)
            })
        }
