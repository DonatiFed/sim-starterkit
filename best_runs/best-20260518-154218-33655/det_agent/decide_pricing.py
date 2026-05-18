"""Per-dish pricing decisions.

Pricing rules:
- Default 1.00x base. Tilt up on high-demand days, down on slow days.
- Premium dishes (Salmon, Risotto, Tagliatelle, Parmesan) tolerate higher mults.
- Pizzas are demand-sensitive; keep close to 1.00x except weekend evenings.
- Salads are inelastic upward; can mark up on hot/sunny days.
- End-game (days 25-30): +5-8% on premium dishes; final rep matters more than volume.
- Demand crash (rep declining, low covers): cut prices 5-10% to stimulate.
"""

from __future__ import annotations

from .constants import RECIPES, ALL_DISHES, PRICE_MULT_MIN, PRICE_MULT_MAX
from . import config


# Dish elasticity buckets (1=premium/inelastic, 0=elastic)
PREMIUM = {"Grilled Salmon", "Mushroom Risotto", "Chicken Parmesan", "Mushroom Tagliatelle"}
MID     = {"Spaghetti Carbonara", "Chicken Caesar Salad"}
ELASTIC = {"Pizza Margherita", "Pizza Pepperoni"}


# Per-DOW pricing modulation (additive on top of weekend/slow flags)
# Saturday is peak — push prices. Sunday is dead — drop them.
DOW_PRICE_DELTA: dict[str, float] = {
    "Monday": -0.02, "Tuesday": 0.00, "Wednesday": 0.00, "Thursday": 0.02,
    "Friday": 0.04, "Saturday": 0.06, "Sunday": -0.04,
}


def plan_prices(state, memory) -> dict[str, float]:
    """Return {dish: price} for each dish in active menu."""
    weekend = state.day_of_week in ("Friday", "Saturday")
    slow_day = state.day_of_week in ("Sunday", "Monday")
    sunny    = state.weather_today == "sunny"
    rainy    = state.weather_today in ("rainy", "stormy")
    end_game = state.days_remaining <= 5
    mid_game = 10 <= state.day <= 22
    rep_low  = state.reputation_rank <= 2  # Good or worse
    declining = state.customer_trend == "Declining"

    # Base multiplier shift by context.
    base_shift = config.BASE_PRICE_SHIFT
    # DOW-specific delta — finer-grained than weekend/slow_day flags
    base_shift += DOW_PRICE_DELTA.get(state.day_of_week, 0.0)

    # Reputation-tier pricing: high rep deserves premium pricing
    rep_band = state.reputation_band
    if rep_band == "Excellent":
        base_shift += 0.05
    elif rep_band == "Very Good":
        base_shift += 0.02
    elif rep_band == "Good":
        base_shift -= 0.02
    elif rep_band == "Fair":
        base_shift -= 0.06
    elif rep_band == "Poor":
        base_shift -= 0.10

    # Cash-tier pricing: when flush, we can risk a small demand dip for higher margin
    if state.cash > 30_000:
        base_shift += 0.03
    elif state.cash > 20_000:
        base_shift += 0.01
    elif state.cash < 5_000:
        base_shift -= 0.03
    if weekend:
        base_shift += config.WEEKEND_LIFT
    if slow_day:
        base_shift += config.SLOW_DAY_CUT
    if sunny:
        base_shift += config.SUNNY_LIFT
    if rainy:
        base_shift += config.RAINY_CUT
    if end_game:
        base_shift += config.END_GAME_LIFT
    if mid_game and state.reputation_rank >= 3:
        base_shift += config.MID_GAME_LIFT
    # Last 3 days: aggressive push (every cover counts toward final rep)
    if state.days_remaining <= 3 and state.reputation_rank >= 3:
        base_shift += 0.04
    # Sunny + weekend = peak: extra push for premium
    sunny_weekend_boost = 0.04 if (sunny and weekend) else 0.0
    if state.walkout_rank >= 2:
        base_shift += config.WALKOUT_DISCOUNT
    if declining and rep_low:
        base_shift += config.DECLINING_DISCOUNT
    if memory.scen_tourist and state.day <= 3:
        # Tourist surge: max push. Demand exceeds capacity, every cover is profit.
        base_shift += config.TOURIST_SURGE_LIFT + 0.04
    if memory.scen_tourist and 5 <= state.day <= 9:
        base_shift += config.TOURIST_DROP_CUT
    # Crisis-active pricing: supply-limited demand → charge more per cover
    if memory.scen_crisis and 5 <= state.day <= 20:
        base_shift += 0.03
    if memory.scen_crisis:
        base_shift -= 0.02
    if memory.scen_inflation:
        base_shift += config.INFLATION_LIFT
    if memory.scen_health:
        base_shift -= 0.05
    # Renovation: tables halved → suppress demand with higher prices, preserve margin
    if memory.scen_renovation and state.day <= memory.renov_start + 13:
        base_shift += 0.08
    # Post-renovation: satisfaction bonus + restored capacity → push prices
    if memory.scen_renovation and memory.renov_start + 14 <= state.day <= memory.renov_start + 24:
        base_shift += 0.04

    out: dict[str, float] = {}
    for dish in state.active_menu or ALL_DISHES:
        entry = state.menu_book.get(dish)
        if not entry:
            continue
        base_price = float(entry.get("base_price", 0))
        if base_price <= 0:
            continue
        # Per-bucket adjustment
        if dish in PREMIUM:
            mult = 1.00 + base_shift + config.PREMIUM_EXTRA + sunny_weekend_boost
        elif dish in ELASTIC:
            mult = 1.00 + base_shift + config.ELASTIC_EXTRA
        else:
            mult = 1.00 + base_shift

        # Force discount on dishes whose ingredient is expiring (push consumption)
        _, recipe = RECIPES.get(dish, (0, {}))
        for ing in recipe:
            inv = state.inventory.get(ing)
            if inv and inv.expiring_within(2) > 0.5:
                mult += config.EXPIRY_DISCOUNT
                break

        mult = max(PRICE_MULT_MIN, min(PRICE_MULT_MAX, mult))
        out[dish] = round(base_price * mult, 2)

    return out
