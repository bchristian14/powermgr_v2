"""
Thermostat adjustment logic - supports both fixed and predictive modes
"""
import logging
from typing import Dict, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class AdjustmentMode(Enum):
    """Thermostat adjustment modes"""
    FIXED = "fixed"
    PREDICTIVE = "predictive"


class ThermostatAdjustmentEngine:
    """
    Determines thermostat adjustments using either fixed thresholds or predictive analytics
    """

    def __init__(self, config):
        """
        Initialize adjustment engine

        Args:
            config: Configuration object with adjustment settings
        """
        self.config = config
        self.mode = AdjustmentMode(config.adjustment_mode)

    def calculate_adjustment(
        self,
        current_battery_pct: float,
        current_status: int,
        analytics: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Calculate thermostat adjustment based on configured mode

        Args:
            current_battery_pct: Current battery percentage
            current_status: Current threshold status (0, 1, 2, or 3)
            analytics: Optional analytics data (required for predictive mode)

        Returns:
            Dictionary with:
                - adjustment: Temperature adjustment in degrees F (+2, +4, -2, or 0)
                - new_status: New threshold status (for fixed mode)
                - reason: Explanation of adjustment
                - mode_used: Which mode was used
        """
        if self.mode == AdjustmentMode.FIXED:
            return self._calculate_fixed_adjustment(current_battery_pct, current_status)
        elif self.mode == AdjustmentMode.PREDICTIVE:
            return self._calculate_predictive_adjustment(
                current_battery_pct,
                current_status,
                analytics
            )
        else:
            raise ValueError(f"Unknown adjustment mode: {self.mode}")

    def _calculate_fixed_adjustment(
        self,
        battery_pct: float,
        current_status: int
    ) -> Dict[str, Any]:
        """
        Fixed threshold-based adjustment (original Pi logic)

        Thresholds:
        - 50%: First threshold, +2°F
        - 35%: Second threshold, +2°F (total +4°F)
        - 20%: Third threshold, +4°F (total +8°F)

        Args:
            battery_pct: Current battery percentage
            current_status: Current status (0-3)

        Returns:
            Adjustment details
        """
        adjustment = 0
        new_status = current_status
        reason = "No adjustment needed"

        # First threshold
        if battery_pct <= self.config.first_threshold and current_status < 1:
            adjustment = 2
            new_status = 1
            reason = f"Battery at {battery_pct}% crossed first threshold ({self.config.first_threshold}%)"

        # Second threshold
        elif battery_pct <= self.config.second_threshold and current_status < 2:
            adjustment = 2
            new_status = 2
            reason = f"Battery at {battery_pct}% crossed second threshold ({self.config.second_threshold}%)"

        # Third threshold (critical)
        elif battery_pct <= self.config.third_threshold and current_status < 3:
            adjustment = 4  # Aggressive adjustment
            new_status = 3
            reason = f"Battery at {battery_pct}% crossed third threshold ({self.config.third_threshold}%) - CRITICAL"

        return {
            'adjustment': adjustment,
            'new_status': new_status,
            'reason': reason,
            'mode_used': 'fixed',
            'current_battery': battery_pct
        }

    def _calculate_predictive_adjustment(
        self,
        battery_pct: float,
        current_status: int,
        analytics: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Predictive analytics-based adjustment (Phase 2+)

        Uses projected battery level at peak end to make smarter decisions.

        Args:
            battery_pct: Current battery percentage
            current_status: Current status (for state tracking)
            analytics: Analytics data with projections

        Returns:
            Adjustment details
        """
        if not analytics:
            # Fallback to fixed mode if analytics unavailable
            logger.warning("Predictive mode enabled but no analytics data available, using fixed thresholds")
            return self._calculate_fixed_adjustment(battery_pct, current_status)

        projected_battery = analytics.get('projected_battery_at_peak_end', battery_pct)
        target_minimum = self.config.target_battery_minimum
        current_adjustment = analytics.get('current_total_adjustment', 0)

        adjustment = 0
        reason = "No adjustment needed"

        # Calculate deficit/surplus from target
        deficit = target_minimum - projected_battery

        # Decision logic based on projection
        if deficit > 10:
            # Significant deficit - aggressive adjustment
            adjustment = 4
            reason = f"Projected {projected_battery:.1f}% at peak end, {deficit:.1f}% below target - AGGRESSIVE"

        elif deficit > 5:
            # Moderate deficit - moderate adjustment
            adjustment = 2
            reason = f"Projected {projected_battery:.1f}% at peak end, {deficit:.1f}% below target"

        elif deficit > 0:
            # Small deficit - small adjustment
            adjustment = 2
            reason = f"Projected {projected_battery:.1f}% at peak end, slightly below target"

        elif projected_battery > (target_minimum + 10) and current_adjustment > 0:
            # Comfortable margin - can reduce previous adjustments
            adjustment = -2
            reason = f"Projected {projected_battery:.1f}% at peak end, sufficient margin to restore comfort"

        else:
            reason = f"Projected {projected_battery:.1f}% at peak end, on target"

        # Apply predictive override if enabled
        if self.config.enable_predictive_override and adjustment == 0:
            # Even if predictive says no adjustment, check fixed thresholds as safety net
            fixed_result = self._calculate_fixed_adjustment(battery_pct, current_status)
            if fixed_result['adjustment'] > 0:
                logger.info("Predictive override: applying fixed threshold adjustment as safety measure")
                return {
                    **fixed_result,
                    'mode_used': 'predictive_with_fixed_override',
                    'predicted_battery': projected_battery
                }

        return {
            'adjustment': adjustment,
            'new_status': current_status,  # Predictive doesn't use status
            'reason': reason,
            'mode_used': 'predictive',
            'current_battery': battery_pct,
            'projected_battery': projected_battery,
            'deficit': deficit,
            'depletion_rate': analytics.get('depletion_rate_kwh_per_hour', 0),
            'confidence': analytics.get('confidence_score', 0)
        }

    def validate_adjustment(self, adjustment: int) -> bool:
        """
        Validate that adjustment is within safe bounds

        Args:
            adjustment: Proposed temperature adjustment

        Returns:
            True if valid, False otherwise
        """
        # Safety limits: don't adjust more than ±8°F total
        return -8 <= adjustment <= 8

    def get_mode_description(self) -> str:
        """Get human-readable description of current mode"""
        if self.mode == AdjustmentMode.FIXED:
            return (
                f"Fixed threshold mode:\n"
                f"  • {self.config.first_threshold}% battery: +2°F\n"
                f"  • {self.config.second_threshold}% battery: +2°F more\n"
                f"  • {self.config.third_threshold}% battery: +4°F more (critical)"
            )
        else:
            return (
                f"Predictive mode:\n"
                f"  • Target: {self.config.target_battery_minimum}% at peak end\n"
                f"  • Uses battery depletion rate & solar forecast\n"
                f"  • Adjusts based on projected end state\n"
                f"  • Override enabled: {self.config.enable_predictive_override}"
            )
