#!/usr/bin/env python3
"""
Test script for storage module.

Usage:
    python scripts/test_storage.py

This script:
1. Creates a sample SpotCandidate
2. Tests serialization round-trip
3. Saves to Firestore (optional - requires credentials)
4. Tests puzzle conversion
"""

import sys
from pathlib import Path
from datetime import datetime
from uuid import uuid4

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from deepsolver.spot_extractor import SpotCandidate
from storage.models import (
    spot_to_firestore,
    spot_from_firestore,
    spot_to_puzzle,
    ApprovedPuzzle,
)


def create_sample_spot() -> SpotCandidate:
    """Create a sample SpotCandidate for testing."""
    return SpotCandidate(
        id=str(uuid4()),
        source_task_id="test-task-123",
        board="7hTh3d",
        hero_combo="AhKd",
        hero_position="BB",
        villain_position="UTG",
        street="flop",
        pot_size_bb=4.5,
        stack_size_bb=97.5,
        action_sequence="UTG bets small, BB to act",
        tree_path="r:0:b1485000",
        available_actions=["Fold", "Call", "Raise"],
        action_frequencies={"Fold": 0.02, "Call": 0.78, "Raise": 0.20},
        correct_action="Call",
        correct_frequency=0.78,
        ev_by_action={"Fold": -1.5, "Call": 2.1, "Raise": 1.8},
        hand_category="top_pair",
        board_texture="wet",
        created_at=datetime.now(),
    )


def test_serialization():
    """Test spot serialization round-trip."""
    print("\n" + "=" * 60)
    print("SERIALIZATION TEST")
    print("=" * 60)

    spot = create_sample_spot()
    print(f"\nOriginal spot:")
    print(f"  ID: {spot.id}")
    print(f"  Board: {spot.board}")
    print(f"  Hero: {spot.hero_position} with {spot.hero_combo}")
    print(f"  Correct action: {spot.correct_action} ({spot.correct_frequency*100:.0f}%)")

    # Serialize to Firestore format
    doc = spot_to_firestore(spot)
    print(f"\nSerialized to Firestore:")
    print(f"  Keys: {list(doc.keys())}")
    print(f"  Status: {doc['status']}")

    # Deserialize back
    restored = spot_from_firestore(doc)
    print(f"\nRestored from Firestore:")
    print(f"  ID: {restored.id}")
    print(f"  Board: {restored.board}")
    print(f"  Hero: {restored.hero_position} with {restored.hero_combo}")

    # Verify round-trip
    assert spot.id == restored.id
    assert spot.board == restored.board
    assert spot.hero_combo == restored.hero_combo
    assert spot.correct_action == restored.correct_action
    assert spot.action_frequencies == restored.action_frequencies

    print("\nSerialization round-trip: PASSED")


def test_puzzle_conversion():
    """Test converting spot to puzzle."""
    print("\n" + "=" * 60)
    print("PUZZLE CONVERSION TEST")
    print("=" * 60)

    spot = create_sample_spot()

    puzzle = spot_to_puzzle(
        spot=spot,
        puzzle_id=999,
        title="Test Puzzle Title",
        explanation="This is a test explanation for the puzzle.",
        difficulty=2,
    )

    print(f"\nConverted to ApprovedPuzzle:")
    print(f"  PuzzleID: {puzzle.puzzle_id}")
    print(f"  Title: {puzzle.title}")
    print(f"  Question: {puzzle.question_text}")
    print(f"  Hero: {puzzle.hero}")
    print(f"  Correct: {puzzle.correct_answer}")
    print(f"  Difficulty: {puzzle.difficulty}")
    print(f"  Tags: {puzzle.tags}")

    # Test Firestore serialization
    firestore_doc = puzzle.to_firestore()
    print(f"\nFirestore document keys: {list(firestore_doc.keys())}")
    print(f"  PuzzleID: {firestore_doc['PuzzleID']}")
    print(f"  Title: {firestore_doc['Title']}")

    # Verify structure
    assert firestore_doc["PuzzleID"] == 999
    assert firestore_doc["Title"] == "Test Puzzle Title"
    assert firestore_doc["CorrectAnswer"] == "Call"
    assert "Action" in firestore_doc
    assert isinstance(firestore_doc["Tags"], list)

    print("\nPuzzle conversion: PASSED")


def test_firestore_integration():
    """Test actual Firestore operations (requires credentials)."""
    print("\n" + "=" * 60)
    print("FIRESTORE INTEGRATION TEST")
    print("=" * 60)

    try:
        from storage.firestore import PuzzleStorage
        storage = PuzzleStorage()
        print("\nFirestore client initialized")
    except FileNotFoundError as e:
        print(f"\nSkipping Firestore test: {e}")
        return
    except Exception as e:
        print(f"\nSkipping Firestore test: {e}")
        return

    # Test 1: Get existing puzzles
    print("\nFetching existing puzzles...")
    try:
        puzzles = storage.get_all_puzzles()
        print(f"  Found {len(puzzles)} puzzles")
        if puzzles:
            print(f"  Latest: #{puzzles[-1].puzzle_id} - {puzzles[-1].title}")
    except Exception as e:
        print(f"  Error: {e}")
        return

    # Test 2: Get next puzzle ID
    print("\nGetting next puzzle ID...")
    try:
        next_id = storage.get_next_puzzle_id()
        print(f"  Next ID: {next_id}")
    except Exception as e:
        print(f"  Error: {e}")
        return

    # Test 3: Save a test candidate (optional)
    print("\nSaving test spot candidate...")
    spot = create_sample_spot()
    spot.id = f"test-{spot.id[:8]}"  # Use shorter ID for test

    try:
        doc_id = storage.save_candidate(spot)
        print(f"  Saved spot: {doc_id}")

        # Retrieve it back
        retrieved = storage.get_candidate(spot.id)
        if retrieved:
            print(f"  Retrieved: {retrieved.hero_combo} - {retrieved.correct_action}")

        # Update status
        storage.update_candidate_status(spot.id, "rejected")
        print(f"  Updated status to: rejected")

    except Exception as e:
        print(f"  Error: {e}")
        return

    print("\nFirestore integration: PASSED")


def main():
    print("\n" + "=" * 60)
    print("STORAGE MODULE TEST")
    print("=" * 60)

    test_serialization()
    test_puzzle_conversion()
    test_firestore_integration()

    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETE")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
