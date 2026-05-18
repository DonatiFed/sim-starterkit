"""Deterministic staff planner.

Staff level is critical: too few → walkouts → reputation damage. Too many →
burn cash. We size staff to expected covers (with a small safety margin) and
react to observed signals (bottleneck hours, wait times, walkouts).
"""

from __future__ import annotations

from .constants import DOW_STAFF, STAFF_MIN, STAFF_MAX, KITCHEN_THROUGHPUT_PER_STAFF
from .predict import demand_estimate, staff_needed_for
from . import config


def plan_staff(state, memory) -> int:
    """Return target staff level (3-15)."""
    # Start from expected demand
    de = demand_estimate(state, memory)
    expected = de["expected"]
    capacity_staff = staff_needed_for(expected, state)

    # Floor: DOW-anchored default (in case demand prediction is too low)
    dow_default = DOW_STAFF.get(state.day_of_week, 6) + config.STAFF_DELTA
    target = max(capacity_staff, dow_default)

    # Weekend + sunny + good rep → push to max (peak revenue day)
    if (state.day_of_week in ("Friday", "Saturday")
            and state.weather_today == "sunny"
            and state.reputation_rank >= 3):
        target = max(target, 14)

    # Excellent rep → demand surges, push staff
    if state.reputation_band == "Excellent" and state.day_of_week in ("Thursday", "Friday", "Saturday"):
        target = max(target, 13)

    # Stormy weather on slow day → bare minimum staff
    if state.weather_today == "stormy" and state.day_of_week in ("Sunday", "Monday"):
        target = min(target, 4)

    # Reactive bump if yesterday had walkouts on a similar day type
    if state.walkout_rank >= 2:  # Some/Many
        # Big bump for Many (3) walkouts
        bump = 2 if state.walkout_rank >= 3 else 1
        target = max(target, state.staff_level + bump)
    elif state.walkout_rank >= 1 and len(state.bottleneck_hours) >= 2:
        target = max(target, state.staff_level + 1)

    # If yesterday utilization was low (<40%) AND no walkouts, trim staff
    if state.walkout_rank == 0 and state.table_util_peak < 0.40 and state.day > 1:
        target = max(target - 1, capacity_staff)
    # Aggressive trim on consecutive low-util days (Sun/Mon mostly)
    if state.walkout_rank == 0 and state.table_util_peak < 0.25 and state.day > 1:
        target = max(target - 2, 3)

    # Scenario adjustments
    # Renovation: capacity halved → kitchen rarely bottleneck. Cap staff hard.
    if memory.scen_renovation and state.day <= memory.renov_start + 13:
        target = min(target, 5)
    # Post-renovation boost: capacity restored + satisfaction bonus → ramp up
    if memory.scen_renovation and state.day > memory.renov_start + 13:
        target = max(target, dow_default + 1)
    # Tourist surge first 3 days: staff up aggressively
    if memory.scen_tourist and state.day <= 4:
        target = max(target, 11)
    # Tourist post-surge (5-10): drop
    if memory.scen_tourist and 5 <= state.day <= 9:
        target = min(target, dow_default)
    # End-game: don't cut staff (quality matters for final rep)
    if state.days_remaining <= 5:
        target = max(target, dow_default)
    # Crisis: keep modest staff (capacity already limited by inventory)
    if memory.scen_crisis:
        target = min(target, dow_default + 1)

    return max(STAFF_MIN, min(STAFF_MAX, int(target)))
