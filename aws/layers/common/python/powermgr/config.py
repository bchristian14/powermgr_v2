"""
Configuration management - loads settings from AWS Systems Manager Parameter Store
"""
import os
import json
import logging
from typing import Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages configuration from Parameter Store with caching"""

    def __init__(self, prefix: str = None):
        self.ssm = boto3.client('ssm')
        self.prefix = prefix or os.environ.get('PARAMETER_STORE_PREFIX', '/powermgr')
        self._cache: Dict[str, Any] = {}

    def get_parameter(self, param_name: str, decrypt: bool = True, use_cache: bool = True) -> str:
        """
        Get a single parameter from Parameter Store

        Args:
            param_name: Parameter name (without prefix)
            decrypt: Whether to decrypt SecureString parameters
            use_cache: Whether to use cached value

        Returns:
            Parameter value as string
        """
        full_path = f"{self.prefix}/{param_name}"

        if use_cache and full_path in self._cache:
            return self._cache[full_path]

        try:
            response = self.ssm.get_parameter(
                Name=full_path,
                WithDecryption=decrypt
            )
            value = response['Parameter']['Value']
            self._cache[full_path] = value
            return value
        except ClientError as e:
            if e.response['Error']['Code'] == 'ParameterNotFound':
                logger.error(f"Parameter not found: {full_path}")
                raise ValueError(f"Required parameter not found: {param_name}")
            raise

    def get_json_parameter(self, param_name: str, decrypt: bool = True) -> Dict[str, Any]:
        """Get parameter and parse as JSON"""
        value = self.get_parameter(param_name, decrypt)
        try:
            return json.loads(value)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON parameter {param_name}: {e}")
            raise ValueError(f"Invalid JSON in parameter {param_name}")

    def get_parameters_by_path(self, path: str = "", decrypt: bool = True) -> Dict[str, str]:
        """
        Get all parameters under a path

        Args:
            path: Sub-path under prefix (e.g., "config" or "secrets/tesla")
            decrypt: Whether to decrypt SecureString parameters

        Returns:
            Dictionary of parameter names (without prefix) to values
        """
        full_path = f"{self.prefix}/{path}" if path else self.prefix

        try:
            paginator = self.ssm.get_paginator('get_parameters_by_path')
            parameters = {}

            for page in paginator.paginate(
                Path=full_path,
                Recursive=True,
                WithDecryption=decrypt
            ):
                for param in page['Parameters']:
                    # Remove prefix from name for easier access
                    name = param['Name'].replace(f"{self.prefix}/", "")
                    parameters[name] = param['Value']

            return parameters
        except ClientError as e:
            logger.error(f"Failed to get parameters by path {full_path}: {e}")
            raise

    def reload_cache(self):
        """Clear cache and force reload on next access"""
        self._cache.clear()


class Config:
    """
    Power Management configuration - loads all settings from Parameter Store
    """

    def __init__(self):
        self.config_mgr = ConfigManager()
        self._load_all_config()

    def _load_all_config(self):
        """Load all configuration from Parameter Store"""
        try:
            # Load all config parameters at once
            all_params = self.config_mgr.get_parameters_by_path()

            # Parse configuration parameters
            self._parse_config(all_params)

        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise

    def _parse_config(self, params: Dict[str, str]):
        """Parse configuration parameters into class attributes"""

        # Tesla configuration
        self.tesla_energy_site_id = params.get('config/tesla/energy_site_id', '')
        self.tesla_api_url = "https://owner-api.teslamotors.com/api/1"
        self.tesla_token_url = "https://owner-api.teslamotors.com/oauth/token"

        # Tesla URLs (constructed from site ID)
        self.tesla_status_url = f"{self.tesla_api_url}/energy_sites/{self.tesla_energy_site_id}/live_status"
        self.tesla_site_info_url = f"{self.tesla_api_url}/energy_sites/{self.tesla_energy_site_id}/site_info"
        self.tesla_reserve_url = f"{self.tesla_api_url}/energy_sites/{self.tesla_energy_site_id}/backup"

        # Parse battery thresholds (JSON)
        thresholds_json = params.get('config/battery_thresholds', '{"first": 50, "second": 35, "third": 20}')
        thresholds = json.loads(thresholds_json)
        self.first_threshold = thresholds.get('first', 50)
        self.second_threshold = thresholds.get('second', 35)
        self.third_threshold = thresholds.get('third', 20)

        # Parse thermostat settings (JSON)
        thermostat_json = params.get('config/thermostat_settings',
            '{"ids": [], "base_url": "https://www.mytotalconnectcomfort.com/portal"}')
        thermostat_settings = json.loads(thermostat_json)
        self.thermostat_ids = thermostat_settings.get('ids', [])
        self.thermostat_base_url = thermostat_settings.get('base_url',
            'https://www.mytotalconnectcomfort.com/portal')
        self.thermostat_operation_url = f"{self.thermostat_base_url}/Device/SubmitControlScreenChanges"

        # Parse precool settings (JSON)
        precool_json = params.get('config/precool_settings',
            '{"temp": 67, "threshold": 90, "lat": 40.71, "lon": -74.00, "forecast_threshold": 105}')
        precool_settings = json.loads(precool_json)
        self.precool_temp = precool_settings.get('temp', 67)
        self.precool_threshold = precool_settings.get('threshold', 90)
        self.latitude = precool_settings.get('lat', 40.71)
        self.longitude = precool_settings.get('lon', -74.00)
        self.forecast_threshold = precool_settings.get('forecast_threshold', 105)

        # Parse peak hours configuration (JSON)
        peak_hours_json = params.get('config/peak_hours',
            '''{"summer": {"first_month": 5, "last_month": 10, "peak_start": 14, "peak_end": 20},
                "winter": {"morning_peak_start": 5, "morning_peak_end": 9, "evening_peak_start": 17, "evening_peak_end": 21}}''')
        peak_hours = json.loads(peak_hours_json)

        summer = peak_hours.get('summer', {})
        self.summer_first_month = summer.get('first_month', 5)
        self.summer_last_month = summer.get('last_month', 10)
        self.summer_peak_start = summer.get('peak_start', 14)
        self.summer_peak_end = summer.get('peak_end', 20)

        winter = peak_hours.get('winter', {})
        self.winter_morning_peak_start = winter.get('morning_peak_start', 5)
        self.winter_morning_peak_end = winter.get('morning_peak_end', 9)
        self.winter_evening_peak_start = winter.get('evening_peak_start', 17)
        self.winter_evening_peak_end = winter.get('evening_peak_end', 21)

        # Parse holidays (JSON array)
        holidays_json = params.get('config/holidays', '[]')
        self.holidays = json.loads(holidays_json)

        # Parse notification emails (JSON array)
        emails_json = params.get('config/notification_emails', '[]')
        self.notification_emails = json.loads(emails_json)

        # Email settings
        self.email_port = 465

        # Token refresh threshold
        self.token_refresh_threshold = 15 * 24 * 60 * 60  # 15 days in seconds

        # Adjustment mode configuration
        adjustment_mode_json = params.get('config/adjustment_mode',
            '{"mode": "fixed", "target_battery_minimum": 20, "enable_predictive_override": false}')
        adjustment_mode = json.loads(adjustment_mode_json)
        self.adjustment_mode = adjustment_mode.get('mode', 'fixed')  # 'fixed' or 'predictive'
        self.target_battery_minimum = adjustment_mode.get('target_battery_minimum', 20)
        self.enable_predictive_override = adjustment_mode.get('enable_predictive_override', False)

        # Load credentials for services (cached from params)
        # These are loaded on-demand in get_credentials(), but we can also set commonly used ones
        honeywell_creds = params.get('secrets/honeywell/username', ''), params.get('secrets/honeywell/password', '')
        openweather_key = params.get('secrets/openweather/api_key', '')

        # Set as properties for easy access (will be empty string if not found)
        self.honeywell_username = honeywell_creds[0]
        self.honeywell_password = honeywell_creds[1]
        self.openweather_api_key = openweather_key

        # Dry-run mode (prevents actual control actions, only logs what would happen)
        dry_run_str = params.get('config/dry_run', 'false').lower()
        self.dry_run = dry_run_str in ['true', '1', 'yes']

    def get_credentials(self, service: str) -> Dict[str, str]:
        """
        Get credentials for a specific service

        Args:
            service: Service name (e.g., 'tesla', 'honeywell', 'gmail', 'openweather')

        Returns:
            Dictionary of credential key-value pairs
        """
        try:
            params = self.config_mgr.get_parameters_by_path(f"secrets/{service}", decrypt=True)
            # Remove service prefix from keys
            credentials = {}
            for key, value in params.items():
                # Extract credential name (e.g., 'secrets/tesla/username' -> 'username')
                cred_name = key.split('/')[-1]
                credentials[cred_name] = value
            return credentials
        except Exception as e:
            logger.error(f"Failed to get credentials for {service}: {e}")
            raise


# Singleton instance
_config_instance: Optional[Config] = None


def get_config() -> Config:
    """Get or create configuration singleton instance"""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance


def reload_config():
    """Force reload configuration from Parameter Store"""
    global _config_instance
    _config_instance = Config()
    return _config_instance
