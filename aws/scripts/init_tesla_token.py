#!/usr/bin/env python3
"""
Initialize Tesla token in DynamoDB PowerStateTable
Migrates token from file-based storage to DynamoDB
"""
import json
import argparse
import sys
from datetime import datetime
import boto3
from botocore.exceptions import ClientError


def load_token_from_file(token_file: str) -> dict:
    """Load Tesla token from file"""
    try:
        with open(token_file, 'r') as f:
            token_data = json.load(f)

        # Validate token structure
        required_fields = ['access_token', 'refresh_token', 'expires_in', 'created_at']
        for field in required_fields:
            if field not in token_data:
                print(f"✗ Missing required field: {field}")
                return None

        return token_data

    except FileNotFoundError:
        print(f"✗ Token file not found: {token_file}")
        return None
    except json.JSONDecodeError as e:
        print(f"✗ Invalid JSON in token file: {e}")
        return None


def store_token_in_dynamodb(token_data: dict, table_name: str, environment: str = 'prod'):
    """Store Tesla token in DynamoDB PowerStateTable"""
    try:
        dynamodb = boto3.resource('dynamodb')

        # Construct table name with environment
        full_table_name = f"PowerState-{environment}"
        if table_name:
            full_table_name = table_name

        table = dynamodb.Table(full_table_name)

        # Prepare item
        item = {
            'state_key': 'tesla_token',
            'value': json.dumps(token_data),
            'last_updated': datetime.utcnow().isoformat() + 'Z'
        }

        # Store in DynamoDB
        table.put_item(Item=item)

        print(f"✓ Tesla token stored in DynamoDB table: {full_table_name}")

        # Calculate and display expiration
        created_at = token_data['created_at']
        expires_in = token_data['expires_in']
        expiry_timestamp = created_at + expires_in
        expiry_date = datetime.fromtimestamp(expiry_timestamp)

        print(f"  Token expires: {expiry_date.isoformat()}")
        print(f"  Days until expiration: {(expiry_date - datetime.now()).days}")

        return True

    except ClientError as e:
        print(f"✗ Failed to store token in DynamoDB: {e}")
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            print(f"  Table '{full_table_name}' not found. Deploy stack first.")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False


def verify_token_storage(table_name: str, environment: str = 'prod'):
    """Verify token is stored and accessible"""
    try:
        dynamodb = boto3.resource('dynamodb')

        full_table_name = f"PowerState-{environment}"
        if table_name:
            full_table_name = table_name

        table = dynamodb.Table(full_table_name)

        # Retrieve token
        response = table.get_item(Key={'state_key': 'tesla_token'})

        if 'Item' in response:
            item = response['Item']
            token_data = json.loads(item['value'])

            print("\n✓ Token verification successful")
            print(f"  Access token: {token_data.get('access_token', '')[:30]}...")
            print(f"  Refresh token: {token_data.get('refresh_token', '')[:30]}...")
            print(f"  Last updated: {item.get('last_updated', 'Unknown')}")

            return True
        else:
            print("✗ Token not found in DynamoDB")
            return False

    except Exception as e:
        print(f"✗ Verification failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Initialize Tesla token in DynamoDB PowerStateTable'
    )
    parser.add_argument(
        'token_file',
        help='Path to tesla.token JSON file'
    )
    parser.add_argument(
        '--table-name',
        help='DynamoDB table name (default: PowerState-{environment})'
    )
    parser.add_argument(
        '--environment',
        default='prod',
        choices=['dev', 'staging', 'prod'],
        help='Environment (default: prod)'
    )
    parser.add_argument(
        '--verify',
        action='store_true',
        help='Verify token after storing'
    )

    args = parser.parse_args()

    print("=== Tesla Token Initialization ===\n")

    # Load token from file
    print(f"Loading token from: {args.token_file}")
    token_data = load_token_from_file(args.token_file)

    if not token_data:
        print("\n✗ Failed to load token")
        sys.exit(1)

    print("✓ Token loaded successfully")

    # Store in DynamoDB
    print(f"\nStoring token in DynamoDB...")
    success = store_token_in_dynamodb(token_data, args.table_name, args.environment)

    if not success:
        print("\n✗ Failed to store token")
        sys.exit(1)

    # Verify if requested
    if args.verify:
        print("\nVerifying token storage...")
        verified = verify_token_storage(args.table_name, args.environment)

        if not verified:
            print("\n✗ Verification failed")
            sys.exit(1)

    print("\n✓ Tesla token initialization complete!")
    print("\nNext steps:")
    print("  1. Verify token with: python3 scripts/init_tesla_token.py --verify")
    print("  2. Deploy Lambda functions")
    print("  3. Test data collection")


if __name__ == '__main__':
    main()
