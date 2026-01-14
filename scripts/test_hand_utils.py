#!/usr/bin/env python3
"""
Test script for hand utilities and range parsing.

Usage:
    python scripts/test_hand_utils.py
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from deepsolver import (
    HAND_ORDER,
    combo_to_index,
    index_to_combo,
    normalize_combo,
    is_combo_blocked,
    get_unblocked_combos,
    parse_range_string,
    count_combos,
    get_combos_in_range,
)


def test_hand_order():
    """Test that hand order loaded correctly."""
    print("=" * 50)
    print("HAND ORDER")
    print("=" * 50)

    print(f"Hand order loaded: {len(HAND_ORDER)} combos")
    print(f"First combo: {HAND_ORDER[0]} (index 0)")
    print(f"Last combo: {HAND_ORDER[-1]} (index 1325)")

    assert len(HAND_ORDER) == 1326, f"Expected 1326 combos, got {len(HAND_ORDER)}"
    assert HAND_ORDER[0] == "2d2c", f"Expected first combo 2d2c, got {HAND_ORDER[0]}"

    print("PASSED")


def test_round_trip():
    """Test combo -> index -> combo round trip."""
    print("\n" + "=" * 50)
    print("ROUND TRIP TEST")
    print("=" * 50)

    test_combos = ["AhKh", "2d2c", "AsAh", "JsTc", "7h7d"]

    for combo in test_combos:
        idx = combo_to_index(combo)
        back = index_to_combo(idx)
        status = "OK" if back == combo else "FAIL"
        print(f"  {combo} -> {idx} -> {back} [{status}]")
        assert back == combo, f"Round trip failed for {combo}"

    print("PASSED")


def test_normalize():
    """Test combo normalization."""
    print("\n" + "=" * 50)
    print("NORMALIZE TEST")
    print("=" * 50)

    test_cases = [
        ("AhKh", "AhKh"),  # Already normalized
        ("KhAh", "AhKh"),  # Reversed ranks
        ("2d2c", "2d2c"),  # Pair, already normalized
        ("2c2d", "2d2c"),  # Pair, reversed suits
        ("TsJd", "JdTs"),  # J > T
    ]

    for input_combo, expected in test_cases:
        result = normalize_combo(input_combo)
        status = "OK" if result == expected else "FAIL"
        print(f"  {input_combo} -> {result} (expected {expected}) [{status}]")
        assert result == expected, f"Normalize failed for {input_combo}"

    print("PASSED")


def test_blocking():
    """Test combo blocking detection."""
    print("\n" + "=" * 50)
    print("BLOCKING TEST")
    print("=" * 50)

    board = "Ah7d2c"

    test_cases = [
        ("AhKh", True),   # Ah is on board
        ("AsKs", False),  # No overlap
        ("7d7c", True),   # 7d is on board
        ("2c2d", True),   # 2c is on board
        ("KsQs", False),  # No overlap
    ]

    for combo, expected in test_cases:
        result = is_combo_blocked(combo, board)
        status = "OK" if result == expected else "FAIL"
        print(f"  {combo} blocked by {board}: {result} (expected {expected}) [{status}]")
        assert result == expected, f"Block test failed for {combo}"

    # Test unblocked combos count
    unblocked = get_unblocked_combos(board)
    print(f"\n  Unblocked combos for {board}: {len(unblocked)} / 1326")
    # 3 cards on board, each blocks some combos
    # Rough estimate: each card blocks ~102 combos (51 pairs with other 51 cards)
    # But there's overlap, so fewer blocked total
    assert 1100 < len(unblocked) < 1326, f"Unexpected unblocked count: {len(unblocked)}"

    print("PASSED")


def test_range_parsing():
    """Test range string parsing."""
    print("\n" + "=" * 50)
    print("RANGE PARSING TEST")
    print("=" * 50)

    test_cases = [
        ("AA", 6),       # 6 combos of AA
        ("KK", 6),       # 6 combos of KK
        ("AKs", 4),      # 4 suited combos
        ("AKo", 12),     # 12 offsuit combos
        ("AK", 16),      # All 16 combos
        ("AA,KK", 12),   # 6 + 6
        ("AA,KK,AKs", 16),  # 6 + 6 + 4
    ]

    for range_str, expected_count in test_cases:
        weights = parse_range_string(range_str)
        actual_count = count_combos(weights)
        status = "OK" if actual_count == expected_count else "FAIL"
        print(f"  {range_str} -> {actual_count} combos (expected {expected_count}) [{status}]")
        assert actual_count == expected_count, f"Range parsing failed for {range_str}"

    print("PASSED")


def test_plus_notation():
    """Test plus notation expansion."""
    print("\n" + "=" * 50)
    print("PLUS NOTATION TEST")
    print("=" * 50)

    test_cases = [
        ("99+", 6 * 6),   # 99, TT, JJ, QQ, KK, AA = 6 pairs * 6 combos each
        ("JTs+", 4 * 4),  # JTs, QTs, KTs, ATs = 4 hands * 4 suited combos
        ("AQo+", 12 * 2), # AQo, AKo = 2 hands * 12 offsuit combos
    ]

    for range_str, expected_count in test_cases:
        weights = parse_range_string(range_str)
        actual_count = count_combos(weights)
        status = "OK" if actual_count == expected_count else "FAIL"
        print(f"  {range_str} -> {actual_count} combos (expected {expected_count}) [{status}]")
        assert actual_count == expected_count, f"Plus notation failed for {range_str}"

    print("PASSED")


def test_combos_in_range():
    """Test getting combos from a range."""
    print("\n" + "=" * 50)
    print("COMBOS IN RANGE TEST")
    print("=" * 50)

    weights = parse_range_string("AA")
    combos = get_combos_in_range(weights)

    print(f"  AA combos: {combos}")
    assert len(combos) == 6, f"Expected 6 AA combos, got {len(combos)}"

    # All should be pairs of aces
    for combo in combos:
        assert combo[0] == "A" and combo[2] == "A", f"Unexpected combo in AA: {combo}"

    print("PASSED")


def main():
    """Run all tests."""
    print("\n" + "=" * 50)
    print("HAND UTILITIES TEST SUITE")
    print("=" * 50 + "\n")

    try:
        test_hand_order()
        test_round_trip()
        test_normalize()
        test_blocking()
        test_range_parsing()
        test_plus_notation()
        test_combos_in_range()

        print("\n" + "=" * 50)
        print("ALL TESTS PASSED!")
        print("=" * 50)

    except AssertionError as e:
        print(f"\nTEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
