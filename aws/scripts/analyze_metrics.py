#!/usr/bin/env python3
"""
Local Analytics Script - Query DynamoDB metrics and generate reports
Works entirely with DynamoDB data (no S3 needed for forever-free architecture)
"""
import argparse
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Any
import boto3
from boto3.dynamodb.conditions import Key


class DecimalEncoder(json.JSONEncoder):
    """Helper to convert Decimal to float for JSON serialization"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)


class MetricsAnalyzer:
    """Analyze power metrics from DynamoDB"""

    def __init__(self, table_name: str = 'PowerMetrics-prod'):
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table(table_name)

    def query_date_range(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """
        Query metrics for a date range

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            List of metrics
        """
        metrics = []
        current_date = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)

        while current_date <= end:
            date_str = current_date.strftime('%Y-%m-%d')

            try:
                response = self.table.query(
                    KeyConditionExpression=Key('metric_date').eq(date_str)
                )

                items = response.get('Items', [])
                metrics.extend(items)

                # Handle pagination
                while 'LastEvaluatedKey' in response:
                    response = self.table.query(
                        KeyConditionExpression=Key('metric_date').eq(date_str),
                        ExclusiveStartKey=response['LastEvaluatedKey']
                    )
                    metrics.extend(response.get('Items', []))

            except Exception as e:
                print(f"Error querying {date_str}: {e}")

            current_date += timedelta(days=1)

        # Convert Decimals to floats
        for metric in metrics:
            for key, value in metric.items():
                if isinstance(value, Decimal):
                    metric[key] = float(value)

        return metrics

    def analyze_battery_depletion(self, metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze battery depletion rates"""
        if not metrics:
            return {}

        # Filter peak period metrics only
        peak_metrics = [m for m in metrics if 'peak' in m.get('peak_period', '')]

        if not peak_metrics:
            return {}

        # Calculate average depletion rate
        total_battery_power = sum(m.get('battery_power', 0) for m in peak_metrics)
        avg_battery_power = total_battery_power / len(peak_metrics)

        # Group by day
        daily_stats = {}
        for metric in peak_metrics:
            date = metric['timestamp'][:10]
            if date not in daily_stats:
                daily_stats[date] = {
                    'min_battery': 100,
                    'max_battery': 0,
                    'avg_solar': 0,
                    'grid_events': 0,
                    'count': 0
                }

            stats = daily_stats[date]
            battery_pct = metric.get('battery_percentage', 0)
            stats['min_battery'] = min(stats['min_battery'], battery_pct)
            stats['max_battery'] = max(stats['max_battery'], battery_pct)
            stats['avg_solar'] += metric.get('solar_power', 0)
            if metric.get('grid_power', 0) > 500:
                stats['grid_events'] += 1
            stats['count'] += 1

        # Calculate averages
        for date, stats in daily_stats.items():
            if stats['count'] > 0:
                stats['avg_solar'] /= stats['count']
                stats['depletion'] = stats['max_battery'] - stats['min_battery']

        return {
            'avg_battery_draw_kw': avg_battery_power / 1000.0,
            'total_peak_readings': len(peak_metrics),
            'daily_stats': daily_stats
        }

    def generate_weekly_report(self, days: int = 7) -> str:
        """Generate a weekly report"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        print(f"Fetching metrics from {start_date.date()} to {end_date.date()}...")
        metrics = self.query_date_range(
            start_date.strftime('%Y-%m-%d'),
            end_date.strftime('%Y-%m-%d')
        )

        print(f"Analyzing {len(metrics)} data points...")
        analysis = self.analyze_battery_depletion(metrics)

        # Build report
        report = []
        report.append("="*70)
        report.append(f"POWER MANAGEMENT REPORT - {days} Day Analysis")
        report.append(f"Period: {start_date.date()} to {end_date.date()}")
        report.append("="*70)
        report.append("")

        report.append("SUMMARY:")
        report.append(f"  Total data points: {len(metrics)}")
        report.append(f"  Peak period readings: {analysis.get('total_peak_readings', 0)}")
        report.append(f"  Average battery draw: {analysis.get('avg_battery_draw_kw', 0):.2f} kW")
        report.append("")

        report.append("DAILY BREAKDOWN:")
        daily_stats = analysis.get('daily_stats', {})
        for date in sorted(daily_stats.keys()):
            stats = daily_stats[date]
            report.append(f"\n  {date}:")
            report.append(f"    Battery range: {stats['min_battery']:.1f}% - {stats['max_battery']:.1f}%")
            report.append(f"    Battery depleted: {stats['depletion']:.1f}%")
            report.append(f"    Avg solar: {stats['avg_solar']:.0f} W")
            report.append(f"    Grid events: {stats['grid_events']}")

        report.append("")
        report.append("="*70)

        return "\n".join(report)

    def export_to_json(self, start_date: str, end_date: str, output_file: str):
        """Export metrics to JSON file"""
        print(f"Fetching metrics from {start_date} to {end_date}...")
        metrics = self.query_date_range(start_date, end_date)

        print(f"Writing {len(metrics)} records to {output_file}...")
        with open(output_file, 'w') as f:
            json.dump(metrics, f, cls=DecimalEncoder, indent=2)

        print(f"✓ Exported to {output_file}")

    def export_to_csv(self, start_date: str, end_date: str, output_file: str):
        """Export metrics to CSV file"""
        import csv

        print(f"Fetching metrics from {start_date} to {end_date}...")
        metrics = self.query_date_range(start_date, end_date)

        if not metrics:
            print("No metrics found")
            return

        print(f"Writing {len(metrics)} records to {output_file}...")

        # Get all unique keys
        fieldnames = set()
        for metric in metrics:
            fieldnames.update(metric.keys())
        fieldnames = sorted(list(fieldnames))

        with open(output_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for metric in metrics:
                # Convert Decimals to floats
                row = {}
                for key, value in metric.items():
                    if isinstance(value, Decimal):
                        row[key] = float(value)
                    else:
                        row[key] = value
                writer.writerow(row)

        print(f"✓ Exported to {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Analyze power management metrics from DynamoDB'
    )
    parser.add_argument(
        '--table',
        default='PowerMetrics-prod',
        help='DynamoDB table name (default: PowerMetrics-prod)'
    )
    parser.add_argument(
        '--report',
        action='store_true',
        help='Generate weekly report'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=7,
        help='Number of days for report (default: 7)'
    )
    parser.add_argument(
        '--export-json',
        metavar='FILE',
        help='Export data to JSON file'
    )
    parser.add_argument(
        '--export-csv',
        metavar='FILE',
        help='Export data to CSV file'
    )
    parser.add_argument(
        '--start-date',
        help='Start date for export (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--end-date',
        help='End date for export (YYYY-MM-DD)'
    )

    args = parser.parse_args()

    analyzer = MetricsAnalyzer(table_name=args.table)

    if args.report:
        report = analyzer.generate_weekly_report(days=args.days)
        print(report)

    elif args.export_json:
        if not args.start_date or not args.end_date:
            print("Error: --start-date and --end-date required for export")
            return 1

        analyzer.export_to_json(args.start_date, args.end_date, args.export_json)

    elif args.export_csv:
        if not args.start_date or not args.end_date:
            print("Error: --start-date and --end-date required for export")
            return 1

        analyzer.export_to_csv(args.start_date, args.end_date, args.export_csv)

    else:
        parser.print_help()

    return 0


if __name__ == '__main__':
    exit(main())
