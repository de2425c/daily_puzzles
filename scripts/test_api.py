#!/usr/bin/env python3
"""
Test script to verify Deepsolver API connection.

Usage:
    python scripts/test_api.py

This script:
1. Loads the sample request from deepsolver-request-flop.json
2. Submits it to the Deepsolver API
3. Polls for the result
4. Prints a summary of the response
"""

import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from deepsolver import DeepsolverClient, get_api_token


def count_nodes(tree: dict) -> int:
    """Recursively count nodes in the tree."""
    count = 1
    for child in tree.get("children", []):
        count += count_nodes(child)
    return count


def main():
    # Load sample request
    request_path = Path(__file__).parent.parent / "deepsolver-request-flop.json"

    if not request_path.exists():
        print(f"Error: Sample request not found at {request_path}")
        sys.exit(1)

    print(f"Loading request from {request_path.name}...")
    with open(request_path) as f:
        request = json.load(f)

    print(f"  Board: {request.get('board')}")
    print(f"  Iterations: {request.get('iters')}")

    # Create client
    try:
        token = get_api_token()
        print(f"  API token loaded (ends with ...{token[-8:]})")
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    client = DeepsolverClient(api_token=token)

    # Run solve
    print("\n" + "=" * 50)
    try:
        result = client.run_and_wait(
            request,
            timeout_seconds=300,  # 5 minutes max
            poll_interval_seconds=5,
        )
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)

    # Analyze result
    print("\n" + "=" * 50)
    print("RESULT SUMMARY")
    print("=" * 50)

    # Check structure
    if "tree" not in result:
        print("Warning: No 'tree' in result")
        print(f"Keys: {list(result.keys())}")
        return

    tree = result["tree"]
    stats = result.get("stats", {})
    config = result.get("config", {})

    # Tree info
    node_count = count_nodes(tree)
    print(f"\nTree:")
    print(f"  Total nodes: {node_count}")
    print(f"  Root actions: {tree.get('actions')}")
    print(f"  Root player: {tree.get('player_id')}")
    print(f"  Street: {tree.get('street_id')} (1=flop, 2=turn, 3=river)")

    # Stats
    if stats:
        print(f"\nSolver stats:")
        print(f"  Iterations: {stats.get('iters')}")
        print(f"  Nash distance: {stats.get('nash_distance')}")
        print(f"  Time taken: {stats.get('time_taken')}s")
        print(f"  Tree size: {stats.get('tree_size')}")

    # Config
    if config:
        print(f"\nConfig:")
        print(f"  Board: {config.get('board')}")

    # Strategy sample (root node)
    if "data" in tree and "strategy" in tree["data"]:
        strategy = tree["data"]["strategy"]
        print(f"\nStrategy at root:")
        print(f"  Shape: {len(strategy)} actions x {len(strategy[0]) if strategy else 0} combos")

    print("\nAPI test completed successfully!")


if __name__ == "__main__":
    main()
