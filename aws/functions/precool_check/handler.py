"""
Precool Check Lambda Function
Checks weather forecast and battery level to decide on precooling
"""
import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional
import requests

# Import from Lambda Layer
from powermgr.config import get_config
from powermgr.tesla_client import TeslaClient
from powermgr.honeywell_client import HoneywellClient
from powermgr.notifications import NotificationManager

# Set up logging
logger = logging.getLogger()
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logger.setLevel(getattr(logging, log_level))

# Initialize clients (reused across invocations)
config = None
tesla_client = None
honeywell_client = None
notification_manager = None


def init_clients():
    """Initialize clients on cold start"""
    global config, tesla_client, honeywell_client, notification_manager

    if config is None:
        config = get_config()
        tesla_client = TeslaClient(config)
        honeywell_client = HoneywellClient(config)
        notification_manager = NotificationManager(config)

    return config, tesla_client, honeywell_client, notification_manager


def get_weather_forecast(cfg) -> Optional[float]:
    """
    Get today's high temperature forecast from OpenWeather

    Args:
        cfg: Configuration object

    Returns:
        Forecasted high temperature in Fahrenheit, or None if failed
    """
    try:
        url = f"https://api.openweathermap.org/data/2.5/onecall"
        params = {
            'lat': cfg.latitude,
            'lon': cfg.longitude,
            'exclude': 'current,minutely,hourly,alerts',
            'appid': cfg.openweather_api_key,
            'units': 'imperial'
        }

        logger.info(f"Fetching weather forecast for lat={cfg.latitude}, lon={cfg.longitude}")

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()

        # Get today's forecast (first item in daily array)
        forecast_high = data['daily'][0]['temp']['max']

        logger.info(f"Forecasted high: {forecast_high}°F")

        return float(forecast_high)

    except Exception as e:
        logger.error(f"Failed to get weather forecast: {e}")
        return None


def lambda_handler(event, context):
    """
    Lambda handler for precool check

    Runs early morning (e.g., 7am) to check if precooling should occur
    based on forecasted high temperature and current battery level

    Args:
        event: EventBridge scheduled event
        context: Lambda context

    Returns:
        Response dictionary
    """
    try:
        logger.info("Starting precool check")

        # Initialize clients
        cfg, tesla, honeywell, notif_mgr = init_clients()

        # Get current battery level
        logger.info("Getting current battery level from Tesla")
        status = tesla.get_live_status()
        battery_pct = status.get('percentage_charged', 0)

        logger.info(f"Current battery: {battery_pct}%")

        # Get weather forecast
        forecast_high = get_weather_forecast(cfg)

        if forecast_high is None:
            logger.error("Cannot proceed without weather forecast")
            notif_mgr.send_warning(
                subject="Precool Check Failed - No Weather Data",
                message="Failed to retrieve weather forecast.\nPrecool check aborted."
            )
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': 'Weather forecast unavailable',
                    'message': 'Cannot determine if precooling is needed'
                })
            }

        # Determine if precooling should occur
        precool_reasons = []

        # Check forecast threshold
        if forecast_high >= cfg.forecast_threshold:
            precool_reasons.append(f"Forecasted high of {forecast_high}°F exceeds threshold of {cfg.forecast_threshold}°F")

        # Check battery threshold
        if battery_pct <= cfg.precool_threshold:
            precool_reasons.append(f"Battery level of {battery_pct}% is below threshold of {cfg.precool_threshold}%")

        # Precool if either condition is met
        if precool_reasons:
            logger.info("Precooling conditions met:")
            for reason in precool_reasons:
                logger.info(f"  - {reason}")

            # Set all thermostats to precool temperature
            logger.info(f"Setting all thermostats to {cfg.precool_temp}°F")

            message = "Precool initiated:\n\n"
            message += "\n".join(precool_reasons)
            message += f"\n\nSetting thermostats to {cfg.precool_temp}°F\n"

            try:
                # Set each thermostat to precool temp (not adjustment, absolute value)
                results = []
                for device_id in cfg.thermostat_ids:
                    try:
                        old_temp = honeywell.get_setpoint(device_id)
                        actual_temp = honeywell.set_setpoint(device_id, cfg.precool_temp)
                        results.append({
                            'device_id': device_id,
                            'old_temp': old_temp,
                            'new_temp': actual_temp
                        })
                    except Exception as e:
                        logger.error(f"Failed to set device {device_id}: {e}")
                        message += f"\nError setting device {device_id}: {str(e)}"

                # Add results to message
                message += "\nThermostat changes:\n"
                for result in results:
                    message += f"Device {result['device_id']}: {result['old_temp']}°F → {result['new_temp']}°F\n"

                # Send notification
                notif_mgr.send_info(
                    subject="Precool Activated",
                    message=message
                )

                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'message': 'Precool activated',
                        'forecast_high': forecast_high,
                        'battery_percentage': battery_pct,
                        'precool_temp': cfg.precool_temp,
                        'reasons': precool_reasons,
                        'devices_adjusted': len(results)
                    })
                }

            except Exception as e:
                logger.error(f"Failed to adjust thermostats: {e}")
                notif_mgr.send_warning(
                    subject="Precool Failed",
                    message=f"Precool was needed but thermostat adjustment failed:\n\n{str(e)}"
                )
                raise

        else:
            logger.info("No precooling needed")
            logger.info(f"Forecast: {forecast_high}°F (threshold: {cfg.forecast_threshold}°F)")
            logger.info(f"Battery: {battery_pct}% (threshold: {cfg.precool_threshold}%)")

            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'No precooling needed',
                    'forecast_high': forecast_high,
                    'forecast_threshold': cfg.forecast_threshold,
                    'battery_percentage': battery_pct,
                    'battery_threshold': cfg.precool_threshold
                })
            }

    except Exception as e:
        logger.exception(f"Precool check failed: {e}")

        try:
            notif_mgr.send_warning(
                subject="Precool Check Error",
                message=f"Failed to check precool conditions:\n{str(e)}"
            )
        except:
            pass

        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Precool check failed',
                'message': str(e)
            })
        }
