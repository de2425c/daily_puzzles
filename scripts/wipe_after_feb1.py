"""Delete all day_plans and scheduled_puzzles with date > 2026-02-01 from Firestore."""

import sys
sys.path.insert(0, ".")

from storage.firestore import PuzzleStorage

def main():
    store = PuzzleStorage()

    cutoff = "2026-02-01"

    # Wipe day plans after cutoff
    plans = store.get_all_day_plans()
    deleted_plans = 0
    for plan in plans:
        if plan.scheduled_date > cutoff:
            store.delete_day_plan(plan.id)
            print(f"Deleted day_plan {plan.id} ({plan.scheduled_date})")
            deleted_plans += 1

    # Wipe scheduled puzzles after cutoff
    puzzles = store.get_all_scheduled_puzzles()
    deleted_puzzles = 0
    for puzzle in puzzles:
        if puzzle.scheduled_date > cutoff:
            store.delete_scheduled_puzzle(puzzle.id)
            print(f"Deleted puzzle {puzzle.id} ({puzzle.scheduled_date})")
            deleted_puzzles += 1

    print(f"\nDone. Deleted {deleted_plans} day plans and {deleted_puzzles} puzzles after {cutoff}.")

if __name__ == "__main__":
    main()
