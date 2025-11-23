"""
Weekly Report Lambda Function
Generates comprehensive weekly performance and cost savings report
"""
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List
from collections import defaultdict

# Import from Lambda Layer
from powermgr.config import get_config
from powermgr.state_manager import MetricsManager, AnalyticsManager, StateManager
from powermgr.notifications import NotificationManager

# Set up logging
logger = logging.getLogger()
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logger.setLevel(getattr(logging, log_level))

# Initialize clients (reused across invocations)
config = None
metrics_manager = None
analytics_manager = None
state_manager = None
notification_manager = None


def init_clients():
    """Initialize clients on cold start"""
    global config, metrics_manager, analytics_manager, state_manager, notification_manager

    if config is None:
        config = get_config()
        metrics_manager = MetricsManager()
        analytics_manager = AnalyticsManager()
        state_manager = StateManager()
        notification_manager = NotificationManager(config)

    return config, metrics_manager, analytics_manager, state_manager, notification_manager


def calculate_cost_savings(metrics: List[Dict[str, Any]], cfg) -> Dict[str, Any]:
    """
    Calculate cost savings from avoided grid usage during peak periods

    Args:
        metrics: List of metrics from last week
        cfg: Configuration object

    Returns:
        Dictionary with cost savings calculations
    """
    # Typical utility rates (configurable in future)
    peak_rate_per_kwh = 0.45  # $0.45/kWh during peak
    off_peak_rate_per_kwh = 0.12  # $0.12/kWh off-peak

    total_peak_battery_kwh = 0
    total_peak_solar_kwh = 0
    total_grid_usage_kwh = 0
    peak_periods_count = 0

    for metric in metrics:
        # Only count peak period metrics
        if 'peak' not in metric.get('peak_period', ''):
            continue

        peak_periods_count += 1

        # Battery discharge during peak (negative battery_power means discharging)
        battery_power = metric.get('battery_power', 0)
        if battery_power < 0:
            # Convert W to kWh for 5-minute interval
            battery_kwh = abs(battery_power) / 1000.0 * (5.0 / 60.0)
            total_peak_battery_kwh += battery_kwh

        # Solar generation during peak
        solar_power = metric.get('solar_power', 0)
        if solar_power > 0:
            solar_kwh = solar_power / 1000.0 * (5.0 / 60.0)
            total_peak_solar_kwh += solar_kwh

        # Grid usage (should be minimal/zero)
        grid_power = metric.get('grid_power', 0)
        if grid_power > 0:
            grid_kwh = grid_power / 1000.0 * (5.0 / 60.0)
            total_grid_usage_kwh += grid_kwh

    # Calculate savings: Battery + Solar used during peak avoided grid purchase
    total_grid_avoided_kwh = total_peak_battery_kwh + total_peak_solar_kwh
    peak_cost_savings = total_grid_avoided_kwh * peak_rate_per_kwh

    # Cost if we had used grid instead
    would_be_cost = total_grid_avoided_kwh * peak_rate_per_kwh

    # Actual grid cost (minimal, should be near zero)
    actual_grid_cost = total_grid_usage_kwh * peak_rate_per_kwh

    return {
        'total_battery_kwh': total_peak_battery_kwh,
        'total_solar_kwh': total_peak_solar_kwh,
        'total_grid_avoided_kwh': total_grid_avoided_kwh,
        'total_grid_usage_kwh': total_grid_usage_kwh,
        'peak_cost_savings': peak_cost_savings,
        'would_be_cost': would_be_cost,
        'actual_cost': actual_grid_cost,
        'net_savings': peak_cost_savings - actual_grid_cost,
        'peak_periods_count': peak_periods_count,
        'peak_rate': peak_rate_per_kwh,
        'off_peak_rate': off_peak_rate_per_kwh
    }


def analyze_battery_performance(metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze battery performance metrics

    Args:
        metrics: List of metrics from last week

    Returns:
        Dictionary with battery performance stats
    """
    battery_levels = [m.get('battery_percentage', 0) for m in metrics if 'battery_percentage' in m]

    if not battery_levels:
        return {
            'avg_battery_level': 0,
            'min_battery_level': 0,
            'max_battery_level': 0,
            'times_below_20': 0,
            'times_below_35': 0
        }

    times_below_20 = sum(1 for level in battery_levels if level < 20)
    times_below_35 = sum(1 for level in battery_levels if level < 35)

    return {
        'avg_battery_level': sum(battery_levels) / len(battery_levels),
        'min_battery_level': min(battery_levels),
        'max_battery_level': max(battery_levels),
        'times_below_20': times_below_20,
        'times_below_35': times_below_35,
        'total_readings': len(battery_levels)
    }


def analyze_thermostat_adjustments(analytics: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze thermostat adjustment effectiveness

    Args:
        analytics: List of analytics from last week

    Returns:
        Dictionary with adjustment stats
    """
    total_adjustments = 0
    adjustments_by_urgency = defaultdict(int)
    total_deficit = 0
    readings_with_deficit = 0

    for record in analytics:
        adjustment = record.get('recommended_temp_adjustment', 0)
        if adjustment != 0:
            total_adjustments += 1

        urgency = record.get('urgency', 'NONE')
        if urgency != 'NONE':
            adjustments_by_urgency[urgency] += 1

        deficit = record.get('deficit_from_target', 0)
        if deficit > 0:
            total_deficit += deficit
            readings_with_deficit += 1

    avg_deficit = total_deficit / readings_with_deficit if readings_with_deficit > 0 else 0

    return {
        'total_adjustments_needed': total_adjustments,
        'critical_adjustments': adjustments_by_urgency.get('CRITICAL', 0),
        'high_adjustments': adjustments_by_urgency.get('HIGH', 0),
        'medium_adjustments': adjustments_by_urgency.get('MEDIUM', 0),
        'avg_deficit': avg_deficit,
        'total_analytics_runs': len(analytics)
    }


def analyze_peak_compliance(metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze compliance with peak period management goals

    Args:
        metrics: List of metrics from last week

    Returns:
        Dictionary with compliance stats
    """
    peak_metrics = [m for m in metrics if 'peak' in m.get('peak_period', '')]
    off_peak_metrics = [m for m in metrics if 'off-peak' in m.get('peak_period', '')]

    # Grid usage during peak (should be minimal)
    peak_grid_usage = [m.get('grid_power', 0) for m in peak_metrics]
    peak_grid_incidents = sum(1 for power in peak_grid_usage if power > 500)

    # Battery charging during off-peak
    off_peak_charging = [m for m in off_peak_metrics if m.get('battery_power', 0) > 0]

    return {
        'total_peak_periods': len(peak_metrics),
        'total_off_peak_periods': len(off_peak_metrics),
        'peak_grid_incidents': peak_grid_incidents,
        'peak_compliance_pct': ((len(peak_metrics) - peak_grid_incidents) / len(peak_metrics) * 100) if peak_metrics else 100,
        'off_peak_charging_periods': len(off_peak_charging),
        'off_peak_charging_pct': (len(off_peak_charging) / len(off_peak_metrics) * 100) if off_peak_metrics else 0
    }


def format_report_email(
    cost_savings: Dict[str, Any],
    battery_perf: Dict[str, Any],
    adjustments: Dict[str, Any],
    compliance: Dict[str, Any],
    week_start: datetime,
    week_end: datetime
) -> str:
    """
    Format comprehensive weekly report email

    Args:
        cost_savings: Cost savings calculations
        battery_perf: Battery performance stats
        adjustments: Thermostat adjustment stats
        compliance: Peak period compliance stats
        week_start: Start of reporting week
        week_end: End of reporting week

    Returns:
        Formatted email message
    """
    message = f"""
POWER MANAGEMENT WEEKLY REPORT
{week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}

═══════════════════════════════════════════════════════════════

💰 COST SAVINGS SUMMARY

Grid Energy Avoided:     {cost_savings['total_grid_avoided_kwh']:.2f} kWh
  - Battery Usage:       {cost_savings['total_battery_kwh']:.2f} kWh
  - Solar Generation:    {cost_savings['total_solar_kwh']:.2f} kWh

Estimated Savings:       ${cost_savings['net_savings']:.2f}
  - Would-be Cost:       ${cost_savings['would_be_cost']:.2f} (@ ${cost_savings['peak_rate']}/kWh)
  - Actual Grid Cost:    ${cost_savings['actual_cost']:.2f}

Peak Periods Tracked:    {cost_savings['peak_periods_count']}

═══════════════════════════════════════════════════════════════

🔋 BATTERY PERFORMANCE

Average Battery Level:   {battery_perf['avg_battery_level']:.1f}%
Battery Range:           {battery_perf['min_battery_level']:.1f}% - {battery_perf['max_battery_level']:.1f}%

Threshold Events:
  - Below 20%:           {battery_perf['times_below_20']} times
  - Below 35%:           {battery_perf['times_below_35']} times

Total Readings:          {battery_perf['total_readings']}

═══════════════════════════════════════════════════════════════

🌡️  THERMOSTAT ADJUSTMENTS

Total Adjustments:       {adjustments['total_adjustments_needed']}
  - CRITICAL:            {adjustments['critical_adjustments']} (+4°F)
  - HIGH:                {adjustments['high_adjustments']} (+2°F)
  - MEDIUM:              {adjustments['medium_adjustments']} (+2°F)

Avg Battery Deficit:     {adjustments['avg_deficit']:.1f}% from target
Analytics Runs:          {adjustments['total_analytics_runs']}

═══════════════════════════════════════════════════════════════

✅ PEAK PERIOD COMPLIANCE

Peak Periods:            {compliance['total_peak_periods']}
Grid Usage Incidents:    {compliance['peak_grid_incidents']}
Peak Compliance:         {compliance['peak_compliance_pct']:.1f}%

Off-Peak Periods:        {compliance['total_off_peak_periods']}
Charging Periods:        {compliance['off_peak_charging_periods']}
Charging Rate:           {compliance['off_peak_charging_pct']:.1f}%

═══════════════════════════════════════════════════════════════

📊 WEEKLY INSIGHTS

"""

    # Add insights based on data
    if cost_savings['net_savings'] > 20:
        message += "✨ Excellent savings this week! System is performing optimally.\n"
    elif cost_savings['net_savings'] > 10:
        message += "✓ Good savings this week. System is working well.\n"
    else:
        message += "⚠ Lower savings than expected. Review battery usage patterns.\n"

    if battery_perf['times_below_20'] > 5:
        message += "⚠ Battery dropped below 20% multiple times. Consider adjusting thresholds.\n"

    if compliance['peak_grid_incidents'] > 0:
        message += f"⚠ {compliance['peak_grid_incidents']} grid usage incidents during peak. Investigate causes.\n"
    else:
        message += "✓ Perfect peak period compliance - zero grid usage!\n"

    if adjustments['critical_adjustments'] > 10:
        message += "⚠ Frequent critical adjustments. Battery may be undersized for load.\n"

    message += f"\n═══════════════════════════════════════════════════════════════\n"
    message += f"\nReport generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n"

    return message


def lambda_handler(event, context):
    """
    Lambda handler for weekly report generation

    Runs weekly (e.g., Sunday night) to send comprehensive performance report

    Args:
        event: EventBridge scheduled event
        context: Lambda context

    Returns:
        Response dictionary
    """
    try:
        logger.info("Starting weekly report generation")

        # Initialize clients
        cfg, metrics_mgr, analytics_mgr, state_mgr, notif_mgr = init_clients()

        # Calculate date range (last 7 days)
        week_end = datetime.utcnow()
        week_start = week_end - timedelta(days=7)

        logger.info(f"Generating report for {week_start.date()} to {week_end.date()}")

        # Collect metrics from last week
        logger.info("Querying metrics from last 7 days...")
        all_metrics = []

        for day_offset in range(7):
            query_date = week_start + timedelta(days=day_offset)
            date_str = query_date.strftime('%Y-%m-%d')

            try:
                daily_metrics = metrics_mgr.query_metrics_by_date(date_str)
                all_metrics.extend(daily_metrics)
                logger.info(f"  {date_str}: {len(daily_metrics)} metrics")
            except Exception as e:
                logger.warning(f"Failed to query metrics for {date_str}: {e}")

        logger.info(f"Total metrics collected: {len(all_metrics)}")

        # Collect analytics from last week
        logger.info("Querying analytics from last 7 days...")
        all_analytics = []

        for day_offset in range(7):
            query_date = week_start + timedelta(days=day_offset)
            date_str = query_date.strftime('%Y-%m-%d')

            try:
                daily_analytics = analytics_mgr.query_analytics_by_date(date_str)
                all_analytics.extend(daily_analytics)
                logger.info(f"  {date_str}: {len(daily_analytics)} analytics")
            except Exception as e:
                logger.warning(f"Failed to query analytics for {date_str}: {e}")

        logger.info(f"Total analytics collected: {len(all_analytics)}")

        # Calculate all metrics
        logger.info("Calculating cost savings...")
        cost_savings = calculate_cost_savings(all_metrics, cfg)

        logger.info("Analyzing battery performance...")
        battery_perf = analyze_battery_performance(all_metrics)

        logger.info("Analyzing thermostat adjustments...")
        adjustments = analyze_thermostat_adjustments(all_analytics)

        logger.info("Analyzing peak compliance...")
        compliance = analyze_peak_compliance(all_metrics)

        # Format report email
        logger.info("Formatting report email...")
        report_message = format_report_email(
            cost_savings,
            battery_perf,
            adjustments,
            compliance,
            week_start,
            week_end
        )

        # Send report via SNS
        logger.info("Sending weekly report email...")
        notif_mgr.send_info(
            subject=f"Power Management Weekly Report - Week of {week_start.strftime('%Y-%m-%d')}",
            message=report_message
        )

        logger.info("Weekly report sent successfully")

        # Return summary
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Weekly report generated successfully',
                'week_start': week_start.isoformat(),
                'week_end': week_end.isoformat(),
                'metrics_analyzed': len(all_metrics),
                'analytics_analyzed': len(all_analytics),
                'cost_savings': cost_savings['net_savings'],
                'peak_compliance': compliance['peak_compliance_pct']
            })
        }

    except Exception as e:
        logger.exception(f"Weekly report generation failed: {e}")

        try:
            notif_mgr.send_warning(
                subject="Weekly Report Generation Failed",
                message=f"Failed to generate weekly report:\n{str(e)}"
            )
        except:
            pass

        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Weekly report generation failed',
                'message': str(e)
            })
        }
