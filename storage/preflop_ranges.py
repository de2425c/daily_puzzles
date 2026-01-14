"""Fetch preflop ranges from Firestore 9m100bb collection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request


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


class PreflopRangeStorage:
    """Fetch preflop ranges from Firestore 9m100bb collection."""

    COLLECTION = "9m100bb"

    # Standard RFI positions in order
    RFI_POSITIONS = ["UTG", "UTG1", "UTG2", "LJ", "HJ", "CO", "BTN", "SB"]

    def __init__(self, credentials_path: str | None = None):
        """Initialize with Firebase credentials."""
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

        self.base_url = (
            f"https://firestore.googleapis.com/v1/projects/{self.project_id}"
            f"/databases/(default)/documents"
        )
        self.credentials = service_account.Credentials.from_service_account_file(
            credentials_path, scopes=["https://www.googleapis.com/auth/datastore"]
        )
        self._refresh_token()

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

    def _get_document(self, path: str) -> dict | None:
        """Get a document at the given path."""
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

    def _list_subcollection(self, path: str) -> list[str]:
        """List document IDs in a subcollection."""
        self._ensure_token()
        url = f"{self.base_url}/{path}"

        response = requests.get(url, headers=self.headers, timeout=30)

        if response.status_code != 200:
            return []

        data = response.json()
        doc_ids = []
        for doc in data.get("documents", []):
            # Extract doc ID from full path
            doc_path = doc.get("name", "")
            doc_id = doc_path.split("/")[-1]
            doc_ids.append(doc_id)

        return doc_ids

    def get_rfi_positions(self) -> list[str]:
        """Get available RFI positions."""
        return self.RFI_POSITIONS

    def get_rfi_node(self, position: str) -> dict | None:
        """
        Get RFI data for a position.

        Returns: {action, size, range, children: [...]}
        """
        doc_name = f"{position}_RFI"
        path = f"{self.COLLECTION}/{doc_name}"
        doc = self._get_document(path)

        if not doc:
            return None

        # Get children from subcollection
        children_path = f"{self.COLLECTION}/{doc_name}/children"
        children = self._list_subcollection(children_path)

        return {
            "name": doc_name,
            "action": doc.get("action", "Raise"),
            "size": doc.get("size", 2.5),
            "range": doc.get("range", {}),
            "children": children,
        }

    def get_node_at_path(self, path: list[str]) -> dict | None:
        """
        Get node data at a path through the tree.

        Args:
            path: ["BTN_RFI", "BB_3B", "BTN_Call"]

        Returns:
            {name, action, size, range: {combo: freq, ...}, children: [...]}
        """
        if not path:
            return None

        # Build Firestore path
        # First element is the RFI document
        # Subsequent elements are in children subcollections
        if len(path) == 1:
            firestore_path = f"{self.COLLECTION}/{path[0]}"
        else:
            # Build path like: 9m100bb/BTN_RFI/children/BB_3B/children/BTN_Call
            parts = [self.COLLECTION, path[0]]
            for p in path[1:]:
                parts.extend(["children", p])
            firestore_path = "/".join(parts)

        doc = self._get_document(firestore_path)

        if not doc:
            return None

        # Get children
        children_path = f"{firestore_path}/children"
        children = self._list_subcollection(children_path)

        return {
            "name": path[-1],
            "action": doc.get("action", ""),
            "size": doc.get("size"),
            "range": doc.get("range", {}),
            "children": children,
        }

    def get_children_at_path(self, path: list[str]) -> list[dict]:
        """
        Get available child actions at a path.

        Returns list of {name, action, size} for each child.
        """
        if not path:
            return []

        # Build children path
        if len(path) == 1:
            children_path = f"{self.COLLECTION}/{path[0]}/children"
        else:
            parts = [self.COLLECTION, path[0]]
            for p in path[1:]:
                parts.extend(["children", p])
            parts.append("children")
            children_path = "/".join(parts)

        child_ids = self._list_subcollection(children_path)

        # Fetch each child's data
        children = []
        for child_id in child_ids:
            child_path = f"{children_path}/{child_id}"
            doc = self._get_document(child_path)
            if doc:
                children.append({
                    "name": child_id,
                    "action": doc.get("action", ""),
                    "size": doc.get("size"),
                })

        return children

    def get_scenario_data(self, path: list[str]) -> dict:
        """
        Get complete scenario data for a path.

        Returns: {
            nodes: [{name, action, size, range}, ...],
            ip_position: str,
            oop_position: str,
            ip_range: {combo: freq},
            oop_range: {combo: freq},
        }
        """
        nodes = []
        for i in range(len(path)):
            node = self.get_node_at_path(path[: i + 1])
            if node:
                nodes.append(node)

        if len(nodes) < 2:
            raise ValueError("Need at least opener and responder for a scenario")

        # Determine IP and OOP from the final action
        # The last node is the final action (call/4bet)
        # Need to determine who ended up IP vs OOP
        ip_pos, oop_pos, ip_range, oop_range = self._determine_positions_and_ranges(path, nodes)

        return {
            "nodes": nodes,
            "ip_position": ip_pos,
            "oop_position": oop_pos,
            "ip_range": ip_range,
            "oop_range": oop_range,
        }

    def _determine_positions_and_ranges(
        self, path: list[str], nodes: list[dict]
    ) -> tuple[str, str, dict, dict]:
        """
        Determine IP/OOP positions and their ranges from the action path.

        Position order (most OOP to most IP):
        SB < BB < UTG < UTG1 < UTG2 < LJ < HJ < CO < BTN

        Returns: (ip_position, oop_position, ip_range, oop_range)
        """
        # Position order for determining IP/OOP
        POSITION_ORDER = ["SB", "BB", "UTG", "UTG1", "UTG2", "LJ", "HJ", "CO", "BTN"]

        # Extract positions from node names
        # E.g., "BTN_RFI" -> "BTN", "BB_3B" -> "BB", "BTN_Call" -> "BTN"
        def extract_position(name: str) -> str:
            parts = name.split("_")
            return parts[0]

        # Get the two players involved
        opener_pos = extract_position(path[0])  # e.g., "BTN" from "BTN_RFI"

        # Find the other player from responses
        responder_pos = None
        for p in path[1:]:
            pos = extract_position(p)
            if pos != opener_pos:
                responder_pos = pos
                break

        if not responder_pos:
            # Default to BB if can't determine
            responder_pos = "BB"

        # Determine IP/OOP based on position order
        opener_idx = POSITION_ORDER.index(opener_pos) if opener_pos in POSITION_ORDER else 0
        responder_idx = POSITION_ORDER.index(responder_pos) if responder_pos in POSITION_ORDER else 0

        if opener_idx > responder_idx:
            ip_pos = opener_pos
            oop_pos = responder_pos
        else:
            ip_pos = responder_pos
            oop_pos = opener_pos

        # Get ranges - need to find the last action for each player
        ip_range = {}
        oop_range = {}

        for node in nodes:
            pos = extract_position(node["name"])
            if pos == ip_pos:
                ip_range = node.get("range", {})
            elif pos == oop_pos:
                oop_range = node.get("range", {})

        return ip_pos, oop_pos, ip_range, oop_range
