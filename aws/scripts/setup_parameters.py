#!/usr/bin/env python3
"""
Setup script to configure AWS Systems Manager Parameter Store
Migrates configuration from config.py and sets up secure parameter storage
"""
import sys
import json
import argparse
import boto3
from botocore.exceptions import ClientError


class ParameterStoreSetup:
    """Setup Parameter Store configuration"""

    def __init__(self, prefix='/powermgr', dry_run=False):
        self.ssm = boto3.client('ssm')
        self.prefix = prefix
        self.dry_run = dry_run

    def put_parameter(self, name, value, param_type='String', description=''):
        """
        Create or update a parameter

        Args:
            name: Parameter name (without prefix)
            value: Parameter value
            param_type: String, StringList, or SecureString
            description: Parameter description
        """
        full_name = f"{self.prefix}/{name}"

        if self.dry_run:
            print(f"[DRY RUN] Would create/update: {full_name}")
            return

        try:
            self.ssm.put_parameter(
                Name=full_name,
                Value=value if isinstance(value, str) else json.dumps(value),
                Type=param_type,
                Description=description,
                Overwrite=True,
                Tier='Standard'  # Free tier
            )
            print(f"✓ Created/updated: {full_name}")

        except ClientError as e:
            print(f"✗ Failed to create {full_name}: {e}")
            if not self.dry_run:
                raise

    def setup_configuration_parameters(self):
        """Setup all configuration parameters"""
        print("\n=== Setting up Configuration Parameters ===\n")

        # Tesla configuration
        print("Tesla Configuration:")
        self.put_parameter(
            'config/tesla/energy_site_id',
            '',  # User must provide
            'String',
            'Tesla Energy Site ID'
        )

        # Battery thresholds
        print("\nBattery Thresholds:")
        thresholds = {
            'first': 50,
            'second': 35,
            'third': 20
        }
        self.put_parameter(
            'config/battery_thresholds',
            json.dumps(thresholds),
            'String',
            'Battery percentage thresholds for thermostat adjustments'
        )

        # Thermostat settings
        print("\nThermostat Settings:")
        thermostat_settings = {
            'ids': [],  # User must provide
            'base_url': 'https://www.mytotalconnectcomfort.com/portal'
        }
        self.put_parameter(
            'config/thermostat_settings',
            json.dumps(thermostat_settings),
            'String',
            'Honeywell thermostat configuration'
        )

        # Precool settings
        print("\nPrecool Settings:")
        precool_settings = {
            'temp': 67,
            'threshold': 90,
            'lat': 40.71,  # User should update
            'lon': -74.00,  # User should update
            'forecast_threshold': 105
        }
        self.put_parameter(
            'config/precool_settings',
            json.dumps(precool_settings),
            'String',
            'Precool configuration including lat/lon and temperature settings'
        )

        # Peak hours configuration
        print("\nPeak Hours Configuration:")
        peak_hours = {
            'summer': {
                'first_month': 5,
                'last_month': 10,
                'peak_start': 14,
                'peak_end': 20
            },
            'winter': {
                'morning_peak_start': 5,
                'morning_peak_end': 9,
                'evening_peak_start': 17,
                'evening_peak_end': 21
            }
        }
        self.put_parameter(
            'config/peak_hours',
            json.dumps(peak_hours),
            'String',
            'Peak period schedule for summer and winter'
        )

        # Holidays (update annually)
        print("\nHolidays:")
        holidays = [
            '2025-01-01',  # New Year's
            '2025-05-26',  # Memorial Day
            '2025-07-04',  # Independence Day
            '2025-09-01',  # Labor Day
            '2025-11-27',  # Thanksgiving
            '2025-12-25'   # Christmas
        ]
        self.put_parameter(
            'config/holidays',
            json.dumps(holidays),
            'String',
            'Dates with off-peak pricing (YYYY-MM-DD format)'
        )

        # Adjustment mode configuration
        print("\nAdjustment Mode Configuration:")
        adjustment_mode = {
            'mode': 'fixed',  # 'fixed' or 'predictive'
            'target_battery_minimum': 20,  # Target minimum battery % at peak end
            'enable_predictive_override': False  # Allow predictive to override fixed thresholds
        }
        self.put_parameter(
            'config/adjustment_mode',
            json.dumps(adjustment_mode),
            'String',
            'Thermostat adjustment mode: fixed (threshold-based) or predictive (analytics-based)'
        )

        # Dry-run mode (testing without actual control)
        print("\nDry-Run Mode Configuration:")
        self.put_parameter(
            'config/dry_run',
            'false',  # Set to 'true' for testing without actual control actions
            'String',
            'Dry-run mode: true to log actions without executing, false for normal operation'
        )

        # Notification emails
        print("\nNotification Configuration:")
        notification_emails = []  # User must provide
        self.put_parameter(
            'config/notification_emails',
            json.dumps(notification_emails),
            'String',
            'List of email addresses for notifications'
        )

    def setup_secret_parameters(self):
        """Setup secure credential parameters (placeholders)"""
        print("\n=== Setting up Secret Parameters (Encrypted) ===\n")

        # Tesla secrets
        print("Tesla Credentials:")
        self.put_parameter(
            'secrets/tesla/access_token',
            'PLACEHOLDER',
            'SecureString',
            'Tesla API access token'
        )
        self.put_parameter(
            'secrets/tesla/refresh_token',
            'PLACEHOLDER',
            'SecureString',
            'Tesla API refresh token'
        )

        # Honeywell secrets
        print("\nHoneywell Credentials:")
        self.put_parameter(
            'secrets/honeywell/username',
            'PLACEHOLDER',
            'SecureString',
            'Honeywell Total Connect username'
        )
        self.put_parameter(
            'secrets/honeywell/password',
            'PLACEHOLDER',
            'SecureString',
            'Honeywell Total Connect password'
        )

        # OpenWeather secrets
        print("\nOpenWeather Credentials:")
        self.put_parameter(
            'secrets/openweather/api_key',
            'PLACEHOLDER',
            'SecureString',
            'OpenWeatherMap API key'
        )

        # Gmail secrets
        print("\nGmail Credentials:")
        self.put_parameter(
            'secrets/gmail/username',
            'PLACEHOLDER',
            'SecureString',
            'Gmail username/email'
        )
        self.put_parameter(
            'secrets/gmail/password',
            'PLACEHOLDER',
            'SecureString',
            'Gmail app password (not account password)'
        )

    def initialize_tesla_token(self, token_file: str):
        """
        Initialize Tesla token from existing token file

        Args:
            token_file: Path to tesla.token file
        """
        print(f"\n=== Importing Tesla Token from {token_file} ===\n")

        try:
            with open(token_file, 'r') as f:
                token_data = json.load(f)

            # Store token as JSON in state
            # Note: This will be stored in DynamoDB PowerStateTable by the auth_refresh function
            print("Tesla token loaded successfully")
            print("Token will be stored in DynamoDB PowerStateTable during first deployment")
            print(f"  Access Token: {token_data.get('access_token', '')[:20]}...")
            print(f"  Refresh Token: {token_data.get('refresh_token', '')[:20]}...")
            print(f"  Expires In: {token_data.get('expires_in', 0)} seconds")

            return token_data

        except FileNotFoundError:
            print(f"✗ Token file not found: {token_file}")
            print("  You'll need to authenticate with Tesla and store the token manually")
            return None
        except json.JSONDecodeError as e:
            print(f"✗ Invalid JSON in token file: {e}")
            return None

    def migrate_from_config_file(self, config_file: str, credentials_file: str):
        """
        Migrate configuration from existing config.py and credentials.py

        Args:
            config_file: Path to config.py
            credentials_file: Path to credentials.py
        """
        print(f"\n=== Migrating from {config_file} ===\n")
        print("Note: This is a helper to extract values. Manual review recommended.\n")

        # Load config values
        try:
            with open(config_file, 'r') as f:
                config_content = f.read()

            # Simple extraction (not full Python parsing)
            print("Extracted configuration values:")
            print("Please update Parameter Store with these values manually or via AWS CLI\n")

            # Extract key values using simple string parsing
            import re

            patterns = {
                'TESLA_ENERGY_SITE_ID': r'TESLA_ENERGY_SITE_ID\s*=\s*(\d+)',
                'THERMOSTAT_IDS': r'THERMOSTAT_IDS\s*=\s*\[(.*?)\]',
                'LAT': r'LAT\s*=\s*([\d.-]+)',
                'LON': r'LON\s*=\s*([\d.-]+)',
                'NOTIFICATION_EMAILS': r'NOTIFICATION_EMAILS\s*=\s*\[(.*?)\]',
            }

            for key, pattern in patterns.items():
                match = re.search(pattern, config_content)
                if match:
                    print(f"{key}: {match.group(1)}")

        except FileNotFoundError:
            print(f"Config file not found: {config_file}")

    def verify_parameters(self):
        """Verify all parameters are set"""
        print("\n=== Verifying Parameters ===\n")

        required_params = [
            'config/tesla/energy_site_id',
            'config/battery_thresholds',
            'config/thermostat_settings',
            'config/precool_settings',
            'config/peak_hours',
            'config/holidays',
            'config/notification_emails',
            'secrets/tesla/access_token',
            'secrets/honeywell/username',
            'secrets/openweather/api_key',
        ]

        missing = []
        placeholder = []

        for param in required_params:
            full_name = f"{self.prefix}/{param}"
            try:
                response = self.ssm.get_parameter(Name=full_name, WithDecryption=False)
                value = response['Parameter']['Value']

                if value == 'PLACEHOLDER' or value == '' or value == '[]':
                    placeholder.append(param)
                    print(f"⚠ {param}: Needs configuration (placeholder value)")
                else:
                    print(f"✓ {param}: Configured")

            except ClientError:
                missing.append(param)
                print(f"✗ {param}: Missing")

        print("\n=== Summary ===")
        print(f"Total parameters: {len(required_params)}")
        print(f"Configured: {len(required_params) - len(missing) - len(placeholder)}")
        print(f"Need configuration: {len(placeholder)}")
        print(f"Missing: {len(missing)}")

        if placeholder:
            print("\n⚠ The following parameters need real values:")
            for param in placeholder:
                print(f"  - {self.prefix}/{param}")

        if missing:
            print("\n✗ The following parameters are missing:")
            for param in missing:
                print(f"  - {self.prefix}/{param}")

        return len(missing) == 0 and len(placeholder) == 0


def main():
    parser = argparse.ArgumentParser(
        description='Setup AWS Systems Manager Parameter Store for Power Management System'
    )
    parser.add_argument(
        '--prefix',
        default='/powermgr',
        help='Parameter Store prefix (default: /powermgr)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be created without making changes'
    )
    parser.add_argument(
        '--migrate-from-config',
        metavar='CONFIG_FILE',
        help='Path to existing config.py to extract values'
    )
    parser.add_argument(
        '--import-tesla-token',
        metavar='TOKEN_FILE',
        help='Path to existing tesla.token file to import'
    )
    parser.add_argument(
        '--verify',
        action='store_true',
        help='Verify all parameters are configured'
    )
    parser.add_argument(
        '--setup-all',
        action='store_true',
        help='Setup all parameters with defaults'
    )

    args = parser.parse_args()

    setup = ParameterStoreSetup(prefix=args.prefix, dry_run=args.dry_run)

    if args.verify:
        all_configured = setup.verify_parameters()
        sys.exit(0 if all_configured else 1)

    if args.migrate_from_config:
        setup.migrate_from_config(args.migrate_from_config, 'credentials.py')

    if args.import_tesla_token:
        setup.initialize_tesla_token(args.import_tesla_token)

    if args.setup_all:
        print("Setting up Parameter Store with default values...")
        setup.setup_configuration_parameters()
        setup.setup_secret_parameters()
        print("\n✓ Parameter Store setup complete!")
        print("\n⚠ IMPORTANT: Update placeholder values with real credentials")
        print("Use AWS Console or CLI to update sensitive parameters")
        print("\nExample AWS CLI commands:")
        print(f"  aws ssm put-parameter --name '{args.prefix}/secrets/tesla/access_token' \\")
        print("    --value 'YOUR_TOKEN' --type SecureString --overwrite")


if __name__ == '__main__':
    main()
