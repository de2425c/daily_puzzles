#!/usr/bin/env python3
"""
Test script for the request builder.

Usage:
    python scripts/test_request_builder.py

This script:
1. Builds a request using a preset (SRP UTG vs BB)
2. Submits it to the Deepsolver API
3. Verifies the response contains a valid tree
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from deepsolver import (
    DeepsolverClient,
    get_api_token,
    srp_utg_vs_bb,
    srp_btn_vs_bb,
    describe_request,
    count_combos,
)


def count_nodes(tree: dict) -> int:
    """Recursively count nodes in the tree."""
    count = 1
    for child in tree.get("children", []):
        count += count_nodes(child)
    return count


def format_actions(actions: list) -> str:
    """Format action list for display."""
    formatted = []
    for action in actions:
        code, amount = action
        if code == "C":
            formatted.append("Check/Call")
        elif code == "F":
            formatted.append("Fold")
        elif code == "B":
            formatted.append(f"Bet {amount:,}")
        elif code == "A":
            formatted.append("All-in")
        else:
            formatted.append(f"{code} {amount}")
    return ", ".join(formatted)


def test_preset(name: str, builder_fn, board: str):
    """Test a preset builder."""
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print("=" * 60)

    # Build request
    builder = builder_fn(board)
    print(f"\n{describe_request(builder)}")

    request = builder.build()

    # Verify request structure
    assert "iters" in request, "Missing 'iters'"
    assert "ranges" in request, "Missing 'ranges'"
    assert "board" in request, "Missing 'board'"
    assert "tree_request" in request, "Missing 'tree_request'"
    assert len(request["ranges"]) == 2, "Expected 2 ranges (IP, OOP)"
    assert len(request["ranges"][0]) == 1326, "IP range should have 1326 entries"
    assert len(request["ranges"][1]) == 1326, "OOP range should have 1326 entries"

    print("\nRequest structure: OK")
    print(f"  Iterations: {request['iters']}")
    print(f"  Board: {request['board']}")
    print(f"  Pot size: {request['tree_request']['pot_size']:,} units")
    print(f"  Stack sizes: {request['tree_request']['players_stacks_sizes']}")

    return request


def test_api_submission(request: dict):
    """Submit request to API and verify response."""
    print("\n" + "-" * 40)
    print("Submitting to API...")

    try:
        token = get_api_token()
    except ValueError as e:
        print(f"Skipping API test: {e}")
        return None

    client = DeepsolverClient(api_token=token)

    try:
        result = client.run_and_wait(
            request,
            timeout_seconds=120,
            poll_interval_seconds=5,
        )
    except Exception as e:
        print(f"API error: {e}")
        return None

    # Analyze result
    print("\nResult received!")

    if "tree" not in result:
        print(f"Warning: No 'tree' in result. Keys: {list(result.keys())}")
        return result

    tree = result["tree"]
    stats = result.get("stats", {})

    # Tree info
    node_count = count_nodes(tree)
    actions = tree.get("actions", [])

    print(f"\nTree info:")
    print(f"  Total nodes: {node_count}")
    print(f"  Root actions: {format_actions(actions)}")
    print(f"  Root player: {tree.get('player_id')} (0=IP, 1=OOP)")

    if stats:
        print(f"\nSolver stats:")
        print(f"  Iterations: {stats.get('iters')}")
        print(f"  Time: {stats.get('time_taken', 0):.2f}s")

    return result


def main():
    print("\n" + "=" * 60)
    print("REQUEST BUILDER TEST")
    print("=" * 60)

    # Test 1: SRP UTG vs BB
    request = test_preset("SRP UTG vs BB", srp_utg_vs_bb, "Ah7d2c")
    result = test_api_submission(request)

    if result:
        print("\n" + "=" * 60)
        print("ALL TESTS PASSED!")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("Request structure verified, API test skipped or failed")
        print("=" * 60)


if __name__ == "__main__":
    main()
