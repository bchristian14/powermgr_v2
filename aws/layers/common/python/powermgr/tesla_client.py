"""
Tesla API client for Power Management System
"""
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import requests
from requests.exceptions import RequestException

from .config import get_config
from .state_manager import StateManager

logger = logging.getLogger(__name__)


class TeslaAPIError(Exception):
    """Custom exception for Tesla API errors"""
    pass


class TeslaClient:
    """Client for interacting with Tesla Owner API"""

    def __init__(self, config=None, state_manager=None):
        self.config = config or get_config()
        self.state_manager = state_manager or StateManager()
        self.session = requests.Session()
        self._token = None

    def _get_access_token(self) -> str:
        """
        Get valid access token from state manager

        Returns:
            Valid access token

        Raises:
            TeslaAPIError if token not found or invalid
        """
        token_data = self.state_manager.get_state('tesla_token')

        if not token_data:
            raise TeslaAPIError("Tesla token not found in state. Please authenticate first.")

        # Check if token is expired or needs refresh
        created_at = token_data.get('created_at', 0)
        expires_in = token_data.get('expires_in', 0)
        expiry_time = created_at + expires_in

        # If less than 15 days remaining, should be refreshed by auth_refresh function
        if expiry_time - datetime.now().timestamp() < self.config.token_refresh_threshold:
            logger.warning("Tesla token is expiring soon and should be refreshed")

        if expiry_time <= datetime.now().timestamp():
            raise TeslaAPIError("Tesla token has expired. Please refresh token.")

        return token_data.get('access_token')

    def _get_headers(self) -> Dict[str, str]:
        """Get authorization headers for API requests"""
        token = self._get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

    def _make_request(self, method: str, url: str, **kwargs) -> Dict[str, Any]:
        """
        Make authenticated request to Tesla API

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Full URL to request
            **kwargs: Additional arguments for requests

        Returns:
            Response JSON data

        Raises:
            TeslaAPIError on request failure
        """
        try:
            headers = self._get_headers()
            headers.update(kwargs.pop('headers', {}))

            response = self.session.request(
                method=method,
                url=url,
                headers=headers,
                timeout=30,
                **kwargs
            )
            response.raise_for_status()

            return response.json()

        except RequestException as e:
            logger.error(f"Tesla API request failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(f"Response body: {e.response.text}")
            raise TeslaAPIError(f"Tesla API request failed: {e}")

    def get_live_status(self) -> Dict[str, Any]:
        """
        Get live status of energy site (battery, solar, grid)

        Returns:
            Dictionary containing:
                - percentage_charged: Battery percentage (0-100)
                - battery_power: Battery power in watts (negative = discharging)
                - solar_power: Solar power in watts
                - grid_power: Grid power in watts (positive = importing)
                - battery_remaining: Battery energy remaining in Wh
                - total_pack_energy: Total battery capacity in Wh
                - grid_status: Grid connection status
                - and more...
        """
        response = self._make_request('GET', self.config.tesla_status_url)
        return response.get('response', {})

    def get_site_info(self) -> Dict[str, Any]:
        """
        Get site information including backup reserve percentage

        Returns:
            Dictionary containing:
                - backup_reserve_percent: Current backup reserve setting (0-100)
                - site_name: Name of the site
                - and more...
        """
        response = self._make_request('GET', self.config.tesla_site_info_url)
        return response.get('response', {})

    def set_backup_reserve(self, reserve_percent: float) -> bool:
        """
        Set backup reserve percentage

        Args:
            reserve_percent: Desired backup reserve (0-100)

        Returns:
            True if successful

        Raises:
            TeslaAPIError on failure
        """
        if not 0 <= reserve_percent <= 100:
            raise ValueError("Reserve percent must be between 0 and 100")

        payload = {"backup_reserve_percent": reserve_percent}

        logger.info(f"Setting backup reserve to {reserve_percent}%")

        try:
            self._make_request('POST', self.config.tesla_reserve_url, json=payload)

            # Verify the change
            site_info = self.get_site_info()
            new_reserve = site_info.get('backup_reserve_percent')

            if new_reserve == reserve_percent:
                logger.info(f"Successfully set backup reserve to {reserve_percent}%")
                return True
            else:
                logger.warning(f"Reserve set to {new_reserve}% instead of {reserve_percent}%")
                return False

        except TeslaAPIError as e:
            logger.error(f"Failed to set backup reserve: {e}")
            raise

    def get_battery_metrics(self) -> Dict[str, Any]:
        """
        Get comprehensive battery metrics for data collection

        Returns:
            Dictionary with all relevant metrics for storage
        """
        try:
            status = self.get_live_status()

            # Extract and normalize metrics
            metrics = {
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'battery_percentage': float(status.get('percentage_charged', 0)),
                'battery_power': float(status.get('battery_power', 0)),
                'solar_power': float(status.get('solar_power', 0)),
                'grid_power': float(status.get('grid_power', 0)),
                'battery_remaining_kwh': float(status.get('energy_left', 0)) / 1000.0,  # Convert Wh to kWh
                'total_pack_energy_kwh': float(status.get('total_pack_energy', 0)) / 1000.0,
                'grid_status': status.get('grid_status', 'Unknown'),
                'battery_is_charging': bool(status.get('battery_power', 0) > 0),
            }

            # Get site info for additional context
            try:
                site_info = self.get_site_info()
                metrics['backup_reserve_percent'] = float(site_info.get('backup_reserve_percent', 0))
            except Exception as e:
                logger.warning(f"Could not fetch site info: {e}")
                metrics['backup_reserve_percent'] = None

            return metrics

        except Exception as e:
            logger.error(f"Failed to get battery metrics: {e}")
            raise TeslaAPIError(f"Failed to get battery metrics: {e}")

    def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh access token using refresh token

        Args:
            refresh_token: Current refresh token

        Returns:
            New token data dictionary

        Raises:
            TeslaAPIError on failure
        """
        payload = {
            "grant_type": "refresh_token",
            "client_id": "ownerapi",
            "refresh_token": refresh_token,
        }

        try:
            response = requests.post(
                self.config.tesla_token_url,
                json=payload,
                timeout=30
            )
            response.raise_for_status()

            new_token = response.json()
            logger.info("Successfully refreshed Tesla token")

            # Store new token
            self.state_manager.set_state('tesla_token', new_token)

            return new_token

        except RequestException as e:
            logger.error(f"Failed to refresh Tesla token: {e}")
            raise TeslaAPIError(f"Token refresh failed: {e}")
