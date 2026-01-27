"""Pydantic models for API requests and responses."""

from pydantic import BaseModel


class StreetAction(BaseModel):
    """Action breakdown for a single street."""

    street: str
    cards: str
    actions: str


class SpotResponse(BaseModel):
    """Response model for a spot candidate."""

    id: str
    source_task_id: str  # e.g., "sim-{uuid}" - used for regeneration
    board: str
    hero_combo: str
    hero_position: str
    villain_position: str
    street: str
    pot_size_bb: float
    stack_size_bb: float
    action_sequence: str
    tree_path: str
    available_actions: list[str]
    action_frequencies: dict[str, float]
    correct_action: str
    correct_frequency: float
    ev_by_action: dict[str, float]
    hand_category: str
    board_texture: str
    street_actions: list[StreetAction] = []
    status: str
    created_at: str


class PuzzleResponse(BaseModel):
    """Response model for an approved puzzle."""

    puzzle_id: int
    title: str
    question_text: str
    structure: str
    effective_stacks: int
    hero: str
    action: dict
    pot_size_at_decision: float
    answer_options: list[str]
    correct_answer: str
    explanation: str
    difficulty: int
    tags: list[str]


class ApproveRequest(BaseModel):
    """Request to approve a spot and create a puzzle."""

    question_text: str
    answer_options: list[str]  # Actions to include in the question
    correct_answers: list[str]  # Can have multiple correct answers
    explanations: dict[str, str]  # Per-action explanations: {"Check": "...", "Bet 1.5bb": "..."}
    difficulty: int
    tags: list[str]
    scheduled_date: str  # YYYY-MM-DD format


class GenerateRequest(BaseModel):
    """Request to generate new spots from solver."""

    board: str = ""  # Empty for random
    scenario: str = "srp_utg_vs_bb"
    iterations: int = 500


class GenerateResponse(BaseModel):
    """Response from spot generation."""

    task_id: str
    status: str
    spots_count: int = 0
    message: str = ""
    sim_id: str = ""


class SimResponse(BaseModel):
    """Response model for a solver sim."""

    id: str
    board: str
    scenario: str
    ip_position: str
    oop_position: str
    stack_size_bb: float
    iterations: int
    street: str
    created_at: str
    # Chained sim fields
    parent_sim_id: str | None = None
    parent_action_path: str | None = None
    pot_size_bb: float | None = None


class RandomSpotRequest(BaseModel):
    """Request to generate a random spot with optional filters."""

    hero_position: str | None = None  # "IP" or "OOP" to filter by position
    hero_combo: str | None = None  # e.g., "AhKs" to use specific hand


class CreateSpotAtPathRequest(BaseModel):
    """Request to create a spot at a specific tree path."""

    path: str  # Tree path like "r:0:c:b1650000"
    combo: str  # Hero's combo like "AhKs"


class RandomSpotResponse(BaseModel):
    """Response from generating a random spot from a sim."""

    spot_id: str
    message: str


# =============================================================================
# Turn Builder Schemas
# =============================================================================


class ActionOption(BaseModel):
    """A single available action at a tree node."""

    label: str  # Human-readable: "Check", "Bet 33%"
    path: str  # Child path: "r:0:c", "r:0:b1500000"


class TreeActionsResponse(BaseModel):
    """Response for available actions at a tree node."""

    path: str
    player_id: int | None
    position: str  # "IP" or "OOP"
    is_terminal: bool
    actions: list[ActionOption] = []


class TreeRangesResponse(BaseModel):
    """Response for ranges at a tree node."""

    path: str
    is_terminal: bool
    pot_size_bb: float
    ip_combos: int
    oop_combos: int
    ip_range: list[float] | None = None   # 1326 weights for IP player
    oop_range: list[float] | None = None  # 1326 weights for OOP player
    # Strategy data for showing action frequencies on hover
    strategy: list[list[float]] | None = None  # shape: (num_actions, 1326)
    action_names: list[str] | None = None  # Action names for each row in strategy


class CreateTurnSimRequest(BaseModel):
    """Request to create a turn sim from a flop sim."""

    flop_action_path: str  # Path to terminal flop node
    turn_card: str | None = None  # Optional, random if not provided
    iterations: int = 500


class CreateTurnSimResponse(BaseModel):
    """Response from creating a turn sim."""

    sim_id: str
    board: str
    turn_card: str
    ip_combos: int
    oop_combos: int
    pot_size_bb: float
    stack_size_bb: float


class CreateRiverSimRequest(BaseModel):
    """Request to create a river sim from a turn sim."""

    turn_action_path: str  # Path to terminal turn node
    river_card: str | None = None  # Optional, random if not provided
    iterations: int = 500


class CreateRiverSimResponse(BaseModel):
    """Response from creating a river sim."""

    sim_id: str
    board: str
    river_card: str
    ip_combos: int
    oop_combos: int
    pot_size_bb: float
    stack_size_bb: float


# =============================================================================
# Workflow Dashboard Schemas
# =============================================================================


class DatePuzzleCount(BaseModel):
    """Puzzle count for a specific date."""

    date: str  # YYYY-MM-DD format
    count: int
    target: int = 10


class WorkflowStatusResponse(BaseModel):
    """Response for workflow dashboard."""

    dates: list[DatePuzzleCount]


class ScheduledPuzzleResponse(BaseModel):
    """Response model for a scheduled puzzle (summary)."""

    id: str
    scheduled_date: str
    question_text: str
    hero: str
    correct_answer: str
    difficulty: int
    created_at: str


class FullScheduledPuzzleResponse(BaseModel):
    """Full response model for a scheduled puzzle with all details."""

    id: str
    scheduled_date: str
    question_text: str
    structure: str
    effective_stacks: int
    hero: str
    action: dict
    pot_size_at_decision: float
    answer_options: list[str]
    correct_answers: list[str]
    explanations: dict[str, str]
    ev_by_action: dict[str, float]
    action_frequencies: dict[str, float]
    difficulty: int
    tags: list[str]
    created_at: str


class UpdatePuzzleRequest(BaseModel):
    """Request to update a scheduled puzzle."""

    question_text: str | None = None
    answer_options: list[str] | None = None
    correct_answers: list[str] | None = None
    explanations: dict[str, str] | None = None
    difficulty: int | None = None
    tags: list[str] | None = None
    scheduled_date: str | None = None


# =============================================================================
# Preflop Builder Schemas
# =============================================================================


class PreflopChildNode(BaseModel):
    """A child node option in the preflop tree."""

    name: str  # e.g., "BB_3B", "BTN_Call"
    action: str  # "Raise" or "Call"
    size: float | None  # Size in bb for raises


class PreflopNodeResponse(BaseModel):
    """Response model for a preflop tree node."""

    name: str
    action: str
    size: float | None
    range_combos: int  # Count of combos with freq > 0
    children: list[str]  # Names of available child actions


class PreflopScenarioSummary(BaseModel):
    """Summary of a preflop scenario for display before generation."""

    ip_position: str
    oop_position: str
    ip_combos: int  # Combos with freq > 0
    oop_combos: int
    pot_size_bb: float
    effective_stack_bb: float
    preflop_description: str  # "BTN opens 2.5bb, BB 3-bets 13bb, BTN calls"
    path: list[str]  # The action path for reference


class PreflopSimRequest(BaseModel):
    """Request to create a flop sim from a preflop scenario."""

    path: list[str]  # e.g., ["BTN_RFI", "BB_3B", "BTN_Call"]
    board: str | None = None  # Optional, random if not provided
    iterations: int = 500


# =============================================================================
# Premium Data (iOS)
# =============================================================================


class HeroHandData(BaseModel):
    """Data for a single hand in the hero range grid."""

    weight: float  # 0-1, frequency of hand in range
    actions: dict[str, float]  # Action frequencies: {"Bet 1.6bb": 0.85, "Check": 0.15}


class PremiumPuzzleData(BaseModel):
    """Premium analysis data for a puzzle (iOS app)."""

    puzzle_id: str
    explanations: dict[str, str]  # Per-action explanations
    ev_by_action: dict[str, float]  # EV for each action
    action_frequencies: dict[str, float]  # GTO frequencies
    hero_range_grid: dict[str, HeroHandData] | None = None  # 13x13 grid with actions: {"AA": {"weight": 1.0, "actions": {...}}}
    villain_range_grid: dict[str, float] | None = None  # 13x13 grid for villain (static weights only)


# =============================================================================
# Day Plan Schemas
# =============================================================================


class PuzzleSlotResponse(BaseModel):
    """Response model for a puzzle slot."""

    id: str
    street: str  # "flop", "turn", "river"
    sim_id: str | None = None
    puzzle_id: str | None = None
    parent_slot_id: str | None = None
    action_path: str | None = None
    board: str | None = None
    status: str = "empty"  # "empty", "sim_ready", "complete"


class PreflopConfigResponse(BaseModel):
    """Response model for a preflop config."""

    id: str
    preflop_path: list[str]
    ip_position: str
    oop_position: str
    description: str
    slots: list[PuzzleSlotResponse] = []


class DayPlanResponse(BaseModel):
    """Response model for a day plan."""

    id: str
    scheduled_date: str
    configs: list[PreflopConfigResponse] = []
    status: str = "draft"
    created_at: str


class CreateDayPlanRequest(BaseModel):
    """Request to create a day plan."""

    scheduled_date: str  # YYYY-MM-DD format


class SetPreflopConfigRequest(BaseModel):
    """Request to set a preflop config on a day plan."""

    preflop_path: list[str]  # e.g., ["BTN_RFI", "BB_Call"]


class CreateSlotSimRequest(BaseModel):
    """Request to create a sim for a slot."""

    board: str | None = None  # Random if not provided
    iterations: int = 500


class LinkSlotSimRequest(BaseModel):
    """Request to link an existing sim to a slot."""

    sim_id: str


class UpdateSlotRequest(BaseModel):
    """Request to update a slot after puzzle creation."""

    puzzle_id: str | None = None
    status: str | None = None


class CreateChildSlotSimRequest(BaseModel):
    """Request to create a turn/river sim from a parent slot."""

    action_path: str  # Path in parent sim to terminal node
    card: str | None = None  # Turn/river card, random if not provided
    iterations: int = 500


class CompatibleSimResponse(BaseModel):
    """Response for a compatible sim that can be linked to a slot."""

    id: str
    board: str
    scenario: str
    ip_position: str
    oop_position: str
    street: str
    created_at: str
