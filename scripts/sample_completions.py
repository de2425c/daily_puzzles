#!/usr/bin/env python3
"""
Script to sample user completions to understand the data structure.
Uses collection group query to directly query all daily_spot_completions.
Standalone - no internal imports needed.
"""

import json
from pathlib import Path
import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request


def from_firestore_value(fv: dict):
    """Convert a Firestore value to Python."""
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


def main():
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

    print("Connecting to Firebase...")
    print("Fetching completions using collection group query...")

    # Firestore REST API runQuery endpoint for collection group
    query_url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents:runQuery"

    # Query for daily_spot_completions across all users (limit to 50 samples)
    query_body = {
        "structuredQuery": {
            "from": [{"collectionId": "daily_spot_completions", "allDescendants": True}],
            "limit": 50
        }
    }

    response = requests.post(query_url, headers=headers, json=query_body, timeout=60)

    if response.status_code != 200:
        print(f"Error: {response.status_code} - {response.text[:500]}")
        return

    results = response.json()
    print(f"Found {len(results)} completion documents")

    # Analyze completions
    puzzle_counts = {}
    max_scores = {}

    for result in results:
        if "document" not in result:
            continue

        doc = result["document"]
        doc_name = doc.get("name", "")
        # Extract user_id from path: .../users/{user_id}/daily_spot_completions/{date}
        parts = doc_name.split("/")
        user_id = parts[-3] if len(parts) >= 3 else "unknown"
        comp_id = parts[-1]

        fields = doc.get("fields", {})

        scheduled_date = from_firestore_value(fields.get("scheduledDate", {}))
        puzzle_count = from_firestore_value(fields.get("puzzleCount", {}))
        total_score = from_firestore_value(fields.get("totalScore", {}))
        max_score = from_firestore_value(fields.get("maxScore", {}))
        correct_count = from_firestore_value(fields.get("correctCount", {}))
        answers = from_firestore_value(fields.get("answers", {}))
        answers_count = len(answers) if isinstance(answers, list) else 0

        # Track puzzle counts and max scores to understand variations
        puzzle_counts[puzzle_count] = puzzle_counts.get(puzzle_count, 0) + 1
        max_scores[max_score] = max_scores.get(max_score, 0) + 1

        print(f"\n{comp_id} (user: {user_id[:8]}...):")
        print(f"  scheduledDate: {scheduled_date}")
        print(f"  puzzleCount: {puzzle_count}")
        print(f"  totalScore: {total_score}")
        print(f"  maxScore: {max_score}")
        print(f"  correctCount: {correct_count}")
        print(f"  answers count: {answers_count}")
        print(f"  All fields: {list(fields.keys())}")

    print(f"\n{'='*60}")
    print("SUMMARY")
    print("="*60)
    print(f"Puzzle count distribution: {puzzle_counts}")
    print(f"Max score distribution: {max_scores}")


if __name__ == "__main__":
    main()
