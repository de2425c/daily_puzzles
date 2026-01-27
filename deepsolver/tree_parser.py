"""Parser for Deepsolver solver tree responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .ranges import count_combos

# Units: 1,000,000 = 1 big blind
UNITS_PER_BB = 1_000_000


@dataclass
class TreeNode:
    """Structured representation of a solver tree node."""

    path: str  # _pio_path
    player_id: int | None  # 0=IP, 1=OOP, None=terminal
    street_id: int  # 1=flop, 2=turn, 3=river
    pot_size: int  # In units (1M = 1bb)
    actions: list[tuple[str, int]] | None  # [("C", 0), ("B", 1485000)]
    strategy: list[list[float]] | None  # shape (num_actions, 1326)
    ev: list[list[float]] | None  # shape (2 players, 1326)
    ranges: list[list[int]] | None  # shape (2 players, 1326)
    bets: list[int] | None  # [IP_bet, OOP_bet] in units - tracks money committed
    children: list[TreeNode] = field(default_factory=list)

    def is_terminal(self) -> bool:
        """Check if this is a terminal node (no player to act)."""
        return self.player_id is None


def parse_tree(raw: dict) -> TreeNode:
    """
    Convert raw JSON tree to TreeNode structure (recursive).

    Args:
        raw: Raw tree dict from API response

    Returns:
        Parsed TreeNode with children
    """
    # Parse actions from [["C", 0], ["B", 1485000]] format
    raw_actions = raw.get("actions", [])
    actions = [(a[0], a[1]) for a in raw_actions] if raw_actions else None

    # Parse data section
    data = raw.get("data", {})
    strategy = data.get("strategy") if data else None
    ev = data.get("EV") if data else None
    ranges = data.get("ranges") if data else None

    # Parse bets array (tracks money committed by each player)
    bets = raw.get("bets")

    # Create node
    node = TreeNode(
        path=raw.get("_pio_path", ""),
        player_id=raw.get("player_id"),
        street_id=raw.get("street_id", 1),
        pot_size=raw.get("pot_size", 0),
        actions=actions,
        strategy=strategy,
        ev=ev,
        ranges=ranges,
        bets=bets,
    )

    # Recursively parse children
    for child_raw in raw.get("children", []):
        node.children.append(parse_tree(child_raw))

    return node


def get_node_by_path(root: TreeNode, path: str) -> TreeNode | None:
    """
    Navigate to a node by its _pio_path string.

    Args:
        root: Root node of the tree
        path: Path string like "r:0:c:b1485000"

    Returns:
        Node at the path, or None if not found
    """
    if root.path == path:
        return root

    for child in root.children:
        result = get_node_by_path(child, path)
        if result is not None:
            return result

    return None


def find_decision_nodes(
    root: TreeNode, player_id: int | None = None
) -> list[TreeNode]:
    """
    Find all non-terminal nodes, optionally filtered by player.

    Args:
        root: Root node of the tree
        player_id: Optional filter for specific player (0=IP, 1=OOP)

    Returns:
        List of decision nodes
    """
    nodes = []

    def _collect(node: TreeNode):
        if not node.is_terminal():
            if player_id is None or node.player_id == player_id:
                nodes.append(node)
        for child in node.children:
            _collect(child)

    _collect(root)
    return nodes


def format_action(action: tuple[str, int], pot_size: int) -> str:
    """
    Convert action tuple to human-readable string with bb amounts.

    Args:
        action: Tuple of (action_code, amount)
        pot_size: Current pot size in units

    Returns:
        Human-readable string like "Bet 2.5bb"

    Examples:
        ("C", 0) -> "Check"
        ("C", 1000000) -> "Call"
        ("B", 1650000) -> "Bet 1.7bb"
        ("F", 0) -> "Fold"
        ("A", 98000000) -> "All-in"
    """
    code, amount = action

    if code == "C":
        return "Check" if amount == 0 else "Call"
    elif code == "F":
        return "Fold"
    elif code == "A":
        return "All-in"
    elif code == "B":
        # Convert to bb and display actual amount
        bb_amount = amount / UNITS_PER_BB
        if bb_amount >= 50:
            return "All-in"
        return f"Bet {bb_amount:.1f}bb"
    else:
        return f"{code} {amount}"


def get_strategy_for_combo(
    node: TreeNode, combo_idx: int
) -> dict[str, float]:
    """
    Return action frequencies for a specific combo at this node.

    Args:
        node: Tree node with strategy data
        combo_idx: Index into the 1326 combo array

    Returns:
        Dict mapping action name to frequency
        Example: {"Check": 0.15, "Bet 33%": 0.85}
    """
    if node.strategy is None or node.actions is None:
        return {}

    result = {}
    for i, action in enumerate(node.actions):
        action_name = format_action(action, node.pot_size)
        freq = node.strategy[i][combo_idx]
        result[action_name] = freq

    return result


def get_ev_for_combo(node: TreeNode, player_id: int, combo_idx: int) -> float:
    """
    Return EV in big blinds for a specific combo at this node.

    Args:
        node: Tree node with EV data
        player_id: 0 for IP, 1 for OOP
        combo_idx: Index into the 1326 combo array

    Returns:
        EV in big blinds
    """
    if node.ev is None:
        return 0.0

    return node.ev[player_id][combo_idx] / UNITS_PER_BB


def get_ev_by_action(
    node: TreeNode, player_id: int, combo_idx: int
) -> dict[str, float]:
    """
    Return EV for each action at this node.

    The raw EV at child nodes includes the bet amount as part of the value.
    We subtract the bet to get the true action EV (net expected value).

    In GTO equilibrium, all actions with positive frequency should have
    approximately equal EV after this correction.

    Args:
        node: Tree node with children
        player_id: 0 for IP, 1 for OOP
        combo_idx: Index into the 1326 combo array

    Returns:
        Dict mapping action name to EV in big blinds
    """
    if node.actions is None:
        return {}

    result = {}
    for i, action in enumerate(node.actions):
        action_name = format_action(action, node.pot_size)

        # Get EV from child node
        if i < len(node.children):
            child = node.children[i]
            if child.ev is not None:
                raw_ev = child.ev[player_id][combo_idx] / UNITS_PER_BB

                # Subtract the bet amount to get true action EV
                # The child's bets array tracks money committed at that node
                bet_amount = 0.0
                if child.bets is not None:
                    bet_amount = child.bets[player_id] / UNITS_PER_BB

                ev = raw_ev - bet_amount
            else:
                ev = 0.0
        else:
            ev = 0.0

        result[action_name] = ev

    return result


def count_nodes(root: TreeNode) -> int:
    """Count total nodes in tree."""
    count = 1
    for child in root.children:
        count += count_nodes(child)
    return count


def get_actions_at_node(root: TreeNode, path: str) -> dict:
    """
    Get available actions at a tree node formatted for GUI display.

    Args:
        root: Root node of the tree
        path: Path string like "r:0:c:b1485000"

    Returns:
        Dict with path, player_id, is_terminal, and list of actions.
        Each action has label (human-readable) and path (child path).

    Example:
        {
            "path": "r:0",
            "player_id": 1,
            "is_terminal": False,
            "actions": [
                {"label": "Check", "path": "r:0:c"},
                {"label": "Bet 33%", "path": "r:0:b1500000"},
            ]
        }
    """
    node = get_node_by_path(root, path)
    if not node:
        return {"error": "Node not found", "path": path}

    if node.is_terminal():
        return {"path": path, "player_id": None, "is_terminal": True, "actions": []}

    if node.actions is None:
        return {"path": path, "player_id": node.player_id, "is_terminal": False, "actions": []}

    actions = []
    for i, (code, amount) in enumerate(node.actions):
        # Build the child path
        if code == "C":
            child_path = f"{path}:c"
        elif code == "F":
            child_path = f"{path}:f"
        elif code == "A":
            child_path = f"{path}:a"
        elif code == "B":
            child_path = f"{path}:b{amount}"
        else:
            child_path = f"{path}:{code.lower()}{amount}"

        actions.append({
            "label": format_action((code, amount), node.pot_size),
            "path": child_path,
        })

    return {
        "path": path,
        "player_id": node.player_id,
        "is_terminal": False,
        "actions": actions,
    }


def get_ranges_at_node(root: TreeNode, path: str) -> dict:
    """
    Extract ranges at a specific tree node.

    Args:
        root: Root node of the tree
        path: Path string like "r:0:c:b1485000:c"

    Returns:
        Dict with path, terminal status, combo counts, full ranges, and strategy.

    Example:
        {
            "path": "r:0:c:b1500000:c",
            "is_terminal": True,
            "ip_combos": 142,
            "oop_combos": 89,
            "ip_range": [...],  # 1326 weights
            "oop_range": [...],  # 1326 weights
            "strategy": [[...], [...]],  # num_actions x 1326
            "action_names": ["Check", "Bet 1.6bb"]
        }
    """
    node = get_node_by_path(root, path)
    if not node:
        return {"error": "Node not found", "path": path}

    if node.ranges is None:
        return {"error": "No ranges at node", "path": path}

    ip_range = node.ranges[0]
    oop_range = node.ranges[1]

    # Calculate actual pot size: starting pot + bets from both players
    actual_pot = node.pot_size
    if node.bets:
        actual_pot += sum(node.bets)

    result = {
        "path": path,
        "is_terminal": node.is_terminal(),
        "pot_size": actual_pot,
        "ip_combos": count_combos(ip_range),
        "oop_combos": count_combos(oop_range),
        "ip_range": ip_range,
        "oop_range": oop_range,
    }

    # Add strategy data if this is a decision node
    if not node.is_terminal() and node.strategy is not None and node.actions is not None:
        result["strategy"] = node.strategy
        result["action_names"] = [format_action(a, node.pot_size) for a in node.actions]

    return result
