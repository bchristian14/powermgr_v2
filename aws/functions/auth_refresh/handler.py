"""
Auth Refresh Lambda Function
Monitors Tesla token expiration and refreshes when needed
"""
import json
import logging
import os
from datetime import datetime
from typing import Dict, Any

# Import from Lambda Layer
from powermgr.config import get_config
from powermgr.tesla_client import TeslaClient
from powermgr.state_manager import StateManager
from powermgr.notifications import NotificationManager

# Set up logging
logger = logging.getLogger()
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logger.setLevel(getattr(logging, log_level))

# Initialize clients (reused across invocations)
config = None
tesla_client = None
state_manager = None
notification_manager = None


def init_clients():
    """Initialize clients on cold start"""
    global config, tesla_client, state_manager, notification_manager

    if config is None:
        config = get_config()
        tesla_client = TeslaClient(config)
        state_manager = StateManager()
        notification_manager = NotificationManager(config)

    return config, tesla_client, state_manager, notification_manager


def lambda_handler(event, context):
    """
    Lambda handler for Tesla token refresh

    Runs nightly to check token expiration and refresh if needed
    Refreshes when less than 15 days remaining

    Args:
        event: EventBridge scheduled event
        context: Lambda context

    Returns:
        Response dictionary
    """
    try:
        logger.info("Starting auth refresh check")

        # Initialize clients
        cfg, tesla, state_mgr, notif_mgr = init_clients()

        # Get current token from state
        token_data = state_mgr.get_state('tesla_token')

        if not token_data:
            logger.error("No Tesla token found in state")
            notif_mgr.send_warning(
                subject="Tesla Token Missing",
                message="Tesla authentication token not found in state.\n"
                       "Please re-authenticate using the init_tesla_token.py script."
            )
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': 'Token not found',
                    'message': 'Tesla token not in state - re-authentication required'
                })
            }

        # Check token expiration
        created_at = token_data.get('created_at', 0)
        expires_in = token_data.get('expires_in', 0)
        expiry_timestamp = created_at + expires_in

        current_timestamp = datetime.utcnow().timestamp()
        seconds_until_expiry = expiry_timestamp - current_timestamp
        days_until_expiry = seconds_until_expiry / (24 * 60 * 60)

        expiry_datetime = datetime.fromtimestamp(expiry_timestamp)

        logger.info(f"Token expires: {expiry_datetime.isoformat()}")
        logger.info(f"Days until expiry: {days_until_expiry:.1f}")

        # Check if token is already expired
        if seconds_until_expiry <= 0:
            logger.error("Token has already expired!")
            notif_mgr.send_warning(
                subject="Tesla Token Expired",
                message=f"Tesla authentication token expired on {expiry_datetime.isoformat()}\n"
                       f"Re-authentication required using init_tesla_token.py script."
            )
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': 'Token expired',
                    'expiry_date': expiry_datetime.isoformat(),
                    'days_expired': abs(days_until_expiry)
                })
            }

        # Check if refresh is needed (< 15 days)
        threshold_seconds = cfg.token_refresh_threshold

        if seconds_until_expiry < threshold_seconds:
            logger.info(f"Token expires in {days_until_expiry:.1f} days - refreshing")

            try:
                # Refresh token using Tesla client
                refresh_token = token_data.get('refresh_token')

                if not refresh_token:
                    raise ValueError("No refresh_token found in token data")

                logger.info("Attempting to refresh token...")
                new_token = tesla.refresh_token(refresh_token)

                # Token is automatically saved to state by TeslaClient.refresh_token()

                new_expiry_timestamp = new_token.get('created_at', 0) + new_token.get('expires_in', 0)
                new_expiry_datetime = datetime.fromtimestamp(new_expiry_timestamp)

                logger.info(f"Token refreshed successfully - new expiry: {new_expiry_datetime.isoformat()}")

                # Send success notification
                notif_mgr.send_info(
                    subject="Tesla Token Refreshed",
                    message=f"Tesla authentication token refreshed successfully.\n\n"
                           f"Old expiry: {expiry_datetime.isoformat()}\n"
                           f"New expiry: {new_expiry_datetime.isoformat()}\n"
                           f"Days until expiry: {(new_expiry_timestamp - current_timestamp) / (24 * 60 * 60):.1f}"
                )

                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'message': 'Token refreshed successfully',
                        'old_expiry': expiry_datetime.isoformat(),
                        'new_expiry': new_expiry_datetime.isoformat(),
                        'days_until_expiry': (new_expiry_timestamp - current_timestamp) / (24 * 60 * 60)
                    })
                }

            except Exception as e:
                logger.exception(f"Failed to refresh token: {e}")

                # Send failure notification
                notif_mgr.send_warning(
                    subject="Tesla Token Refresh FAILED",
                    message=f"Failed to refresh Tesla authentication token!\n\n"
                           f"Error: {str(e)}\n"
                           f"Token expires: {expiry_datetime.isoformat()}\n"
                           f"Days remaining: {days_until_expiry:.1f}\n\n"
                           f"Manual intervention may be required."
                )

                return {
                    'statusCode': 500,
                    'body': json.dumps({
                        'error': 'Token refresh failed',
                        'message': str(e),
                        'expiry_date': expiry_datetime.isoformat(),
                        'days_until_expiry': days_until_expiry
                    })
                }

        else:
            logger.info(f"Token has {days_until_expiry:.1f} days remaining - no refresh needed")

            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Token still valid - no refresh needed',
                    'expiry_date': expiry_datetime.isoformat(),
                    'days_until_expiry': days_until_expiry,
                    'refresh_threshold_days': threshold_seconds / (24 * 60 * 60)
                })
            }

    except Exception as e:
        logger.exception(f"Auth refresh check failed: {e}")

        try:
            notif_mgr.send_warning(
                subject="Auth Refresh Check Error",
                message=f"Failed to check Tesla token expiration:\n{str(e)}"
            )
        except:
            pass

        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Auth refresh check failed',
                'message': str(e)
            })
        }
