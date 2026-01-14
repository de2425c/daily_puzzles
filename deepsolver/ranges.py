"""Utilities for parsing and creating poker ranges in the solver's 1326-combo format."""

import re
from typing import Iterator

from .hand_utils import HAND_ORDER, HAND_TO_INDEX, RANKS, SUITS, RANK_ORDER, normalize_combo

# Default weight for included hands
DEFAULT_WEIGHT = 10000


def empty_range() -> list[int]:
    """Return an empty range (all zeros)."""
    return [0] * 1326


def full_range() -> list[int]:
    """Return a full range (all hands at max weight)."""
    return [DEFAULT_WEIGHT] * 1326


def _get_pair_combos(rank: str) -> list[str]:
    """Get all 6 combos for a pocket pair."""
    combos = []
    for i, s1 in enumerate(SUITS):
        for s2 in SUITS[i + 1 :]:
            # Higher suit first
            combos.append(f"{rank}{s1}{rank}{s2}")
    return combos


def _get_suited_combos(rank1: str, rank2: str) -> list[str]:
    """Get all 4 suited combos for two different ranks."""
    # Ensure rank1 is higher
    if RANK_ORDER[rank1] < RANK_ORDER[rank2]:
        rank1, rank2 = rank2, rank1

    combos = []
    for suit in SUITS:
        combos.append(f"{rank1}{suit}{rank2}{suit}")
    return combos


def _get_offsuit_combos(rank1: str, rank2: str) -> list[str]:
    """Get all 12 offsuit combos for two different ranks."""
    # Ensure rank1 is higher
    if RANK_ORDER[rank1] < RANK_ORDER[rank2]:
        rank1, rank2 = rank2, rank1

    combos = []
    for s1 in SUITS:
        for s2 in SUITS:
            if s1 != s2:
                combos.append(f"{rank1}{s1}{rank2}{s2}")
    return combos


def _get_all_combos(rank1: str, rank2: str) -> list[str]:
    """Get all 16 combos (4 suited + 12 offsuit) for two different ranks."""
    return _get_suited_combos(rank1, rank2) + _get_offsuit_combos(rank1, rank2)


def _expand_plus_notation(hand: str) -> Iterator[str]:
    """
    Expand plus notation to individual hands.

    Convention:
        - For pairs: go up to AA (99+ = 99, TT, JJ, QQ, KK, AA)
        - For non-pairs: keep lower card fixed, move higher card up
          (JTs+ = JTs, QTs, KTs, ATs)
        - When high card is A (max): keep A, move kicker up
          (AQo+ = AQo, AKo)

    Examples:
        JTs+ -> JTs, QTs, KTs, ATs
        99+ -> 99, TT, JJ, QQ, KK, AA
        AQo+ -> AQo, AKo
    """
    if len(hand) < 2:
        yield hand
        return

    rank1 = hand[0]
    rank2 = hand[1]

    # Check for suited/offsuit suffix
    suffix = ""
    if len(hand) >= 3 and hand[2] in "so":
        suffix = hand[2]

    r1_idx = RANK_ORDER.get(rank1, -1)
    r2_idx = RANK_ORDER.get(rank2, -1)

    if r1_idx < 0 or r2_idx < 0:
        yield hand.rstrip("+")
        return

    # Ensure r1_idx >= r2_idx (high card first)
    if r1_idx < r2_idx:
        r1_idx, r2_idx = r2_idx, r1_idx
        rank1, rank2 = rank2, rank1

    if rank1 == rank2:
        # Pair: 99+ means 99, TT, JJ, QQ, KK, AA
        for i in range(r1_idx, len(RANKS)):
            yield RANKS[i] + RANKS[i] + suffix
    elif r1_idx == len(RANKS) - 1:
        # High card is A (max): keep A, move kicker up
        # AQo+ = AQo, AKo (Q goes to K)
        for i in range(r2_idx, r1_idx):
            yield RANKS[r1_idx] + RANKS[i] + suffix
    else:
        # Non-pair: keep lower card fixed, move higher card up
        # JTs+ = JTs, QTs, KTs, ATs (T stays, J goes up)
        for i in range(r1_idx, len(RANKS)):
            low_idx = r2_idx  # lower card stays fixed
            if low_idx >= 0:
                yield RANKS[i] + RANKS[low_idx] + suffix


def _parse_single_hand(hand: str, weights: list[int], weight: int = DEFAULT_WEIGHT):
    """
    Parse a single hand notation and update weights.

    Supports:
        AA - pocket pair (6 combos)
        AKs - suited (4 combos)
        AKo - offsuit (12 combos)
        AK - all combos (16 combos)
    """
    hand = hand.strip()
    if not hand:
        return

    if len(hand) < 2:
        raise ValueError(f"Invalid hand notation: {hand}")

    rank1 = hand[0].upper()
    rank2 = hand[1].upper()

    if rank1 not in RANK_ORDER or rank2 not in RANK_ORDER:
        raise ValueError(f"Invalid ranks in hand: {hand}")

    suffix = hand[2:].lower() if len(hand) > 2 else ""

    if rank1 == rank2:
        # Pocket pair
        combos = _get_pair_combos(rank1)
    elif suffix == "s":
        combos = _get_suited_combos(rank1, rank2)
    elif suffix == "o":
        combos = _get_offsuit_combos(rank1, rank2)
    else:
        # All combos (suited + offsuit)
        combos = _get_all_combos(rank1, rank2)

    for combo in combos:
        normalized = normalize_combo(combo)
        if normalized in HAND_TO_INDEX:
            weights[HAND_TO_INDEX[normalized]] = weight


def parse_range_string(range_str: str, weight: int = DEFAULT_WEIGHT) -> list[int]:
    """
    Parse a range string into a 1326-element weight array.

    Args:
        range_str: Comma-separated hand notations like "AA,KK,AKs,AQo,JTs+"
        weight: Weight to assign to included hands (default: 10000)

    Returns:
        List of 1326 integers (0 or weight)

    Examples:
        parse_range_string("AA") -> 6 combos at weight
        parse_range_string("AKs") -> 4 combos
        parse_range_string("AK") -> 16 combos
        parse_range_string("JTs+") -> 16 combos (JTs,QTs,KTs,ATs)
        parse_range_string("AA,KK,AKs") -> 14 combos
    """
    weights = empty_range()

    # Split by comma and process each hand
    for hand in range_str.split(","):
        hand = hand.strip()
        if not hand:
            continue

        # Handle plus notation
        if hand.endswith("+"):
            for expanded in _expand_plus_notation(hand[:-1]):
                _parse_single_hand(expanded, weights, weight)
        else:
            _parse_single_hand(hand, weights, weight)

    return weights


def count_combos(weights: list[int], threshold: int = 1) -> int:
    """Count the number of combos with weight >= threshold."""
    return sum(1 for w in weights if w >= threshold)


def get_combos_in_range(weights: list[int], threshold: int = 1) -> list[str]:
    """Get list of combo strings with weight >= threshold."""
    return [HAND_ORDER[i] for i, w in enumerate(weights) if w >= threshold]


def range_to_string(weights: list[int], threshold: int = 5000) -> str:
    """
    Convert a weight array back to a human-readable range string.

    Note: This is a simplified conversion that lists individual hands,
    not optimized notation like "AA+" or "AKs".
    """
    combos = get_combos_in_range(weights, threshold)
    if not combos:
        return ""

    # Group by hand type
    pairs = []
    suited = []
    offsuit = []

    for combo in combos:
        r1, s1, r2, s2 = combo[0], combo[1], combo[2], combo[3]
        if r1 == r2:
            if r1 not in pairs:
                pairs.append(r1)
        elif s1 == s2:
            hand = f"{r1}{r2}s"
            if hand not in suited:
                suited.append(hand)
        else:
            hand = f"{r1}{r2}o"
            if hand not in offsuit:
                offsuit.append(hand)

    parts = []
    parts.extend(f"{r}{r}" for r in pairs)
    parts.extend(suited)
    parts.extend(offsuit)

    return ",".join(parts)


def firestore_range_to_weights(range_map: dict[str, float]) -> list[int]:
    """
    Convert a Firestore range format to a 1326-element weight array.

    Firestore stores ranges as: {"AcKc": 1.0, "AcKd": 0.5, "2d2c": 0.515, ...}
    where keys are 4-char combo strings and values are frequencies (0.0 to 1.0).

    Args:
        range_map: Dict mapping combo strings to frequencies (0.0-1.0)

    Returns:
        List of 1326 integers (weights scaled to 0-10000)

    Example:
        firestore_range_to_weights({"AcKc": 1.0, "AcKd": 0.5})
        -> [0, 0, ..., 10000, ..., 5000, ..., 0]  # at appropriate indices
    """
    weights = empty_range()

    for combo, freq in range_map.items():
        if not combo or not isinstance(freq, (int, float)):
            continue

        # Normalize the combo to canonical format
        try:
            normalized = normalize_combo(combo)
        except ValueError:
            # Skip invalid combos
            continue

        # Look up the index
        if normalized not in HAND_TO_INDEX:
            continue

        idx = HAND_TO_INDEX[normalized]

        # Convert frequency (0-1) to weight (0-10000)
        weight = int(freq * DEFAULT_WEIGHT)
        weights[idx] = weight

    return weights


def count_combos_weighted(weights: list[int]) -> float:
    """
    Count weighted combos (sum of frequencies).

    For a weight array, returns the sum divided by DEFAULT_WEIGHT,
    giving the effective number of combos accounting for mixed frequencies.

    Example:
        If a range has 100 combos at 100% and 50 combos at 50%,
        this returns 100 + 25 = 125.0
    """
    return sum(weights) / DEFAULT_WEIGHT
