"""
Analytics Lambda Function
Calculates battery depletion rates and projects battery levels at peak end
"""
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

# Import from Lambda Layer
from powermgr.config import get_config
from powermgr.state_manager import MetricsManager, AnalyticsManager
from powermgr.notifications import NotificationManager

# Set up logging
logger = logging.getLogger()
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logger.setLevel(getattr(logging, log_level))

# Initialize clients (reused across invocations)
config = None
metrics_manager = None
analytics_manager = None
notification_manager = None


def init_clients():
    """Initialize clients on cold start"""
    global config, metrics_manager, analytics_manager, notification_manager

    if config is None:
        config = get_config()
        metrics_manager = MetricsManager()
        analytics_manager = AnalyticsManager()
        notification_manager = NotificationManager(config)

    return config, metrics_manager, analytics_manager, notification_manager


def calculate_depletion_rate(metrics: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Calculate battery depletion rate from historical metrics

    Args:
        metrics: List of metrics sorted by timestamp (newest first)

    Returns:
        Dictionary with depletion rates and statistics
    """
    if len(metrics) < 2:
        return {
            'depletion_rate_kwh_per_hour': 0.0,
            'depletion_rate_percent_per_hour': 0.0,
            'sample_count': len(metrics),
            'confidence_score': 0.0
        }

    # Calculate time span
    newest = datetime.fromisoformat(metrics[0]['timestamp'].replace('Z', '+00:00'))
    oldest = datetime.fromisoformat(metrics[-1]['timestamp'].replace('Z', '+00:00'))
    hours_elapsed = (newest - oldest).total_seconds() / 3600.0

    if hours_elapsed <= 0:
        return {
            'depletion_rate_kwh_per_hour': 0.0,
            'depletion_rate_percent_per_hour': 0.0,
            'sample_count': len(metrics),
            'confidence_score': 0.0
        }

    # Calculate battery change
    battery_kwh_change = metrics[-1]['battery_remaining_kwh'] - metrics[0]['battery_remaining_kwh']
    battery_pct_change = metrics[-1]['battery_percentage'] - metrics[0]['battery_percentage']

    # Positive values mean battery is discharging
    depletion_rate_kwh = battery_kwh_change / hours_elapsed
    depletion_rate_pct = battery_pct_change / hours_elapsed

    # Calculate confidence based on sample count and variance
    # More samples = higher confidence
    confidence = min(1.0, len(metrics) / 12.0)  # 12 samples (1 hour at 5-min intervals) = 100%

    # Check for variance (stable rate = higher confidence)
    if len(metrics) >= 3:
        # Calculate variance in battery power readings
        avg_power = sum(m.get('battery_power', 0) for m in metrics) / len(metrics)
        variance = sum((m.get('battery_power', 0) - avg_power) ** 2 for m in metrics) / len(metrics)
        std_dev = variance ** 0.5

        # Lower variance = higher confidence
        if avg_power != 0:
            coefficient_of_variation = abs(std_dev / avg_power)
            variance_confidence = max(0.0, 1.0 - coefficient_of_variation)
            confidence = (confidence + variance_confidence) / 2.0

    return {
        'depletion_rate_kwh_per_hour': depletion_rate_kwh,
        'depletion_rate_percent_per_hour': depletion_rate_pct,
        'avg_battery_power': sum(m.get('battery_power', 0) for m in metrics) / len(metrics),
        'avg_solar_power': sum(m.get('solar_power', 0) for m in metrics) / len(metrics),
        'sample_count': len(metrics),
        'hours_analyzed': hours_elapsed,
        'confidence_score': confidence
    }


def calculate_sunset_impact(
    current_time: datetime,
    minutes_until_sunset: int,
    current_solar_power: float,
    hours_until_peak_end: float
) -> Dict[str, float]:
    """
    Calculate impact of sunset on future battery depletion

    Args:
        current_time: Current timestamp
        minutes_until_sunset: Minutes until sunset
        current_solar_power: Current solar power in watts
        hours_until_peak_end: Hours remaining in peak period

    Returns:
        Dictionary with sunset impact calculations
    """
    # If sunset already happened or solar is negligible, no impact
    if minutes_until_sunset <= 0 or current_solar_power < 100:
        return {
            'solar_contribution_kwh_per_hour': 0.0,
            'solar_loss_at_sunset': 0.0,
            'adjusted_depletion_increase': 0.0,
            'solar_factor': 0.0
        }

    # Calculate current solar contribution (offsetting battery drain)
    solar_contribution_kwh = current_solar_power / 1000.0  # Convert W to kW

    # Calculate solar degradation factor (linear over last 2 hours before sunset)
    sunset_degradation_window = 120  # minutes
    if minutes_until_sunset < sunset_degradation_window:
        solar_factor = minutes_until_sunset / sunset_degradation_window
    else:
        solar_factor = 1.0

    # Calculate hours after sunset (within peak period)
    hours_until_sunset = minutes_until_sunset / 60.0
    hours_after_sunset = max(0, hours_until_peak_end - hours_until_sunset)

    # When solar stops, battery will drain faster by the solar contribution amount
    # This only affects the time AFTER sunset
    additional_drain_after_sunset = solar_contribution_kwh * hours_after_sunset

    return {
        'solar_contribution_kwh_per_hour': solar_contribution_kwh,
        'solar_loss_at_sunset': solar_contribution_kwh,
        'additional_drain_kwh': additional_drain_after_sunset,
        'solar_factor': solar_factor,
        'hours_until_sunset': hours_until_sunset,
        'hours_after_sunset': hours_after_sunset
    }


def project_battery_at_peak_end(
    current_battery_kwh: float,
    current_battery_pct: float,
    total_capacity_kwh: float,
    depletion_rate_kwh: float,
    minutes_until_peak_end: int,
    sunset_impact: Dict[str, float]
) -> Dict[str, float]:
    """
    Project battery level at end of peak period

    Args:
        current_battery_kwh: Current battery in kWh
        current_battery_pct: Current battery percentage
        total_capacity_kwh: Total battery capacity
        depletion_rate_kwh: Current depletion rate in kWh/hour
        minutes_until_peak_end: Minutes until peak period ends
        sunset_impact: Sunset impact calculations

    Returns:
        Projection results
    """
    hours_remaining = minutes_until_peak_end / 60.0

    # Base projection using current depletion rate
    base_projection_kwh = current_battery_kwh - (depletion_rate_kwh * hours_remaining)

    # Adjust for sunset impact (additional drain when solar stops)
    adjusted_projection_kwh = base_projection_kwh - sunset_impact['additional_drain_kwh']

    # Convert to percentage
    if total_capacity_kwh > 0:
        base_projection_pct = (base_projection_kwh / total_capacity_kwh) * 100
        adjusted_projection_pct = (adjusted_projection_kwh / total_capacity_kwh) * 100
    else:
        base_projection_pct = 0
        adjusted_projection_pct = 0

    return {
        'projected_battery_kwh_base': base_projection_kwh,
        'projected_battery_pct_base': base_projection_pct,
        'projected_battery_kwh_adjusted': adjusted_projection_kwh,
        'projected_battery_pct_adjusted': adjusted_projection_pct,
        'hours_remaining': hours_remaining
    }


def generate_recommendation(
    current_battery_pct: float,
    projected_battery_pct: float,
    target_minimum: float,
    depletion_rate: Dict[str, float],
    config
) -> Dict[str, Any]:
    """
    Generate thermostat adjustment recommendation

    Args:
        current_battery_pct: Current battery percentage
        projected_battery_pct: Projected battery at peak end
        target_minimum: Target minimum battery percentage
        depletion_rate: Depletion rate statistics
        config: Configuration object

    Returns:
        Recommendation details
    """
    deficit = target_minimum - projected_battery_pct

    # Use adjustment engine logic (from predictive mode)
    if deficit > 10:
        adjustment = 4
        urgency = "CRITICAL"
        reason = f"Projected {projected_battery_pct:.1f}% is {deficit:.1f}% below target - aggressive adjustment needed"
    elif deficit > 5:
        adjustment = 2
        urgency = "HIGH"
        reason = f"Projected {projected_battery_pct:.1f}% is {deficit:.1f}% below target - moderate adjustment needed"
    elif deficit > 0:
        adjustment = 2
        urgency = "MEDIUM"
        reason = f"Projected {projected_battery_pct:.1f}% is slightly below target"
    elif projected_battery_pct > (target_minimum + 10):
        adjustment = -2
        urgency = "LOW"
        reason = f"Projected {projected_battery_pct:.1f}% has comfortable margin - can restore comfort"
    else:
        adjustment = 0
        urgency = "NONE"
        reason = f"Projected {projected_battery_pct:.1f}% is on target"

    return {
        'recommended_temp_adjustment': adjustment,
        'urgency': urgency,
        'reason': reason,
        'deficit': deficit,
        'confidence': depletion_rate['confidence_score']
    }


def lambda_handler(event, context):
    """
    Lambda handler for analytics calculation

    Args:
        event: EventBridge scheduled event
        context: Lambda context

    Returns:
        Response dictionary
    """
    try:
        logger.info("Starting analytics calculation")

        # Initialize clients
        cfg, metrics_mgr, analytics_mgr, notif_mgr = init_clients()

        # Get latest metrics to determine current state
        current_time = datetime.utcnow()

        # Query last 60 minutes of metrics
        logger.info("Querying metrics from last 60 minutes")
        recent_metrics = metrics_mgr.query_recent_metrics(hours=1)

        if not recent_metrics:
            logger.warning("No metrics available for analysis")
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'No metrics available, skipping analysis'})
            }

        # Filter for peak period only (analytics only needed during peak)
        peak_metrics = [m for m in recent_metrics if 'peak' in m.get('peak_period', '')]

        if not peak_metrics:
            logger.info("Not in peak period, skipping analysis")
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'Off-peak period, no analysis needed'})
            }

        logger.info(f"Analyzing {len(peak_metrics)} peak period metrics")

        # Get current state from most recent metric
        latest = peak_metrics[0]
        current_battery_kwh = latest['battery_remaining_kwh']
        current_battery_pct = latest['battery_percentage']
        total_capacity_kwh = latest['total_pack_energy_kwh']
        current_solar_power = latest.get('solar_power', 0)
        minutes_until_peak_end = latest.get('minutes_until_peak_end', 0)
        minutes_until_sunset = latest.get('minutes_until_sunset', 0)

        # Calculate depletion rate
        depletion = calculate_depletion_rate(peak_metrics)
        logger.info(f"Depletion rate: {depletion['depletion_rate_kwh_per_hour']:.2f} kWh/hr "
                   f"({depletion['depletion_rate_percent_per_hour']:.2f}%/hr), "
                   f"confidence: {depletion['confidence_score']:.2f}")

        # Calculate sunset impact
        hours_until_peak_end = minutes_until_peak_end / 60.0
        sunset_impact = calculate_sunset_impact(
            current_time,
            minutes_until_sunset,
            current_solar_power,
            hours_until_peak_end
        )
        logger.info(f"Sunset impact: {sunset_impact['additional_drain_kwh']:.2f} kWh additional drain expected")

        # Project battery at peak end
        projection = project_battery_at_peak_end(
            current_battery_kwh,
            current_battery_pct,
            total_capacity_kwh,
            depletion['depletion_rate_kwh_per_hour'],
            minutes_until_peak_end,
            sunset_impact
        )
        logger.info(f"Projection: {projection['projected_battery_pct_adjusted']:.1f}% at peak end "
                   f"(base: {projection['projected_battery_pct_base']:.1f}%)")

        # Generate recommendation
        recommendation = generate_recommendation(
            current_battery_pct,
            projection['projected_battery_pct_adjusted'],
            cfg.target_battery_minimum,
            depletion,
            cfg
        )
        logger.info(f"Recommendation: {recommendation['recommended_temp_adjustment']}°F "
                   f"({recommendation['urgency']}) - {recommendation['reason']}")

        # Compile analytics result
        analytics_result = {
            'timestamp': current_time.isoformat() + 'Z',

            # Current state
            'current_battery_pct': current_battery_pct,
            'current_battery_kwh': current_battery_kwh,
            'current_solar_power': current_solar_power,
            'minutes_until_peak_end': minutes_until_peak_end,
            'minutes_until_sunset': minutes_until_sunset,

            # Depletion analysis
            'depletion_rate_kwh_per_hour': depletion['depletion_rate_kwh_per_hour'],
            'depletion_rate_percent_per_hour': depletion['depletion_rate_percent_per_hour'],
            'avg_battery_power': depletion['avg_battery_power'],
            'avg_solar_power': depletion['avg_solar_power'],
            'sample_count': depletion['sample_count'],
            'confidence_score': depletion['confidence_score'],

            # Sunset impact
            'solar_contribution_kwh_per_hour': sunset_impact['solar_contribution_kwh_per_hour'],
            'additional_drain_after_sunset_kwh': sunset_impact['additional_drain_kwh'],
            'solar_factor': sunset_impact['solar_factor'],

            # Projections
            'projected_battery_at_peak_end': projection['projected_battery_pct_adjusted'],
            'projected_battery_base': projection['projected_battery_pct_base'],
            'projected_battery_kwh': projection['projected_battery_kwh_adjusted'],

            # Recommendation
            'recommended_temp_adjustment': recommendation['recommended_temp_adjustment'],
            'urgency': recommendation['urgency'],
            'reason': recommendation['reason'],
            'deficit_from_target': recommendation['deficit'],
            'target_battery_minimum': cfg.target_battery_minimum
        }

        # Store analytics result
        analytics_mgr.save_analytics(analytics_result)
        logger.info("Analytics result saved to DynamoDB")

        # Send alert if critical situation
        if recommendation['urgency'] == 'CRITICAL':
            notif_mgr.send_warning(
                subject="Critical Battery Projection",
                message=f"Battery projected to reach {projection['projected_battery_pct_adjusted']:.1f}% at peak end\n"
                       f"Target: {cfg.target_battery_minimum}%\n"
                       f"Deficit: {recommendation['deficit']:.1f}%\n"
                       f"Recommendation: {recommendation['recommended_temp_adjustment']}°F adjustment\n"
                       f"Current battery: {current_battery_pct:.1f}%\n"
                       f"Depletion rate: {depletion['depletion_rate_kwh_per_hour']:.2f} kWh/hr"
            )

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Analytics calculation successful',
                'timestamp': analytics_result['timestamp'],
                'projected_battery': projection['projected_battery_pct_adjusted'],
                'recommendation': recommendation['recommended_temp_adjustment'],
                'urgency': recommendation['urgency']
            })
        }

    except Exception as e:
        logger.exception(f"Analytics calculation failed: {e}")

        try:
            notif_mgr.send_warning(
                subject="Analytics Function Error",
                message=f"Failed to calculate analytics:\n{str(e)}"
            )
        except:
            pass

        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Analytics calculation failed',
                'message': str(e)
            })
        }
