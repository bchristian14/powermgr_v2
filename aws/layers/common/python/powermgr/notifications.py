"""
Notification management - SNS and email
"""
import os
import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import List, Optional
import boto3
from botocore.exceptions import ClientError

from .config import get_config

logger = logging.getLogger(__name__)


class NotificationManager:
    """Manages notifications via SNS and/or email"""

    def __init__(self, config=None):
        self.config = config or get_config()
        self.sns = boto3.client('sns')
        self.sns_topic_arn = os.environ.get('SNS_TOPIC_ARN')

    def send_notification(
        self,
        subject: str,
        message: str,
        level: str = 'INFO',
        use_sns: bool = True,
        use_email: bool = False
    ):
        """
        Send notification via SNS and/or email

        Args:
            subject: Message subject
            message: Message body
            level: Notification level (INFO, WARNING, ERROR, CRITICAL)
            use_sns: Whether to send via SNS
            use_email: Whether to send via direct email (Gmail)
        """
        # Format message with level
        formatted_message = f"[{level}] {message}"

        success = False

        # Send via SNS
        if use_sns and self.sns_topic_arn:
            success = self._send_sns(subject, formatted_message) or success

        # Send via direct email
        if use_email:
            success = self._send_email(subject, formatted_message) or success

        if not success:
            logger.warning("Failed to send notification via any method")

        return success

    def _send_sns(self, subject: str, message: str) -> bool:
        """Send notification via SNS"""
        if not self.sns_topic_arn:
            logger.warning("SNS topic ARN not configured")
            return False

        try:
            self.sns.publish(
                TopicArn=self.sns_topic_arn,
                Subject=subject[:100],  # SNS subject max 100 chars
                Message=message
            )
            logger.info(f"Sent SNS notification: {subject}")
            return True

        except ClientError as e:
            logger.error(f"Failed to send SNS notification: {e}")
            return False

    def _send_email(self, subject: str, message: str) -> bool:
        """Send notification via Gmail SMTP"""
        try:
            # Get Gmail credentials
            gmail_creds = self.config.get_credentials('gmail')
            gmail_user = gmail_creds.get('username')
            gmail_password = gmail_creds.get('password')

            if not gmail_user or not gmail_password:
                logger.warning("Gmail credentials not configured")
                return False

            # Create message
            msg = EmailMessage()
            msg['Subject'] = subject
            msg['From'] = gmail_user
            msg['To'] = ', '.join(self.config.notification_emails)
            msg.set_content(message)

            # Send via Gmail SMTP
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL("smtp.gmail.com", self.config.email_port, context=context) as server:
                server.login(gmail_user, gmail_password)
                server.send_message(msg)

            logger.info(f"Sent email notification: {subject}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")
            return False

    def send_critical_alert(self, subject: str, message: str):
        """Send critical alert via all available channels"""
        return self.send_notification(
            subject=subject,
            message=message,
            level='CRITICAL',
            use_sns=True,
            use_email=True
        )

    def send_info(self, subject: str, message: str):
        """Send informational notification"""
        return self.send_notification(
            subject=subject,
            message=message,
            level='INFO',
            use_sns=True,
            use_email=False
        )

    def send_warning(self, subject: str, message: str):
        """Send warning notification"""
        return self.send_notification(
            subject=subject,
            message=message,
            level='WARNING',
            use_sns=True,
            use_email=False
        )
