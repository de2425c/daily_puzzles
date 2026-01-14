"""Standard preflop ranges for common poker scenarios.

These are simplified approximations of GTO ranges, suitable for generating
training puzzles. They are not meant to be perfectly balanced.
"""

from .ranges import parse_range_string

# =============================================================================
# RFI (Raise First In) Ranges by Position
# =============================================================================

# UTG (Under the Gun) - Tightest opening range (~15%)
UTG_RFI_STR = ",".join([
    # Premium pairs
    "AA,KK,QQ,JJ,TT,99,88,77",
    # Premium broadways
    "AKs,AQs,AJs,ATs,KQs,KJs,QJs,JTs",
    "AKo,AQo",
    # Some suited aces
    "A5s,A4s",
])

# HJ (Hijack) - Slightly wider (~18%)
HJ_RFI_STR = ",".join([
    UTG_RFI_STR,
    "66",
    "A9s,A3s,A2s",
    "KTs,QTs,T9s",
    "AJo,KQo",
])

# CO (Cutoff) - Wider (~25%)
CO_RFI_STR = ",".join([
    HJ_RFI_STR,
    "55,44",
    "A8s,A7s,A6s",
    "K9s,Q9s,J9s,98s,87s,76s",
    "KJo,QJo,JTo",
])

# BTN (Button) - Widest (~45%)
BTN_RFI_STR = ",".join([
    CO_RFI_STR,
    "33,22",
    "K8s,K7s,K6s,K5s,K4s,K3s,K2s",
    "Q8s,Q7s,Q6s",
    "J8s,J7s",
    "T8s,T7s",
    "97s,96s,86s,85s,75s,74s,65s,64s,54s,53s,43s",
    "KTo,QTo,JTo,T9o,98o,87o",
    "A9o,A8o,A7o,A6o,A5o,A4o,A3o,A2o",
])

# SB (Small Blind) - Wide but not as wide as BTN (~35%)
SB_RFI_STR = ",".join([
    CO_RFI_STR,
    "33,22",
    "K8s,K7s,K6s,K5s",
    "Q8s,Q7s",
    "J8s,T8s,97s,86s,75s,64s,54s",
    "KTo,QTo,A9o,A8o,A7o,A6o,A5o,A4o,A3o,A2o",
])

# =============================================================================
# BB Defense Ranges (vs different positions)
# =============================================================================

# BB vs UTG - Tight defense (~25% of hands)
BB_DEFEND_VS_UTG_STR = ",".join([
    # Call with medium pairs, suited connectors, suited aces
    "TT,99,88,77,66,55,44,33,22",
    "AQs,AJs,ATs,A9s,A8s,A7s,A6s,A5s,A4s,A3s,A2s",
    "KQs,KJs,KTs,K9s",
    "QJs,QTs,Q9s",
    "JTs,J9s",
    "T9s,T8s",
    "98s,97s",
    "87s,86s",
    "76s,75s",
    "65s,64s",
    "54s",
    # Some offsuit broadways
    "AQo,AJo,ATo",
    "KQo,KJo",
    "QJo",
])

# BB vs CO - Wider defense (~35%)
BB_DEFEND_VS_CO_STR = ",".join([
    BB_DEFEND_VS_UTG_STR,
    "A9o,A8o,A7o,A6o,A5o,A4o",
    "KTo,K9o",
    "QTo,Q9o",
    "JTo,J9o",
    "T9o,T8o",
    "98o,97o",
    "87o",
    "K8s,K7s,K6s,K5s,K4s,K3s,K2s",
    "Q8s,Q7s,Q6s",
    "J8s,J7s",
    "53s,43s",
])

# BB vs BTN - Widest defense (~45%)
BB_DEFEND_VS_BTN_STR = ",".join([
    BB_DEFEND_VS_CO_STR,
    "A3o,A2o",
    "K8o,K7o,K6o,K5o",
    "Q8o,Q7o",
    "J8o,J7o",
    "T7o",
    "96o,86o,85o",
    "76o,75o,74o",
    "65o,64o",
    "54o,53o",
    "Q5s,Q4s,Q3s,Q2s",
    "J6s,J5s,J4s",
    "T6s,T5s",
    "95s,94s",
    "84s,83s",
    "73s,72s",
    "63s,62s",
    "52s,42s,32s",
])

# BB vs SB - Very wide defense (~55%)
BB_DEFEND_VS_SB_STR = ",".join([
    BB_DEFEND_VS_BTN_STR,
    "K4o,K3o,K2o",
    "Q6o,Q5o,Q4o,Q3o,Q2o",
    "J6o,J5o,J4o",
    "T6o,T5o",
    "96o,95o",
    "43o",
])

# =============================================================================
# Cached parsed ranges
# =============================================================================

_RANGE_CACHE: dict[str, list[int]] = {}


def _get_cached_range(range_str: str) -> list[int]:
    """Get or compute a parsed range."""
    if range_str not in _RANGE_CACHE:
        _RANGE_CACHE[range_str] = parse_range_string(range_str)
    return _RANGE_CACHE[range_str].copy()


# =============================================================================
# Public API
# =============================================================================

def get_rfi_range(position: str) -> list[int]:
    """
    Get the RFI (Raise First In) range for a position.

    Args:
        position: One of "UTG", "HJ", "CO", "BTN", "SB"

    Returns:
        1326-element weight array
    """
    position = position.upper()
    ranges = {
        "UTG": UTG_RFI_STR,
        "HJ": HJ_RFI_STR,
        "CO": CO_RFI_STR,
        "BTN": BTN_RFI_STR,
        "SB": SB_RFI_STR,
    }
    if position not in ranges:
        raise ValueError(f"Unknown position: {position}. Use one of {list(ranges.keys())}")
    return _get_cached_range(ranges[position])


def get_defend_range(defender: str, opener: str) -> list[int]:
    """
    Get the defense range for a position vs an opener.

    Args:
        defender: Defending position (currently only "BB" supported)
        opener: Opening position ("UTG", "HJ", "CO", "BTN", "SB")

    Returns:
        1326-element weight array
    """
    defender = defender.upper()
    opener = opener.upper()

    if defender != "BB":
        raise ValueError(f"Only BB defense ranges implemented, got: {defender}")

    ranges = {
        "UTG": BB_DEFEND_VS_UTG_STR,
        "HJ": BB_DEFEND_VS_UTG_STR,  # Use UTG range for HJ too
        "CO": BB_DEFEND_VS_CO_STR,
        "BTN": BB_DEFEND_VS_BTN_STR,
        "SB": BB_DEFEND_VS_SB_STR,
    }
    if opener not in ranges:
        raise ValueError(f"Unknown opener: {opener}. Use one of {list(ranges.keys())}")
    return _get_cached_range(ranges[opener])
