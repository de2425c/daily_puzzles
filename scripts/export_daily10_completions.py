#!/usr/bin/env python3
"""
Export all Daily10 completions to CSV.

Daily10 completions are identified by having a `scheduledDate` field.
Legacy daily spot completions (with puzzleId only) are excluded.

Usage:
    uv run --with google-auth --with requests python scripts/export_daily10_completions.py
"""

import csv
import json
from pathlib import Path
from datetime import datetime
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


def fetch_all_completions(headers, project_id):
    """Fetch all daily_spot_completions using paginated collection group query."""
    query_url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents:runQuery"

    all_completions = []
    page_size = 500
    start_at = None

    while True:
        query_body = {
            "structuredQuery": {
                "from": [{"collectionId": "daily_spot_completions", "allDescendants": True}],
                "orderBy": [{"field": {"fieldPath": "__name__"}, "direction": "ASCENDING"}],
                "limit": page_size
            }
        }

        if start_at:
            query_body["structuredQuery"]["startAt"] = {
                "values": [{"referenceValue": start_at}],
                "before": False
            }

        response = requests.post(query_url, headers=headers, json=query_body, timeout=120)

        if response.status_code != 200:
            print(f"Error: {response.status_code} - {response.text[:500]}")
            break

        results = response.json()

        # Filter out empty results
        docs = [r for r in results if "document" in r]

        if not docs:
            break

        all_completions.extend(docs)
        print(f"  Fetched {len(all_completions)} documents so far...")

        # Get last document name for pagination
        if len(docs) < page_size:
            break

        last_doc = docs[-1]["document"]["name"]
        start_at = last_doc

    return all_completions


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
    print("Fetching all completions (this may take a while)...")

    all_results = fetch_all_completions(headers, project_id)
    print(f"\nTotal documents fetched: {len(all_results)}")

    # Filter for Daily10 completions (those with scheduledDate)
    daily10_completions = []
    legacy_count = 0

    for result in all_results:
        if "document" not in result:
            continue

        doc = result["document"]
        fields = doc.get("fields", {})

        # Check if this is a Daily10 completion (has scheduledDate)
        if "scheduledDate" not in fields:
            legacy_count += 1
            continue

        doc_name = doc.get("name", "")
        # Extract user_id from path: .../users/{user_id}/daily_spot_completions/{date}
        parts = doc_name.split("/")
        user_id = parts[-3] if len(parts) >= 3 else "unknown"

        scheduled_date = from_firestore_value(fields.get("scheduledDate", {}))
        puzzle_count = from_firestore_value(fields.get("puzzleCount", {}))
        total_score = from_firestore_value(fields.get("totalScore", {}))
        max_score = from_firestore_value(fields.get("maxScore", {}))
        correct_count = from_firestore_value(fields.get("correctCount", {}))
        completed_at = from_firestore_value(fields.get("completedAt", {}))
        answers = from_firestore_value(fields.get("answers", {})) or []
        unlocked_indices = from_firestore_value(fields.get("unlockedPuzzleIndices", {})) or []

        # Calculate derived metrics
        score_percentage = (total_score / max_score * 100) if max_score and max_score > 0 else 0
        accuracy = (correct_count / puzzle_count * 100) if puzzle_count and puzzle_count > 0 else 0

        # Extract individual puzzle data
        puzzle_scores = [a.get("score", 0) for a in answers] if answers else []
        puzzle_evlosses = [a.get("evLoss", 0) for a in answers] if answers else []
        puzzle_correct = [a.get("isCorrect", False) for a in answers] if answers else []

        daily10_completions.append({
            "user_id": user_id,
            "scheduled_date": scheduled_date,
            "completed_at": completed_at,
            "puzzle_count": puzzle_count,
            "correct_count": correct_count,
            "total_score": round(total_score, 2) if total_score else 0,
            "max_score": max_score,
            "score_percentage": round(score_percentage, 2),
            "accuracy_percentage": round(accuracy, 2),
            "unlocked_insights": len(unlocked_indices),
            "avg_ev_loss": round(sum(puzzle_evlosses) / len(puzzle_evlosses), 4) if puzzle_evlosses else 0,
            "answers_json": json.dumps(answers) if answers else "[]"
        })

    print(f"\nDaily10 completions: {len(daily10_completions)}")
    print(f"Legacy completions (excluded): {legacy_count}")

    # Write to CSV
    output_path = Path(__file__).parent.parent / "daily10_completions_export.csv"

    # Sort by scheduled_date, then user_id
    daily10_completions.sort(key=lambda x: (x["scheduled_date"] or "", x["user_id"]))

    fieldnames = [
        "user_id",
        "scheduled_date",
        "completed_at",
        "puzzle_count",
        "correct_count",
        "total_score",
        "max_score",
        "score_percentage",
        "accuracy_percentage",
        "unlocked_insights",
        "avg_ev_loss",
        "answers_json"
    ]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(daily10_completions)

    print(f"\nExported to: {output_path}")

    # Print summary statistics
    print("\n" + "=" * 60)
    print("SUMMARY STATISTICS")
    print("=" * 60)

    if daily10_completions:
        dates = set(c["scheduled_date"] for c in daily10_completions if c["scheduled_date"])
        users = set(c["user_id"] for c in daily10_completions)
        avg_score = sum(c["score_percentage"] for c in daily10_completions) / len(daily10_completions)
        avg_accuracy = sum(c["accuracy_percentage"] for c in daily10_completions) / len(daily10_completions)

        print(f"Total completions: {len(daily10_completions)}")
        print(f"Unique users: {len(users)}")
        print(f"Unique dates: {len(dates)}")
        print(f"Date range: {min(dates)} to {max(dates)}")
        print(f"Average score: {avg_score:.1f}%")
        print(f"Average accuracy: {avg_accuracy:.1f}%")

        # Puzzle count distribution
        puzzle_counts = {}
        for c in daily10_completions:
            pc = c["puzzle_count"]
            puzzle_counts[pc] = puzzle_counts.get(pc, 0) + 1
        print(f"Puzzle count distribution: {dict(sorted(puzzle_counts.items()))}")


if __name__ == "__main__":
    main()
