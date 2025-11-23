"""
State management using DynamoDB
"""
import os
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from decimal import Decimal
import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class DecimalEncoder(json.JSONEncoder):
    """Helper to convert Decimal to float for JSON serialization"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)


class StateManager:
    """Manages application state in DynamoDB"""

    def __init__(self):
        self.dynamodb = boto3.resource('dynamodb')
        self.state_table_name = os.environ.get('POWERSTATE_TABLE')
        self.state_table = self.dynamodb.Table(self.state_table_name)

    def get_state(self, state_key: str) -> Optional[Any]:
        """
        Get state value by key

        Args:
            state_key: State key (e.g., 'battery_status', 'tesla_token')

        Returns:
            State value or None if not found
        """
        try:
            response = self.state_table.get_item(Key={'state_key': state_key})

            if 'Item' in response:
                item = response['Item']
                value = item.get('value')

                # Handle JSON strings
                if isinstance(value, str):
                    try:
                        return json.loads(value)
                    except json.JSONDecodeError:
                        return value

                return value

            return None

        except ClientError as e:
            logger.error(f"Failed to get state for {state_key}: {e}")
            raise

    def set_state(self, state_key: str, value: Any, ttl_days: Optional[int] = None):
        """
        Set state value

        Args:
            state_key: State key
            value: Value to store (will be JSON serialized if dict/list)
            ttl_days: Optional TTL in days for automatic expiration
        """
        try:
            # Prepare item
            item = {
                'state_key': state_key,
                'value': value if not isinstance(value, (dict, list)) else json.dumps(value, cls=DecimalEncoder),
                'last_updated': datetime.utcnow().isoformat() + 'Z'
            }

            # Add TTL if specified
            if ttl_days:
                ttl_timestamp = int((datetime.utcnow() + timedelta(days=ttl_days)).timestamp())
                item['ttl'] = ttl_timestamp

            self.state_table.put_item(Item=item)
            logger.debug(f"Set state for {state_key}")

        except ClientError as e:
            logger.error(f"Failed to set state for {state_key}: {e}")
            raise

    def get_battery_status(self) -> int:
        """
        Get current battery threshold status (0, 1, 2, or 3)

        Returns:
            Current threshold level
        """
        status = self.get_state('battery_status')

        if status is None:
            # Initialize if not exists
            self.set_battery_status(0)
            return 0

        # Check if it needs daily reset
        item = self.state_table.get_item(Key={'state_key': 'battery_status'}).get('Item', {})
        last_reset = item.get('last_reset_date')
        today = datetime.utcnow().date().isoformat()

        if last_reset != today:
            logger.info("Resetting battery status for new day")
            self.set_battery_status(0)
            return 0

        return int(status)

    def set_battery_status(self, status: int):
        """
        Set battery threshold status

        Args:
            status: Threshold level (0, 1, 2, or 3)
        """
        if status not in [0, 1, 2, 3]:
            raise ValueError("Battery status must be 0, 1, 2, or 3")

        item = {
            'state_key': 'battery_status',
            'value': status,
            'last_updated': datetime.utcnow().isoformat() + 'Z',
            'last_reset_date': datetime.utcnow().date().isoformat()
        }

        self.state_table.put_item(Item=item)
        logger.info(f"Set battery status to {status}")

    def get_thermostat_state(self) -> Dict[str, Any]:
        """
        Get current thermostat state including total adjustment

        Returns:
            Dictionary with thermostat state info
        """
        state = self.get_state('thermostat_state')

        if state is None:
            # Initialize default state
            default_state = {
                'total_adjustment': 0,
                'last_adjustment_time': None,
                'adjustments_today': []
            }
            self.set_state('thermostat_state', default_state)
            return default_state

        return state

    def record_thermostat_adjustment(self, adjustment: int, reason: str):
        """
        Record thermostat adjustment

        Args:
            adjustment: Temperature adjustment in degrees F
            reason: Reason for adjustment
        """
        state = self.get_thermostat_state()

        # Update total adjustment
        state['total_adjustment'] = state.get('total_adjustment', 0) + adjustment

        # Record adjustment
        adjustment_record = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'adjustment': adjustment,
            'new_total': state['total_adjustment'],
            'reason': reason
        }

        state['adjustments_today'] = state.get('adjustments_today', [])
        state['adjustments_today'].append(adjustment_record)
        state['last_adjustment_time'] = adjustment_record['timestamp']

        self.set_state('thermostat_state', state)
        logger.info(f"Recorded thermostat adjustment: {adjustment}°F (total: {state['total_adjustment']}°F)")

    def reset_daily_state(self):
        """Reset state that should be cleared daily"""
        # Reset battery status
        self.set_battery_status(0)

        # Reset thermostat adjustments
        state = self.get_thermostat_state()
        state['total_adjustment'] = 0
        state['adjustments_today'] = []
        self.set_state('thermostat_state', state)

        logger.info("Daily state reset completed")


class MetricsManager:
    """Manages power metrics storage in DynamoDB"""

    def __init__(self):
        self.dynamodb = boto3.resource('dynamodb')
        self.metrics_table_name = os.environ.get('POWERMETRICS_TABLE')
        self.metrics_table = self.dynamodb.Table(self.metrics_table_name)

    def save_metrics(self, metrics: Dict[str, Any]):
        """
        Save power metrics to DynamoDB

        Args:
            metrics: Dictionary of metrics to save
        """
        try:
            timestamp = metrics.get('timestamp', datetime.utcnow().isoformat() + 'Z')
            metric_date = timestamp[:10]  # Extract YYYY-MM-DD

            # Convert float values to Decimal for DynamoDB
            item = {
                'metric_date': metric_date,
                'timestamp': timestamp,
            }

            # Add all metrics, converting floats to Decimal
            for key, value in metrics.items():
                if key not in ['metric_date', 'timestamp']:
                    if isinstance(value, float):
                        item[key] = Decimal(str(value))
                    else:
                        item[key] = value

            # Set TTL for 1 year (365 days) - stays within 25GB free tier
            ttl_timestamp = int((datetime.utcnow() + timedelta(days=365)).timestamp())
            item['ttl'] = ttl_timestamp

            self.metrics_table.put_item(Item=item)
            logger.debug(f"Saved metrics for {timestamp}")

        except ClientError as e:
            logger.error(f"Failed to save metrics: {e}")
            raise

    def query_recent_metrics(self, hours: int = 1) -> List[Dict[str, Any]]:
        """
        Query recent metrics from the last N hours

        Args:
            hours: Number of hours to look back

        Returns:
            List of metrics dictionaries, sorted by timestamp (newest first)
        """
        try:
            # Calculate time range
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=hours)

            # We might need to query multiple days if crossing midnight
            dates_to_query = set()
            current = start_time
            while current <= end_time:
                dates_to_query.add(current.date().isoformat())
                current += timedelta(days=1)

            all_items = []

            for metric_date in dates_to_query:
                response = self.metrics_table.query(
                    KeyConditionExpression=Key('metric_date').eq(metric_date) &
                                         Key('timestamp').gte(start_time.isoformat() + 'Z')
                )
                all_items.extend(response.get('Items', []))

            # Convert Decimals back to floats
            metrics = []
            for item in all_items:
                metric = {}
                for key, value in item.items():
                    if isinstance(value, Decimal):
                        metric[key] = float(value)
                    else:
                        metric[key] = value
                metrics.append(metric)

            # Sort by timestamp (newest first)
            metrics.sort(key=lambda x: x['timestamp'], reverse=True)

            return metrics

        except ClientError as e:
            logger.error(f"Failed to query metrics: {e}")
            raise

    def query_metrics_by_date(self, date_str: str) -> List[Dict[str, Any]]:
        """
        Query all metrics for a specific date

        Args:
            date_str: Date in YYYY-MM-DD format

        Returns:
            List of metrics dictionaries for that date
        """
        try:
            response = self.metrics_table.query(
                KeyConditionExpression=Key('metric_date').eq(date_str)
            )

            # Convert Decimals back to floats
            metrics = []
            for item in response.get('Items', []):
                metric = {}
                for key, value in item.items():
                    if isinstance(value, Decimal):
                        metric[key] = float(value)
                    else:
                        metric[key] = value
                metrics.append(metric)

            return metrics

        except ClientError as e:
            logger.error(f"Failed to query metrics for {date_str}: {e}")
            raise


class AnalyticsManager:
    """Manages analytics results in DynamoDB"""

    def __init__(self):
        self.dynamodb = boto3.resource('dynamodb')
        self.analytics_table_name = os.environ.get('POWERANALYTICS_TABLE')
        self.analytics_table = self.dynamodb.Table(self.analytics_table_name)

    def save_analytics(self, analytics: Dict[str, Any]):
        """
        Save analytics results

        Args:
            analytics: Dictionary of analytics results
        """
        try:
            timestamp = analytics.get('timestamp', datetime.utcnow().isoformat() + 'Z')
            analysis_date = timestamp[:10]  # Extract YYYY-MM-DD

            # Convert float values to Decimal
            item = {
                'analysis_date': analysis_date,
                'timestamp': timestamp,
            }

            for key, value in analytics.items():
                if key not in ['analysis_date', 'timestamp']:
                    if isinstance(value, float):
                        item[key] = Decimal(str(value))
                    else:
                        item[key] = value

            # Set TTL for 1 year (365 days) - stays within 25GB free tier
            ttl_timestamp = int((datetime.utcnow() + timedelta(days=365)).timestamp())
            item['ttl'] = ttl_timestamp

            self.analytics_table.put_item(Item=item)
            logger.debug(f"Saved analytics for {timestamp}")

        except ClientError as e:
            logger.error(f"Failed to save analytics: {e}")
            raise

    def get_latest_analytics(self) -> Optional[Dict[str, Any]]:
        """
        Get the most recent analytics result

        Returns:
            Latest analytics dictionary or None
        """
        try:
            today = datetime.utcnow().date().isoformat()

            response = self.analytics_table.query(
                KeyConditionExpression=Key('analysis_date').eq(today),
                ScanIndexForward=False,  # Sort descending (newest first)
                Limit=1
            )

            items = response.get('Items', [])

            if items:
                item = items[0]
                # Convert Decimals to floats
                analytics = {}
                for key, value in item.items():
                    if isinstance(value, Decimal):
                        analytics[key] = float(value)
                    else:
                        analytics[key] = value
                return analytics

            return None

        except ClientError as e:
            logger.error(f"Failed to get latest analytics: {e}")
            raise

    def query_analytics_by_date(self, date_str: str) -> List[Dict[str, Any]]:
        """
        Query all analytics for a specific date

        Args:
            date_str: Date in YYYY-MM-DD format

        Returns:
            List of analytics dictionaries for that date
        """
        try:
            response = self.analytics_table.query(
                KeyConditionExpression=Key('analysis_date').eq(date_str)
            )

            # Convert Decimals back to floats
            analytics_list = []
            for item in response.get('Items', []):
                analytics = {}
                for key, value in item.items():
                    if isinstance(value, Decimal):
                        analytics[key] = float(value)
                    else:
                        analytics[key] = value
                analytics_list.append(analytics)

            return analytics_list

        except ClientError as e:
            logger.error(f"Failed to query analytics for {date_str}: {e}")
            raise
