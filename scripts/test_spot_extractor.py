#!/usr/bin/env python3
"""
Test script for the spot extractor.

Usage:
    python scripts/test_spot_extractor.py

This script:
1. Loads flop-response (1).json
2. Parses the tree
3. Extracts spot candidates
4. Prints summary and examples
"""

import json
import sys
from pathlib import Path
from collections import Counter

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from deepsolver.tree_parser import parse_tree, count_nodes, find_decision_nodes
from deepsolver.spot_extractor import SpotExtractor, categorize_board


def main():
    print("\n" + "=" * 60)
    print("SPOT EXTRACTOR TEST")
    print("=" * 60)

    # Load response file
    response_file = Path(__file__).parent.parent / "flop-response (1).json"
    if not response_file.exists():
        print(f"Error: {response_file} not found")
        return

    print(f"\nLoading {response_file.name}...")
    with open(response_file) as f:
        data = json.load(f)

    # Get metadata
    board = data.get("config", {}).get("board", "unknown")
    stats = data.get("stats", {})
    print(f"Board: {board}")
    print(f"Board texture: {categorize_board(board)}")
    print(f"Solver iterations: {stats.get('iters', 'N/A')}")
    print(f"Time taken: {stats.get('time_taken', 0):.2f}s")

    # Parse tree
    print("\nParsing tree...")
    tree = parse_tree(data["tree"])
    node_count = count_nodes(tree)
    decision_nodes = find_decision_nodes(tree)
    print(f"Total nodes: {node_count}")
    print(f"Decision nodes: {len(decision_nodes)}")

    # Extract spots
    print("\n" + "-" * 40)
    extractor = SpotExtractor(min_frequency=0.70, max_second_best=0.25)
    print(f"Extracting spots (min_freq={extractor.min_frequency}, max_second={extractor.max_second_best})...")

    spots = extractor.extract_spots(
        tree=tree,
        board=board,
        ip_position="UTG",
        oop_position="BB",
        task_id="test",
        stack_size_bb=98.0,  # From the response
    )

    print(f"Spots found: {len(spots)}")

    if not spots:
        print("No spots found. Try lowering thresholds.")
        return

    # Print some examples
    print("\n" + "=" * 60)
    print("SAMPLE SPOTS")
    print("=" * 60)

    # Show diverse examples
    shown_categories = set()
    shown_paths = set()
    sample_count = 0

    for spot in spots:
        # Show variety
        if spot.hand_category in shown_categories and spot.tree_path in shown_paths:
            continue

        sample_count += 1
        if sample_count > 5:
            break

        shown_categories.add(spot.hand_category)
        shown_paths.add(spot.tree_path)

        print(f"\nSpot {sample_count}:")
        print(f"  Board: {spot.board} ({spot.board_texture})")
        print(f"  Path: {spot.tree_path}")
        print(f"  Hero: {spot.hero_position} with {spot.hero_combo} ({spot.hand_category})")
        print(f"  Action: {spot.action_sequence}")
        print(f"  Pot: {spot.pot_size_bb:.1f}bb")

        print("  Actions:")
        for action, freq in sorted(spot.action_frequencies.items(), key=lambda x: -x[1]):
            ev = spot.ev_by_action.get(action, 0)
            marker = " <-- CORRECT" if action == spot.correct_action else ""
            print(f"    {action}: {freq*100:.0f}% (EV: {ev:.2f}bb){marker}")

    # Summary stats
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    # By position
    by_position = Counter(s.hero_position for s in spots)
    print(f"\nBy hero position:")
    for pos, count in by_position.most_common():
        print(f"  {pos}: {count}")

    # By hand category
    by_category = Counter(s.hand_category for s in spots)
    print(f"\nBy hand category:")
    for cat, count in by_category.most_common(10):
        print(f"  {cat}: {count}")

    # By correct action
    by_action = Counter(s.correct_action for s in spots)
    print(f"\nBy correct action:")
    for action, count in by_action.most_common():
        print(f"  {action}: {count}")

    # By tree depth
    by_depth = Counter(len(s.tree_path.split(":")) - 2 for s in spots)
    print(f"\nBy tree depth (actions taken):")
    for depth, count in sorted(by_depth.items()):
        print(f"  {depth} actions: {count}")

    print("\n" + "=" * 60)
    print("SPOT EXTRACTION TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
