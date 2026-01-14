"""Utilities for working with poker hands in the solver's 1326-combo format."""

from pathlib import Path

# Rank and suit ordering
RANKS = "23456789TJQKA"
SUITS = "cdhs"
RANK_ORDER = {r: i for i, r in enumerate(RANKS)}
SUIT_ORDER = {s: i for i, s in enumerate(SUITS)}


def _load_hand_order() -> tuple[list[str], dict[str, int]]:
    """Load the canonical hand order from solver_hand_order.txt."""
    order_file = Path(__file__).parent.parent / "solver_hand_order.txt"

    if not order_file.exists():
        raise FileNotFoundError(
            f"Hand order file not found: {order_file}. "
            "This file is required for combo/index conversion."
        )

    with open(order_file) as f:
        hand_order = [line.strip() for line in f if line.strip()]

    if len(hand_order) != 1326:
        raise ValueError(
            f"Expected 1326 combos in hand order file, got {len(hand_order)}"
        )

    hand_to_index = {combo: i for i, combo in enumerate(hand_order)}

    return hand_order, hand_to_index


# Load on module import
HAND_ORDER, HAND_TO_INDEX = _load_hand_order()


def normalize_combo(combo: str) -> str:
    """
    Normalize a combo to the canonical format (higher rank first).

    Examples:
        normalize_combo("AhKh") -> "AhKh"
        normalize_combo("KhAh") -> "AhKh"
        normalize_combo("2d2c") -> "2d2c"
    """
    if len(combo) != 4:
        raise ValueError(f"Invalid combo format: {combo}")

    rank1, suit1 = combo[0], combo[1]
    rank2, suit2 = combo[2], combo[3]

    # Validate
    if rank1 not in RANK_ORDER or rank2 not in RANK_ORDER:
        raise ValueError(f"Invalid rank in combo: {combo}")
    if suit1 not in SUIT_ORDER or suit2 not in SUIT_ORDER:
        raise ValueError(f"Invalid suit in combo: {combo}")

    # Higher rank first; if same rank, higher suit first
    r1_val, r2_val = RANK_ORDER[rank1], RANK_ORDER[rank2]
    s1_val, s2_val = SUIT_ORDER[suit1], SUIT_ORDER[suit2]

    if r1_val > r2_val:
        return combo
    elif r1_val < r2_val:
        return f"{rank2}{suit2}{rank1}{suit1}"
    else:
        # Same rank (pair) - higher suit first
        if s1_val >= s2_val:
            return combo
        else:
            return f"{rank2}{suit2}{rank1}{suit1}"


def combo_to_index(combo: str) -> int:
    """
    Convert a combo string to its index in the canonical ordering.

    Args:
        combo: Four-character combo like "AhKh" or "2d2c"

    Returns:
        Index from 0 to 1325

    Raises:
        KeyError: If combo is not found (may need normalization)
    """
    # Try as-is first
    if combo in HAND_TO_INDEX:
        return HAND_TO_INDEX[combo]

    # Try normalized
    normalized = normalize_combo(combo)
    if normalized in HAND_TO_INDEX:
        return HAND_TO_INDEX[normalized]

    raise KeyError(f"Combo not found in hand order: {combo}")


def index_to_combo(index: int) -> str:
    """
    Convert an index to its combo string.

    Args:
        index: Index from 0 to 1325

    Returns:
        Four-character combo string
    """
    if not 0 <= index < 1326:
        raise IndexError(f"Index out of range: {index}")
    return HAND_ORDER[index]


def parse_card(card: str) -> tuple[str, str]:
    """Parse a 2-character card into (rank, suit)."""
    if len(card) != 2:
        raise ValueError(f"Invalid card format: {card}")
    return card[0], card[1]


def parse_board(board: str) -> list[str]:
    """
    Parse a board string into individual cards.

    Args:
        board: Board string like "As7d2c" or "7hTh3d"

    Returns:
        List of 2-character card strings
    """
    if len(board) % 2 != 0:
        raise ValueError(f"Invalid board format: {board}")

    cards = []
    for i in range(0, len(board), 2):
        card = board[i : i + 2]
        rank, suit = parse_card(card)
        if rank not in RANK_ORDER or suit not in SUIT_ORDER:
            raise ValueError(f"Invalid card in board: {card}")
        cards.append(card)

    return cards


def is_combo_blocked(combo: str, board: str) -> bool:
    """
    Check if a combo is blocked by the board (shares any cards).

    Args:
        combo: Four-character combo like "AhKh"
        board: Board string like "As7d2c"

    Returns:
        True if combo shares any card with board
    """
    board_cards = set(parse_board(board))
    combo_cards = {combo[0:2], combo[2:4]}

    return bool(combo_cards & board_cards)


def get_unblocked_combos(board: str) -> list[int]:
    """
    Get indices of all combos not blocked by the board.

    Args:
        board: Board string like "As7d2c"

    Returns:
        List of indices (0-1325) for playable combos
    """
    return [
        i for i, combo in enumerate(HAND_ORDER) if not is_combo_blocked(combo, board)
    ]


def get_combo_cards(combo: str) -> tuple[str, str]:
    """
    Split a combo into its two cards.

    Args:
        combo: Four-character combo like "AhKh"

    Returns:
        Tuple of two 2-character card strings
    """
    return combo[0:2], combo[2:4]


def get_remaining_deck(board: str) -> list[str]:
    """
    Get all cards not on the board.

    Args:
        board: Board string like "As7d2c"

    Returns:
        List of 2-character card strings not on board
    """
    board_cards = set(parse_board(board))
    all_cards = [f"{r}{s}" for r in RANKS for s in SUITS]
    return [card for card in all_cards if card not in board_cards]


def deal_random_card(
    board: str,
    ip_range: list[int] | None = None,
    oop_range: list[int] | None = None,
) -> str:
    """
    Deal a random card that doesn't block too many combos in the ranges.

    Picks a card that preserves the most combos across both ranges.
    This helps ensure the turn/river spots have enough combos to analyze.

    Args:
        board: Current board string like "As7d2c"
        ip_range: Optional 1326-element weight array for IP player
        oop_range: Optional 1326-element weight array for OOP player

    Returns:
        2-character card string like "8h"
    """
    import random

    remaining_cards = get_remaining_deck(board)

    if not remaining_cards:
        raise ValueError("No cards remaining in deck")

    # If no ranges provided, just pick random card
    if ip_range is None and oop_range is None:
        return random.choice(remaining_cards)

    # Score each card by how many combos it preserves
    # Lower blockers = better card
    card_scores = []

    for card in remaining_cards:
        blocked_combos = 0
        new_board = board + card

        for i, combo in enumerate(HAND_ORDER):
            # Check if combo was in range and would now be blocked
            in_ip = ip_range is not None and ip_range[i] > 0
            in_oop = oop_range is not None and oop_range[i] > 0

            if (in_ip or in_oop) and is_combo_blocked(combo, new_board):
                blocked_combos += 1

        card_scores.append((card, blocked_combos))

    # Sort by fewest blocked combos
    card_scores.sort(key=lambda x: x[1])

    # Pick from top 10 candidates randomly to add variety
    top_candidates = [c[0] for c in card_scores[:10]]
    return random.choice(top_candidates)
