#!/usr/bin/env python3
"""
Script to delete puzzles from new_daily_puzzles with scheduled_date >= a given date.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.firestore import PuzzleStorage


def main():
    cutoff_date = "2026-01-28"

    print("Connecting to Firebase...")
    storage = PuzzleStorage()

    print("Fetching scheduled puzzles from new_daily_puzzles...")
    puzzles = storage.get_all_scheduled_puzzles()
    print(f"Found {len(puzzles)} total puzzles")

    # Filter puzzles on or after cutoff date
    to_delete = [p for p in puzzles if p.scheduled_date >= cutoff_date]
    print(f"\nPuzzles scheduled on or after {cutoff_date}: {len(to_delete)}")

    if not to_delete:
        print("No puzzles to delete.")
        return

    # Show what will be deleted
    print("\nPuzzles to delete:")
    for p in to_delete:
        print(f"  {p.id[:8]}... | {p.scheduled_date} | {p.hero}")

    print(f"\n{'='*50}")
    print(f"Deleting {len(to_delete)} puzzles...")
    print('='*50)

    deleted = 0
    errors = 0

    for puzzle in to_delete:
        path = f"{storage.NEW_DAILY_PUZZLES_COLLECTION}/{puzzle.id}"
        try:
            storage._delete_document(path)
            print(f"  Deleted {puzzle.id[:8]}... ({puzzle.scheduled_date})")
            deleted += 1
        except Exception as e:
            print(f"  ERROR deleting {puzzle.id[:8]}...: {e}")
            errors += 1

    print('='*50)
    print(f"\nDeleted {deleted} puzzles, {errors} errors")

    # Verify remaining
    print("\nRemaining scheduled dates:")
    remaining = storage.get_puzzle_counts_by_date()
    for date in sorted(remaining.keys()):
        print(f"  {date}: {remaining[date]} puzzles")


if __name__ == "__main__":
    main()
