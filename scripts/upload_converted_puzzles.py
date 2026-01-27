#!/usr/bin/env python3
"""
One-time script to convert puzzles from new_daily_puzzles to daily_puzzles format
and upload them as puzzles 16 and 17.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.firestore import PuzzleStorage
from storage.models import ApprovedPuzzle


def generate_title(sched) -> str:
    """Generate a catchy title based on the puzzle content."""
    hero = sched.hero
    street = "Flop" if "flop" in str(sched.action).lower() else "Turn" if "turn" in str(sched.action).lower() else "River"

    # Try to determine the type of decision
    correct = sched.correct_answers[0] if sched.correct_answers else ""

    if "check" in correct.lower():
        return f"{hero}'s Check Decision"
    elif "bet" in correct.lower():
        if "overbet" in correct.lower() or "all-in" in correct.lower():
            return f"{hero}'s Big Bet Spot"
        return f"{hero}'s Value Bet"
    elif "call" in correct.lower():
        return f"{hero}'s Calling Decision"
    elif "fold" in correct.lower():
        return f"{hero}'s Tough Fold"
    elif "raise" in correct.lower():
        return f"{hero}'s Raise or Fold"

    return f"{hero} on the {street}"


def convert_scheduled_to_approved(sched, puzzle_id: int) -> ApprovedPuzzle:
    """Convert a ScheduledPuzzle to ApprovedPuzzle format."""
    # Get the primary correct answer (first in list)
    correct_answer = sched.correct_answers[0] if sched.correct_answers else ""

    # Get the explanation for the correct answer
    explanation = sched.explanations.get(correct_answer, "")
    if not explanation and sched.explanations:
        # Fall back to first available explanation
        explanation = next(iter(sched.explanations.values()))

    # Generate a title
    title = generate_title(sched)

    return ApprovedPuzzle(
        puzzle_id=puzzle_id,
        title=title,
        question_text=sched.question_text,
        structure=sched.structure,
        effective_stacks=sched.effective_stacks,
        hero=sched.hero,
        action=sched.action,
        pot_size_at_decision=sched.pot_size_at_decision,
        answer_options=sched.answer_options,
        correct_answer=correct_answer,
        explanation=explanation,
        difficulty=sched.difficulty,
        tags=sched.tags,
    )


def main():
    print("Connecting to Firebase...")
    storage = PuzzleStorage()

    print("Fetching scheduled puzzles from new_daily_puzzles...")
    scheduled = storage.get_all_scheduled_puzzles()
    print(f"Found {len(scheduled)} scheduled puzzles")

    if len(scheduled) < 2:
        print(f"Error: Need at least 2 puzzles, but only found {len(scheduled)}")
        return

    # Show what we found
    print("\nAvailable puzzles:")
    for i, sched in enumerate(scheduled[:5]):
        print(f"  {i+1}. ID: {sched.id[:8]}... | Date: {sched.scheduled_date} | Hero: {sched.hero}")
        print(f"      Correct: {sched.correct_answers}")

    # Convert and upload first 2 puzzles as puzzles 16 and 17
    print("\n" + "="*50)
    print("Converting and uploading puzzles...")
    print("="*50)

    for i, sched in enumerate(scheduled[:2]):
        puzzle_id = 16 + i
        print(f"\n--- Puzzle {puzzle_id} ---")
        print(f"Source ID: {sched.id}")
        print(f"Scheduled date: {sched.scheduled_date}")
        print(f"Hero: {sched.hero}")
        print(f"Correct answers: {sched.correct_answers}")

        approved = convert_scheduled_to_approved(sched, puzzle_id)

        print(f"Title: {approved.title}")
        print(f"Correct answer: {approved.correct_answer}")
        print(f"Explanation preview: {approved.explanation[:100]}..." if len(approved.explanation) > 100 else f"Explanation: {approved.explanation}")

        # Upload to Firebase
        doc_id = storage.save_puzzle(approved)
        print(f"Uploaded as document ID: {doc_id}")

    print("\n" + "="*50)
    print("Upload complete!")
    print("="*50)

    # Verify by reading back
    print("\nVerifying uploads...")
    for puzzle_id in [16, 17]:
        puzzle = storage.get_puzzle(puzzle_id)
        if puzzle:
            print(f"  Puzzle {puzzle_id}: {puzzle.title} - OK")
        else:
            print(f"  Puzzle {puzzle_id}: NOT FOUND - ERROR")


if __name__ == "__main__":
    main()
