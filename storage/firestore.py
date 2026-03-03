"""Firestore storage for puzzle candidates and approved puzzles."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import requests
import google.auth
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from google.cloud import storage as gcs

from .models import spot_to_firestore, spot_from_firestore, ApprovedPuzzle, SolverSim, ScheduledPuzzle, DayPlan

if TYPE_CHECKING:
    from deepsolver.spot_extractor import SpotCandidate


def _to_firestore_value(value: Any) -> dict:
    """Convert a Python value to Firestore REST API format."""
    if isinstance(value, bool):
        return {"booleanValue": value}
    elif isinstance(value, int):
        return {"integerValue": str(value)}
    elif isinstance(value, float):
        return {"doubleValue": value}
    elif isinstance(value, str):
        return {"stringValue": value}
    elif isinstance(value, dict):
        return {
            "mapValue": {
                "fields": {k: _to_firestore_value(v) for k, v in value.items()}
            }
        }
    elif isinstance(value, list):
        return {"arrayValue": {"values": [_to_firestore_value(v) for v in value]}}
    elif value is None:
        return {"nullValue": None}
    else:
        return {"stringValue": str(value)}


def _from_firestore_value(fv: dict) -> Any:
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
        return {k: _from_firestore_value(v) for k, v in fields.items()}
    elif "arrayValue" in fv:
        values = fv["arrayValue"].get("values", [])
        return [_from_firestore_value(v) for v in values]
    elif "nullValue" in fv:
        return None
    else:
        return None


class PuzzleStorage:
    """Firestore storage for puzzles using REST API."""

    SPOT_CANDIDATES_COLLECTION = "spot_candidates"
    DAILY_PUZZLES_COLLECTION = "daily_puzzles"
    NEW_DAILY_PUZZLES_COLLECTION = "new_daily_puzzles"
    SOLVER_SIMS_COLLECTION = "solver_sims"
    DAY_PLANS_COLLECTION = "day_plans"
    GCS_BUCKET_NAME = "stack-24dea.firebasestorage.app"
    GCS_SIMS_PREFIX = "solver_sims"

    def __init__(self, credentials_path: str | None = None):
        """
        Initialize with Firebase credentials.

        In Cloud Run, uses Application Default Credentials (ADC).
        Locally, uses service account JSON file.

        Args:
            credentials_path: Path to Firebase service account JSON.
                             Defaults to backend credentials location.
                             Ignored in Cloud Run (uses ADC).
        """
        # Check if running in Cloud Run (K_SERVICE env var is set)
        if os.getenv("K_SERVICE"):
            # Use Application Default Credentials in Cloud Run
            self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "stack-24dea")
            self.credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/datastore"]
            )
            self.gcs_client = gcs.Client()
        else:
            # Local development - use service account file
            if credentials_path is None:
                credentials_path = str(
                    Path(__file__).parent.parent.parent
                    / "backend"
                    / "stack-24dea-firebase-adminsdk-fbsvc-928dfa73a0.json"
                )

            if not Path(credentials_path).exists():
                raise FileNotFoundError(f"Firebase credentials not found: {credentials_path}")

            with open(credentials_path) as f:
                creds_data = json.load(f)
                self.project_id = creds_data["project_id"]

            self.credentials = service_account.Credentials.from_service_account_file(
                credentials_path, scopes=["https://www.googleapis.com/auth/datastore"]
            )
            self.gcs_client = gcs.Client.from_service_account_json(credentials_path)

        self.base_url = (
            f"https://firestore.googleapis.com/v1/projects/{self.project_id}"
            f"/databases/(default)/documents"
        )
        self._refresh_token()

        # Initialize GCS bucket
        self.gcs_bucket = self.gcs_client.bucket(self.GCS_BUCKET_NAME)

    def _refresh_token(self):
        """Refresh access token."""
        self.credentials.refresh(Request())
        self.headers = {
            "Authorization": f"Bearer {self.credentials.token}",
            "Content-Type": "application/json",
        }

    def _ensure_token(self):
        """Refresh token if expired."""
        if self.credentials.expired:
            self._refresh_token()

    def _set_document(self, path: str, data: dict) -> bool:
        """
        Set a document at the given path.

        Args:
            path: Document path like "collection/doc"
            data: Dictionary of field values

        Returns:
            True if successful
        """
        self._ensure_token()
        url = f"{self.base_url}/{path}"

        # Convert data to Firestore format
        fields = {k: _to_firestore_value(v) for k, v in data.items()}
        payload = {"fields": fields}

        response = requests.patch(url, headers=self.headers, json=payload, timeout=30)

        if response.status_code == 200:
            return True
        else:
            raise Exception(f"Firestore error: {response.status_code} - {response.text[:200]}")

    def _get_document(self, path: str) -> dict | None:
        """
        Get a document at the given path.

        Args:
            path: Document path like "collection/doc"

        Returns:
            Document data or None if not found
        """
        self._ensure_token()
        url = f"{self.base_url}/{path}"

        response = requests.get(url, headers=self.headers, timeout=30)

        if response.status_code == 200:
            doc = response.json()
            fields = doc.get("fields", {})
            return {k: _from_firestore_value(v) for k, v in fields.items()}
        elif response.status_code == 404:
            return None
        else:
            raise Exception(f"Firestore error: {response.status_code} - {response.text[:200]}")

    def _delete_document(self, path: str) -> bool:
        """
        Delete a document at the given path.

        Args:
            path: Document path like "collection/doc"

        Returns:
            True if successful
        """
        self._ensure_token()
        url = f"{self.base_url}/{path}"

        response = requests.delete(url, headers=self.headers, timeout=30)

        if response.status_code == 200:
            return True
        elif response.status_code == 404:
            return False
        else:
            raise Exception(f"Firestore error: {response.status_code} - {response.text[:200]}")

    def _list_documents(self, collection: str, page_size: int = 100) -> list[dict]:
        """
        List all documents in a collection.

        Args:
            collection: Collection name
            page_size: Max documents per page

        Returns:
            List of document data dicts
        """
        self._ensure_token()
        url = f"{self.base_url}/{collection}?pageSize={page_size}"

        documents = []
        next_page_token = None

        while True:
            page_url = url
            if next_page_token:
                page_url += f"&pageToken={next_page_token}"

            response = requests.get(page_url, headers=self.headers, timeout=30)

            if response.status_code != 200:
                raise Exception(f"Firestore error: {response.status_code} - {response.text[:200]}")

            data = response.json()

            for doc in data.get("documents", []):
                fields = doc.get("fields", {})
                documents.append({k: _from_firestore_value(v) for k, v in fields.items()})

            next_page_token = data.get("nextPageToken")
            if not next_page_token:
                break

        return documents

    def _update_field(self, path: str, field: str, value: Any) -> bool:
        """Update a single field in a document."""
        self._ensure_token()
        url = f"{self.base_url}/{path}?updateMask.fieldPaths={field}"

        fields = {field: _to_firestore_value(value)}
        payload = {"fields": fields}

        response = requests.patch(url, headers=self.headers, json=payload, timeout=30)

        if response.status_code == 200:
            return True
        else:
            raise Exception(f"Firestore error: {response.status_code} - {response.text[:200]}")

    # =========================================================================
    # Spot Candidates
    # =========================================================================

    def save_candidate(self, spot: SpotCandidate) -> str:
        """
        Save spot to spot_candidates collection.

        Args:
            spot: SpotCandidate to save

        Returns:
            Document ID (spot.id)
        """
        doc = spot_to_firestore(spot)
        path = f"{self.SPOT_CANDIDATES_COLLECTION}/{spot.id}"
        self._set_document(path, doc)
        return spot.id

    def save_candidates_batch(self, spots: list[SpotCandidate]) -> int:
        """
        Save multiple spots to spot_candidates collection.

        Args:
            spots: List of SpotCandidates to save

        Returns:
            Number of spots saved
        """
        count = 0
        for spot in spots:
            try:
                self.save_candidate(spot)
                count += 1
            except Exception as e:
                print(f"Failed to save spot {spot.id}: {e}")
        return count

    def get_candidate(self, spot_id: str) -> SpotCandidate | None:
        """
        Get a spot candidate by ID.

        Args:
            spot_id: The spot's UUID

        Returns:
            SpotCandidate or None if not found
        """
        path = f"{self.SPOT_CANDIDATES_COLLECTION}/{spot_id}"
        doc = self._get_document(path)
        if doc:
            return spot_from_firestore(doc)
        return None

    def get_pending_candidates(self, limit: int = 50) -> list[SpotCandidate]:
        """
        Get pending candidates for review.

        Args:
            limit: Maximum number to return

        Returns:
            List of SpotCandidates with status="pending"
        """
        # Note: Firestore REST API filtering is limited.
        # For a proper implementation, we'd use the runQuery endpoint.
        # For now, we fetch all and filter client-side.
        all_docs = self._list_documents(self.SPOT_CANDIDATES_COLLECTION)

        pending = []
        for doc in all_docs:
            if doc.get("status") == "pending":
                try:
                    pending.append(spot_from_firestore(doc))
                except Exception:
                    pass
            if len(pending) >= limit:
                break

        return pending

    def update_candidate_status(self, spot_id: str, status: str):
        """
        Update candidate status.

        Args:
            spot_id: The spot's UUID
            status: New status ("pending", "approved", "rejected")
        """
        path = f"{self.SPOT_CANDIDATES_COLLECTION}/{spot_id}"
        self._update_field(path, "status", status)

    # =========================================================================
    # Approved Puzzles
    # =========================================================================

    def save_puzzle(self, puzzle: ApprovedPuzzle) -> str:
        """
        Save puzzle to daily_puzzles collection.

        Args:
            puzzle: ApprovedPuzzle to save

        Returns:
            Document ID (puzzle_id as string)
        """
        doc = puzzle.to_firestore()
        path = f"{self.DAILY_PUZZLES_COLLECTION}/{puzzle.puzzle_id}"
        self._set_document(path, doc)
        return str(puzzle.puzzle_id)

    def get_puzzle(self, puzzle_id: int) -> ApprovedPuzzle | None:
        """
        Get a puzzle by ID.

        Args:
            puzzle_id: The puzzle's ID

        Returns:
            ApprovedPuzzle or None if not found
        """
        path = f"{self.DAILY_PUZZLES_COLLECTION}/{puzzle_id}"
        doc = self._get_document(path)
        if doc:
            return ApprovedPuzzle(
                puzzle_id=doc["PuzzleID"],
                title=doc["Title"],
                question_text=doc["QuestionText"],
                structure=doc["Structure"],
                effective_stacks=doc["EffectiveStacks"],
                hero=doc["Hero"],
                action=doc["Action"],
                pot_size_at_decision=doc["PotSizeAtDecision"],
                answer_options=doc["AnswerOptions"],
                correct_answer=doc["CorrectAnswer"],
                explanation=doc["Explanation"],
                difficulty=doc["Difficulty"],
                tags=doc["Tags"],
            )
        return None

    def get_next_puzzle_id(self) -> int:
        """
        Get the next available puzzle ID.

        Returns:
            Next ID (max existing + 1, or 1 if none exist)
        """
        all_docs = self._list_documents(self.DAILY_PUZZLES_COLLECTION)

        if not all_docs:
            return 1

        max_id = max(doc.get("PuzzleID", 0) for doc in all_docs)
        return max_id + 1

    def get_all_puzzles(self) -> list[ApprovedPuzzle]:
        """
        Get all approved puzzles.

        Returns:
            List of ApprovedPuzzles
        """
        all_docs = self._list_documents(self.DAILY_PUZZLES_COLLECTION)

        puzzles = []
        for doc in all_docs:
            try:
                puzzles.append(
                    ApprovedPuzzle(
                        puzzle_id=doc["PuzzleID"],
                        title=doc["Title"],
                        question_text=doc["QuestionText"],
                        structure=doc["Structure"],
                        effective_stacks=doc["EffectiveStacks"],
                        hero=doc["Hero"],
                        action=doc["Action"],
                        pot_size_at_decision=doc["PotSizeAtDecision"],
                        answer_options=doc["AnswerOptions"],
                        correct_answer=doc["CorrectAnswer"],
                        explanation=doc["Explanation"],
                        difficulty=doc["Difficulty"],
                        tags=doc["Tags"],
                    )
                )
            except KeyError:
                pass

        return sorted(puzzles, key=lambda p: p.puzzle_id)

    # =========================================================================
    # Solver Sims
    # =========================================================================

    def _upload_tree_to_gcs(self, sim_id: str, tree: dict) -> str:
        """Upload tree JSON to GCS and return the path."""
        gcs_path = f"{self.GCS_SIMS_PREFIX}/{sim_id}.json"
        blob = self.gcs_bucket.blob(gcs_path)
        blob.upload_from_string(
            json.dumps(tree),
            content_type="application/json"
        )
        return gcs_path

    def _download_tree_from_gcs(self, gcs_path: str) -> dict:
        """Download tree JSON from GCS."""
        blob = self.gcs_bucket.blob(gcs_path)
        content = blob.download_as_string()
        return json.loads(content)

    def save_sim(self, sim: SolverSim) -> str:
        """
        Save solver sim: tree to GCS, metadata to Firestore.

        Args:
            sim: SolverSim to save (with tree attached)

        Returns:
            Document ID (sim.id)
        """
        # Upload tree to GCS
        if sim.tree is None:
            raise ValueError("SolverSim must have tree data to save")

        gcs_path = self._upload_tree_to_gcs(sim.id, sim.tree)
        sim.tree_gcs_path = gcs_path

        # Save metadata to Firestore
        doc = sim.to_firestore()
        path = f"{self.SOLVER_SIMS_COLLECTION}/{sim.id}"
        self._set_document(path, doc)
        return sim.id

    def get_sim(self, sim_id: str, load_tree: bool = True) -> SolverSim | None:
        """
        Get a solver sim by ID.

        Args:
            sim_id: The sim's UUID
            load_tree: Whether to load the tree from GCS (default True)

        Returns:
            SolverSim or None if not found
        """
        path = f"{self.SOLVER_SIMS_COLLECTION}/{sim_id}"
        doc = self._get_document(path)
        if not doc:
            return None

        sim = SolverSim.from_firestore(doc)

        # Load tree from GCS if requested
        if load_tree and sim.tree_gcs_path:
            sim.tree = self._download_tree_from_gcs(sim.tree_gcs_path)

        return sim

    def get_all_sims(self) -> list[SolverSim]:
        """
        Get all solver sims (metadata only, without trees).

        Returns:
            List of SolverSims sorted by created_at descending
        """
        all_docs = self._list_documents(self.SOLVER_SIMS_COLLECTION)

        sims = []
        for doc in all_docs:
            try:
                sims.append(SolverSim.from_firestore(doc))
            except KeyError:
                pass

        return sorted(sims, key=lambda s: s.created_at, reverse=True)

    def delete_sim(self, sim_id: str) -> bool:
        """
        Delete a solver sim by ID.

        Args:
            sim_id: The sim's UUID

        Returns:
            True if deleted, False if not found
        """
        # Also delete from GCS if exists
        try:
            blob = self.gcs_bucket.blob(f"{self.GCS_SIMS_PREFIX}/{sim_id}.json")
            if blob.exists():
                blob.delete()
        except Exception:
            pass  # GCS deletion is best-effort

        path = f"{self.SOLVER_SIMS_COLLECTION}/{sim_id}"
        return self._delete_document(path)

    # =========================================================================
    # Scheduled Puzzles (new_daily_puzzles collection)
    # =========================================================================

    def save_scheduled_puzzle(self, puzzle: ScheduledPuzzle) -> str:
        """
        Save puzzle to new_daily_puzzles collection.

        Args:
            puzzle: ScheduledPuzzle to save

        Returns:
            Document ID (puzzle.id)
        """
        doc = puzzle.to_firestore()
        path = f"{self.NEW_DAILY_PUZZLES_COLLECTION}/{puzzle.id}"
        self._set_document(path, doc)
        return puzzle.id

    def get_scheduled_puzzle(self, puzzle_id: str) -> ScheduledPuzzle | None:
        """
        Get a scheduled puzzle by ID.

        Args:
            puzzle_id: The puzzle's UUID

        Returns:
            ScheduledPuzzle or None if not found
        """
        path = f"{self.NEW_DAILY_PUZZLES_COLLECTION}/{puzzle_id}"
        doc = self._get_document(path)
        if doc:
            return ScheduledPuzzle.from_firestore(doc)
        return None

    def get_all_scheduled_puzzles(self) -> list[ScheduledPuzzle]:
        """
        Get all scheduled puzzles.

        Returns:
            List of ScheduledPuzzles sorted by scheduled_date
        """
        all_docs = self._list_documents(self.NEW_DAILY_PUZZLES_COLLECTION)

        puzzles = []
        for doc in all_docs:
            try:
                puzzles.append(ScheduledPuzzle.from_firestore(doc))
            except KeyError:
                pass

        return sorted(puzzles, key=lambda p: p.scheduled_date)

    def get_puzzles_by_date(self, scheduled_date: str) -> list[ScheduledPuzzle]:
        """
        Get puzzles scheduled for a specific date.

        Args:
            scheduled_date: Date in YYYY-MM-DD format

        Returns:
            List of ScheduledPuzzles for that date
        """
        all_puzzles = self.get_all_scheduled_puzzles()
        return [p for p in all_puzzles if p.scheduled_date == scheduled_date]

    def get_puzzle_counts_by_date(self) -> dict[str, int]:
        """
        Get count of puzzles for each scheduled date.

        Returns:
            Dict mapping date strings to puzzle counts
        """
        all_puzzles = self.get_all_scheduled_puzzles()
        counts: dict[str, int] = {}
        for puzzle in all_puzzles:
            date = puzzle.scheduled_date
            counts[date] = counts.get(date, 0) + 1
        return counts

    def update_scheduled_puzzle(self, puzzle_id: str, updates: dict) -> bool:
        """
        Update fields in a scheduled puzzle.

        Args:
            puzzle_id: The puzzle's UUID
            updates: Dictionary of field names to new values

        Returns:
            True if successful
        """
        if not updates:
            return True

        self._ensure_token()
        path = f"{self.NEW_DAILY_PUZZLES_COLLECTION}/{puzzle_id}"

        # Build updateMask with all field paths
        field_paths = "&".join(f"updateMask.fieldPaths={field}" for field in updates.keys())
        url = f"{self.base_url}/{path}?{field_paths}"

        # Convert values to Firestore format
        fields = {k: _to_firestore_value(v) for k, v in updates.items()}
        payload = {"fields": fields}

        response = requests.patch(url, headers=self.headers, json=payload, timeout=30)

        if response.status_code == 200:
            return True
        else:
            raise Exception(f"Firestore error: {response.status_code} - {response.text[:200]}")

    def delete_scheduled_puzzle(self, puzzle_id: str) -> bool:
        """
        Delete a scheduled puzzle.

        Args:
            puzzle_id: The puzzle's UUID

        Returns:
            True if successful
        """
        self._ensure_token()
        path = f"{self.NEW_DAILY_PUZZLES_COLLECTION}/{puzzle_id}"
        url = f"{self.base_url}/{path}"

        response = requests.delete(url, headers=self.headers, timeout=30)

        if response.status_code == 200:
            return True
        elif response.status_code == 404:
            return False  # Already deleted
        else:
            raise Exception(f"Firestore error: {response.status_code} - {response.text[:200]}")

    # =========================================================================
    # Day Plans
    # =========================================================================

    def save_day_plan(self, plan: DayPlan) -> str:
        """
        Save a day plan to the day_plans collection.

        Args:
            plan: DayPlan to save

        Returns:
            Document ID (plan.id)
        """
        doc = plan.to_firestore()
        path = f"{self.DAY_PLANS_COLLECTION}/{plan.id}"
        self._set_document(path, doc)
        return plan.id

    def get_day_plan(self, plan_id: str) -> DayPlan | None:
        """
        Get a day plan by ID.

        Args:
            plan_id: The plan's UUID

        Returns:
            DayPlan or None if not found
        """
        path = f"{self.DAY_PLANS_COLLECTION}/{plan_id}"
        doc = self._get_document(path)
        if doc:
            return DayPlan.from_firestore(doc)
        return None

    def get_day_plan_by_date(self, scheduled_date: str) -> DayPlan | None:
        """
        Get a day plan by scheduled date.

        Args:
            scheduled_date: Date in YYYY-MM-DD format

        Returns:
            DayPlan or None if not found
        """
        all_plans = self._list_documents(self.DAY_PLANS_COLLECTION)
        for doc in all_plans:
            if doc.get("scheduled_date") == scheduled_date:
                return DayPlan.from_firestore(doc)
        return None

    def get_all_day_plans(self) -> list[DayPlan]:
        """
        Get all day plans.

        Returns:
            List of DayPlans sorted by scheduled_date
        """
        all_docs = self._list_documents(self.DAY_PLANS_COLLECTION)

        plans = []
        for doc in all_docs:
            try:
                plans.append(DayPlan.from_firestore(doc))
            except KeyError:
                pass

        return sorted(plans, key=lambda p: p.scheduled_date)

    def update_day_plan(self, plan_id: str, updates: dict) -> bool:
        """
        Update fields in a day plan.

        Args:
            plan_id: The plan's UUID
            updates: Dictionary of field names to new values

        Returns:
            True if successful
        """
        if not updates:
            return True

        self._ensure_token()
        path = f"{self.DAY_PLANS_COLLECTION}/{plan_id}"

        # Build updateMask with all field paths
        field_paths = "&".join(f"updateMask.fieldPaths={field}" for field in updates.keys())
        url = f"{self.base_url}/{path}?{field_paths}"

        # Convert values to Firestore format
        fields = {k: _to_firestore_value(v) for k, v in updates.items()}
        payload = {"fields": fields}

        response = requests.patch(url, headers=self.headers, json=payload, timeout=30)

        if response.status_code == 200:
            return True
        else:
            raise Exception(f"Firestore error: {response.status_code} - {response.text[:200]}")

    def delete_day_plan(self, plan_id: str) -> bool:
        """
        Delete a day plan by ID.

        Args:
            plan_id: The plan's UUID

        Returns:
            True if deleted, False if not found
        """
        path = f"{self.DAY_PLANS_COLLECTION}/{plan_id}"
        return self._delete_document(path)
