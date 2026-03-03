#!/usr/bin/env python3
"""
Export all Daily10 puzzles to CSV by:
1. Extracting unique puzzle IDs from completions CSV
2. Fetching full puzzle data from new_daily_puzzles collection

Usage:
    uv run --with google-auth --with requests --with pandas python scripts/export_daily10_puzzles.py
"""

import csv
import json
from pathlib import Path
import pandas as pd
import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request


def from_firestore_value(fv: dict):
    """Convert a Firestore value to Python."""
    if not fv:
        return None
    if "booleanValue" in fv:
        return fv["booleanValue"]
    elif "integerValue" in fv:
        return int(fv["integerValue"])
    elif "doubleValue" in fv:
        return fv["doubleValue"]
    elif "stringValue" in fv:
        return fv["stringValue"]
    elif "mapValue" in fv:
        fields = fv["mapValue"].get("fields", {})
        return {k: from_firestore_value(v) for k, v in fields.items()}
    elif "arrayValue" in fv:
        values = fv["arrayValue"].get("values", [])
        return [from_firestore_value(v) for v in values]
    elif "nullValue" in fv:
        return None
    elif "timestampValue" in fv:
        return fv["timestampValue"]
    else:
        return None


def extract_puzzle_ids_from_completions():
    """Extract all unique puzzle IDs from the completions CSV."""
    csv_path = Path(__file__).parent.parent / "daily10_completions_export.csv"

    if not csv_path.exists():
        print(f"Completions CSV not found at: {csv_path}")
        print("Run export_daily10_completions.py first.")
        return set()

    df = pd.read_csv(csv_path)

    puzzle_ids = set()
    for answers_json in df['answers_json']:
        try:
            answers = json.loads(answers_json)
            for answer in answers:
                if 'puzzleId' in answer:
                    puzzle_ids.add(answer['puzzleId'])
        except (json.JSONDecodeError, TypeError):
            continue

    return puzzle_ids


def fetch_all_puzzles(headers, project_id):
    """Fetch all puzzles from new_daily_puzzles collection."""
    base_url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents"

    all_puzzles = []
    page_token = None

    while True:
        url = f"{base_url}/new_daily_puzzles?pageSize=500"
        if page_token:
            url += f"&pageToken={page_token}"

        response = requests.get(url, headers=headers, timeout=60)

        if response.status_code != 200:
            print(f"Error: {response.status_code} - {response.text[:500]}")
            break

        data = response.json()
        docs = data.get("documents", [])

        if not docs:
            break

        all_puzzles.extend(docs)
        print(f"  Fetched {len(all_puzzles)} puzzles so far...")

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return all_puzzles


def main():
    # First, extract puzzle IDs from completions
    print("Extracting puzzle IDs from completions CSV...")
    puzzle_ids_from_completions = extract_puzzle_ids_from_completions()
    print(f"Found {len(puzzle_ids_from_completions)} unique puzzle IDs in completions")

    # Load credentials
    creds_path = Path(__file__).parent.parent.parent / "backend" / "stack-24dea-firebase-adminsdk-fbsvc-928dfa73a0.json"

    if not creds_path.exists():
        print(f"Credentials not found at: {creds_path}")
        return

    with open(creds_path) as f:
        creds_data = json.load(f)
        project_id = creds_data["project_id"]

    credentials = service_account.Credentials.from_service_account_file(
        str(creds_path), scopes=["https://www.googleapis.com/auth/datastore"]
    )
    credentials.refresh(Request())

    headers = {
        "Authorization": f"Bearer {credentials.token}",
        "Content-Type": "application/json",
    }

    print("\nFetching puzzles from new_daily_puzzles collection...")
    all_docs = fetch_all_puzzles(headers, project_id)
    print(f"Total puzzles in collection: {len(all_docs)}")

    # Parse puzzles
    puzzles = []
    for doc in all_docs:
        doc_name = doc.get("name", "")
        puzzle_id = doc_name.split("/")[-1]
        fields = doc.get("fields", {})

        # Extract all fields
        scheduled_date = from_firestore_value(fields.get("scheduled_date", {}))
        hero = from_firestore_value(fields.get("Hero", {}))
        question_text = from_firestore_value(fields.get("QuestionText", {}))
        answer_options = from_firestore_value(fields.get("AnswerOptions", {})) or []
        correct_answers = from_firestore_value(fields.get("CorrectAnswers", {})) or []
        difficulty = from_firestore_value(fields.get("Difficulty", {}))
        tags = from_firestore_value(fields.get("Tags", {})) or []
        structure = from_firestore_value(fields.get("Structure", {}))
        effective_stacks = from_firestore_value(fields.get("EffectiveStacks", {}))
        pot_size = from_firestore_value(fields.get("PotSizeAtDecision", {}))
        ev_by_action = from_firestore_value(fields.get("EvByAction", {})) or {}
        action_frequencies = from_firestore_value(fields.get("ActionFrequencies", {})) or {}
        explanations = from_firestore_value(fields.get("Explanations", {})) or {}
        action_data = from_firestore_value(fields.get("Action", {})) or {}
        flavor_text = from_firestore_value(fields.get("FlavorText", {}))
        order = from_firestore_value(fields.get("Order", {}))

        # Extract hero cards and board from Action
        hero_cards = None
        board_cards = ""

        if action_data:
            # Get hero cards from preflop
            preflop = action_data.get("preflop", {})
            if hero and hero in preflop:
                hero_action = preflop.get(hero, {})
                hero_cards = hero_action.get("Cards")

            # Build board cards
            for street in ["flop", "turn", "river"]:
                street_data = action_data.get(street, {})
                if street_data:
                    # Check for Cards at street level
                    cards = street_data.get("Cards")
                    if cards:
                        board_cards += cards
                    else:
                        # Check inside position actions
                        for key, val in street_data.items():
                            if isinstance(val, dict) and "Cards" in val:
                                board_cards += val["Cards"]
                                break

        # Determine street from tags
        street = "preflop"
        for s in ["river", "turn", "flop"]:
            if s in tags:
                street = s
                break

        # Calculate best EV and action
        best_ev = max(ev_by_action.values()) if ev_by_action else 0
        best_action = max(ev_by_action, key=ev_by_action.get) if ev_by_action else ""

        # Check if this puzzle was used in completions
        in_completions = puzzle_id in puzzle_ids_from_completions

        puzzles.append({
            "puzzle_id": puzzle_id,
            "scheduled_date": scheduled_date,
            "order": order,
            "hero": hero,
            "hero_cards": hero_cards,
            "board_cards": board_cards if board_cards else None,
            "street": street,
            "question_text": question_text,
            "answer_options": "|".join(answer_options) if answer_options else "",
            "correct_answers": "|".join(correct_answers) if correct_answers else "",
            "best_action": best_action,
            "best_ev": round(best_ev, 4) if best_ev else 0,
            "difficulty": difficulty,
            "tags": "|".join(tags) if tags else "",
            "structure": structure,
            "effective_stacks": effective_stacks,
            "pot_size_at_decision": pot_size,
            "flavor_text": flavor_text,
            "in_completions": in_completions,
            "ev_by_action_json": json.dumps(ev_by_action) if ev_by_action else "{}",
            "action_frequencies_json": json.dumps(action_frequencies) if action_frequencies else "{}",
            "explanations_json": json.dumps(explanations) if explanations else "{}"
        })

    # Sort by scheduled_date and order
    puzzles.sort(key=lambda x: (x["scheduled_date"] or "", x["order"] or 0))

    # Write to CSV
    output_path = Path(__file__).parent.parent / "daily10_puzzles_export.csv"

    fieldnames = [
        "puzzle_id",
        "scheduled_date",
        "order",
        "hero",
        "hero_cards",
        "board_cards",
        "street",
        "question_text",
        "answer_options",
        "correct_answers",
        "best_action",
        "best_ev",
        "difficulty",
        "tags",
        "structure",
        "effective_stacks",
        "pot_size_at_decision",
        "flavor_text",
        "in_completions",
        "ev_by_action_json",
        "action_frequencies_json",
        "explanations_json"
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(puzzles)

    print(f"\nExported to: {output_path}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    dates = set(p["scheduled_date"] for p in puzzles if p["scheduled_date"])
    streets = {}
    positions = {}

    for p in puzzles:
        s = p["street"]
        streets[s] = streets.get(s, 0) + 1
        h = p["hero"]
        if h:
            positions[h] = positions.get(h, 0) + 1

    in_completions_count = sum(1 for p in puzzles if p["in_completions"])

    print(f"Total puzzles: {len(puzzles)}")
    print(f"Unique dates: {len(dates)}")
    print(f"Date range: {min(dates)} to {max(dates)}")
    print(f"Puzzles used in completions: {in_completions_count}")
    print(f"Puzzles NOT in completions: {len(puzzles) - in_completions_count}")
    print(f"\nStreet distribution: {dict(sorted(streets.items()))}")
    print(f"\nHero position distribution: {dict(sorted(positions.items()))}")

    # Puzzles per date
    puzzles_per_date = {}
    for p in puzzles:
        d = p["scheduled_date"]
        if d:
            puzzles_per_date[d] = puzzles_per_date.get(d, 0) + 1

    print(f"\nPuzzles per date:")
    for date in sorted(puzzles_per_date.keys()):
        print(f"  {date}: {puzzles_per_date[date]}")


if __name__ == "__main__":
    main()
