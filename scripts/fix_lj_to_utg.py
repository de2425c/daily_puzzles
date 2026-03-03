#!/usr/bin/env python3
"""
Fix LJ -> UTG in existing puzzles.

The iOS app uses UTG for the first position in 6-max, but the backend was
saving LJ (Lojack). This script updates all puzzles that have Hero="LJ"
to use "UTG" instead, and also fixes the Action tree.
"""

import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.firestore import PuzzleStorage


def fix_action_tree(action: dict) -> dict:
    """Replace LJ with UTG in the action tree."""
    if not action:
        return action

    fixed = {}
    for street, street_data in action.items():
        if not isinstance(street_data, dict):
            fixed[street] = street_data
            continue

        fixed_street = {}
        for key, value in street_data.items():
            # Replace LJ key with UTG
            new_key = "UTG" if key == "LJ" else key
            fixed_street[new_key] = value
        fixed[street] = fixed_street

    return fixed


def main(auto_confirm=False):
    storage = PuzzleStorage()

    # Get all scheduled puzzles
    print("Fetching all scheduled puzzles...")
    all_puzzles = storage.get_all_scheduled_puzzles()
    print(f"Found {len(all_puzzles)} puzzles")

    # Find puzzles with Hero="LJ" or LJ in action tree
    lj_puzzles = []
    for p in all_puzzles:
        has_lj = p.hero == "LJ"
        # Check if LJ is in the action tree
        if p.action:
            for street_data in p.action.values():
                if isinstance(street_data, dict) and "LJ" in street_data:
                    has_lj = True
                    break
        if has_lj:
            lj_puzzles.append(p)

    print(f"Found {len(lj_puzzles)} puzzles with LJ references")

    if not lj_puzzles:
        print("No puzzles to fix!")
        return

    # Confirm before proceeding
    print("\nPuzzles to update:")
    for p in lj_puzzles:
        print(f"  - {p.id}: {p.scheduled_date} - Hero={p.hero}")

    if not auto_confirm:
        response = input(f"\nUpdate {len(lj_puzzles)} puzzles? (y/n): ")
        if response.lower() != 'y':
            print("Aborted.")
            return
    else:
        print(f"\nAuto-confirming update of {len(lj_puzzles)} puzzles...")

    # Update each puzzle
    updated = 0
    for puzzle in lj_puzzles:
        try:
            path = f"{storage.NEW_DAILY_PUZZLES_COLLECTION}/{puzzle.id}"

            # Fix Hero field
            if puzzle.hero == "LJ":
                storage._update_field(path, "Hero", "UTG")
                print(f"  Fixed Hero for {puzzle.id}")

            # Fix Action tree
            fixed_action = fix_action_tree(puzzle.action)
            if fixed_action != puzzle.action:
                storage._update_field(path, "Action", fixed_action)
                print(f"  Fixed Action tree for {puzzle.id}")

            updated += 1
        except Exception as e:
            print(f"  ERROR updating {puzzle.id}: {e}")

    print(f"\nDone! Updated {updated}/{len(lj_puzzles)} puzzles.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()
    main(auto_confirm=args.yes)
