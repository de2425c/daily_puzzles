"""
Classify puzzles by SPOT TYPE based on the Action structure.

Classification is based on spot type (the situation), NOT on what action hero takes.
All data comes from the Action structure - no tags needed.

Spot Types:
- "C-Betting": Hero is PFR, on flop, not facing bet
- "Barreling": Hero is PFR, on turn/river, bet prior street, not facing bet
- "Delayed C-Bet": Hero is PFR, on turn/river, didn't bet prior street, not facing bet
- "Facing C-Bet": Hero is NOT PFR, on flop, facing bet
- "Facing Barrels": Hero is NOT PFR, on turn/river, facing bet
- "Probing": Hero is NOT PFR, not facing bet
- "Facing Probe": Hero is PFR, facing bet (opponent probed)
"""

import re


def get_aggression_level(action_type: str) -> int:
    """
    Return aggression level for preflop actions.
    Higher number = later in the aggression sequence.
    """
    levels = {
        "Raise": 1,
        "3Bet": 2,
        "4Bet": 3,
        "5Bet": 4,
    }
    return levels.get(action_type, 0)


def get_action_sequence_key(key: str) -> int:
    """
    Get sort key for action sequence order.

    Keys like BTN, BB, BTN_2, BB_2 represent action order:
    - No suffix = first action round (0)
    - _2 suffix = second action round (2)
    - _call suffix = call after raise in same round (1)
    """
    match = re.match(r'^([A-Z]+)(?:_(\d+|call))?$', key)
    if match:
        suffix = match.group(2)
        if suffix is None:
            return 0
        elif suffix == "call":
            return 1
        else:
            return int(suffix)
    return 0


def find_preflop_aggressor(action_data: dict) -> str | None:
    """
    Find the LAST preflop aggressor (PFR).

    Critical: Must find the LAST aggressor, not the first opener.
    "BTN opens, SB 3-bets, BTN calls" -> SB is the PFR (last aggressor)

    Uses aggression level to determine order when suffix is the same:
    - Raise comes before 3Bet comes before 4Bet comes before 5Bet
    """
    preflop = action_data.get("preflop", {})
    if not preflop:
        return None

    aggressive_actions = {"Raise", "3Bet", "4Bet", "5Bet"}

    # Find the highest aggression level - that's the PFR
    highest_aggression = 0
    last_aggressor = None

    for key, action_info in preflop.items():
        if key == "Cards":
            continue
        if isinstance(action_info, dict):
            action_type = action_info.get("Action", "")
            if action_type in aggressive_actions:
                level = get_aggression_level(action_type)
                if level > highest_aggression:
                    highest_aggression = level
                    base_pos = key.split("_")[0]
                    last_aggressor = base_pos

    return last_aggressor


def get_decision_street(action_data: dict) -> str:
    """
    Determine the decision street from the Action structure.
    The decision is on the LAST street present in the action data.
    """
    if "river" in action_data:
        return "river"
    elif "turn" in action_data:
        return "turn"
    else:
        return "flop"


def is_facing_bet(action_data: dict, hero: str, street: str) -> bool:
    """
    Check if hero is facing a bet/raise on the decision street.

    The hero is facing a bet if any opponent bet/raised on this street.
    This handles cases where hero checks and then opponent bets.
    """
    street_data = action_data.get(street, {})
    if not street_data:
        return False

    hero_upper = hero.upper()

    # Check if any opponent bet or raised on this street
    for key, action_info in street_data.items():
        if key == "Cards":
            continue

        base_pos = key.split("_")[0]

        # Skip hero's own actions
        if base_pos == hero_upper:
            continue

        if isinstance(action_info, dict):
            action_type = action_info.get("Action", "")
            if action_type in ("Bet", "Raise"):
                return True

    return False


def hero_bet_prior_street(action_data: dict, hero: str, street: str) -> bool:
    """
    Check if hero bet on the prior street.
    For turn, check flop. For river, check turn.
    """
    if street == "flop":
        return False  # No prior street

    prior_street = "flop" if street == "turn" else "turn"
    prior_data = action_data.get(prior_street, {})

    if not prior_data:
        return False

    hero_upper = hero.upper()
    for key, action_info in prior_data.items():
        if key == "Cards":
            continue
        base_pos = key.split("_")[0]
        if base_pos == hero_upper and isinstance(action_info, dict):
            action_type = action_info.get("Action", "")
            if action_type in ("Bet", "Raise"):
                return True

    return False


def classify_spot_type(action_data: dict, hero: str) -> str | None:
    """
    Classify a puzzle by spot type based on the Action structure.

    Args:
        action_data: The Action dict with preflop, flop, turn, river data
        hero: The hero position (e.g., "SB", "BTN", "BB")

    Returns one of:
    - "C-Betting"
    - "Barreling"
    - "Delayed C-Bet"
    - "Facing C-Bet"
    - "Facing Barrels"
    - "Probing"
    - "Facing Probe"
    - None if classification fails
    """
    if not action_data or not hero:
        return None

    # Determine key factors
    pfr = find_preflop_aggressor(action_data)
    hero_is_pfr = (pfr == hero.upper())
    street = get_decision_street(action_data)
    opponent_bet = is_facing_bet(action_data, hero, street)
    hero_bet_prior = hero_bet_prior_street(action_data, hero, street)

    # Classification logic
    if hero_is_pfr:
        if opponent_bet:
            return "Facing Probe"
        if street == "flop":
            return "C-Betting"
        if hero_bet_prior:
            return "Barreling"
        else:
            return "Delayed C-Bet"
    else:
        # Hero is NOT the PFR
        if opponent_bet:
            if street == "flop":
                return "Facing C-Bet"
            else:
                return "Facing Barrels"
        else:
            return "Probing"
