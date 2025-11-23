"""
Honeywell Total Connect Comfort API client for Power Management System
"""
import logging
from typing import Dict, Any, List, Optional
import requests
from requests.exceptions import RequestException

from .config import get_config

logger = logging.getLogger(__name__)


class HoneywellAPIError(Exception):
    """Custom exception for Honeywell API errors"""
    pass


class HoneywellClient:
    """Client for interacting with Honeywell Total Connect Comfort API"""

    def __init__(self, config=None):
        self.config = config or get_config()
        self.session = requests.Session()
        self.session.headers['X-Requested-With'] = 'XMLHttpRequest'
        self._authenticated = False

    def _authenticate(self):
        """
        Authenticate with Honeywell API

        Raises:
            HoneywellAPIError on authentication failure
        """
        if self._authenticated:
            return

        params = {
            'UserName': self.config.honeywell_username,
            'Password': self.config.honeywell_password,
            'RememberMe': 'false',
            'timeOffset': 0
        }

        try:
            logger.debug("Authenticating with Honeywell API")

            # Initial GET to establish session
            self.session.get(self.config.honeywell_base_url, timeout=60)

            # Login POST
            login_response = self.session.post(
                self.config.honeywell_base_url,
                params=params,
                timeout=60
            )
            login_response.raise_for_status()

            # Verify login worked
            login_data = login_response.json()
            if not login_data:
                raise HoneywellAPIError("Login failed - no response data")

            self._authenticated = True
            logger.info("Successfully authenticated with Honeywell API")

        except RequestException as e:
            logger.error(f"Honeywell authentication failed: {e}")
            raise HoneywellAPIError(f"Authentication failed: {e}")

    def get_setpoint(self, device_id: str) -> int:
        """
        Get current cooling setpoint for a device

        Args:
            device_id: Honeywell device ID

        Returns:
            Current cooling setpoint in Fahrenheit

        Raises:
            HoneywellAPIError on failure
        """
        self._authenticate()

        url = f"{self.config.honeywell_base_url}/Device/CheckDataSession/{device_id}"

        try:
            logger.debug(f"Getting setpoint for device {device_id}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            data = response.json()
            setpoint = data['latestData']['uiData']['CoolSetpoint']
            logger.info(f"Device {device_id} current setpoint: {setpoint}°F")

            return int(setpoint)

        except (RequestException, KeyError, ValueError) as e:
            logger.error(f"Failed to get setpoint for device {device_id}: {e}")
            raise HoneywellAPIError(f"Failed to get setpoint: {e}")

    def set_setpoint(self, device_id: str, new_temp: int) -> int:
        """
        Set cooling setpoint for a device

        Args:
            device_id: Honeywell device ID
            new_temp: New temperature setpoint in Fahrenheit

        Returns:
            Actual new setpoint after setting

        Raises:
            HoneywellAPIError on failure
        """
        self._authenticate()

        # Validate temperature
        if not 50 <= new_temp <= 90:
            raise ValueError(f"Temperature {new_temp}°F is out of valid range (50-90°F)")

        operation_url = f"{self.config.honeywell_base_url}/Device/SubmitControlScreenChanges"

        data = {
            'SystemSwitch': None,
            'HeatSetpoint': None,
            'CoolSetpoint': new_temp,
            'HeatNextPeriod': None,
            'CoolNextPeriod': 81,  # Default next period temp
            'StatusHeat': None,
            'StatusCool': 1,  # Cooling enabled
            'DeviceID': device_id,
        }

        # DRY-RUN MODE: Log but don't execute
        if self.config.dry_run:
            logger.warning(f"[DRY-RUN] Would set device {device_id} to {new_temp}°F (skipped)")
            logger.info(f"[DRY-RUN] Data would be: {data}")
            return new_temp  # Return requested temp as if it worked

        try:
            logger.info(f"Setting device {device_id} to {new_temp}°F")

            response = self.session.post(operation_url, data=data, timeout=30)
            response.raise_for_status()

            # Verify the change
            actual_setpoint = self.get_setpoint(device_id)

            if actual_setpoint == new_temp:
                logger.info(f"Successfully set device {device_id} to {new_temp}°F")
            else:
                logger.warning(f"Device {device_id} set to {actual_setpoint}°F instead of {new_temp}°F")

            return actual_setpoint

        except RequestException as e:
            logger.error(f"Failed to set setpoint for device {device_id}: {e}")
            raise HoneywellAPIError(f"Failed to set setpoint: {e}")

    def adjust_setpoint(self, device_id: str, temp_delta: int) -> Dict[str, Any]:
        """
        Adjust setpoint by a delta amount

        Args:
            device_id: Honeywell device ID
            temp_delta: Temperature change (positive = warmer, negative = cooler)

        Returns:
            Dictionary with old_temp, new_temp, delta

        Raises:
            HoneywellAPIError on failure
        """
        try:
            old_temp = self.get_setpoint(device_id)
            new_temp = old_temp + temp_delta

            # Clamp to valid range
            new_temp = max(50, min(90, new_temp))

            actual_temp = self.set_setpoint(device_id, new_temp)

            return {
                'device_id': device_id,
                'old_temp': old_temp,
                'new_temp': actual_temp,
                'requested_delta': temp_delta,
                'actual_delta': actual_temp - old_temp
            }

        except Exception as e:
            logger.error(f"Failed to adjust setpoint for device {device_id}: {e}")
            raise HoneywellAPIError(f"Setpoint adjustment failed: {e}")

    def adjust_all_thermostats(self, temp_delta: int) -> List[Dict[str, Any]]:
        """
        Adjust all configured thermostats by the same delta

        Args:
            temp_delta: Temperature change for all devices

        Returns:
            List of adjustment results for each device

        Raises:
            HoneywellAPIError if any device fails
        """
        results = []
        errors = []

        for device_id in self.config.thermostat_ids:
            try:
                result = self.adjust_setpoint(device_id, temp_delta)
                results.append(result)
            except HoneywellAPIError as e:
                error = {
                    'device_id': device_id,
                    'error': str(e)
                }
                errors.append(error)
                logger.error(f"Failed to adjust device {device_id}: {e}")

        if errors and not results:
            # All devices failed
            raise HoneywellAPIError(f"Failed to adjust all thermostats: {errors}")

        if errors:
            # Some succeeded, some failed
            logger.warning(f"Some thermostats failed to adjust: {errors}")

        return results
