#!/usr/bin/env python3
"""
One-time script to convert puzzles from new_daily_puzzles to daily_puzzles format
and upload them as puzzles 18-21.

Excludes puzzles where hero's hole cards are:
- Pocket 88 (any pair of eights)
- 96 (nine-six in any suit/order)

Also filters for puzzles with real explanations (not placeholders).
"""

import random
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.firestore import PuzzleStorage
from storage.models import ApprovedPuzzle, ScheduledPuzzle


def generate_title(sched: ScheduledPuzzle) -> str:
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


def get_hero_cards(sched: ScheduledPuzzle) -> str | None:
    """Extract hero's hole cards from the action structure."""
    try:
        preflop = sched.action.get("preflop", {})
        hero_pos = sched.hero

        # Try direct hero position first
        if hero_pos in preflop and "Cards" in preflop[hero_pos]:
            return preflop[hero_pos]["Cards"]

        # Look for hero position in any key (might have suffix like BB_2)
        for key, value in preflop.items():
            if key.startswith(hero_pos) and isinstance(value, dict) and "Cards" in value:
                return value["Cards"]

        return None
    except Exception:
        return None


def is_pocket_eights(cards: str) -> bool:
    """Check if cards represent pocket eights (any pair of 8s)."""
    if not cards or len(cards) != 4:
        return False

    # Extract ranks (first and third characters)
    rank1 = cards[0]
    rank2 = cards[2]

    return rank1 == "8" and rank2 == "8"


def is_nine_six(cards: str) -> bool:
    """Check if cards represent 96 (nine-six in any order/suit)."""
    if not cards or len(cards) != 4:
        return False

    # Extract ranks (first and third characters)
    rank1 = cards[0]
    rank2 = cards[2]

    ranks = {rank1, rank2}
    return ranks == {"9", "6"}


def has_real_explanation(sched: ScheduledPuzzle, min_length: int = 50) -> bool:
    """Check if the puzzle has a real explanation (not a placeholder)."""
    if not sched.correct_answers:
        return False

    correct_answer = sched.correct_answers[0]
    explanation = sched.explanations.get(correct_answer, "")

    return len(explanation) >= min_length


def should_exclude(sched: ScheduledPuzzle) -> tuple[bool, str]:
    """
    Check if puzzle should be excluded based on hero's hole cards or missing explanation.

    Returns:
        (should_exclude, reason)
    """
    # Check for real explanation first
    if not has_real_explanation(sched):
        return True, "no real explanation"

    cards = get_hero_cards(sched)

    if cards is None:
        return False, ""

    if is_pocket_eights(cards):
        return True, f"pocket 88 ({cards})"

    if is_nine_six(cards):
        return True, f"96 hand ({cards})"

    return False, ""


def convert_scheduled_to_approved(sched: ScheduledPuzzle, puzzle_id: int) -> ApprovedPuzzle:
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

    # Filter out excluded puzzles
    print("\nFiltering out excluded hands (pocket 88, 96)...")
    eligible = []
    excluded_count = 0

    for sched in scheduled:
        exclude, reason = should_exclude(sched)
        if exclude:
            excluded_count += 1
            print(f"  Excluding {sched.id[:8]}... - {reason}")
        else:
            eligible.append(sched)

    print(f"Excluded {excluded_count} puzzles, {len(eligible)} eligible")

    if len(eligible) < 4:
        print(f"Error: Need at least 4 eligible puzzles, but only found {len(eligible)}")
        return

    # Randomly select 4 puzzles
    print("\nRandomly selecting 4 puzzles...")
    selected = random.sample(eligible, 4)

    # Show what we selected
    print("\nSelected puzzles:")
    for i, sched in enumerate(selected):
        cards = get_hero_cards(sched)
        print(f"  {i+1}. ID: {sched.id[:8]}... | Date: {sched.scheduled_date} | Hero: {sched.hero} | Cards: {cards}")
        print(f"      Correct: {sched.correct_answers}")

    # Convert and upload as puzzles 18 and 19
    print("\n" + "="*50)
    print("Converting and uploading puzzles...")
    print("="*50)

    for i, sched in enumerate(selected):
        puzzle_id = 18 + i
        print(f"\n--- Puzzle {puzzle_id} ---")
        print(f"Source ID: {sched.id}")
        print(f"Scheduled date: {sched.scheduled_date}")
        print(f"Hero: {sched.hero}")
        print(f"Hero cards: {get_hero_cards(sched)}")
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
    for puzzle_id in [18, 19, 20, 21]:
        puzzle = storage.get_puzzle(puzzle_id)
        if puzzle:
            print(f"  Puzzle {puzzle_id}: {puzzle.title} - OK")
        else:
            print(f"  Puzzle {puzzle_id}: NOT FOUND - ERROR")


if __name__ == "__main__":
    main()
