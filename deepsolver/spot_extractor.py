"""Extract puzzle-worthy spots from solver trees."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from .tree_parser import (
    TreeNode,
    format_action,
    get_strategy_for_combo,
    get_ev_by_action,
    find_decision_nodes,
    UNITS_PER_BB,
)
from .hand_utils import HAND_ORDER, is_combo_blocked, RANK_ORDER


@dataclass
class SpotCandidate:
    """A potential puzzle spot extracted from solver output."""

    # Identification
    id: str
    source_task_id: str

    # Game state
    board: str
    hero_combo: str
    hero_position: str
    villain_position: str
    street: str
    pot_size_bb: float
    stack_size_bb: float
    action_sequence: str
    tree_path: str

    # Decision info
    available_actions: list[str]
    action_frequencies: dict[str, float]
    correct_action: str
    correct_frequency: float
    ev_by_action: dict[str, float]

    # Metadata
    hand_category: str
    board_texture: str
    created_at: datetime = field(default_factory=datetime.now)

    # Street-by-street action history
    street_actions: list[dict] = field(default_factory=list)


def categorize_hand(combo: str, board: str) -> str:
    """
    Classify hand strength relative to board.

    Args:
        combo: Hand like "AhKd"
        board: Board like "7hTh3d"

    Returns:
        Category string: overpair, top_pair, flush_draw, etc.
    """
    # Parse board cards
    board_ranks = [board[i] for i in range(0, len(board), 2)]
    board_suits = [board[i + 1] for i in range(0, len(board), 2)]

    # Parse combo
    combo_ranks = [combo[0], combo[2]]
    combo_suits = [combo[1], combo[3]]

    # Get rank values for comparison
    def rank_value(r: str) -> int:
        return RANK_ORDER.get(r, 0)

    board_rank_values = [rank_value(r) for r in board_ranks]
    combo_rank_values = [rank_value(r) for r in combo_ranks]
    max_board_rank = max(board_rank_values)

    # Check for pocket pair
    if combo_ranks[0] == combo_ranks[1]:
        pair_value = combo_rank_values[0]
        if combo_ranks[0] in board_ranks:
            return "set"
        elif pair_value > max_board_rank:
            return "overpair"
        elif pair_value == max_board_rank:
            return "top_pair"  # Unlikely but handle it
        else:
            return "underpair"

    # Check for made hands (pair with board)
    for i, board_rank in enumerate(board_ranks):
        if board_rank in combo_ranks:
            board_rank_value = board_rank_values[i]
            if board_rank_value == max_board_rank:
                return "top_pair"
            elif board_rank_value == sorted(board_rank_values)[-2]:
                return "second_pair"
            else:
                return "bottom_pair"

    # Check for flush draws (4+ cards of same suit on flop)
    for suit in set(combo_suits):
        suit_count = combo_suits.count(suit) + board_suits.count(suit)
        if suit_count >= 4:
            return "flush_draw"

    # Check for straight draws (simplified)
    all_ranks = combo_rank_values + board_rank_values
    sorted_ranks = sorted(set(all_ranks))
    # Check for OESD (4 consecutive or close)
    for i in range(len(sorted_ranks) - 3):
        window = sorted_ranks[i : i + 4]
        if window[-1] - window[0] <= 4:
            gaps = sum(1 for j in range(3) if window[j + 1] - window[j] > 1)
            if gaps == 0:
                return "oesd"
            elif gaps == 1:
                return "gutshot"

    # Check for overcards
    if all(cv > max_board_rank for cv in combo_rank_values):
        return "overcards"

    # Default
    return "high_card"


def categorize_board(board: str) -> str:
    """
    Classify board texture.

    Args:
        board: Board like "7hTh3d"

    Returns:
        Texture string: dry, wet, monotone, paired
    """
    suits = [board[i + 1] for i in range(0, len(board), 2)]
    ranks = [board[i] for i in range(0, len(board), 2)]
    rank_values = [RANK_ORDER.get(r, 0) for r in ranks]

    # Monotone (3 of same suit)
    if len(set(suits)) == 1:
        return "monotone"

    # Paired
    if len(set(ranks)) < len(ranks):
        return "paired"

    # Check for wet vs dry
    sorted_ranks = sorted(rank_values)
    gaps = [sorted_ranks[i + 1] - sorted_ranks[i] for i in range(len(sorted_ranks) - 1)]
    is_connected = all(g <= 2 for g in gaps)
    has_two_tone = len(set(suits)) == 2

    if is_connected or has_two_tone:
        return "wet"

    return "dry"


def _street_name(street_id: int) -> str:
    """Convert street_id to name."""
    return {1: "flop", 2: "turn", 3: "river"}.get(street_id, "unknown")


def _is_donk_bet_spot(node: TreeNode, starting_street_id: int) -> bool:
    """
    Check if this is a donk bet spot (OOP betting after calling on previous street).

    A donk bet is when the out-of-position player bets into the in-position player
    who had the betting initiative on the previous street.

    Args:
        node: The decision node to check
        starting_street_id: The street where the tree starts (1=flop, 2=turn, 3=river)

    Returns:
        True if this is a donk bet spot that should be skipped
    """
    # Only applies to OOP player (player_id == 1)
    if node.player_id != 1:
        return False

    # Parse the path to understand action history
    path_parts = node.path.split(":")
    if len(path_parts) <= 2:
        # Root node, OOP first to act
        # If tree starts on flop, OOP betting is a donk bet (called preflop)
        # For turn/river trees, we can't tell without parent context
        return starting_street_id == 1  # Donk bet on flop after preflop call

    actions = path_parts[2:]  # Skip "r" and "0"

    # Track what happened on each street
    current_street = starting_street_id
    street_actions = {1: [], 2: [], 3: []}  # flop, turn, river
    current_player = 1  # OOP acts first

    for action in actions:
        street_actions[current_street].append((current_player, action))

        # Check for street transition (both players acted without open bet, or call closed the action)
        # Street transitions happen when:
        # 1. check-check sequence
        # 2. bet-call sequence
        actions_on_street = street_actions[current_street]
        if len(actions_on_street) >= 2:
            last_two = actions_on_street[-2:]
            # Check-check: both checks
            if last_two[0][1] == "c" and last_two[1][1] == "c":
                # Check if there was a bet before these checks
                has_bet = any(a.startswith("b") for _, a in actions_on_street[:-2])
                if not has_bet:
                    # Pure check-check, move to next street
                    current_street = min(current_street + 1, 3)
                    current_player = 1  # OOP acts first on new street
                    continue
            # Bet-call: bet followed by call
            if last_two[0][1].startswith("b") and last_two[1][1] == "c":
                current_street = min(current_street + 1, 3)
                current_player = 1  # OOP acts first on new street
                continue

        # Alternate players
        current_player = 1 - current_player

    # Now check if we're in a donk bet situation:
    # - We're on a new street (OOP first to act)
    # - OOP's last action on previous street was a call

    decision_street = node.street_id
    previous_street = decision_street - 1

    # If we're on the first street of the tree, check if tree starts after preflop call
    if decision_street == starting_street_id:
        # OOP is first to act at tree root - this is a donk spot if starting on flop
        # (because OOP called preflop in SRP setup)
        return starting_street_id == 1

    # Check OOP's last action on previous street
    if previous_street < 1 or previous_street not in street_actions:
        # Previous street was preflop (not in tree), OOP called
        return True

    prev_street_actions = street_actions.get(previous_street, [])
    if not prev_street_actions:
        # No actions on previous street in tree means preflop call
        return True

    # Find OOP's last action on previous street
    oop_actions = [a for p, a in prev_street_actions if p == 1]
    if oop_actions:
        last_oop_action = oop_actions[-1]
        # If OOP called on previous street, this is a donk bet spot
        if last_oop_action == "c":
            # Need to check if it was a call (facing bet) or check
            # Look for a bet before this call
            idx = None
            for i, (p, a) in enumerate(prev_street_actions):
                if p == 1 and a == "c" and i == len([x for x in prev_street_actions if x[0] == 1]) - 1:
                    idx = i
                    break
            if idx is not None and idx > 0:
                # Check if there was a bet before OOP's call
                for p, a in prev_street_actions[:idx]:
                    if a.startswith("b"):
                        return True  # OOP called a bet, this is donk territory

    return False


def _format_board_cards(board: str) -> str:
    """Format board cards with dashes: Ah7d2c -> Ah-7d-2c"""
    cards = [board[i:i+2] for i in range(0, len(board), 2)]
    return "-".join(cards)


def _get_board_for_street(board: str, street: str) -> str:
    """Get the board cards revealed on a specific street."""
    if street == "flop":
        return _format_board_cards(board[:6]) if len(board) >= 6 else board
    elif street == "turn":
        return board[6:8] if len(board) >= 8 else ""
    elif street == "river":
        return board[8:10] if len(board) >= 10 else ""
    return ""


def _build_action_sequence(
    path: str, pot_size: int, ip_position: str, oop_position: str
) -> str:
    """
    Convert a path to structured action sequence with BB amounts.

    Args:
        path: Path like "r:0:c:b1485000"
        pot_size: Initial pot size in units (1M = 1bb)
        ip_position: IP player position name
        oop_position: OOP player position name

    Returns:
        String like "BB checks → UTG bets 3.3bb → BB raises 11bb → UTG to act"
    """
    # Parse path segments after "r:0"
    parts = path.split(":")
    if len(parts) <= 2:
        return f"{oop_position} to act"

    actions_taken = parts[2:]  # Skip "r" and "0"
    descriptions = []
    current_player = 1  # OOP acts first on flop

    last_action_was_bet = False

    for action_str in actions_taken:
        player_name = oop_position if current_player == 1 else ip_position

        if action_str == "c":
            if last_action_was_bet:
                descriptions.append(f"{player_name} calls")
            else:
                descriptions.append(f"{player_name} checks")
            last_action_was_bet = False
        elif action_str.startswith("b"):
            try:
                amount = int(action_str[1:])
                amount_bb = amount / UNITS_PER_BB

                if last_action_was_bet:
                    descriptions.append(f"{player_name} raises {amount_bb:.1f}bb")
                else:
                    descriptions.append(f"{player_name} bets {amount_bb:.1f}bb")
                last_action_was_bet = True
            except ValueError:
                descriptions.append(f"{player_name} bets")
                last_action_was_bet = True
        elif action_str == "f":
            descriptions.append(f"{player_name} folds")
            last_action_was_bet = False

        # Alternate players
        current_player = 1 - current_player

    # Who is to act now?
    current_player_name = oop_position if current_player == 1 else ip_position

    if descriptions:
        return " → ".join(descriptions) + f" → {current_player_name} to act"
    else:
        return f"{current_player_name} to act"


def _build_street_actions(
    tree: TreeNode,
    target_path: str,
    board: str,
    ip_position: str,
    oop_position: str,
) -> list[dict]:
    """
    Build a street-by-street breakdown of actions from root to target node.

    Args:
        tree: Root of the tree
        target_path: Path to the target node
        board: Full board string
        ip_position: IP player name
        oop_position: OOP player name

    Returns:
        List of street action dicts like:
        [
            {"street": "preflop", "cards": "", "actions": "UTG raises 2.5bb, BB calls"},
            {"street": "flop", "cards": "Ah-7d-2c", "actions": "BB checks, UTG checks"},
            {"street": "turn", "cards": "8d", "actions": "BB checks, UTG checks"},
            {"street": "river", "cards": "Kd", "actions": "BB bets 3.3bb, UTG to act"},
        ]
    """
    result = []
    street_names = {1: "flop", 2: "turn", 3: "river"}

    # Always include preflop context
    result.append({
        "street": "preflop",
        "cards": "",
        "actions": f"{ip_position} raises 2.5bb, {oop_position} calls",
    })

    # Parse path to get actions
    parts = target_path.split(":")

    # Determine starting street from tree
    starting_street = tree.street_id

    if len(parts) <= 2:
        # No actions yet - hero is first to act on starting street
        result.append({
            "street": street_names.get(starting_street, "flop"),
            "cards": _get_board_for_street(board, street_names.get(starting_street, "flop")),
            "actions": f"{oop_position} to act",
        })
        return result

    actions_taken = parts[2:]  # Skip "r" and "0"

    # Walk the tree to track street transitions
    current_node = tree
    current_street = tree.street_id  # Start on the tree's actual starting street
    street_actions = {1: [], 2: [], 3: []}
    current_player = 1  # OOP acts first
    last_action_was_bet = {1: False, 2: False, 3: False}  # Track per street

    for action_str in actions_taken:
        player_name = oop_position if current_player == 1 else ip_position

        # Record the action FIRST (before checking street transition)
        if action_str == "c":
            if last_action_was_bet[current_street]:
                street_actions[current_street].append(f"{player_name} calls")
            else:
                street_actions[current_street].append(f"{player_name} checks")
            last_action_was_bet[current_street] = False
        elif action_str.startswith("b"):
            try:
                amount = int(action_str[1:])
                amount_bb = amount / UNITS_PER_BB
                if last_action_was_bet[current_street]:
                    street_actions[current_street].append(f"{player_name} raises to {amount_bb:.1f}bb")
                else:
                    street_actions[current_street].append(f"{player_name} bets {amount_bb:.1f}bb")
                last_action_was_bet[current_street] = True
            except ValueError:
                street_actions[current_street].append(f"{player_name} bets")
                last_action_was_bet[current_street] = True
        elif action_str == "f":
            street_actions[current_street].append(f"{player_name} folds")
            last_action_was_bet[current_street] = False

        # Alternate players
        current_player = 1 - current_player

        # Find the child node that matches this action
        child_found = None
        for child in current_node.children:
            child_action = child.path.split(":")[-1]
            if child_action == action_str:
                child_found = child
                break

        # Check if street changed AFTER recording action
        if child_found:
            if child_found.street_id != current_street:
                # Moving to a new street
                current_street = child_found.street_id
                current_player = 1  # OOP acts first on new street
            current_node = child_found

    # Get who is to act
    current_player_name = oop_position if current_player == 1 else ip_position

    # Build result for each street from the sim's starting street onward
    for street_id in [starting_street, starting_street + 1, starting_street + 2]:
        if street_id > 3:
            break  # No street after river

        street = street_names.get(street_id, "unknown")
        cards = _get_board_for_street(board, street)

        if not cards:
            # No cards for this street
            continue

        actions = street_actions.get(street_id, [])
        if actions:
            if street_id == current_street:
                # This is the decision street
                action_text = ", ".join(actions) + f", {current_player_name} to act"
            else:
                action_text = ", ".join(actions)
        else:
            if street_id == current_street:
                action_text = f"{current_player_name} to act"
            elif street_id < current_street:
                # Previous street with no actions means check-check
                action_text = f"{oop_position} checks, {ip_position} checks"
            else:
                continue  # Future street with no actions

        result.append({
            "street": street,
            "cards": cards,
            "actions": action_text,
        })

    return result


def extract_random_spot_same_street(
    tree: TreeNode,
    board: str,
    ip_position: str,
    oop_position: str,
    task_id: str = "",
    stack_size_bb: float = 100.0,
    min_frequency: float = 0.70,
    max_second_best: float = 0.25,
    max_attempts: int = 100,
    hero_position: str | None = None,
    hero_combo: str | None = None,
) -> SpotCandidate | None:
    """
    Extract a random spot from the SAME street as the tree's starting street.

    Uses random walk approach:
    1. Pick a random combo that's in range
    2. Walk the tree taking the MOST FREQUENT action at each step
    3. Stop at a decision node on the target street
    4. Check if spot has a clear correct answer

    Args:
        tree: Parsed tree root
        board: Board string
        ip_position: IP player position name
        oop_position: OOP player position name
        task_id: Source task ID for tracking
        stack_size_bb: Effective stack in big blinds
        min_frequency: Minimum frequency for "correct" action (default 70%)
        max_second_best: Maximum frequency for second-best action (default 25%)
        max_attempts: Maximum attempts to find a valid spot
        hero_position: Optional filter - "IP" or "OOP" to only get spots for that player
        hero_combo: Optional filter - specific combo like "AhKs" to use

    Returns:
        SpotCandidate if found, None otherwise
    """
    import random

    target_street = tree.street_id

    # Check if tree has ranges
    if tree.ranges is None:
        return None

    # Get combos in range at root
    ip_range = tree.ranges[0]
    oop_range = tree.ranges[1]

    # Find combos in BOTH ranges (not blocked by board)
    valid_combos = [
        i for i in range(1326)
        if ip_range[i] > 0 and oop_range[i] > 0
        and not is_combo_blocked(HAND_ORDER[i], board)
    ]

    if not valid_combos:
        return None

    # If specific combo requested, filter to just that combo
    if hero_combo:
        try:
            target_combo_idx = HAND_ORDER.index(hero_combo)
            if target_combo_idx in valid_combos:
                valid_combos = [target_combo_idx]
            else:
                return None  # Requested combo not in range
        except ValueError:
            return None  # Invalid combo string

    # Determine target player_id if hero_position specified
    target_player_id = None
    if hero_position:
        if hero_position.upper() == "OOP":
            target_player_id = 1
        elif hero_position.upper() == "IP":
            target_player_id = 0

    for attempt in range(max_attempts):
        # Pick random combo
        combo_idx = random.choice(valid_combos)
        combo = HAND_ORDER[combo_idx]

        # Randomly decide how many decision points to skip (0-2)
        # This gives variety: sometimes OOP spots, sometimes IP spots after OOP acts
        spots_to_skip = random.randint(0, 2)
        skipped = 0

        # Walk tree, taking most frequent action, until we hit a decision node
        # on the target street
        node = tree
        found_decision = False

        while not node.is_terminal():
            # Check if this is a decision node on target street
            if node.street_id == target_street and node.strategy is not None:
                # If hero_position filter is set, check if this node matches
                if target_player_id is not None and node.player_id != target_player_id:
                    # Wrong player, take best action and continue searching
                    strategy = get_strategy_for_combo(node, combo_idx)
                    if not strategy:
                        break
                    actions = list(strategy.keys())
                    freqs = list(strategy.values())
                    if not freqs or max(freqs) == 0:
                        break
                    best_action_idx = freqs.index(max(freqs))
                    if best_action_idx >= len(node.children):
                        break
                    node = node.children[best_action_idx]
                    continue

                # Check if we should skip this spot for variety
                if skipped < spots_to_skip:
                    skipped += 1
                    # Take most frequent action and continue
                    strategy = get_strategy_for_combo(node, combo_idx)
                    if not strategy:
                        break
                    actions = list(strategy.keys())
                    freqs = list(strategy.values())
                    if not freqs or max(freqs) == 0:
                        break
                    best_action_idx = freqs.index(max(freqs))
                    if best_action_idx >= len(node.children):
                        break
                    node = node.children[best_action_idx]
                    continue
                else:
                    found_decision = True
                    break

            # If we've passed target street, stop
            if node.street_id > target_street:
                break

            if node.strategy is None or node.actions is None:
                break

            # Get strategy for this combo
            strategy = get_strategy_for_combo(node, combo_idx)
            if not strategy:
                break

            # Take the MOST FREQUENT action (follow main line)
            actions = list(strategy.keys())
            freqs = list(strategy.values())

            if not freqs or max(freqs) == 0:
                break

            # Find action with highest frequency
            best_action_idx = freqs.index(max(freqs))

            # Follow child
            if best_action_idx >= len(node.children):
                break
            node = node.children[best_action_idx]

        if not found_decision:
            continue

        # Check if this combo has a clear correct action at this node
        strategy = get_strategy_for_combo(node, combo_idx)
        if not strategy:
            continue

        # Sort actions by frequency
        sorted_actions = sorted(strategy.items(), key=lambda x: x[1], reverse=True)
        if len(sorted_actions) < 2:
            continue

        best_action, best_freq = sorted_actions[0]
        second_best_freq = sorted_actions[1][1]

        # Check if this is a "clear" spot
        if best_freq < min_frequency or second_best_freq > max_second_best:
            continue

        # Skip fold spots
        if best_action.lower() == "fold":
            continue

        # Skip donk bet spots (OOP betting after calling on previous street)
        if _is_donk_bet_spot(node, tree.street_id) and best_action.lower().startswith("bet"):
            continue

        # Build the spot
        hero_position = oop_position if node.player_id == 1 else ip_position
        villain_position = ip_position if node.player_id == 1 else oop_position

        ev_by_action = get_ev_by_action(node, node.player_id, combo_idx)

        action_seq = _build_action_sequence(
            node.path,
            tree.pot_size,
            ip_position,
            oop_position,
        )

        street_actions = _build_street_actions(
            tree,
            node.path,
            board,
            ip_position,
            oop_position,
        )

        return SpotCandidate(
            id=str(uuid4()),
            source_task_id=task_id,
            board=board,
            hero_combo=combo,
            hero_position=hero_position,
            villain_position=villain_position,
            street=_street_name(node.street_id),
            pot_size_bb=node.pot_size / UNITS_PER_BB,
            stack_size_bb=stack_size_bb,
            action_sequence=action_seq,
            tree_path=node.path,
            available_actions=list(strategy.keys()),
            action_frequencies=strategy,
            correct_action=best_action,
            correct_frequency=best_freq,
            ev_by_action=ev_by_action,
            hand_category=categorize_hand(combo, board),
            board_texture=categorize_board(board),
            street_actions=street_actions,
        )

    return None


def extract_random_river_spot(
    tree: TreeNode,
    board: str,
    ip_position: str,
    oop_position: str,
    task_id: str = "",
    stack_size_bb: float = 100.0,
    min_frequency: float = 0.70,
    max_second_best: float = 0.25,
    max_attempts: int = 50,
) -> SpotCandidate | None:
    """
    Traverse tree to find a river spot with a clear correct action.

    Uses main-line walk approach:
    1. Pick a random combo that's in range for both players
    2. Walk the tree, taking the MOST FREQUENT action at each step
    3. Stop at a river decision node (street_id=3)
    4. Check if the spot has a clear correct answer
    5. Return the spot with full action history

    Args:
        tree: Parsed tree root
        board: Board string (should be 3 cards for flop sim)
        ip_position: IP player position name
        oop_position: OOP player position name
        task_id: Source task ID for tracking
        stack_size_bb: Effective stack in big blinds
        min_frequency: Minimum frequency for "correct" action (default 70%)
        max_second_best: Maximum frequency for second-best action (default 25%)
        max_attempts: Maximum attempts to find a valid river spot

    Returns:
        SpotCandidate if found, None otherwise
    """
    import random

    # Check if tree has ranges
    if tree.ranges is None:
        return None

    # Get combos in range at root (both players)
    ip_range = tree.ranges[0]
    oop_range = tree.ranges[1]

    # Find combos in BOTH ranges (not blocked by board)
    valid_combos = [
        i for i in range(1326)
        if ip_range[i] > 0 and oop_range[i] > 0
        and not is_combo_blocked(HAND_ORDER[i], board)
    ]

    if not valid_combos:
        return None

    for attempt in range(max_attempts):
        # Pick random combo
        combo_idx = random.choice(valid_combos)
        combo = HAND_ORDER[combo_idx]

        # Walk tree to river, taking most frequent action
        node = tree
        while node.street_id < 3 and not node.is_terminal():
            if node.strategy is None or node.actions is None:
                break

            # Get strategy for this combo
            strategy = get_strategy_for_combo(node, combo_idx)
            if not strategy:
                break

            # Take the MOST FREQUENT action (follow main line)
            actions = list(strategy.keys())
            freqs = list(strategy.values())

            if not freqs or max(freqs) == 0:
                break

            # Find action with highest frequency
            best_action_idx = freqs.index(max(freqs))

            # Follow child
            if best_action_idx >= len(node.children):
                break
            node = node.children[best_action_idx]

        # Check if we reached a river decision node
        if node.street_id != 3 or node.is_terminal():
            continue  # Try again

        if node.strategy is None or node.actions is None:
            continue

        # Check if this combo is blocked by the full board at this node
        # The board might have turn/river cards now
        full_board = board  # TODO: get full board from node if available

        # Get strategy for this combo at river
        strategy = get_strategy_for_combo(node, combo_idx)
        if not strategy:
            continue

        # Sort actions by frequency
        sorted_actions = sorted(strategy.items(), key=lambda x: x[1], reverse=True)
        if len(sorted_actions) < 2:
            continue

        best_action, best_freq = sorted_actions[0]
        second_best_freq = sorted_actions[1][1]

        # Check if this is a "clear" spot
        if best_freq < min_frequency or second_best_freq > max_second_best:
            continue  # Not a clear spot, try again

        # Skip fold spots
        if best_action.lower() == "fold":
            continue

        # Skip donk bet spots (OOP betting after calling on previous street)
        if _is_donk_bet_spot(node, tree.street_id) and best_action.lower().startswith("bet"):
            continue

        # Get position info
        hero_position = oop_position if node.player_id == 1 else ip_position
        villain_position = ip_position if node.player_id == 1 else oop_position

        # Get EV by action
        ev_by_action = get_ev_by_action(node, node.player_id, combo_idx)

        # Build action sequence
        action_seq = _build_action_sequence(
            node.path,
            tree.pot_size,
            ip_position,
            oop_position,
        )

        # Build street-by-street action breakdown
        street_actions = _build_street_actions(
            tree,
            node.path,
            board,
            ip_position,
            oop_position,
        )

        return SpotCandidate(
            id=str(uuid4()),
            source_task_id=task_id,
            board=board,
            hero_combo=combo,
            hero_position=hero_position,
            villain_position=villain_position,
            street=_street_name(node.street_id),
            pot_size_bb=node.pot_size / UNITS_PER_BB,
            stack_size_bb=stack_size_bb,
            action_sequence=action_seq,
            tree_path=node.path,
            available_actions=list(strategy.keys()),
            action_frequencies=strategy,
            correct_action=best_action,
            correct_frequency=best_freq,
            ev_by_action=ev_by_action,
            hand_category=categorize_hand(combo, board),
            board_texture=categorize_board(board),
            street_actions=street_actions,
        )

    # Failed to find a valid river spot after max_attempts
    return None


class SpotExtractor:
    """Extract puzzle-worthy spots from solver trees."""

    def __init__(
        self,
        min_frequency: float = 0.70,
        max_second_best: float = 0.25,
    ):
        """
        Configure extraction thresholds.

        Args:
            min_frequency: Minimum frequency for "correct" action (default 70%)
            max_second_best: Maximum frequency for second-best action (default 25%)
        """
        self.min_frequency = min_frequency
        self.max_second_best = max_second_best

    def extract_spots(
        self,
        tree: TreeNode,
        board: str,
        ip_position: str,
        oop_position: str,
        task_id: str = "",
        stack_size_bb: float = 100.0,
        ip_range: list[int] | None = None,
        oop_range: list[int] | None = None,
        target_street: int | None = None,
    ) -> list[SpotCandidate]:
        """
        Find all clear spots in the tree.

        A "clear" spot has:
        - One action with frequency >= min_frequency
        - Second-best action <= max_second_best
        - Hero combo not blocked by board
        - Hero combo is in player's range (if range provided)

        Args:
            tree: Parsed tree root
            board: Board string like "7hTh3d"
            ip_position: IP player position name
            oop_position: OOP player position name
            task_id: Source task ID for tracking
            stack_size_bb: Effective stack in big blinds
            ip_range: Optional 1326-element weight array for IP player
            oop_range: Optional 1326-element weight array for OOP player
            target_street: Only extract spots from this street (1=flop, 2=turn, 3=river).
                          If None, extracts from all streets.

        Returns:
            List of SpotCandidate objects
        """
        spots = []
        decision_nodes = find_decision_nodes(tree)

        for node in decision_nodes:
            # Filter by target street if specified
            if target_street is not None and node.street_id != target_street:
                continue
            if node.strategy is None or node.actions is None:
                continue

            # Get position info
            hero_position = oop_position if node.player_id == 1 else ip_position
            villain_position = ip_position if node.player_id == 1 else oop_position

            # Get hero's range
            hero_range = oop_range if node.player_id == 1 else ip_range

            # Check each combo
            for combo_idx in range(1326):
                combo = HAND_ORDER[combo_idx]

                # Skip blocked combos
                if is_combo_blocked(combo, board):
                    continue

                # Skip combos not in hero's range
                if hero_range is not None and hero_range[combo_idx] == 0:
                    continue

                # Get strategy for this combo
                strategy = get_strategy_for_combo(node, combo_idx)
                if not strategy:
                    continue

                # Sort actions by frequency
                sorted_actions = sorted(
                    strategy.items(), key=lambda x: x[1], reverse=True
                )

                if len(sorted_actions) < 2:
                    continue

                best_action, best_freq = sorted_actions[0]
                second_best_freq = sorted_actions[1][1]

                # Skip fold spots
                if best_action.lower() == "fold":
                    continue

                # Skip donk bet spots (OOP betting after calling on previous street)
                if _is_donk_bet_spot(node, tree.street_id) and best_action.lower().startswith("bet"):
                    continue

                # Check if this is a "clear" spot
                if (
                    best_freq >= self.min_frequency
                    and second_best_freq <= self.max_second_best
                ):
                    # Get EV by action
                    ev_by_action = get_ev_by_action(
                        node, node.player_id, combo_idx
                    )

                    # Build action sequence
                    action_seq = _build_action_sequence(
                        node.path,
                        tree.pot_size,  # Use root pot size for % calc
                        ip_position,
                        oop_position,
                    )

                    # Build street-by-street action breakdown
                    street_actions = _build_street_actions(
                        tree,
                        node.path,
                        board,
                        ip_position,
                        oop_position,
                    )

                    spot = SpotCandidate(
                        id=str(uuid4()),
                        source_task_id=task_id,
                        board=board,
                        hero_combo=combo,
                        hero_position=hero_position,
                        villain_position=villain_position,
                        street=_street_name(node.street_id),
                        pot_size_bb=node.pot_size / UNITS_PER_BB,
                        stack_size_bb=stack_size_bb,
                        action_sequence=action_seq,
                        tree_path=node.path,
                        available_actions=list(strategy.keys()),
                        action_frequencies=strategy,
                        correct_action=best_action,
                        correct_frequency=best_freq,
                        ev_by_action=ev_by_action,
                        hand_category=categorize_hand(combo, board),
                        board_texture=categorize_board(board),
                        street_actions=street_actions,
                    )
                    spots.append(spot)

        return spots
