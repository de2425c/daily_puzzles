"""Calculate pot size and effective stacks from preflop action sequences."""

from __future__ import annotations


# Position order from OOP to IP (SB is most OOP, BTN is most IP)
POSITION_ORDER = ["SB", "BB", "UTG", "UTG1", "UTG2", "LJ", "HJ", "CO", "BTN"]


def calculate_pot_and_stacks(
    nodes: list[dict],
    starting_stack: float = 100.0,
) -> tuple[float, float]:
    """
    Calculate pot size and remaining effective stacks from preflop action.

    The calculation tracks how much each player has invested:
    - SB posts 0.5bb
    - BB posts 1bb
    - RFI opens to X bb
    - 3-bet raises to Y bb
    - Call matches the previous bet
    - 4-bet raises to Z bb

    Args:
        nodes: List of nodes from the preflop tree, each with:
            - name: e.g., "BTN_RFI", "BB_3B", "BTN_Call"
            - action: "Raise" or "Call"
            - size: bet size in bb (for raises)
        starting_stack: Starting stack in bb (default 100)

    Returns:
        Tuple of (pot_size_bb, effective_stack_bb)

    Example:
        BTN opens 2.5bb, BB 3-bets 13bb, BTN calls
        - BTN invested: 2.5 + (13 - 2.5) = 13bb
        - BB invested: 1 + 12 = 13bb
        - Pot: 13 + 13 = 26bb
        - Remaining: 100 - 13 = 87bb
    """
    if not nodes:
        return 0.0, starting_stack

    # Extract positions involved
    positions_involved = set()
    for node in nodes:
        pos = _extract_position(node["name"])
        positions_involved.add(pos)

    # Track investments by position
    investments: dict[str, float] = {}

    # Initialize with blinds
    if "SB" in positions_involved:
        investments["SB"] = 0.5
    if "BB" in positions_involved:
        investments["BB"] = 1.0

    # Current bet to call (starts at 1bb for BB)
    current_bet = 1.0

    for node in nodes:
        pos = _extract_position(node["name"])
        action = node.get("action", "")
        size = node.get("size")

        if action == "Raise":
            # Raise to size bb (total, not additional)
            if size is not None:
                investments[pos] = float(size)
                current_bet = float(size)
        elif action == "Call":
            # Call matches the current bet
            investments[pos] = current_bet

    # Calculate pot (sum of all investments)
    pot = sum(investments.values())

    # Calculate effective stack (smallest remaining stack)
    remaining_stacks = [
        starting_stack - inv for inv in investments.values()
    ]
    effective_stack = min(remaining_stacks) if remaining_stacks else starting_stack

    return pot, effective_stack


def determine_ip_oop_positions(nodes: list[dict]) -> tuple[str, str]:
    """
    Determine which position is IP and which is OOP.

    Position order (most OOP to most IP):
    SB < BB < UTG < UTG1 < UTG2 < LJ < HJ < CO < BTN

    In a 2-player scenario, the player with higher position index is IP.

    Args:
        nodes: List of nodes from preflop tree

    Returns:
        Tuple of (ip_position, oop_position)
    """
    if not nodes:
        return "BTN", "BB"  # Default

    # Extract unique positions from node names
    positions = set()
    for node in nodes:
        pos = _extract_position(node["name"])
        positions.add(pos)

    if len(positions) < 2:
        # Can't determine with less than 2 positions
        return "BTN", "BB"

    # Sort positions by their order
    sorted_positions = sorted(
        positions,
        key=lambda p: POSITION_ORDER.index(p) if p in POSITION_ORDER else -1,
    )

    # IP is the position with higher index (more to the right)
    oop_pos = sorted_positions[0]
    ip_pos = sorted_positions[-1]

    return ip_pos, oop_pos


def _extract_position(name: str) -> str:
    """
    Extract position from a node name.

    Examples:
        "BTN_RFI" -> "BTN"
        "BB_3B" -> "BB"
        "BTN_Call" -> "BTN"
        "UTG1_RFI" -> "UTG1"
    """
    parts = name.split("_")
    return parts[0] if parts else ""


def build_preflop_description(nodes: list[dict]) -> str:
    """
    Build a human-readable description of the preflop action.

    Args:
        nodes: List of nodes from preflop tree

    Returns:
        Description like "BTN opens 2.5bb, BB 3-bets 13bb, BTN calls"
    """
    if not nodes:
        return ""

    descriptions = []

    for node in nodes:
        pos = _extract_position(node["name"])
        action = node.get("action", "")
        size = node.get("size")
        name = node.get("name", "")

        if "RFI" in name:
            if size:
                descriptions.append(f"{pos} opens {size}bb")
            else:
                descriptions.append(f"{pos} opens")
        elif action == "Raise":
            # Determine if it's a 3-bet, 4-bet, etc.
            bet_type = "raises"
            if "_3B" in name:
                bet_type = "3-bets"
            elif "_4B" in name:
                bet_type = "4-bets"
            elif "_5B" in name:
                bet_type = "5-bets"

            if size:
                descriptions.append(f"{pos} {bet_type} to {size}bb")
            else:
                descriptions.append(f"{pos} {bet_type}")
        elif action == "Call":
            descriptions.append(f"{pos} calls")

    return ", ".join(descriptions)


def get_scenario_summary(
    nodes: list[dict],
    ip_range: dict,
    oop_range: dict,
    starting_stack: float = 100.0,
) -> dict:
    """
    Get a complete summary of a preflop scenario.

    Args:
        nodes: List of nodes from preflop tree
        ip_range: IP player's range as {combo: freq} dict
        oop_range: OOP player's range as {combo: freq} dict
        starting_stack: Starting stack in bb

    Returns:
        Dictionary with:
            - ip_position: str
            - oop_position: str
            - pot_size_bb: float
            - effective_stack_bb: float
            - ip_combos: int (count of combos with freq > 0)
            - oop_combos: int
            - preflop_description: str
    """
    ip_pos, oop_pos = determine_ip_oop_positions(nodes)
    pot, stacks = calculate_pot_and_stacks(nodes, starting_stack)
    description = build_preflop_description(nodes)

    # Count combos (any frequency > 0)
    ip_combos = sum(1 for freq in ip_range.values() if freq > 0)
    oop_combos = sum(1 for freq in oop_range.values() if freq > 0)

    return {
        "ip_position": ip_pos,
        "oop_position": oop_pos,
        "pot_size_bb": pot,
        "effective_stack_bb": stacks,
        "ip_combos": ip_combos,
        "oop_combos": oop_combos,
        "preflop_description": description,
    }
