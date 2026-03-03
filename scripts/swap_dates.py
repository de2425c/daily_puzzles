#!/usr/bin/env python3
"""Move scheduled_date: 2026-01-28 -> 2026-01-29, then 2026-01-31 -> 2026-01-28."""

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

    # Step 1: Move 2026-01-28 -> 2026-01-29
    jan28 = [p for p in puzzles if p.scheduled_date == "2026-01-28"]
    print(f"\nStep 1: Moving {len(jan28)} puzzles from 2026-01-28 -> 2026-01-29")
    for p in jan28:
        storage.update_scheduled_puzzle(p.id, {"scheduled_date": "2026-01-29"})
        print(f"  Updated {p.id[:8]}...")

    # Step 2: Move 2026-01-31 -> 2026-01-28
    jan31 = [p for p in puzzles if p.scheduled_date == "2026-01-31"]
    print(f"\nStep 2: Moving {len(jan31)} puzzles from 2026-01-31 -> 2026-01-28")
    for p in jan31:
        storage.update_scheduled_puzzle(p.id, {"scheduled_date": "2026-01-28"})
        print(f"  Updated {p.id[:8]}...")

    # Verify
    print("\nNew date distribution:")
    new_counts = storage.get_puzzle_counts_by_date()
    for date in sorted(new_counts.keys()):
        print(f"  {date}: {new_counts[date]} puzzles")


if __name__ == "__main__":
    main()
