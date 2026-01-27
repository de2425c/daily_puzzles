#!/usr/bin/env python3
"""
Script to shift scheduled_date for all puzzles in new_daily_puzzles forward by 8 days.

This moves 2026-01-17 -> 2026-01-25, 2026-01-18 -> 2026-01-26, etc.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.firestore import PuzzleStorage


def main():
    print("Connecting to Firebase...")
    storage = PuzzleStorage()

    print("Fetching scheduled puzzles from new_daily_puzzles...")
    puzzles = storage.get_all_scheduled_puzzles()
    print(f"Found {len(puzzles)} puzzles")

    if not puzzles:
        print("No puzzles to update.")
        return

    # Show current date distribution
    print("\nCurrent scheduled dates:")
    date_counts = storage.get_puzzle_counts_by_date()
    for date in sorted(date_counts.keys()):
        print(f"  {date}: {date_counts[date]} puzzles")

    # Calculate the shift
    days_to_add = 1

    print(f"\nShifting all dates forward by {days_to_add} days...")
    print("=" * 50)

    updated = 0
    errors = 0

    for puzzle in puzzles:
        old_date = puzzle.scheduled_date

        # Parse and add 8 days
        old_dt = datetime.strptime(old_date, "%Y-%m-%d")
        new_dt = old_dt + timedelta(days=days_to_add)
        new_date = new_dt.strftime("%Y-%m-%d")

        print(f"  {puzzle.id[:8]}... | {old_date} -> {new_date}")

        try:
            storage.update_scheduled_puzzle(puzzle.id, {"scheduled_date": new_date})
            updated += 1
        except Exception as e:
            print(f"    ERROR: {e}")
            errors += 1

    print("=" * 50)
    print(f"\nUpdated {updated} puzzles, {errors} errors")

    # Verify by showing new date distribution
    print("\nNew scheduled dates:")
    new_date_counts = storage.get_puzzle_counts_by_date()
    for date in sorted(new_date_counts.keys()):
        print(f"  {date}: {new_date_counts[date]} puzzles")


if __name__ == "__main__":
    main()
