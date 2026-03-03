#!/usr/bin/env python3
"""Move all puzzles from 2026-02-10 to 2026-02-09."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.firestore import PuzzleStorage


def main():
    storage = PuzzleStorage()

    print("Fetching all scheduled puzzles...")
    puzzles = storage.get_all_scheduled_puzzles()
    print(f"Found {len(puzzles)} total puzzles\n")

    # Show current counts
    counts = storage.get_puzzle_counts_by_date()
    print("Current date distribution:")
    for date in sorted(counts.keys()):
        print(f"  {date}: {counts[date]} puzzles")

    # Find puzzles on Feb 10
    feb10 = [p for p in puzzles if p.scheduled_date == "2026-02-10"]
    print(f"\nMoving {len(feb10)} puzzles from 2026-02-10 -> 2026-02-09")

    for p in feb10:
        storage.update_scheduled_puzzle(p.id, {"scheduled_date": "2026-02-09"})
        print(f"  Updated {p.id[:8]}...")

    # Verify
    print("\nNew date distribution:")
    new_counts = storage.get_puzzle_counts_by_date()
    for date in sorted(new_counts.keys()):
        print(f"  {date}: {new_counts[date]} puzzles")


if __name__ == "__main__":
    main()
