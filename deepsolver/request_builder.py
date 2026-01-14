"""Builder for constructing Deepsolver API requests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .preflop_ranges import get_rfi_range, get_defend_range
from .ranges import count_combos

# Unit conversion: API uses 1,000,000 units per big blind
UNITS_PER_BB = 1_000_000


@dataclass
class SpotConfig:
    """Configuration for a poker spot to analyze."""

    board: str  # e.g., "Ah7d2c"
    ip_range: list[int]  # 1326 weights for IP player
    oop_range: list[int]  # 1326 weights for OOP player
    pot_size_bb: float  # Pot size in big blinds
    effective_stack_bb: float  # Remaining stack in big blinds
    street_id: int = 1  # 1=flop, 2=turn, 3=river
    ip_position: str = "IP"  # Position name for IP player
    oop_position: str = "OOP"  # Position name for OOP player


# Default bet sizings as pot fractions
# Structure: street -> action_type -> list of sizes
# Bets: 33%, 75%, 125% pot
# Raises: 50%, 75%, 125% pot (50% gives smaller check-raise options)
DEFAULT_IP_SIZINGS = {
    "flop": {"bet": [0.33, 0.75, 1.25], "raise": [0.5, 0.75, 1.25], "3bet": [1.25], "4bet": [1.25]},
    "turn": {"bet": [0.33, 0.75, 1.25], "raise": [0.5, 0.75, 1.25], "3bet": [1.25], "4bet": [1.25]},
    "river": {"bet": [0.33, 0.75, 1.25], "raise": [0.5, 0.75, 1.25], "3bet": [1.25], "4bet": [1.25]},
}

DEFAULT_OOP_SIZINGS = {
    "flop": {"bet": [0.33, 0.75, 1.25], "raise": [0.5, 0.75, 1.25], "3bet": [1.25], "4bet": [1.25]},
    "turn": {"bet": [0.33, 0.75, 1.25], "raise": [0.5, 0.75, 1.25], "3bet": [1.25], "4bet": [1.25]},
    "river": {"bet": [0.33, 0.75, 1.25], "raise": [0.5, 0.75, 1.25], "3bet": [1.25], "4bet": [1.25]},
}

# Donk bet sizings (OOP betting into IP before IP acts)
DEFAULT_DONK_SIZINGS = {
    "flop": [0.33, 0.75],
    "turn": [0.33, 0.75],
    "river": [0.33, 0.75],
}


def _build_pot_fractions(sizings: dict) -> list[list[list[float]]]:
    """
    Build pot_fractions array from sizing dict.

    Returns: [preflop, flop, turn, river] where each street is
             [bet_sizes, raise_sizes, 3bet_sizes, 4bet_sizes]
    """
    streets = ["preflop", "flop", "turn", "river"]
    actions = ["bet", "raise", "3bet", "4bet"]

    result = []
    for street in streets:
        street_sizings = sizings.get(street, {})
        street_result = []
        for action in actions:
            street_result.append(street_sizings.get(action, []))
        result.append(street_result)

    return result


def _build_donk_fractions(donk_sizings: dict) -> list[list[float]]:
    """Build donk_pot_fractions array."""
    streets = ["preflop", "flop", "turn", "river"]
    return [donk_sizings.get(street, []) for street in streets]


def _get_street_id(board: str) -> int:
    """
    Determine street_id from board length.

    Args:
        board: Board string (e.g., "Ah7d2c" for flop, "Ah7d2c8h" for turn)

    Returns:
        street_id: 1 for flop, 2 for turn, 3 for river
    """
    num_cards = len(board) // 2
    if num_cards == 3:
        return 1  # flop
    elif num_cards == 4:
        return 2  # turn
    elif num_cards == 5:
        return 3  # river
    raise ValueError(f"Invalid board length: {len(board)} chars ({num_cards} cards). Expected 3-5 cards.")


class RequestBuilder:
    """Builder for Deepsolver API requests."""

    def __init__(self, config: SpotConfig):
        """
        Initialize the request builder.

        Args:
            config: SpotConfig with board, ranges, pot, and stack info
        """
        self.config = config
        self.iterations = 500
        self.ip_sizings = DEFAULT_IP_SIZINGS.copy()
        self.oop_sizings = DEFAULT_OOP_SIZINGS.copy()
        self.donk_sizings = DEFAULT_DONK_SIZINGS.copy()

    def with_iterations(self, iters: int) -> RequestBuilder:
        """Set the number of solver iterations."""
        self.iterations = iters
        return self

    def with_sizings(
        self,
        ip_sizings: dict | None = None,
        oop_sizings: dict | None = None,
    ) -> RequestBuilder:
        """
        Set custom bet sizings.

        Args:
            ip_sizings: Sizings for IP player
            oop_sizings: Sizings for OOP player
        """
        if ip_sizings:
            self.ip_sizings = ip_sizings
        if oop_sizings:
            self.oop_sizings = oop_sizings
        return self

    def build(self) -> dict[str, Any]:
        """Build the complete API request payload."""
        config = self.config

        # Convert to API units
        pot_size = int(config.pot_size_bb * UNITS_PER_BB)
        stack_size = int(config.effective_stack_bb * UNITS_PER_BB)

        # Build pot_fractions: [IP, OOP] x [streets] x [actions] x [sizes]
        ip_fractions = _build_pot_fractions(self.ip_sizings)
        oop_fractions = _build_pot_fractions(self.oop_sizings)
        pot_fractions = [ip_fractions, oop_fractions]

        # Build donk fractions
        donk_fractions = _build_donk_fractions(self.donk_sizings)

        return {
            "iters": self.iterations,
            "ranges": [config.ip_range, config.oop_range],
            "board": config.board,
            "tree_request": {
                "pot_size": pot_size,
                "players_stacks_sizes": [stack_size, stack_size],
                "street_id": config.street_id,
                "nr_of_streets_to_build": 4 - config.street_id,  # Build through river
                "pot_fractions": pot_fractions,
                "donk_pot_fractions": donk_fractions,
                "all_in_threshold": 0.67,
                "add_all_in_if_stack_lt_pot_times": 3,
                "max_all_in_depth": -1,
                "replace_live_sizes": True,
            },
            "options": {
                "results_format": "HOLDEM",
            },
            "clip_ev": False,
            "add_investments": True,
            "correct_ev_for_node_compare": False,
            "strategies_per_node_path": {},
        }


# =============================================================================
# Preset Builders for Common Scenarios
# =============================================================================


def srp_utg_vs_bb(board: str, stacks_bb: int = 100) -> RequestBuilder:
    """
    Create a builder for Single Raised Pot: UTG opens, BB defends.

    Args:
        board: Board cards (e.g., "Ah7d2c" for flop, "Ah7d2c8h" for turn)
        stacks_bb: Effective stack in big blinds (default 100)

    Returns:
        Configured RequestBuilder
    """
    # UTG opens 2.5bb, BB calls
    # Pot = 2.5 + 2.5 + 0.5 (SB) = 5.5bb (or 5bb if SB folds pre)
    # Actually in HU after open: pot = open_size + call = 2.5 + 2.5 = 5bb
    # Let's use 5bb for simplicity
    pot_size_bb = 5.0

    # Remaining stacks after investing 2.5bb each
    remaining_stack = stacks_bb - 2.5

    config = SpotConfig(
        board=board,
        ip_range=get_rfi_range("UTG"),
        oop_range=get_defend_range("BB", "UTG"),
        pot_size_bb=pot_size_bb,
        effective_stack_bb=remaining_stack,
        street_id=_get_street_id(board),
        ip_position="UTG",
        oop_position="BB",
    )

    return RequestBuilder(config)


def srp_co_vs_bb(board: str, stacks_bb: int = 100) -> RequestBuilder:
    """
    Create a builder for Single Raised Pot: CO opens, BB defends.

    Args:
        board: Board cards (e.g., "Ah7d2c" for flop, "Ah7d2c8h" for turn)
        stacks_bb: Effective stack in big blinds (default 100)
    """
    pot_size_bb = 5.0
    remaining_stack = stacks_bb - 2.5

    config = SpotConfig(
        board=board,
        ip_range=get_rfi_range("CO"),
        oop_range=get_defend_range("BB", "CO"),
        pot_size_bb=pot_size_bb,
        effective_stack_bb=remaining_stack,
        street_id=_get_street_id(board),
        ip_position="CO",
        oop_position="BB",
    )

    return RequestBuilder(config)


def srp_btn_vs_bb(board: str, stacks_bb: int = 100) -> RequestBuilder:
    """
    Create a builder for Single Raised Pot: BTN opens, BB defends.

    Args:
        board: Board cards (e.g., "Ah7d2c" for flop, "Ah7d2c8h" for turn)
        stacks_bb: Effective stack in big blinds (default 100)
    """
    pot_size_bb = 5.0
    remaining_stack = stacks_bb - 2.5

    config = SpotConfig(
        board=board,
        ip_range=get_rfi_range("BTN"),
        oop_range=get_defend_range("BB", "BTN"),
        pot_size_bb=pot_size_bb,
        effective_stack_bb=remaining_stack,
        street_id=_get_street_id(board),
        ip_position="BTN",
        oop_position="BB",
    )

    return RequestBuilder(config)


def describe_request(builder: RequestBuilder) -> str:
    """Return a human-readable description of the request."""
    config = builder.config
    ip_combos = count_combos(config.ip_range)
    oop_combos = count_combos(config.oop_range)

    return (
        f"Board: {config.board}\n"
        f"Pot: {config.pot_size_bb}bb, Stacks: {config.effective_stack_bb}bb\n"
        f"{config.ip_position} (IP): {ip_combos} combos\n"
        f"{config.oop_position} (OOP): {oop_combos} combos"
    )
