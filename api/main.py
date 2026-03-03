"""FastAPI backend for puzzle admin GUI."""

import os
import sys
import random
import uuid
import logging
from datetime import datetime
from pathlib import Path

# Configure logging to flush immediately
logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stdout)
logger = logging.getLogger(__name__)

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api.schemas import (
    SpotResponse,
    PuzzleResponse,
    ApproveRequest,
    GenerateRequest,
    GenerateResponse,
    SimResponse,
    RandomSpotRequest,
    RandomSpotResponse,
    CreateSpotAtPathRequest,
    ActionOption,
    TreeActionsResponse,
    TreeRangesResponse,
    CreateTurnSimRequest,
    CreateTurnSimResponse,
    CreateRiverSimRequest,
    CreateRiverSimResponse,
    DatePuzzleCount,
    WorkflowStatusResponse,
    ScheduledPuzzleResponse,
    FullScheduledPuzzleResponse,
    UpdatePuzzleRequest,
    PreflopChildNode,
    PreflopNodeResponse,
    PreflopScenarioSummary,
    PreflopSimRequest,
    PremiumPuzzleData,
    PuzzleTreeDataResponse,
    # Day Plan schemas
    PuzzleSlotResponse,
    PreflopConfigResponse,
    DayPlanResponse,
    CreateDayPlanRequest,
    SetPreflopConfigRequest,
    CreateSlotSimRequest,
    LinkSlotSimRequest,
    UpdateSlotRequest,
    CreateChildSlotSimRequest,
    WalkLineRequest,
    NodeInfoRequest,
    NodeInfoResponse,
    NodeActionInfo,
    CompatibleSimResponse,
    # Import pipeline schemas
    ImportSpot,
    ImportScenario,
    ImportDayPlanRequest,
    ImportDayPlanResponse,
    PickComboRequest,
)
from storage.firestore import PuzzleStorage
from storage.models import spot_to_puzzle, ApprovedPuzzle, SolverSim, ScheduledPuzzle, DayPlan, PreflopConfig, PuzzleSlot
from deepsolver import (
    DeepsolverClient,
    get_api_token,
    srp_utg_vs_bb,
    srp_btn_vs_bb,
    srp_co_vs_bb,
    parse_tree,
    SpotExtractor,
    extract_random_river_spot,
    extract_random_spot_same_street,
    get_actions_at_node,
    get_ranges_at_node,
)
from deepsolver.hand_utils import deal_random_card
from deepsolver.request_builder import SpotConfig, RequestBuilder, UNITS_PER_BB
from deepsolver.ranges import firestore_range_to_weights
from deepsolver.preflop_calc import (
    calculate_pot_and_stacks,
    determine_ip_oop_positions,
    build_preflop_description,
    get_scenario_summary,
)
from storage.preflop_ranges import PreflopRangeStorage

app = FastAPI(title="Puzzle Admin API")

# CORS configuration - supports local dev and production
cors_origins_env = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,https://admin-ui-iota-three.vercel.app")
cors_origins = [origin.strip() for origin in cors_origins_env.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize storage
storage = PuzzleStorage()
preflop_storage = PreflopRangeStorage()

# Scenario builders
SCENARIO_BUILDERS = {
    "srp_utg_vs_bb": srp_utg_vs_bb,
    "srp_btn_vs_bb": srp_btn_vs_bb,
    "srp_co_vs_bb": srp_co_vs_bb,
}


@app.get("/")
def root():
    """Health check."""
    return {"status": "ok", "service": "puzzle-admin-api"}


# =============================================================================
# Spots
# =============================================================================


@app.get("/spots", response_model=list[SpotResponse])
def list_spots(status: str = "pending", limit: int = 50):
    """List spot candidates."""
    if status == "pending":
        spots = storage.get_pending_candidates(limit=limit)
    else:
        # For now, only pending is supported via the optimized method
        # Could add get_all_candidates later
        spots = storage.get_pending_candidates(limit=limit)

    return [
        SpotResponse(
            id=s.id,
            source_task_id=s.source_task_id,
            board=s.board,
            hero_combo=s.hero_combo,
            hero_position=s.hero_position,
            villain_position=s.villain_position,
            street=s.street,
            pot_size_bb=s.pot_size_bb,
            stack_size_bb=s.stack_size_bb,
            action_sequence=s.action_sequence,
            tree_path=s.tree_path,
            available_actions=s.available_actions,
            action_frequencies=s.action_frequencies,
            correct_action=s.correct_action,
            correct_frequency=s.correct_frequency,
            ev_by_action=s.ev_by_action,
            hand_category=s.hand_category,
            board_texture=s.board_texture,
            street_actions=s.street_actions,
            status="pending",
            created_at=s.created_at.isoformat(),
        )
        for s in spots
    ]


@app.get("/spots/{spot_id}", response_model=SpotResponse)
def get_spot(spot_id: str):
    """Get a single spot by ID."""
    spot = storage.get_candidate(spot_id)
    if not spot:
        raise HTTPException(status_code=404, detail="Spot not found")

    return SpotResponse(
        id=spot.id,
        source_task_id=spot.source_task_id,
        board=spot.board,
        hero_combo=spot.hero_combo,
        hero_position=spot.hero_position,
        villain_position=spot.villain_position,
        street=spot.street,
        pot_size_bb=spot.pot_size_bb,
        stack_size_bb=spot.stack_size_bb,
        action_sequence=spot.action_sequence,
        tree_path=spot.tree_path,
        available_actions=spot.available_actions,
        action_frequencies=spot.action_frequencies,
        correct_action=spot.correct_action,
        correct_frequency=spot.correct_frequency,
        ev_by_action=spot.ev_by_action,
        hand_category=spot.hand_category,
        board_texture=spot.board_texture,
        street_actions=spot.street_actions,
        status="pending",
        created_at=spot.created_at.isoformat(),
    )


@app.post("/spots/{spot_id}/approve", response_model=ScheduledPuzzleResponse)
def approve_spot(spot_id: str, request: ApproveRequest):
    """Approve a spot and create a scheduled puzzle."""
    spot = storage.get_candidate(spot_id)
    if not spot:
        raise HTTPException(status_code=404, detail="Spot not found")

    # Check if date already has 10 puzzles
    existing_count = len(storage.get_puzzles_by_date(request.scheduled_date))
    if existing_count >= 10:
        raise HTTPException(
            status_code=400,
            detail=f"Date {request.scheduled_date} already has 10 puzzles"
        )

    # Create puzzle from spot helper to get the action tree
    temp_puzzle = spot_to_puzzle(
        spot=spot,
        puzzle_id=0,  # Not used
        title="",  # Deprecated
        explanation="",  # Not used - we have per-action explanations
        difficulty=request.difficulty,
        answer_options=request.answer_options,
    )

    # Compute spot type classification
    from utils.spot_classifier import classify_spot_type
    spot_type = classify_spot_type(temp_puzzle.action, spot.hero_position)

    # Create scheduled puzzle with multiple correct answers and per-action explanations
    puzzle = ScheduledPuzzle(
        id=str(uuid.uuid4()),
        scheduled_date=request.scheduled_date,
        question_text=request.question_text,
        structure="6max",
        effective_stacks=int(spot.stack_size_bb),
        hero=spot.hero_position,
        action=temp_puzzle.action,
        pot_size_at_decision=spot.pot_size_bb,
        answer_options=request.answer_options,
        correct_answers=request.correct_answers,
        explanations=request.explanations,
        ev_by_action=spot.ev_by_action,
        action_frequencies=spot.action_frequencies,
        difficulty=request.difficulty,
        tags=request.tags,
        created_at=datetime.utcnow(),
        spot_type=spot_type,
    )

    # Save to new_daily_puzzles collection
    storage.save_scheduled_puzzle(puzzle)

    # Update spot status
    storage.update_candidate_status(spot_id, "approved")

    return ScheduledPuzzleResponse(
        id=puzzle.id,
        scheduled_date=puzzle.scheduled_date,
        question_text=puzzle.question_text,
        hero=puzzle.hero,
        correct_answer=request.correct_answers[0] if request.correct_answers else "",
        difficulty=puzzle.difficulty,
        created_at=puzzle.created_at.isoformat(),
    )


@app.post("/spots/{spot_id}/reject")
def reject_spot(spot_id: str):
    """Reject a spot."""
    spot = storage.get_candidate(spot_id)
    if not spot:
        raise HTTPException(status_code=404, detail="Spot not found")

    storage.update_candidate_status(spot_id, "rejected")
    return {"status": "rejected", "id": spot_id}


# =============================================================================
# Puzzles
# =============================================================================


@app.get("/puzzles", response_model=list[PuzzleResponse])
def list_puzzles():
    """List all approved puzzles."""
    puzzles = storage.get_all_puzzles()
    return [
        PuzzleResponse(
            puzzle_id=p.puzzle_id,
            title=p.title,
            question_text=p.question_text,
            structure=p.structure,
            effective_stacks=p.effective_stacks,
            hero=p.hero,
            action=p.action,
            pot_size_at_decision=p.pot_size_at_decision,
            answer_options=p.answer_options,
            correct_answer=p.correct_answer,
            explanation=p.explanation,
            difficulty=p.difficulty,
            tags=p.tags,
        )
        for p in puzzles
    ]


@app.get("/puzzles/{puzzle_id}", response_model=PuzzleResponse)
def get_puzzle(puzzle_id: int):
    """Get a single puzzle by ID."""
    puzzle = storage.get_puzzle(puzzle_id)
    if not puzzle:
        raise HTTPException(status_code=404, detail="Puzzle not found")

    return PuzzleResponse(
        puzzle_id=puzzle.puzzle_id,
        title=puzzle.title,
        question_text=puzzle.question_text,
        structure=puzzle.structure,
        effective_stacks=puzzle.effective_stacks,
        hero=puzzle.hero,
        action=puzzle.action,
        pot_size_at_decision=puzzle.pot_size_at_decision,
        answer_options=puzzle.answer_options,
        correct_answer=puzzle.correct_answer,
        explanation=puzzle.explanation,
        difficulty=puzzle.difficulty,
        tags=puzzle.tags,
    )


# =============================================================================
# Premium Data (iOS)
# =============================================================================


@app.get("/daily-puzzles/{puzzle_id}/premium", response_model=PremiumPuzzleData)
def get_premium_puzzle_data(puzzle_id: str):
    """
    Get premium analysis data for a scheduled puzzle.

    Returns explanations, EVs, frequencies, and range grids.
    iOS app calls this when user has premium subscription.
    """
    # Get the puzzle from new_daily_puzzles
    puzzle = storage.get_scheduled_puzzle(puzzle_id)
    if not puzzle:
        raise HTTPException(status_code=404, detail="Puzzle not found")

    # Extract board from Action data
    board = _extract_board_from_action(puzzle.action)
    if not board:
        # Return data without range grids
        return PremiumPuzzleData(
            puzzle_id=puzzle_id,
            explanations=puzzle.explanations,
            ev_by_action=puzzle.ev_by_action,
            action_frequencies=puzzle.action_frequencies,
            hero_range_grid=None,
            villain_range_grid=None,
        )

    # Find sim by matching board and positions
    villain = _extract_villain_from_action(puzzle.action, puzzle.hero)
    logger.info(f"PREMIUM: puzzle={puzzle_id}, board={board}, hero={puzzle.hero}, villain={villain}")
    sys.stdout.flush()
    sim = _find_sim_by_board(board, puzzle.hero, villain)
    if not sim:
        logger.info(f"PREMIUM: No sim found for board={board}")
        sys.stdout.flush()
        # Return data without range grids
        return PremiumPuzzleData(
            puzzle_id=puzzle_id,
            explanations=puzzle.explanations,
            ev_by_action=puzzle.ev_by_action,
            action_frequencies=puzzle.action_frequencies,
            hero_range_grid=None,
            villain_range_grid=None,
        )

    logger.info(f"PREMIUM: Found sim={sim.id}, scenario={sim.scenario}, ip={sim.ip_position}, oop={sim.oop_position}, has_tree={sim.tree is not None}")
    sys.stdout.flush()

    # Reconstruct tree path from action sequence
    tree_path = _reconstruct_tree_path(puzzle.action, sim)
    logger.info(f"PREMIUM: tree_path={tree_path}")
    sys.stdout.flush()

    # Get range data
    hero_grid, villain_grid = _get_range_grids(sim, tree_path, puzzle.hero)

    return PremiumPuzzleData(
        puzzle_id=puzzle_id,
        explanations=puzzle.explanations,
        ev_by_action=puzzle.ev_by_action,
        action_frequencies=puzzle.action_frequencies,
        hero_range_grid=hero_grid,
        villain_range_grid=villain_grid,
    )


def _extract_board_from_action(action: dict) -> str | None:
    """Extract full board cards from Action dict (flop + turn + river)."""
    board = ""

    # Get flop cards
    flop = action.get("flop", {})
    flop_cards = flop.get("Cards", "")
    if flop_cards:
        board = flop_cards.replace("-", "")
    else:
        # Try to find Cards in any position entry in flop
        for key, value in flop.items():
            if isinstance(value, dict) and "Cards" in value:
                cards = value.get("Cards", "")
                if len(cards) >= 6:  # Looks like a board
                    board = cards.replace("-", "")
                    break

    if not board:
        return None

    # Add turn card if present
    turn = action.get("turn", {})
    turn_card = turn.get("Cards", "")
    if turn_card:
        board += turn_card.replace("-", "")

    # Add river card if present
    river = action.get("river", {})
    river_card = river.get("Cards", "")
    if river_card:
        board += river_card.replace("-", "")

    return board


def _extract_villain_from_action(action: dict, hero: str) -> str | None:
    """Extract villain position from preflop action."""
    VALID_POSITIONS = {"UTG", "UTG1", "UTG2", "HJ", "LJ", "CO", "BTN", "SB", "BB"}
    preflop = action.get("preflop", {})
    for position in preflop.keys():
        if position != hero and position in VALID_POSITIONS:
            return position
    return None


def _find_sim_by_board(board: str, hero_position: str = None, villain_position: str = None) -> SolverSim | None:
    """Find a sim matching the given board and positions."""
    all_sims = storage.get_all_sims()
    matching_sims = [s for s in all_sims if s.board == board]

    if not matching_sims:
        return None

    # If both positions provided, find exact match
    if hero_position and villain_position and len(matching_sims) > 1:
        for sim in matching_sims:
            positions = {sim.ip_position, sim.oop_position}
            if hero_position in positions and villain_position in positions:
                return storage.get_sim(sim.id, load_tree=True)

    # If only hero position provided, try to find matching sim
    if hero_position and len(matching_sims) > 1:
        for sim in matching_sims:
            if sim.ip_position == hero_position or sim.oop_position == hero_position:
                return storage.get_sim(sim.id, load_tree=True)

    # Fallback to first match
    return storage.get_sim(matching_sims[0].id, load_tree=True)


def _reconstruct_tree_path(action: dict, sim: SolverSim) -> str:
    """
    Reconstruct tree path from action sequence by navigating the actual tree.

    Uses fuzzy matching for bet sizes since puzzle amounts may differ slightly
    from solver's exact bet sizes.
    """
    from deepsolver.tree_parser import parse_tree, get_node_by_path

    # Determine which street's actions to use based on sim
    street = sim.street if sim.street else "flop"
    street_data = action.get(street, {})

    # Parse the tree
    if not sim.tree:
        logger.info("TREEPATH: No tree in sim")
        return "r:0"
    tree = parse_tree(sim.tree)

    # Start with root
    current_path = "r:0"

    # Get the action sequence from the appropriate street
    position_actions = []
    for key, value in sorted(street_data.items()):
        if isinstance(value, dict) and "Action" in value:
            position_actions.append((key, value))

    for pos_key, action_data in position_actions:
        action_type = action_data.get("Action", "").lower()
        amount = action_data.get("Amount")

        # Get current node to find available children
        current_node = get_node_by_path(tree, current_path)
        if not current_node or not current_node.children:
            break

        # Find the best matching child
        if action_type == "check" or action_type == "call":
            # Look for check child (path ends with :c)
            for child in current_node.children:
                if child.path.endswith(":c"):
                    current_path = child.path
                    break
        elif action_type in ("bet", "raise", "3bet", "4bet", "5bet"):
            if amount:
                # Find the closest bet size
                target_units = int(amount * 1_000_000)
                best_child = None
                best_diff = float("inf")

                for child in current_node.children:
                    # Extract bet amount from path like "r:0:b1600000"
                    path_parts = child.path.split(":")
                    last_part = path_parts[-1]
                    if last_part.startswith("b"):
                        try:
                            bet_units = int(last_part[1:])
                            diff = abs(bet_units - target_units)
                            if diff < best_diff:
                                best_diff = diff
                                best_child = child
                        except ValueError:
                            pass

                if best_child:
                    current_path = best_child.path
        elif action_type == "fold":
            # Look for fold child
            for child in current_node.children:
                if child.path.endswith(":f"):
                    current_path = child.path
                    break

    return current_path


def _get_range_grids(
    sim: SolverSim,
    tree_path: str,
    hero_position: str
) -> tuple[dict | None, dict[str, float] | None]:
    """Get 13x13 range grids for hero (with actions) and villain (weights only)."""
    if not sim.tree:
        return None, None

    try:
        tree = parse_tree(sim.tree)
        range_data = get_ranges_at_node(tree, tree_path)

        if "error" in range_data:
            return None, None

        ip_range = range_data.get("ip_range")
        oop_range = range_data.get("oop_range")
        strategy = range_data.get("strategy")  # shape: (num_actions, 1326)
        action_names = range_data.get("action_names")  # list of action names

        if not ip_range or not oop_range:
            return None, None

        # Determine which range is hero's based on sim's actual position assignments
        hero_is_ip = hero_position == sim.ip_position
        logger.info(f"RANGES: hero={hero_position}, sim.ip={sim.ip_position}, sim.oop={sim.oop_position}, hero_is_ip={hero_is_ip}")
        sys.stdout.flush()
        hero_range = ip_range if hero_is_ip else oop_range
        villain_range = oop_range if hero_is_ip else ip_range

        # Aggregate hero grid with strategy (actions), filtering by board
        hero_grid, _ = _aggregate_to_grid_with_actions(hero_range, strategy, action_names, sim.board or "")
        # Villain just gets weights
        villain_grid = _aggregate_to_grid(villain_range)

        return hero_grid, villain_grid
    except Exception as e:
        print(f"Error getting range grids: {e}")
        return None, None


def _aggregate_to_grid(range_1326: list[int | float]) -> dict[str, float]:
    """
    Aggregate 1326 combo weights to 13x13 grid format.

    Returns dict like {"AA": 1.0, "AKs": 0.95, "AKo": 0.85, ...}
    """
    from deepsolver.hand_utils import HAND_ORDER

    RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']

    # Initialize grid with totals and counts
    grid_totals = {}
    grid_counts = {}

    for combo_idx, weight in enumerate(range_1326):
        if combo_idx >= len(HAND_ORDER):
            break

        combo = HAND_ORDER[combo_idx]
        r1, s1 = combo[0], combo[1]
        r2, s2 = combo[2], combo[3]

        # Determine hand type
        if r1 == r2:
            # Pair
            hand_key = f"{r1}{r1}"
        elif s1 == s2:
            # Suited - higher rank first
            ranks = sorted([r1, r2], key=lambda x: RANKS.index(x))
            hand_key = f"{ranks[0]}{ranks[1]}s"
        else:
            # Offsuit - higher rank first
            ranks = sorted([r1, r2], key=lambda x: RANKS.index(x))
            hand_key = f"{ranks[0]}{ranks[1]}o"

        if hand_key not in grid_totals:
            grid_totals[hand_key] = 0.0
            grid_counts[hand_key] = 0

        grid_totals[hand_key] += weight
        grid_counts[hand_key] += 1

    # Calculate averages and normalize (solver uses 0-10000 scale, we want 0-1)
    grid = {}
    for hand_key in grid_totals:
        if grid_counts[hand_key] > 0:
            avg = grid_totals[hand_key] / grid_counts[hand_key]
            normalized = avg / 10000.0  # Convert to 0-1 scale
            if normalized > 0.001:  # Only include non-zero
                grid[hand_key] = round(normalized, 3)

    return grid


def _aggregate_to_grid_with_actions(
    range_1326: list[int | float],
    strategy: list[list[float]] | None,
    action_names: list[str] | None,
    board: str = ""
) -> tuple[dict[str, dict], dict[str, list[dict]]]:
    """
    Aggregate 1326 combo weights to 13x13 grid format with action frequencies.

    Returns tuple of:
    1. Grid dict like:
        {
            "AA": {"weight": 1.0, "actions": {"Bet 1.6bb": 0.85, "Check": 0.15}},
            "AKs": {"weight": 0.95, "actions": {"Bet 1.6bb": 1.0}},
            ...
        }
    2. Combo details dict like:
        {
            "J9s": [
                {"combo": "Js9s", "weight": 0.92, "actions": {"Check": 0.95, "Bet 1.6bb": 0.05}},
                {"combo": "Jh9h", "weight": 0.90, "actions": {"Check": 0.90}},
                ...
            ]
        }
    """
    from deepsolver.hand_utils import HAND_ORDER
    from deepsolver.spot_extractor import is_combo_blocked

    RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']

    # Initialize grid with totals and counts
    grid_totals = {}  # hand_key -> total weight
    grid_counts = {}  # hand_key -> count of combos
    grid_actions = {}  # hand_key -> {action_name -> total frequency}
    combo_details = {}  # hand_key -> list of {combo, weight, actions}

    for combo_idx, weight in enumerate(range_1326):
        if combo_idx >= len(HAND_ORDER):
            break

        combo = HAND_ORDER[combo_idx]

        # Skip combos blocked by board cards
        if board and is_combo_blocked(combo, board):
            continue

        r1, s1 = combo[0], combo[1]
        r2, s2 = combo[2], combo[3]

        # Determine hand type
        if r1 == r2:
            hand_key = f"{r1}{r1}"
        elif s1 == s2:
            ranks = sorted([r1, r2], key=lambda x: RANKS.index(x))
            hand_key = f"{ranks[0]}{ranks[1]}s"
        else:
            ranks = sorted([r1, r2], key=lambda x: RANKS.index(x))
            hand_key = f"{ranks[0]}{ranks[1]}o"

        if hand_key not in grid_totals:
            grid_totals[hand_key] = 0.0
            grid_counts[hand_key] = 0
            grid_actions[hand_key] = {}
            combo_details[hand_key] = []

        grid_totals[hand_key] += weight
        grid_counts[hand_key] += 1

        # Track per-combo details
        normalized_combo_weight = weight / 10000.0
        if normalized_combo_weight > 0.001:
            combo_actions = {}
            if strategy and action_names:
                for action_idx, action_name in enumerate(action_names):
                    if action_idx < len(strategy):
                        action_freq = strategy[action_idx][combo_idx] if combo_idx < len(strategy[action_idx]) else 0
                        if action_freq > 0.001:
                            combo_actions[action_name] = round(action_freq, 3)
            combo_details[hand_key].append({
                "combo": combo,
                "weight": round(normalized_combo_weight, 3),
                "actions": combo_actions
            })

        # Aggregate action frequencies if strategy data available
        if strategy and action_names and weight > 0:
            for action_idx, action_name in enumerate(action_names):
                if action_idx < len(strategy):
                    action_freq = strategy[action_idx][combo_idx] if combo_idx < len(strategy[action_idx]) else 0
                    if action_name not in grid_actions[hand_key]:
                        grid_actions[hand_key][action_name] = 0.0
                    grid_actions[hand_key][action_name] += action_freq * weight

    # Calculate averages and normalize
    grid = {}
    for hand_key in grid_totals:
        if grid_counts[hand_key] > 0:
            avg_weight = grid_totals[hand_key] / grid_counts[hand_key]
            normalized_weight = avg_weight / 10000.0

            if normalized_weight > 0.001:
                # Normalize action frequencies
                actions = {}
                total_action_weight = grid_totals[hand_key]  # Use total weight for action normalization
                if total_action_weight > 0:
                    for action_name, action_total in grid_actions[hand_key].items():
                        # Normalize: action_total / total_weight gives weighted average frequency
                        action_freq = action_total / total_action_weight
                        if action_freq > 0.001:
                            actions[action_name] = round(action_freq, 3)

                grid[hand_key] = {
                    "weight": round(normalized_weight, 3),
                    "actions": actions
                }

    # Filter combo_details to only include hand_keys that appear in the grid
    filtered_combo_details = {k: v for k, v in combo_details.items() if k in grid and len(v) > 0}

    return grid, filtered_combo_details


# =============================================================================
# Generate
# =============================================================================


def random_board() -> str:
    """Generate a random flop."""
    ranks = "23456789TJQKA"
    suits = "cdhs"
    deck = [f"{r}{s}" for r in ranks for s in suits]
    random.shuffle(deck)
    return "".join(deck[:3])


@app.post("/generate", response_model=GenerateResponse)
def generate_spots(request: GenerateRequest):
    """Run solver and extract spots."""
    # Get board
    board = request.board if request.board else random_board()

    # Get scenario builder
    builder_fn = SCENARIO_BUILDERS.get(request.scenario)
    if not builder_fn:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown scenario: {request.scenario}. "
            f"Available: {list(SCENARIO_BUILDERS.keys())}",
        )

    # Build request
    builder = builder_fn(board)
    builder = builder.with_iterations(request.iterations)
    solver_request = builder.build()

    # Get positions from builder config
    ip_position = builder.config.ip_position
    oop_position = builder.config.oop_position

    # Run solver
    try:
        token = get_api_token()
        client = DeepsolverClient(api_token=token)
        result = client.run_and_wait(
            solver_request, timeout_seconds=180, poll_interval_seconds=5
        )
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"API error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Solver error: {e}")

    # Parse tree and extract spots
    if "tree" not in result:
        raise HTTPException(status_code=500, detail="No tree in solver response")

    # Determine street from board length
    street_names = {1: "flop", 2: "turn", 3: "river"}
    street = street_names.get(builder.config.street_id, "flop")

    # Save the sim to library (tree uploaded to GCS)
    sim_id = str(uuid.uuid4())
    sim = SolverSim(
        id=sim_id,
        board=board,
        scenario=request.scenario,
        ip_position=ip_position,
        oop_position=oop_position,
        stack_size_bb=builder.config.effective_stack_bb,
        iterations=request.iterations,
        tree_gcs_path="",  # Set by save_sim after upload
        created_at=datetime.utcnow(),
        street=street,
        tree=result["tree"],
    )
    storage.save_sim(sim)

    return GenerateResponse(
        task_id=f"gen-{board}",
        status="completed",
        spots_count=0,
        message=f"Sim saved for board {board}. Go to Sims to generate spots.",
        sim_id=sim_id,
    )


# =============================================================================
# Sims
# =============================================================================


@app.get("/sims", response_model=list[SimResponse])
def list_sims():
    """List all stored solver sims."""
    sims = storage.get_all_sims()
    return [
        SimResponse(
            id=s.id,
            board=s.board,
            scenario=s.scenario,
            ip_position=s.ip_position,
            oop_position=s.oop_position,
            stack_size_bb=s.stack_size_bb,
            iterations=s.iterations,
            street=s.street,
            created_at=s.created_at.isoformat(),
            parent_sim_id=s.parent_sim_id,
            parent_action_path=s.parent_action_path,
            pot_size_bb=s.pot_size_bb,
        )
        for s in sims
    ]


@app.get("/sims/{sim_id}", response_model=SimResponse)
def get_sim(sim_id: str):
    """Get a single sim by ID (without full tree)."""
    sim = storage.get_sim(sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Sim not found")

    return SimResponse(
        id=sim.id,
        board=sim.board,
        scenario=sim.scenario,
        ip_position=sim.ip_position,
        oop_position=sim.oop_position,
        stack_size_bb=sim.stack_size_bb,
        iterations=sim.iterations,
        street=sim.street,
        created_at=sim.created_at.isoformat(),
        parent_sim_id=sim.parent_sim_id,
        parent_action_path=sim.parent_action_path,
        pot_size_bb=sim.pot_size_bb,
    )


@app.delete("/sims/{sim_id}")
def delete_sim(sim_id: str):
    """Delete a sim by ID."""
    deleted = storage.delete_sim(sim_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Sim not found")
    return {"status": "deleted", "id": sim_id}


def _parse_action_path(path: str, ip_position: str, oop_position: str) -> str:
    """
    Parse an action path like "r:0:c:b1500000:c" into human-readable actions.
    """
    path_parts = path.split(":")[2:]  # Skip "r" and "0"
    actions = []
    current_player = 1  # OOP acts first
    last_was_bet = False

    for part in path_parts:
        player = oop_position if current_player == 1 else ip_position
        if part == "c":
            if last_was_bet:
                actions.append(f"{player} calls")
            else:
                actions.append(f"{player} checks")
            last_was_bet = False
        elif part.startswith("b"):
            amount_bb = int(part[1:]) / UNITS_PER_BB
            if last_was_bet:
                actions.append(f"{player} raises to {amount_bb:.1f}bb")
            else:
                actions.append(f"{player} bets {amount_bb:.1f}bb")
            last_was_bet = True
        elif part == "f":
            actions.append(f"{player} folds")
            last_was_bet = False
        current_player = 1 - current_player

    return ", ".join(actions) if actions else "check, check"


def _build_parent_context(sim, parent_sim) -> list[dict]:
    """
    Build street action context from parent sim chain.

    Handles:
    - Turn sim with flop parent -> returns preflop + flop context
    - River sim with turn parent -> returns preflop + flop + turn context

    Returns list of street_action dicts.
    """
    context = []

    # Preflop context (always present)
    context.append({
        "street": "preflop",
        "cards": "",
        "actions": f"{sim.ip_position} raises 2.5bb, {sim.oop_position} calls",
    })

    # Check if parent_sim itself has a parent (grandparent case for river sims)
    grandparent_sim = None
    if parent_sim.parent_sim_id:
        grandparent_sim = storage.get_sim(parent_sim.parent_sim_id, load_tree=False)

    if grandparent_sim:
        # River sim case: grandparent is flop, parent is turn
        # Flop context from grandparent
        flop_board = grandparent_sim.board  # 6 chars like "Ah7d2c"
        flop_cards = "-".join([flop_board[i:i+2] for i in range(0, len(flop_board), 2)])
        flop_actions = _parse_action_path(
            parent_sim.parent_action_path, sim.ip_position, sim.oop_position
        )
        context.append({
            "street": "flop",
            "cards": flop_cards,
            "actions": flop_actions,
        })

        # Turn context from parent
        turn_card = parent_sim.board[6:8]  # The 4th card
        turn_actions = _parse_action_path(
            sim.parent_action_path, sim.ip_position, sim.oop_position
        )
        context.append({
            "street": "turn",
            "cards": turn_card,
            "actions": turn_actions,
        })
    else:
        # Turn sim case: parent is flop
        flop_board = parent_sim.board  # 6 chars like "Ah7d2c"
        flop_cards = "-".join([flop_board[i:i+2] for i in range(0, len(flop_board), 2)])
        flop_actions = _parse_action_path(
            sim.parent_action_path, sim.ip_position, sim.oop_position
        )
        context.append({
            "street": "flop",
            "cards": flop_cards,
            "actions": flop_actions,
        })

    return context


def _build_previous_street_actions(sim) -> list[dict] | None:
    """
    Build previous street actions for a turn/river sim.

    This wrapper gets the parent sim and calls _build_parent_context.
    """
    if not sim.parent_sim_id:
        return None

    parent_sim = storage.get_sim(sim.parent_sim_id, load_tree=False)
    if not parent_sim:
        return None

    return _build_parent_context(sim, parent_sim)


def _build_preflop_action_from_sim(sim) -> dict:
    """
    Build the preflop action dict from a sim's scenario field.

    For custom preflop scenarios (e.g., "HJ_RFI_BTN_3B_HJ_Call"),
    this reconstructs the path and looks up the full description.

    For legacy SRP scenarios, uses a default based on positions.
    """
    scenario = sim.scenario or ""

    # Check for legacy SRP format
    if scenario.startswith("srp_"):
        # e.g., "srp_utg_vs_bb" -> "UTG raises 2.5bb, BB calls"
        return {
            "street": "preflop",
            "cards": "",
            "actions": f"{sim.ip_position} raises 2.5bb, {sim.oop_position} calls",
        }

    # Try to parse as custom preflop scenario
    # Format: "HJ_RFI_BTN_3B_HJ_Call" -> ["HJ_RFI", "BTN_3B", "HJ_Call"]
    try:
        # Split by position names to reconstruct the path
        path = _parse_scenario_to_path(scenario)
        if path:
            # Look up the scenario data to get full node details
            try:
                scenario_data = preflop_storage.get_scenario_data(path)
                nodes = scenario_data["nodes"]
                description = build_preflop_description(nodes)
                return {
                    "street": "preflop",
                    "cards": "",
                    "actions": description,
                }
            except (ValueError, KeyError):
                pass  # Fall through to default
    except Exception:
        pass  # Fall through to default

    # Default fallback
    return {
        "street": "preflop",
        "cards": "",
        "actions": f"{sim.ip_position} raises 2.5bb, {sim.oop_position} calls",
    }


def _parse_scenario_to_path(scenario: str) -> list[str] | None:
    """
    Parse a scenario string back into a preflop path.

    E.g., "HJ_RFI_BTN_3B_HJ_Call" -> ["HJ_RFI", "BTN_3B", "HJ_Call"]
    """
    if not scenario:
        return None

    # Known position prefixes
    positions = {"SB", "BB", "UTG", "UTG1", "UTG2", "LJ", "HJ", "CO", "BTN"}

    # Known action suffixes
    actions = {"RFI", "3B", "4B", "5B", "Call"}

    parts = scenario.split("_")
    if not parts:
        return None

    path = []
    i = 0
    while i < len(parts):
        # Look for a position
        if parts[i] in positions:
            pos = parts[i]
            # Look for the action part(s)
            if i + 1 < len(parts) and parts[i + 1] in actions:
                path.append(f"{pos}_{parts[i + 1]}")
                i += 2
            else:
                i += 1
        else:
            i += 1

    return path if path else None


@app.post("/sims/{sim_id}/random-spot", response_model=RandomSpotResponse)
def generate_random_spot(sim_id: str, request: RandomSpotRequest | None = None):
    """
    Extract one random spot from a stored sim.

    Extracts spots from the SAME street as the sim:
    - Flop sim -> flop spots
    - Turn sim -> turn spots
    - River sim -> river spots

    Optional filters:
    - hero_position: "IP" or "OOP" to only get spots for that player
    - hero_combo: specific hand like "AhKs" to use
    """
    sim = storage.get_sim(sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Sim not found")

    # Check if this is a chained sim with parent context
    parent_sim = None
    parent_context = []
    if sim.parent_sim_id:
        parent_sim = storage.get_sim(sim.parent_sim_id)
        if parent_sim:
            parent_context = _build_parent_context(sim, parent_sim)

    # Parse tree
    tree = parse_tree(sim.tree)

    # Extract optional filters from request
    hero_position = request.hero_position if request else None
    hero_combo = request.hero_combo if request else None

    # Extract a random spot from the same street as the sim
    spot = extract_random_spot_same_street(
        tree=tree,
        board=sim.board,
        ip_position=sim.ip_position,
        oop_position=sim.oop_position,
        task_id=f"sim-{sim.id}",
        stack_size_bb=sim.stack_size_bb,
        min_frequency=0.70,
        max_second_best=0.25,
        max_attempts=100,
        hero_position=hero_position,
        hero_combo=hero_combo,
    )

    if spot is None:
        raise HTTPException(
            status_code=404,
            detail=f"No interesting {sim.street} spots found in this sim"
        )

    # Fix the preflop action in street_actions
    if parent_context:
        # For turn/river sims with parent context
        existing_actions = spot.street_actions

        # Build new actions: parent context + current street actions (skip generic preflop)
        new_actions = parent_context.copy()  # preflop + flop from parent

        for action in existing_actions:
            if action["street"] not in ("preflop",):
                new_actions.append(action)

        spot.street_actions = new_actions
    else:
        # For flop sims, fix the preflop action using the sim's scenario
        preflop_action = _build_preflop_action_from_sim(sim)
        new_actions = [preflop_action]

        for action in spot.street_actions:
            if action["street"] != "preflop":
                new_actions.append(action)

        spot.street_actions = new_actions

    # Save to spot_candidates
    storage.save_candidate(spot)

    return RandomSpotResponse(
        spot_id=spot.id,
        message=f"Generated {sim.street} spot: {spot.hero_combo} on {spot.board}",
    )


@app.post("/sims/{sim_id}/create-spot", response_model=RandomSpotResponse)
def create_spot_at_path_endpoint(sim_id: str, request: CreateSpotAtPathRequest):
    """
    Create a spot at a specific tree path with a specific combo.

    This allows browsing the tree and creating spots at any decision point,
    regardless of whether it meets the "interesting spot" criteria.
    """
    from deepsolver.spot_extractor import create_spot_at_path

    sim = storage.get_sim(sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Sim not found")

    # Parse tree
    tree = parse_tree(sim.tree)

    # Build previous street actions
    # For turn/river sims: include flop/turn actions from parent
    # For flop sims: include correct preflop action from scenario
    if sim.parent_sim_id and sim.parent_action_path:
        previous_street_actions = _build_previous_street_actions(sim)
    else:
        # Flop sim - just need the preflop action
        previous_street_actions = [_build_preflop_action_from_sim(sim)]

    # Create spot at the specified path
    spot = create_spot_at_path(
        tree=tree,
        path=request.path,
        combo=request.combo,
        board=sim.board,
        ip_position=sim.ip_position,
        oop_position=sim.oop_position,
        task_id=f"sim-{sim.id}",
        stack_size_bb=sim.stack_size_bb,
        previous_street_actions=previous_street_actions,
    )

    if spot is None:
        raise HTTPException(
            status_code=400,
            detail="Could not create spot at this path with this combo. The combo may not be in range or the path may be invalid."
        )

    # Save the spot
    storage.save_candidate(spot)

    return RandomSpotResponse(
        spot_id=spot.id,
        message=f"Created spot: {spot.hero_combo} at {request.path}",
    )


# =============================================================================
# Turn Builder (chained sims)
# =============================================================================


@app.get("/sims/{sim_id}/tree/actions", response_model=TreeActionsResponse)
def get_tree_actions(sim_id: str, path: str = "r:0"):
    """
    Get available actions at a tree node.

    Used by TurnBuilder to show action buttons at each decision point.
    """
    sim = storage.get_sim(sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Sim not found")

    tree = parse_tree(sim.tree)
    result = get_actions_at_node(tree, path)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    # Determine position name from player_id
    if result["player_id"] == 0:
        position = sim.ip_position
    elif result["player_id"] == 1:
        position = sim.oop_position
    else:
        position = ""

    return TreeActionsResponse(
        path=result["path"],
        player_id=result["player_id"],
        position=position,
        is_terminal=result["is_terminal"],
        actions=[ActionOption(label=a["label"], path=a["path"]) for a in result["actions"]],
    )


@app.get("/sims/{sim_id}/tree/ranges", response_model=TreeRangesResponse)
def get_tree_ranges(sim_id: str, path: str):
    """
    Get ranges at a tree node.

    Used by TurnBuilder to show combo counts after selecting actions.
    Also returns full 1326-element range arrays for range grid display.
    """
    sim = storage.get_sim(sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Sim not found")

    tree = parse_tree(sim.tree)
    result = get_ranges_at_node(tree, path)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return TreeRangesResponse(
        path=result["path"],
        is_terminal=result["is_terminal"],
        pot_size_bb=result["pot_size"] / UNITS_PER_BB,
        ip_combos=result["ip_combos"],
        oop_combos=result["oop_combos"],
        ip_range=result.get("ip_range"),
        oop_range=result.get("oop_range"),
        strategy=result.get("strategy"),
        action_names=result.get("action_names"),
    )


@app.get("/hand-order")
def get_hand_order():
    """
    Get the canonical order of 1326 poker hand combos.

    Used by frontend to convert range array indices to combo strings
    for displaying the 13x13 range grid.
    """
    from deepsolver.hand_utils import HAND_ORDER
    return {"hands": HAND_ORDER}


@app.post("/sims/{sim_id}/create-turn-sim", response_model=CreateTurnSimResponse)
def create_turn_sim(sim_id: str, request: CreateTurnSimRequest):
    """
    Create a turn sim from a flop sim with filtered ranges.

    1. Extracts ranges from the specified flop action path
    2. Deals a turn card (random if not specified)
    3. Runs a turn sim with the filtered ranges
    4. Saves the new sim with parent link
    """
    # Get parent flop sim
    parent_sim = storage.get_sim(sim_id)
    if not parent_sim:
        raise HTTPException(status_code=404, detail="Sim not found")

    if parent_sim.street != "flop":
        raise HTTPException(
            status_code=400,
            detail=f"Can only create turn sim from flop sim, got {parent_sim.street}"
        )

    # Parse tree and extract ranges at the action path
    tree = parse_tree(parent_sim.tree)
    ranges_result = get_ranges_at_node(tree, request.flop_action_path)

    if "error" in ranges_result:
        raise HTTPException(status_code=400, detail=ranges_result["error"])

    if not ranges_result["is_terminal"]:
        raise HTTPException(
            status_code=400,
            detail="Action path must end at a terminal node (flop action closed)"
        )

    ip_range = ranges_result["ip_range"]
    oop_range = ranges_result["oop_range"]
    pot_size_bb = ranges_result["pot_size"] / UNITS_PER_BB

    # Deal turn card
    if request.turn_card:
        turn_card = request.turn_card
        # Validate card
        if len(turn_card) != 2:
            raise HTTPException(status_code=400, detail="Turn card must be 2 characters (e.g., '8h')")
        if turn_card in [parent_sim.board[i:i+2] for i in range(0, len(parent_sim.board), 2)]:
            raise HTTPException(status_code=400, detail=f"Turn card {turn_card} is already on the board")
    else:
        turn_card = deal_random_card(parent_sim.board, ip_range, oop_range)

    new_board = parent_sim.board + turn_card

    # Calculate remaining stack (original stack minus pot contributions)
    # For SRP, each player put in ~2.5bb preflop. Flop actions add to pot.
    # pot_size_bb now includes flop action. Each player contributed half of pot increase.
    original_pot = 5.0  # SRP starting pot
    pot_increase = pot_size_bb - original_pot
    # Approximate: each player contributed half of pot increase from flop action
    stack_reduction = 2.5 + (pot_increase / 2)  # preflop + flop contribution
    stack_size_bb = parent_sim.stack_size_bb - stack_reduction

    # Build turn sim request
    config = SpotConfig(
        board=new_board,
        ip_range=ip_range,
        oop_range=oop_range,
        pot_size_bb=pot_size_bb,
        effective_stack_bb=stack_size_bb,
        street_id=2,  # Turn
        ip_position=parent_sim.ip_position,
        oop_position=parent_sim.oop_position,
    )
    builder = RequestBuilder(config)
    builder.with_iterations(request.iterations)
    solver_request = builder.build()

    # Run solver
    try:
        token = get_api_token()
        client = DeepsolverClient(api_token=token)
        print(f"Running turn sim for {new_board} (from {parent_sim.board})...")
        result = client.run_and_wait(
            solver_request, timeout_seconds=180, poll_interval_seconds=5
        )
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"API error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Solver error: {e}")

    if "tree" not in result:
        raise HTTPException(status_code=500, detail="No tree in solver response")

    # Save new turn sim
    turn_sim_id = str(uuid.uuid4())
    turn_sim = SolverSim(
        id=turn_sim_id,
        board=new_board,
        scenario=parent_sim.scenario,
        ip_position=parent_sim.ip_position,
        oop_position=parent_sim.oop_position,
        stack_size_bb=stack_size_bb,
        iterations=request.iterations,
        tree_gcs_path="",  # Set by save_sim
        created_at=datetime.utcnow(),
        street="turn",
        tree=result["tree"],
        parent_sim_id=parent_sim.id,
        parent_action_path=request.flop_action_path,
        pot_size_bb=pot_size_bb,
    )
    storage.save_sim(turn_sim)

    return CreateTurnSimResponse(
        sim_id=turn_sim_id,
        board=new_board,
        turn_card=turn_card,
        ip_combos=ranges_result["ip_combos"],
        oop_combos=ranges_result["oop_combos"],
        pot_size_bb=pot_size_bb,
        stack_size_bb=stack_size_bb,
    )


@app.post("/sims/{sim_id}/create-river-sim", response_model=CreateRiverSimResponse)
def create_river_sim(sim_id: str, request: CreateRiverSimRequest):
    """
    Create a river sim from a turn sim with filtered ranges.

    1. Extracts ranges from the specified turn action path
    2. Deals a river card (random if not specified)
    3. Runs a river sim with the filtered ranges
    4. Saves the new sim with parent link
    """
    # Get parent turn sim
    parent_sim = storage.get_sim(sim_id)
    if not parent_sim:
        raise HTTPException(status_code=404, detail="Sim not found")

    if parent_sim.street != "turn":
        raise HTTPException(
            status_code=400,
            detail=f"Can only create river sim from turn sim, got {parent_sim.street}"
        )

    # Parse tree and extract ranges at the action path
    tree = parse_tree(parent_sim.tree)
    ranges_result = get_ranges_at_node(tree, request.turn_action_path)

    if "error" in ranges_result:
        raise HTTPException(status_code=400, detail=ranges_result["error"])

    if not ranges_result["is_terminal"]:
        raise HTTPException(
            status_code=400,
            detail="Action path must end at a terminal node (turn action closed)"
        )

    ip_range = ranges_result["ip_range"]
    oop_range = ranges_result["oop_range"]
    pot_size_bb = ranges_result["pot_size"] / UNITS_PER_BB

    # Deal river card
    if request.river_card:
        river_card = request.river_card
        # Validate card
        if len(river_card) != 2:
            raise HTTPException(status_code=400, detail="River card must be 2 characters (e.g., '8h')")
        if river_card in [parent_sim.board[i:i+2] for i in range(0, len(parent_sim.board), 2)]:
            raise HTTPException(status_code=400, detail=f"River card {river_card} is already on the board")
    else:
        river_card = deal_random_card(parent_sim.board, ip_range, oop_range)

    new_board = parent_sim.board + river_card

    # Calculate remaining stack (parent stack minus turn betting contribution)
    # parent_sim.pot_size_bb is the pot at the start of the turn
    # pot_size_bb is the pot after turn action
    turn_pot_increase = pot_size_bb - (parent_sim.pot_size_bb or pot_size_bb)
    # Each player contributed approximately half of the pot increase
    stack_reduction = turn_pot_increase / 2
    stack_size_bb = parent_sim.stack_size_bb - stack_reduction

    # Build river sim request
    config = SpotConfig(
        board=new_board,
        ip_range=ip_range,
        oop_range=oop_range,
        pot_size_bb=pot_size_bb,
        effective_stack_bb=stack_size_bb,
        street_id=3,  # River
        ip_position=parent_sim.ip_position,
        oop_position=parent_sim.oop_position,
    )
    builder = RequestBuilder(config)
    builder.with_iterations(request.iterations)
    solver_request = builder.build()

    # Run solver
    try:
        token = get_api_token()
        client = DeepsolverClient(api_token=token)
        print(f"Running river sim for {new_board} (from {parent_sim.board})...")
        result = client.run_and_wait(
            solver_request, timeout_seconds=180, poll_interval_seconds=5
        )
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"API error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Solver error: {e}")

    if "tree" not in result:
        raise HTTPException(status_code=500, detail="No tree in solver response")

    # Save new river sim
    river_sim_id = str(uuid.uuid4())
    river_sim = SolverSim(
        id=river_sim_id,
        board=new_board,
        scenario=parent_sim.scenario,
        ip_position=parent_sim.ip_position,
        oop_position=parent_sim.oop_position,
        stack_size_bb=stack_size_bb,
        iterations=request.iterations,
        tree_gcs_path="",  # Set by save_sim
        created_at=datetime.utcnow(),
        street="river",
        tree=result["tree"],
        parent_sim_id=parent_sim.id,
        parent_action_path=request.turn_action_path,
        pot_size_bb=pot_size_bb,
    )
    storage.save_sim(river_sim)

    return CreateRiverSimResponse(
        sim_id=river_sim_id,
        board=new_board,
        river_card=river_card,
        ip_combos=ranges_result["ip_combos"],
        oop_combos=ranges_result["oop_combos"],
        pot_size_bb=pot_size_bb,
        stack_size_bb=stack_size_bb,
    )


# =============================================================================
# Workflow Dashboard
# =============================================================================


@app.get("/workflow/status", response_model=WorkflowStatusResponse)
def get_workflow_status(days: int = 14):
    """
    Get puzzle counts for the next N days.

    Returns a list of dates with their puzzle counts (target: 10 per day).
    """
    from datetime import timedelta

    # Get existing puzzle counts
    counts = storage.get_puzzle_counts_by_date()

    # Generate dates for the next N days
    today = datetime.utcnow().date()
    dates = []

    for i in range(days):
        date = today + timedelta(days=i)
        date_str = date.isoformat()
        count = counts.get(date_str, 0)
        dates.append(DatePuzzleCount(date=date_str, count=count, target=10))

    return WorkflowStatusResponse(dates=dates)


@app.get("/workflow/puzzles/{date}", response_model=list[FullScheduledPuzzleResponse])
def get_puzzles_for_date(date: str):
    """
    Get all puzzles scheduled for a specific date with full details.

    Args:
        date: Date in YYYY-MM-DD format
    """
    puzzles = storage.get_puzzles_by_date(date)

    return [
        FullScheduledPuzzleResponse(
            id=p.id,
            scheduled_date=p.scheduled_date,
            question_text=p.question_text,
            structure=p.structure,
            effective_stacks=p.effective_stacks,
            hero=p.hero,
            action=p.action,
            pot_size_at_decision=p.pot_size_at_decision,
            answer_options=p.answer_options,
            correct_answers=p.correct_answers,
            explanations=p.explanations,
            ev_by_action=p.ev_by_action,
            action_frequencies=p.action_frequencies,
            difficulty=p.difficulty,
            tags=p.tags,
            order=p.order,
            flavor_text=p.flavor_text,
            spot_type=p.spot_type,
            created_at=p.created_at.isoformat(),
        )
        for p in puzzles
    ]


@app.put("/workflow/puzzles/{puzzle_id}", response_model=FullScheduledPuzzleResponse)
def update_puzzle(puzzle_id: str, request: UpdatePuzzleRequest):
    """
    Update a scheduled puzzle.

    Args:
        puzzle_id: UUID of the puzzle to update
        request: Fields to update (only non-null fields are updated)
    """
    # Get existing puzzle
    puzzle = storage.get_scheduled_puzzle(puzzle_id)
    if not puzzle:
        raise HTTPException(status_code=404, detail="Puzzle not found")

    # Build update dict from non-null fields
    updates = {}
    if request.question_text is not None:
        updates["QuestionText"] = request.question_text
    if request.answer_options is not None:
        updates["AnswerOptions"] = request.answer_options
    if request.correct_answers is not None:
        updates["CorrectAnswers"] = request.correct_answers
    if request.explanations is not None:
        updates["Explanations"] = request.explanations
    if request.difficulty is not None:
        updates["Difficulty"] = request.difficulty
    if request.tags is not None:
        updates["Tags"] = request.tags
    if request.scheduled_date is not None:
        updates["scheduled_date"] = request.scheduled_date
    if request.order is not None:
        updates["Order"] = request.order
    if request.flavor_text is not None:
        updates["FlavorText"] = request.flavor_text

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Update in Firestore
    storage.update_scheduled_puzzle(puzzle_id, updates)

    # Fetch and return updated puzzle
    updated = storage.get_scheduled_puzzle(puzzle_id)
    return FullScheduledPuzzleResponse(
        id=updated.id,
        scheduled_date=updated.scheduled_date,
        question_text=updated.question_text,
        structure=updated.structure,
        effective_stacks=updated.effective_stacks,
        hero=updated.hero,
        action=updated.action,
        pot_size_at_decision=updated.pot_size_at_decision,
        answer_options=updated.answer_options,
        correct_answers=updated.correct_answers,
        explanations=updated.explanations,
        ev_by_action=updated.ev_by_action,
        action_frequencies=updated.action_frequencies,
        difficulty=updated.difficulty,
        tags=updated.tags,
        order=updated.order,
        flavor_text=updated.flavor_text,
        spot_type=updated.spot_type,
        created_at=updated.created_at.isoformat(),
    )


@app.get("/workflow/puzzles/by-id/{puzzle_id}", response_model=FullScheduledPuzzleResponse)
def get_puzzle_by_id(puzzle_id: str):
    """Get a single puzzle by ID."""
    puzzle = storage.get_scheduled_puzzle(puzzle_id)
    if not puzzle:
        raise HTTPException(status_code=404, detail="Puzzle not found")
    return FullScheduledPuzzleResponse(
        id=puzzle.id,
        scheduled_date=puzzle.scheduled_date,
        question_text=puzzle.question_text,
        structure=puzzle.structure,
        effective_stacks=puzzle.effective_stacks,
        hero=puzzle.hero,
        action=puzzle.action,
        pot_size_at_decision=puzzle.pot_size_at_decision,
        answer_options=puzzle.answer_options,
        correct_answers=puzzle.correct_answers,
        explanations=puzzle.explanations,
        ev_by_action=puzzle.ev_by_action,
        action_frequencies=puzzle.action_frequencies,
        difficulty=puzzle.difficulty,
        tags=puzzle.tags,
        order=puzzle.order,
        flavor_text=puzzle.flavor_text,
        spot_type=puzzle.spot_type,
        created_at=puzzle.created_at.isoformat(),
    )


@app.post("/workflow/puzzles/{date}/backfill-order")
def backfill_puzzle_order(date: str):
    """Backfill the Order field on puzzles for a date using their day plan slot order."""
    plan = storage.get_day_plan_by_date(date)
    if not plan:
        raise HTTPException(status_code=404, detail="No day plan for this date")

    updated = 0
    idx = 1
    for config in plan.configs:
        for slot in config.slots:
            if slot.puzzle_id:
                storage.update_scheduled_puzzle(slot.puzzle_id, {"Order": idx})
                updated += 1
            idx += 1

    return {"updated": updated}


@app.post("/workflow/puzzles/{date}/generate-flavor-text")
def generate_flavor_text_for_date(date: str):
    """
    Generate AI flavor text blurbs for all puzzles on a given date.

    Uses Claude to produce a short, punchy one-liner for each puzzle based on
    its street, position, difficulty, and action context.
    """
    import anthropic

    puzzles = storage.get_puzzles_by_date(date)
    if not puzzles:
        raise HTTPException(status_code=404, detail="No puzzles for this date")

    # Build a single prompt with all puzzles for coherent, non-repetitive blurbs
    puzzle_descriptions = []
    for i, p in enumerate(puzzles):
        street = next((t for t in p.tags if t in ("preflop", "flop", "turn", "river")), "unknown")
        correct = ", ".join(p.correct_answers)
        options = ", ".join(p.answer_options)
        puzzle_descriptions.append(
            f"Puzzle {i+1}: Street={street}, Hero={p.hero}, Difficulty={p.difficulty}/10, "
            f"Options=[{options}], Correct=[{correct}], Question=\"{p.question_text}\""
        )

    puzzles_block = "\n".join(puzzle_descriptions)

    prompt = f"""You are writing short flavor text blurbs for a poker training app called Stack.
Each blurb appears as a message bubble from the app before the user sees the puzzle.

Rules:
- Each blurb must be 4-12 words. Punchy, confident, poker-savvy tone.
- No emojis. No questions. No exclamation marks.
- NEVER give away or hint at the correct answer. The user hasn't seen the puzzle yet.
- Reference the specific situation when possible (street, position, action type).
- All {len(puzzles)} blurbs must be unique — no repeated ideas or phrasing.
- Vary the style: some witty, some strategic, some motivational, some matter-of-fact.

Here are the puzzles:
{puzzles_block}

Return exactly {len(puzzles)} lines, one blurb per line, in order. No numbering, no quotes, just the text."""

    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    lines = [line.strip() for line in message.content[0].text.strip().split("\n") if line.strip()]

    # Pad or truncate to match puzzle count
    while len(lines) < len(puzzles):
        lines.append("Trust the process.")
    lines = lines[:len(puzzles)]

    # Write each flavor text to Firestore
    results = []
    for puzzle, flavor in zip(puzzles, lines):
        storage.update_scheduled_puzzle(puzzle.id, {"FlavorText": flavor})
        results.append({"puzzle_id": puzzle.id, "flavor_text": flavor})

    return {"date": date, "count": len(results), "results": results}


@app.get("/workflow/puzzles/{puzzle_id}/tree", response_model=PuzzleTreeDataResponse)
def get_puzzle_tree_data(puzzle_id: str):
    """
    Get tree navigation data for a puzzle.

    Returns sim_id and tree_path so the frontend can use TreeBrowser.
    """
    # Get puzzle from storage
    puzzle = storage.get_scheduled_puzzle(puzzle_id)
    if not puzzle:
        raise HTTPException(status_code=404, detail="Puzzle not found")

    # Extract board from action data
    board = _extract_board_from_action(puzzle.action)
    if not board:
        return PuzzleTreeDataResponse(
            sim_id=None,
            tree_path=None,
            board=None,
            ip_position=None,
            oop_position=None,
            has_tree=False,
        )

    # Extract villain position from action
    villain = _extract_villain_from_action(puzzle.action, puzzle.hero)

    # Find matching sim
    sim = _find_sim_by_board(board, puzzle.hero, villain)
    if not sim:
        return PuzzleTreeDataResponse(
            sim_id=None,
            tree_path=None,
            board=board,
            ip_position=None,
            oop_position=None,
            has_tree=False,
        )

    # Reconstruct tree path from action sequence
    tree_path = _reconstruct_tree_path(puzzle.action, sim)

    return PuzzleTreeDataResponse(
        sim_id=sim.id,
        tree_path=tree_path,
        board=board,
        ip_position=sim.ip_position,
        oop_position=sim.oop_position,
        has_tree=True,
    )


@app.delete("/workflow/puzzles/{puzzle_id}")
def delete_puzzle(puzzle_id: str):
    """
    Delete a scheduled puzzle.

    Args:
        puzzle_id: UUID of the puzzle to delete
    """
    puzzle = storage.get_scheduled_puzzle(puzzle_id)
    if not puzzle:
        raise HTTPException(status_code=404, detail="Puzzle not found")

    storage.delete_scheduled_puzzle(puzzle_id)
    return {"status": "deleted", "id": puzzle_id}


# =============================================================================
# Preflop Builder
# =============================================================================


@app.get("/preflop/positions")
def get_rfi_positions():
    """Get available RFI (raise-first-in) positions."""
    return preflop_storage.get_rfi_positions()


@app.get("/preflop/{position}/rfi", response_model=PreflopNodeResponse)
def get_rfi_node(position: str):
    """
    Get RFI data for a position (the opening raise).

    Returns the node data including range combos and available responses.
    """
    node = preflop_storage.get_rfi_node(position)
    if not node:
        raise HTTPException(status_code=404, detail=f"No RFI data for position: {position}")

    # Count combos in range
    range_dict = node.get("range", {})
    combo_count = sum(1 for freq in range_dict.values() if freq > 0)

    return PreflopNodeResponse(
        name=node["name"],
        action=node["action"],
        size=node.get("size"),
        range_combos=combo_count,
        children=node.get("children", []),
    )


@app.get("/preflop/node", response_model=PreflopNodeResponse)
def get_preflop_node(path: str):
    """
    Get node data at a preflop tree path.

    Query param path is comma-separated, e.g.: ?path=BTN_RFI,BB_3B,BTN_Call
    """
    path_list = [p.strip() for p in path.split(",") if p.strip()]
    if not path_list:
        raise HTTPException(status_code=400, detail="Path cannot be empty")

    node = preflop_storage.get_node_at_path(path_list)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node not found at path: {path}")

    # Count combos in range
    range_dict = node.get("range", {})
    combo_count = sum(1 for freq in range_dict.values() if freq > 0)

    return PreflopNodeResponse(
        name=node["name"],
        action=node["action"],
        size=node.get("size"),
        range_combos=combo_count,
        children=node.get("children", []),
    )


@app.get("/preflop/children", response_model=list[PreflopChildNode])
def get_preflop_children(path: str):
    """
    Get available child actions at a preflop tree path.

    Query param path is comma-separated, e.g.: ?path=BTN_RFI
    Returns list of available next actions with their names and sizes.
    """
    path_list = [p.strip() for p in path.split(",") if p.strip()]
    if not path_list:
        raise HTTPException(status_code=400, detail="Path cannot be empty")

    children = preflop_storage.get_children_at_path(path_list)

    return [
        PreflopChildNode(
            name=c["name"],
            action=c["action"],
            size=c.get("size"),
        )
        for c in children
    ]


@app.get("/preflop/scenario", response_model=PreflopScenarioSummary)
def get_preflop_scenario(path: str):
    """
    Get complete scenario summary for a preflop path.

    This is called when the user has selected all actions and wants to see
    the final ranges and pot/stack sizes before generating a flop sim.

    Query param path is comma-separated, e.g.: ?path=BTN_RFI,BB_3B,BTN_Call
    """
    path_list = [p.strip() for p in path.split(",") if p.strip()]
    if not path_list:
        raise HTTPException(status_code=400, detail="Path cannot be empty")

    try:
        scenario_data = preflop_storage.get_scenario_data(path_list)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    nodes = scenario_data["nodes"]
    ip_range = scenario_data["ip_range"]
    oop_range = scenario_data["oop_range"]

    # Calculate pot and stacks
    pot, stacks = calculate_pot_and_stacks(nodes)

    # Count combos
    ip_combos = sum(1 for freq in ip_range.values() if freq > 0)
    oop_combos = sum(1 for freq in oop_range.values() if freq > 0)

    # Build description
    description = build_preflop_description(nodes)

    return PreflopScenarioSummary(
        ip_position=scenario_data["ip_position"],
        oop_position=scenario_data["oop_position"],
        ip_combos=ip_combos,
        oop_combos=oop_combos,
        pot_size_bb=pot,
        effective_stack_bb=stacks,
        preflop_description=description,
        path=path_list,
    )


@app.post("/preflop/create-sim", response_model=GenerateResponse)
def create_sim_from_preflop(request: PreflopSimRequest):
    """
    Create a flop sim from a preflop scenario.

    Uses the ranges from the specified preflop path and runs a solver.
    """
    if not request.path:
        raise HTTPException(status_code=400, detail="Path cannot be empty")

    # Get scenario data
    try:
        scenario_data = preflop_storage.get_scenario_data(request.path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    nodes = scenario_data["nodes"]
    ip_range_dict = scenario_data["ip_range"]
    oop_range_dict = scenario_data["oop_range"]
    ip_pos = scenario_data["ip_position"]
    oop_pos = scenario_data["oop_position"]

    # Calculate pot and stacks
    pot, stacks = calculate_pot_and_stacks(nodes)

    # Get board (random if not provided)
    board = request.board if request.board else random_board()

    # Validate board length
    if len(board) != 6:
        raise HTTPException(status_code=400, detail="Board must be 6 characters (3 cards)")

    # Convert ranges to solver format (1326 weight arrays)
    ip_range = firestore_range_to_weights(ip_range_dict)
    oop_range = firestore_range_to_weights(oop_range_dict)

    # Build scenario name from path
    scenario_name = "_".join(request.path)

    # Build solver request
    config = SpotConfig(
        board=board,
        ip_range=ip_range,
        oop_range=oop_range,
        pot_size_bb=pot,
        effective_stack_bb=stacks,
        street_id=1,  # Flop
        ip_position=ip_pos,
        oop_position=oop_pos,
    )
    builder = RequestBuilder(config)
    builder.with_iterations(request.iterations)
    solver_request = builder.build()

    # Run solver
    try:
        token = get_api_token()
        client = DeepsolverClient(api_token=token)
        print(f"Running preflop scenario sim: {scenario_name} on {board}...")
        print(f"  IP: {ip_pos} ({sum(1 for w in ip_range if w > 0)} combos)")
        print(f"  OOP: {oop_pos} ({sum(1 for w in oop_range if w > 0)} combos)")
        print(f"  Pot: {pot}bb, Stacks: {stacks}bb")
        result = client.run_and_wait(
            solver_request, timeout_seconds=180, poll_interval_seconds=5
        )
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"API error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Solver error: {e}")

    if "tree" not in result:
        raise HTTPException(status_code=500, detail="No tree in solver response")

    # Save the sim
    sim_id = str(uuid.uuid4())
    sim = SolverSim(
        id=sim_id,
        board=board,
        scenario=scenario_name,
        ip_position=ip_pos,
        oop_position=oop_pos,
        stack_size_bb=stacks,
        iterations=request.iterations,
        tree_gcs_path="",  # Set by save_sim
        created_at=datetime.utcnow(),
        street="flop",
        tree=result["tree"],
        pot_size_bb=pot,
    )
    storage.save_sim(sim)

    return GenerateResponse(
        task_id=f"preflop-{board}",
        status="completed",
        spots_count=0,
        message=f"Sim saved: {build_preflop_description(nodes)} on {board}. Go to Sims to generate spots.",
        sim_id=sim_id,
    )


# =============================================================================
# Day Plans
# =============================================================================


def _slot_to_response(slot: PuzzleSlot) -> PuzzleSlotResponse:
    """Convert PuzzleSlot to response model."""
    return PuzzleSlotResponse(
        id=slot.id,
        street=slot.street,
        sim_id=slot.sim_id,
        puzzle_id=slot.puzzle_id,
        parent_slot_id=slot.parent_slot_id,
        action_path=slot.action_path,
        board=slot.board,
        planned_hero_hand=slot.planned_hero_hand,
        status=slot.status,
        tree_path=slot.tree_path,
        top_combos=slot.top_combos,
        line=slot.line,
        decision_idx=slot.decision_idx,
    )


def _config_to_response(config: PreflopConfig) -> PreflopConfigResponse:
    """Convert PreflopConfig to response model."""
    return PreflopConfigResponse(
        id=config.id,
        preflop_path=config.preflop_path,
        ip_position=config.ip_position,
        oop_position=config.oop_position,
        description=config.description,
        slots=[_slot_to_response(s) for s in config.slots],
    )


def _plan_to_response(plan: DayPlan) -> DayPlanResponse:
    """Convert DayPlan to response model."""
    return DayPlanResponse(
        id=plan.id,
        scheduled_date=plan.scheduled_date,
        configs=[_config_to_response(c) for c in plan.configs],
        status=plan.status,
        created_at=plan.created_at.isoformat(),
    )


def _create_slots_for_config(config_id: str) -> list[PuzzleSlot]:
    """
    Create the 5 puzzle slots for a preflop config.

    Structure:
    - Flop 1 (index 0)
      - Turn 1 (index 1) - stems from Flop 1
    - Flop 2 (index 2)
      - Turn 2 (index 3) - stems from Flop 2
        - River (index 4) - stems from Turn 2
    """
    flop1_id = str(uuid.uuid4())
    flop2_id = str(uuid.uuid4())
    turn1_id = str(uuid.uuid4())
    turn2_id = str(uuid.uuid4())
    river_id = str(uuid.uuid4())

    return [
        PuzzleSlot(id=flop1_id, street="flop"),
        PuzzleSlot(id=turn1_id, street="turn", parent_slot_id=flop1_id),
        PuzzleSlot(id=flop2_id, street="flop"),
        PuzzleSlot(id=turn2_id, street="turn", parent_slot_id=flop2_id),
        PuzzleSlot(id=river_id, street="river", parent_slot_id=turn2_id),
    ]


@app.post("/day-plans", response_model=DayPlanResponse)
def create_day_plan(request: CreateDayPlanRequest):
    """
    Create a new day plan for a specific date.

    Returns existing plan if one already exists for that date.
    """
    # Check if plan already exists for this date
    existing = storage.get_day_plan_by_date(request.scheduled_date)
    if existing:
        return _plan_to_response(existing)

    # Create new plan
    plan = DayPlan(
        id=str(uuid.uuid4()),
        scheduled_date=request.scheduled_date,
        configs=[],
        status="draft",
        created_at=datetime.utcnow(),
    )
    storage.save_day_plan(plan)
    return _plan_to_response(plan)


@app.get("/day-plans/{date}", response_model=DayPlanResponse)
def get_day_plan_by_date(date: str):
    """
    Get day plan for a specific date.

    Creates a new plan if none exists.
    """
    plan = storage.get_day_plan_by_date(date)
    if not plan:
        # Create new plan
        plan = DayPlan(
            id=str(uuid.uuid4()),
            scheduled_date=date,
            configs=[],
            status="draft",
            created_at=datetime.utcnow(),
        )
        storage.save_day_plan(plan)
    else:
        # Auto-link: find slots that have a sim but no puzzle, and check if
        # a puzzle for this date was created with a matching board
        _auto_link_puzzles(plan)

    return _plan_to_response(plan)


def _auto_link_puzzles(plan: DayPlan):
    """Link orphaned puzzles to matching day plan slots."""
    # Collect slots that need linking (sim_ready with no puzzle_id)
    unlinked_slots = []
    for config in plan.configs:
        for slot in config.slots:
            if slot.status == "sim_ready" and slot.board and not slot.puzzle_id:
                unlinked_slots.append(slot)

    if not unlinked_slots:
        return

    # Get all puzzles for this date
    puzzles = storage.get_puzzles_by_date(plan.scheduled_date)
    if not puzzles:
        return

    # Collect already-linked puzzle IDs
    linked_ids = set()
    for config in plan.configs:
        for slot in config.slots:
            if slot.puzzle_id:
                linked_ids.add(slot.puzzle_id)

    # Match puzzles to slots by board
    changed = False
    for slot in unlinked_slots:
        slot_board = slot.board.replace(" ", "")
        for puzzle in puzzles:
            if puzzle.id in linked_ids:
                continue
            puzzle_board = _extract_board_from_action(puzzle.action or {})
            if not puzzle_board:
                continue
            puzzle_board = puzzle_board.replace(" ", "")

            if slot_board == puzzle_board:
                slot.puzzle_id = puzzle.id
                slot.status = "complete"
                linked_ids.add(puzzle.id)
                changed = True
                break

    if changed:
        storage.save_day_plan(plan)


@app.put("/day-plans/{plan_id}/configs/{config_idx}", response_model=DayPlanResponse)
def set_preflop_config(plan_id: str, config_idx: int, request: SetPreflopConfigRequest):
    """
    Set a preflop config on a day plan.

    config_idx is 0 or 1 (for the two configs per day).
    """
    plan = storage.get_day_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Day plan not found")

    if config_idx not in (0, 1):
        raise HTTPException(status_code=400, detail="config_idx must be 0 or 1")

    # Get scenario summary from preflop path
    try:
        scenario_data = preflop_storage.get_scenario_data(request.preflop_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    nodes = scenario_data["nodes"]
    description = build_preflop_description(nodes)
    ip_pos = scenario_data["ip_position"]
    oop_pos = scenario_data["oop_position"]

    # Create new config with slots
    config_id = str(uuid.uuid4())
    new_config = PreflopConfig(
        id=config_id,
        preflop_path=request.preflop_path,
        ip_position=ip_pos,
        oop_position=oop_pos,
        description=description,
        slots=_create_slots_for_config(config_id),
    )

    # Ensure configs list has enough slots
    while len(plan.configs) <= config_idx:
        plan.configs.append(None)

    plan.configs[config_idx] = new_config

    # Filter out None values and update status
    plan.configs = [c for c in plan.configs if c is not None]
    if len(plan.configs) == 2:
        plan.status = "in_progress"

    # Save updated plan
    storage.save_day_plan(plan)
    return _plan_to_response(plan)


@app.delete("/day-plans/{plan_id}/configs/{config_idx}", response_model=DayPlanResponse)
def delete_preflop_config(plan_id: str, config_idx: int):
    """
    Delete/unlock a preflop config from a day plan.

    This removes the config and all its slots, allowing the user to pick a new preflop scenario.
    """
    plan = storage.get_day_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Day plan not found")

    if config_idx < 0 or config_idx >= len(plan.configs):
        raise HTTPException(status_code=400, detail="Invalid config index")

    # Remove the config
    plan.configs.pop(config_idx)

    # Update status
    if len(plan.configs) == 0:
        plan.status = "draft"
    elif len(plan.configs) < 2:
        plan.status = "draft"

    storage.save_day_plan(plan)
    return _plan_to_response(plan)


@app.post("/day-plans/{plan_id}/slots/{slot_id}/create-sim", response_model=DayPlanResponse)
def create_slot_sim(plan_id: str, slot_id: str, request: CreateSlotSimRequest):
    """
    Create a new sim for a flop slot.

    For turn/river slots, use create-child-sim endpoint.
    """
    plan = storage.get_day_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Day plan not found")

    # Find the slot and its config
    target_slot = None
    target_config = None
    for config in plan.configs:
        for slot in config.slots:
            if slot.id == slot_id:
                target_slot = slot
                target_config = config
                break
        if target_slot:
            break

    if not target_slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    if target_slot.street != "flop":
        raise HTTPException(
            status_code=400,
            detail="Use create-child-sim for turn/river slots"
        )

    # Get scenario data
    try:
        scenario_data = preflop_storage.get_scenario_data(target_config.preflop_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    nodes = scenario_data["nodes"]
    ip_range_dict = scenario_data["ip_range"]
    oop_range_dict = scenario_data["oop_range"]
    ip_pos = scenario_data["ip_position"]
    oop_pos = scenario_data["oop_position"]

    # Calculate pot and stacks
    pot, stacks = calculate_pot_and_stacks(nodes)

    # Get board
    board = request.board if request.board else random_board()
    if len(board) != 6:
        raise HTTPException(status_code=400, detail="Board must be 6 characters (3 cards)")

    # Convert ranges
    ip_range = firestore_range_to_weights(ip_range_dict)
    oop_range = firestore_range_to_weights(oop_range_dict)

    # Build scenario name
    scenario_name = "_".join(target_config.preflop_path)

    # Build solver request
    config = SpotConfig(
        board=board,
        ip_range=ip_range,
        oop_range=oop_range,
        pot_size_bb=pot,
        effective_stack_bb=stacks,
        street_id=1,  # Flop
        ip_position=ip_pos,
        oop_position=oop_pos,
    )
    builder = RequestBuilder(config)
    builder.with_iterations(request.iterations)
    solver_request = builder.build()

    # Run solver
    try:
        token = get_api_token()
        client = DeepsolverClient(api_token=token)
        print(f"Running flop sim for day plan slot: {scenario_name} on {board}...")
        result = client.run_and_wait(
            solver_request, timeout_seconds=180, poll_interval_seconds=5
        )
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"API error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Solver error: {e}")

    if "tree" not in result:
        raise HTTPException(status_code=500, detail="No tree in solver response")

    # Save the sim
    sim_id = str(uuid.uuid4())
    sim = SolverSim(
        id=sim_id,
        board=board,
        scenario=scenario_name,
        ip_position=ip_pos,
        oop_position=oop_pos,
        stack_size_bb=stacks,
        iterations=request.iterations,
        tree_gcs_path="",
        created_at=datetime.utcnow(),
        street="flop",
        tree=result["tree"],
        pot_size_bb=pot,
    )
    storage.save_sim(sim)

    # Update slot
    target_slot.sim_id = sim_id
    target_slot.board = board
    target_slot.status = "sim_ready"

    storage.save_day_plan(plan)
    return _plan_to_response(plan)


@app.post("/day-plans/{plan_id}/slots/{slot_id}/create-child-sim", response_model=DayPlanResponse)
def create_child_slot_sim(plan_id: str, slot_id: str, request: CreateChildSlotSimRequest):
    """
    Create a turn/river sim from a parent slot.

    The parent slot must have a sim_ready status.
    """
    plan = storage.get_day_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Day plan not found")

    # Find the slot and its config
    target_slot = None
    target_config = None
    for config in plan.configs:
        for slot in config.slots:
            if slot.id == slot_id:
                target_slot = slot
                target_config = config
                break
        if target_slot:
            break

    if not target_slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    if target_slot.street == "flop":
        raise HTTPException(status_code=400, detail="Use create-sim for flop slots")

    # Find parent slot in the same config
    parent_slot = None
    if target_slot.parent_slot_id:
        for slot in target_config.slots:
            if slot.id == target_slot.parent_slot_id:
                parent_slot = slot
                break

    if not parent_slot:
        raise HTTPException(status_code=400, detail=f"Parent slot not found (parent_id: {target_slot.parent_slot_id})")

    if parent_slot.status != "sim_ready" and parent_slot.status != "complete":
        raise HTTPException(
            status_code=400,
            detail=f"Parent slot must have a sim (status: {parent_slot.status})"
        )

    if not parent_slot.sim_id:
        raise HTTPException(status_code=400, detail="Parent slot has no sim")

    # Get parent sim
    parent_sim = storage.get_sim(parent_slot.sim_id)
    if not parent_sim:
        raise HTTPException(status_code=404, detail="Parent sim not found")

    # Parse tree and get ranges at action path
    tree = parse_tree(parent_sim.tree)
    ranges_result = get_ranges_at_node(tree, request.action_path)

    if "error" in ranges_result:
        raise HTTPException(status_code=400, detail=ranges_result["error"])

    if not ranges_result["is_terminal"]:
        raise HTTPException(
            status_code=400,
            detail="Action path must end at a terminal node"
        )

    ip_range = ranges_result["ip_range"]
    oop_range = ranges_result["oop_range"]
    pot_size_bb = ranges_result["pot_size"] / UNITS_PER_BB

    # Deal card
    if request.card:
        new_card = request.card
        if len(new_card) != 2:
            raise HTTPException(status_code=400, detail="Card must be 2 characters")
        if new_card in [parent_sim.board[i:i+2] for i in range(0, len(parent_sim.board), 2)]:
            raise HTTPException(status_code=400, detail=f"Card {new_card} is already on the board")
    else:
        new_card = deal_random_card(parent_sim.board, ip_range, oop_range)

    new_board = parent_sim.board + new_card

    # Determine street
    if target_slot.street == "turn":
        street_id = 2
        # Calculate stack reduction for turn
        original_pot = parent_sim.pot_size_bb or 5.0
        pot_increase = pot_size_bb - original_pot
        stack_reduction = (parent_sim.pot_size_bb / 2 if parent_sim.pot_size_bb else 2.5) + (pot_increase / 2)
        stack_size_bb = parent_sim.stack_size_bb - stack_reduction
    else:  # river
        street_id = 3
        turn_pot_increase = pot_size_bb - (parent_sim.pot_size_bb or pot_size_bb)
        stack_reduction = turn_pot_increase / 2
        stack_size_bb = parent_sim.stack_size_bb - stack_reduction

    # Build solver request
    config = SpotConfig(
        board=new_board,
        ip_range=ip_range,
        oop_range=oop_range,
        pot_size_bb=pot_size_bb,
        effective_stack_bb=stack_size_bb,
        street_id=street_id,
        ip_position=parent_sim.ip_position,
        oop_position=parent_sim.oop_position,
    )
    builder = RequestBuilder(config)
    builder.with_iterations(request.iterations)
    solver_request = builder.build()

    # Run solver
    try:
        token = get_api_token()
        client = DeepsolverClient(api_token=token)
        print(f"Running {target_slot.street} sim for day plan slot: {new_board}...")
        result = client.run_and_wait(
            solver_request, timeout_seconds=180, poll_interval_seconds=5
        )
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"API error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Solver error: {e}")

    if "tree" not in result:
        raise HTTPException(status_code=500, detail="No tree in solver response")

    # Save the sim
    sim_id = str(uuid.uuid4())
    sim = SolverSim(
        id=sim_id,
        board=new_board,
        scenario=parent_sim.scenario,
        ip_position=parent_sim.ip_position,
        oop_position=parent_sim.oop_position,
        stack_size_bb=stack_size_bb,
        iterations=request.iterations,
        tree_gcs_path="",
        created_at=datetime.utcnow(),
        street=target_slot.street,
        tree=result["tree"],
        parent_sim_id=parent_sim.id,
        parent_action_path=request.action_path,
        pot_size_bb=pot_size_bb,
    )
    storage.save_sim(sim)

    # Update slot
    target_slot.sim_id = sim_id
    target_slot.board = new_board
    target_slot.action_path = request.action_path
    target_slot.status = "sim_ready"

    storage.save_day_plan(plan)
    return _plan_to_response(plan)


@app.post("/day-plans/{plan_id}/slots/{slot_id}/link-sim", response_model=DayPlanResponse)
def link_slot_sim(plan_id: str, slot_id: str, request: LinkSlotSimRequest):
    """
    Link an existing sim to a slot.
    """
    plan = storage.get_day_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Day plan not found")

    # Find the slot
    target_slot = None
    for config in plan.configs:
        for slot in config.slots:
            if slot.id == slot_id:
                target_slot = slot
                break
        if target_slot:
            break

    if not target_slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    # Get the sim
    sim = storage.get_sim(request.sim_id, load_tree=False)
    if not sim:
        raise HTTPException(status_code=404, detail="Sim not found")

    # Verify street matches
    if sim.street != target_slot.street:
        raise HTTPException(
            status_code=400,
            detail=f"Sim street ({sim.street}) doesn't match slot street ({target_slot.street})"
        )

    # Update slot
    target_slot.sim_id = sim.id
    target_slot.board = sim.board
    target_slot.status = "sim_ready"

    storage.save_day_plan(plan)
    return _plan_to_response(plan)


@app.put("/day-plans/{plan_id}/slots/{slot_id}", response_model=DayPlanResponse)
def update_slot(plan_id: str, slot_id: str, request: UpdateSlotRequest):
    """
    Update a slot (typically after puzzle creation).
    """
    plan = storage.get_day_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Day plan not found")

    # Find the slot
    target_slot = None
    for config in plan.configs:
        for slot in config.slots:
            if slot.id == slot_id:
                target_slot = slot
                break
        if target_slot:
            break

    if not target_slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    if request.puzzle_id is not None:
        target_slot.puzzle_id = request.puzzle_id
    if request.status is not None:
        target_slot.status = request.status

    # Check if all slots are complete
    all_complete = all(
        slot.status == "complete"
        for config in plan.configs
        for slot in config.slots
    )
    if all_complete:
        plan.status = "complete"

    storage.save_day_plan(plan)
    return _plan_to_response(plan)


@app.post("/day-plans/{plan_id}/slots/{slot_id}/reset", response_model=DayPlanResponse)
def reset_slot(plan_id: str, slot_id: str):
    """
    Reset a slot back to empty, clearing its sim, board, puzzle, and action path.
    Also resets any child slots that depend on this one.
    """
    plan = storage.get_day_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Day plan not found")

    # Find the slot
    target_slot = None
    for config in plan.configs:
        for slot in config.slots:
            if slot.id == slot_id:
                target_slot = slot
                break
        if target_slot:
            break

    if not target_slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    # Reset this slot
    def reset_slot_fields(s):
        s.sim_id = None
        s.puzzle_id = None
        s.board = None
        s.action_path = None
        s.status = "empty"

    reset_slot_fields(target_slot)

    # Also reset any child slots that depend on this one (recursively)
    def reset_children(parent_id):
        for config in plan.configs:
            for slot in config.slots:
                if slot.parent_slot_id == parent_id and slot.status != "empty":
                    reset_slot_fields(slot)
                    reset_children(slot.id)

    reset_children(slot_id)

    # Update plan status
    plan.status = "in_progress"

    storage.save_day_plan(plan)
    return _plan_to_response(plan)


@app.post("/day-plans/{plan_id}/slots/{slot_id}/repick", response_model=DayPlanResponse)
def repick_slot_combo(plan_id: str, slot_id: str):
    """
    Reset a slot's combo/puzzle without clearing the sim data.

    Keeps: sim_id, tree_path, line, decision_idx, top_combos, board
    Clears: puzzle_id, planned_hero_hand
    Sets status back to sim_ready
    """
    plan = storage.get_day_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Day plan not found")

    # Find the slot
    target_slot = None
    for config in plan.configs:
        for slot in config.slots:
            if slot.id == slot_id:
                target_slot = slot
                break
        if target_slot:
            break

    if not target_slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    if target_slot.status != "complete":
        raise HTTPException(status_code=400, detail="Slot is not complete, nothing to repick")

    if not target_slot.sim_id:
        raise HTTPException(status_code=400, detail="Slot has no sim, use reset instead")

    # Clear combo and puzzle, keep sim data
    target_slot.puzzle_id = None
    target_slot.planned_hero_hand = None
    target_slot.status = "sim_ready"

    # Update plan status
    plan.status = "in_progress"

    storage.save_day_plan(plan)
    return _plan_to_response(plan)


@app.get("/day-plans/{plan_id}/slots/{slot_id}/compatible-sims", response_model=list[CompatibleSimResponse])
def get_compatible_sims(plan_id: str, slot_id: str):
    """
    Find sims that can be linked to a slot.

    For flop slots: any flop sim with matching positions.
    For turn/river slots: must match parent sim chain.
    """
    plan = storage.get_day_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Day plan not found")

    # Find the slot and its config
    target_slot = None
    target_config = None
    for config in plan.configs:
        for slot in config.slots:
            if slot.id == slot_id:
                target_slot = slot
                target_config = config
                break
        if target_slot:
            break

    if not target_slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    all_sims = storage.get_all_sims()
    compatible = []

    for sim in all_sims:
        # Must match street
        if sim.street != target_slot.street:
            continue

        # For flop slots, match positions
        if target_slot.street == "flop":
            if sim.ip_position == target_config.ip_position and sim.oop_position == target_config.oop_position:
                compatible.append(CompatibleSimResponse(
                    id=sim.id,
                    board=sim.board,
                    scenario=sim.scenario,
                    ip_position=sim.ip_position,
                    oop_position=sim.oop_position,
                    street=sim.street,
                    created_at=sim.created_at.isoformat(),
                ))

    return compatible


@app.get("/day-plans/{plan_id}/configs/{config_idx}/existing-sims", response_model=list[CompatibleSimResponse])
def get_existing_sims_for_config(plan_id: str, config_idx: int):
    """
    Find all existing sims (flop/turn/river) that match this preflop config.
    """
    plan = storage.get_day_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Day plan not found")

    if config_idx >= len(plan.configs):
        raise HTTPException(status_code=404, detail="Config not found")

    config = plan.configs[config_idx]
    all_sims = storage.get_all_sims()
    matching = []

    for sim in all_sims:
        # Match by positions (scenario name format varies)
        if sim.ip_position == config.ip_position and sim.oop_position == config.oop_position:
            matching.append(CompatibleSimResponse(
                id=sim.id,
                board=sim.board,
                scenario=sim.scenario,
                ip_position=sim.ip_position,
                oop_position=sim.oop_position,
                street=sim.street,
                created_at=sim.created_at.isoformat(),
            ))

    # Sort by street (flop, turn, river) then by board
    street_order = {"flop": 0, "turn": 1, "river": 2}
    matching.sort(key=lambda s: (street_order.get(s.street, 99), s.board))

    return matching


# =============================================================================
# Import Pipeline
# =============================================================================


def _run_sim(board, ip_range, oop_range, pot_size_bb, stack_size_bb, street_id,
             ip_pos, oop_pos, scenario_name, iterations=500, parent_sim_id=None,
             parent_action_path=None):
    """Run a solver sim and save it. Returns (SolverSim, error_str)."""
    config = SpotConfig(
        board=board,
        ip_range=ip_range,
        oop_range=oop_range,
        pot_size_bb=pot_size_bb,
        effective_stack_bb=stack_size_bb,
        street_id=street_id,
        ip_position=ip_pos,
        oop_position=oop_pos,
    )
    builder = RequestBuilder(config)
    builder.with_iterations(iterations)
    solver_request = builder.build()

    street_name = {1: "flop", 2: "turn", 3: "river"}[street_id]

    try:
        token = get_api_token()
        client = DeepsolverClient(api_token=token)
        logger.info(f"Import: Running {street_name} sim for {board} ({scenario_name})...")
        sys.stdout.flush()
        result = client.run_and_wait(
            solver_request, timeout_seconds=180, poll_interval_seconds=5
        )
    except Exception as e:
        return None, f"solver error for {board}: {e}"

    if "tree" not in result:
        return None, f"no tree in response for {board}"

    sim_id = str(uuid.uuid4())
    sim = SolverSim(
        id=sim_id,
        board=board,
        scenario=scenario_name,
        ip_position=ip_pos,
        oop_position=oop_pos,
        stack_size_bb=stack_size_bb,
        iterations=iterations,
        tree_gcs_path="",
        created_at=datetime.utcnow(),
        street=street_name,
        tree=result["tree"],
        pot_size_bb=pot_size_bb,
        parent_sim_id=parent_sim_id,
        parent_action_path=parent_action_path,
    )
    storage.save_sim(sim)
    return sim, None


def _process_slot_in_sim(sim, import_spot, slot, board, errors, prefix):
    """Walk a slot's line in its sim tree, populate top_combos + action_path.

    Returns the resolution action_path (full tree path) if the line resolves the street,
    or None.
    """
    from deepsolver.spot_extractor import walk_action_line, get_top_combos_at_node

    tree = parse_tree(sim.tree)
    slot.sim_id = sim.id

    line_before = import_spot.line[:import_spot.decision_idx]
    decision_node = walk_action_line(tree, line_before)

    if decision_node is None:
        errors.append(f"{prefix}: couldn't follow line {line_before} in tree")
        return None
    if decision_node.is_terminal():
        errors.append(f"{prefix}: line {line_before} leads to terminal node")
        return None

    top_combos = get_top_combos_at_node(decision_node, board, limit=20)
    slot.tree_path = decision_node.path
    slot.top_combos = top_combos
    slot.status = "sim_ready"

    # Walk the rest of the line to get action_path for child sims
    line_after = import_spot.line[import_spot.decision_idx:]
    resolution_path = None
    if line_after:
        resolution_node = walk_action_line(decision_node, line_after)
        if resolution_node is not None:
            slot.action_path = resolution_node.path
            resolution_path = resolution_node.path

    return resolution_path


@app.post("/day-plans/import", response_model=ImportDayPlanResponse)
def import_day_plan(request: ImportDayPlanRequest):
    """
    Import a full day plan from JSON definition (v2: line-based).

    Runs all sims (flop, turn, river) in sequence. For each slot, walks
    the action line to the decision node and populates top_combos.
    User then picks a combo on each slot to create the puzzle.
    """
    errors = []
    slots_created = 0

    if len(request.scenarios) != 2:
        raise HTTPException(status_code=400, detail="Exactly 2 scenarios required")

    # Create or get day plan
    existing = storage.get_day_plan_by_date(request.date)
    if existing:
        plan = existing
    else:
        plan = DayPlan(
            id=str(uuid.uuid4()),
            scheduled_date=request.date,
            configs=[],
            status="draft",
            created_at=datetime.utcnow(),
        )
        storage.save_day_plan(plan)

    for scenario_idx, scenario in enumerate(request.scenarios):
        if len(scenario.spots) != 5:
            errors.append(f"Scenario {scenario_idx}: expected 5 spots, got {len(scenario.spots)}")
            continue

        try:
            scenario_data = preflop_storage.get_scenario_data(scenario.preflop)
        except ValueError as e:
            errors.append(f"Scenario {scenario_idx}: invalid preflop path: {e}")
            continue

        nodes = scenario_data["nodes"]
        description = build_preflop_description(nodes)
        ip_pos = scenario_data["ip_position"]
        oop_pos = scenario_data["oop_position"]
        ip_range_dict = scenario_data["ip_range"]
        oop_range_dict = scenario_data["oop_range"]
        pot, stacks = calculate_pot_and_stacks(nodes)

        config_id = str(uuid.uuid4())
        new_config = PreflopConfig(
            id=config_id,
            preflop_path=scenario.preflop,
            ip_position=ip_pos,
            oop_position=oop_pos,
            description=description,
            slots=_create_slots_for_config(config_id),
        )

        # Group spots by board
        board_groups = {}
        for spot in scenario.spots:
            board_key = spot.board[:6]
            if board_key not in board_groups:
                board_groups[board_key] = []
            board_groups[board_key].append(spot)

        if len(board_groups) != 2:
            errors.append(f"Scenario {scenario_idx}: expected 2 distinct boards, got {len(board_groups)}")
            continue

        boards_sorted = sorted(board_groups.items(), key=lambda x: len(x[1]))
        board1_key, board1_spots = boards_sorted[0]
        board2_key, board2_spots = boards_sorted[1]

        if len(board1_spots) != 2 or len(board2_spots) != 3:
            errors.append(f"Scenario {scenario_idx}: expected 2+3 spots, got {len(board1_spots)}+{len(board2_spots)}")
            continue

        street_order = {"flop": 0, "turn": 1, "river": 2}
        board1_spots.sort(key=lambda s: street_order.get(s.street, 99))
        board2_spots.sort(key=lambda s: street_order.get(s.street, 99))

        # spot_slot_map: [(import_spot, slot), ...]
        # [0]=flop1, [1]=turn1, [2]=flop2, [3]=turn2, [4]=river
        spot_slot_map = [
            (board1_spots[0], new_config.slots[0]),
            (board1_spots[1], new_config.slots[1]),
            (board2_spots[0], new_config.slots[2]),
            (board2_spots[1], new_config.slots[3]),
            (board2_spots[2], new_config.slots[4]),
        ]

        for import_spot, slot in spot_slot_map:
            slot.line = import_spot.line
            slot.decision_idx = import_spot.decision_idx
            slot.board = import_spot.board if import_spot.street != "flop" else import_spot.board[:6]

        ip_range = firestore_range_to_weights(ip_range_dict)
        oop_range = firestore_range_to_weights(oop_range_dict)
        scenario_name = "_".join(scenario.preflop)

        # ---- Process each board's chain: flop -> turn [-> river] ----

        # Board chains: [(flop_idx, [child_indices])]
        # Board 1: flop(0) -> turn(1)
        # Board 2: flop(2) -> turn(3) -> river(4)
        board_chains = [
            [0, 1],        # board1: flop, turn
            [2, 3, 4],     # board2: flop, turn, river
        ]

        for chain in board_chains:
            from deepsolver.spot_extractor import (
                walk_action_line,
                get_top_combos_at_node,
                get_chain_top_combos,
                get_node_by_path,
            )

            flop_map_idx = chain[0]
            import_spot, slot = spot_slot_map[flop_map_idx]
            board = import_spot.board[:6]
            prefix = f"Scenario {scenario_idx}, {board}"

            if len(board) != 6:
                errors.append(f"{prefix}: invalid board")
                continue

            # Run flop sim
            sim, err = _run_sim(
                board=board, ip_range=ip_range, oop_range=oop_range,
                pot_size_bb=pot, stack_size_bb=stacks, street_id=1,
                ip_pos=ip_pos, oop_pos=oop_pos, scenario_name=scenario_name,
            )
            if err:
                errors.append(f"{prefix}: {err}")
                continue

            # Process flop slot
            resolution_path = _process_slot_in_sim(sim, import_spot, slot, board, errors, prefix + " flop")
            if slot.status == "sim_ready":
                slots_created += 1

            # Collect chain_data for combined top_combos:
            # [(decision_node, line_token_at_decision, board, action_label)]
            chain_data = []
            chain_slots = [slot]
            if slot.status == "sim_ready" and slot.tree_path:
                flop_tree = parse_tree(sim.tree)
                decision_node = get_node_by_path(flop_tree, slot.tree_path)
                if decision_node:
                    token = import_spot.line[import_spot.decision_idx] if import_spot.decision_idx < len(import_spot.line) else None
                    if token:
                        chain_data.append((decision_node, token, board, f"flop:{token}"))

            # Chain through turn/river children
            parent_sim = sim
            for child_map_idx in chain[1:]:
                child_import_spot, child_slot = spot_slot_map[child_map_idx]
                child_street = child_import_spot.street
                child_board = child_import_spot.board
                child_prefix = f"{prefix} {child_street}"

                if resolution_path is None:
                    errors.append(f"{child_prefix}: parent street didn't resolve, can't create child sim")
                    break

                # Extract ranges at the resolution node
                parent_tree = parse_tree(parent_sim.tree)
                ranges_result = get_ranges_at_node(parent_tree, resolution_path)

                if "error" in ranges_result:
                    errors.append(f"{child_prefix}: range extraction error: {ranges_result['error']}")
                    break

                child_ip_range = ranges_result["ip_range"]
                child_oop_range = ranges_result["oop_range"]
                child_pot_bb = ranges_result["pot_size"] / UNITS_PER_BB

                # Calculate remaining stack
                parent_pot_bb = parent_sim.pot_size_bb or pot
                pot_increase = child_pot_bb - parent_pot_bb
                child_stack_bb = parent_sim.stack_size_bb - (pot_increase / 2)

                street_id = {"turn": 2, "river": 3}[child_street]

                # Run child sim
                child_sim, err = _run_sim(
                    board=child_board, ip_range=child_ip_range, oop_range=child_oop_range,
                    pot_size_bb=child_pot_bb, stack_size_bb=child_stack_bb,
                    street_id=street_id,
                    ip_pos=ip_pos, oop_pos=oop_pos, scenario_name=scenario_name,
                    parent_sim_id=parent_sim.id, parent_action_path=resolution_path,
                )
                if err:
                    errors.append(f"{child_prefix}: {err}")
                    break

                # Process child slot in child sim
                resolution_path = _process_slot_in_sim(
                    child_sim, child_import_spot, child_slot, child_board, errors, child_prefix
                )
                if child_slot.status == "sim_ready":
                    slots_created += 1
                    chain_slots.append(child_slot)
                    # Collect chain_data for this slot
                    if child_slot.tree_path:
                        child_tree = parse_tree(child_sim.tree)
                        child_decision = get_node_by_path(child_tree, child_slot.tree_path)
                        if child_decision:
                            token = child_import_spot.line[child_import_spot.decision_idx] if child_import_spot.decision_idx < len(child_import_spot.line) else None
                            if token:
                                chain_data.append((child_decision, token, child_board, f"{child_street}:{token}"))

                parent_sim = child_sim

            # Compute chain-wide top_combos and apply to ALL slots in chain
            if len(chain_data) > 1:
                combined_combos = get_chain_top_combos(chain_data, limit=20)
                for chain_slot in chain_slots:
                    chain_slot.top_combos = combined_combos

        # Add config to plan
        while len(plan.configs) <= scenario_idx:
            plan.configs.append(None)
        plan.configs[scenario_idx] = new_config

    # Clean up None configs
    plan.configs = [c for c in plan.configs if c is not None]
    if len(plan.configs) == 2:
        plan.status = "in_progress"

    storage.save_day_plan(plan)
    return ImportDayPlanResponse(
        day_plan=_plan_to_response(plan),
        flop_spots_created=slots_created,
        errors=errors,
    )


def _find_chain_slots(config: PreflopConfig, slot_id: str) -> list[PuzzleSlot]:
    """Find a slot and all its descendants in the parent chain.

    Returns the chain in order: [flop_slot, turn_slot, river_slot, ...].
    The slot_id can be any slot in the chain — we find the root (no parent or
    parent is a different board) and collect downward.
    """
    slots_by_id = {s.id: s for s in config.slots}

    # Find the target slot
    target = slots_by_id.get(slot_id)
    if not target:
        return []

    # Walk up to find the chain root (flop)
    root = target
    while root.parent_slot_id and root.parent_slot_id in slots_by_id:
        root = slots_by_id[root.parent_slot_id]

    # Walk down to collect the full chain
    chain = [root]
    current = root
    while True:
        child = next((s for s in config.slots if s.parent_slot_id == current.id), None)
        if child is None:
            break
        chain.append(child)
        current = child

    return chain


def _create_puzzle_for_slot(slot, combo, plan, config):
    """Create a spot + ScheduledPuzzle for a sim_ready slot. Returns error string or None."""
    from deepsolver.spot_extractor import create_spot_at_path
    from storage.models import _build_question_text, _generate_tags, _build_action_tree

    if slot.status != "sim_ready" or not slot.sim_id or not slot.tree_path:
        return None  # Skip silently — not ready

    sim = storage.get_sim(slot.sim_id)
    if not sim or not sim.tree:
        return f"Slot {slot.id}: sim not found or tree not loaded"

    tree = parse_tree(sim.tree)
    preflop_action = _build_preflop_action_from_sim(sim)

    # Build previous_street_actions including parent streets (flop/turn)
    previous_street_actions = [preflop_action]
    if slot.parent_slot_id:
        from deepsolver.spot_extractor import _build_street_actions
        slots_by_id = {s.id: s for s in config.slots}
        # Walk up the parent chain to collect ancestors in order (flop first, then turn)
        ancestors = []
        current_id = slot.parent_slot_id
        while current_id and current_id in slots_by_id:
            ancestors.append(slots_by_id[current_id])
            current_id = slots_by_id[current_id].parent_slot_id
        ancestors.reverse()  # flop first, then turn
        for ancestor in ancestors:
            if ancestor.sim_id and ancestor.action_path:
                parent_sim = storage.get_sim(ancestor.sim_id)
                if parent_sim and parent_sim.tree:
                    parent_tree = parse_tree(parent_sim.tree)
                    street_actions = _build_street_actions(
                        tree=parent_tree,
                        target_path=ancestor.action_path,
                        board=ancestor.board,
                        ip_position=config.ip_position,
                        oop_position=config.oop_position,
                        previous_street_actions=None,
                    )
                    # The last entry is the action for this ancestor's street
                    if street_actions:
                        # Skip preflop (index 0) and any prior streets already covered
                        # Just take the last entry which is the ancestor's own street
                        previous_street_actions.append(street_actions[-1])

    result = create_spot_at_path(
        tree=tree,
        path=slot.tree_path,
        combo=combo,
        board=slot.board,
        ip_position=config.ip_position,
        oop_position=config.oop_position,
        task_id=f"sim-{sim.id}",
        stack_size_bb=sim.stack_size_bb,
        previous_street_actions=previous_street_actions,
    )

    # Handle error string or None
    if isinstance(result, str):
        return f"Slot {slot.id} ({slot.street}): {result}"
    if result is None:
        return f"Slot {slot.id} ({slot.street}): couldn't create spot for {combo}"

    spot = result

    storage.save_candidate(spot)

    question_text = _build_question_text(spot)
    tags = _generate_tags(spot)
    action = _build_action_tree(spot)

    sorted_actions = sorted(
        spot.action_frequencies.items(), key=lambda x: x[1], reverse=True
    )
    answer_options = [a[0] for a in sorted_actions[:3]]
    correct_answers = [a[0] for a in sorted_actions if a[1] >= 0.25]
    if not correct_answers:
        correct_answers = [sorted_actions[0][0]]

    explanations = {}
    for action_name, freq in sorted_actions[:3]:
        ev = spot.ev_by_action.get(action_name, 0.0)
        explanations[action_name] = f"{action_name}: {freq:.0%} frequency, EV {ev:.2f}bb"

    best_freq = sorted_actions[0][1] if sorted_actions else 0
    if best_freq > 0.85:
        difficulty = 1
    elif best_freq > 0.65:
        difficulty = 2
    else:
        difficulty = 3

    # Compute slot order (1-indexed position across all configs)
    slot_order = None
    idx = 1
    for c in plan.configs:
        for s in c.slots:
            if s.id == slot.id:
                slot_order = idx
            idx += 1

    # Compute spot type classification
    from utils.spot_classifier import classify_spot_type
    spot_type = classify_spot_type(action, spot.hero_position)

    puzzle = ScheduledPuzzle(
        id=str(uuid.uuid4()),
        scheduled_date=plan.scheduled_date,
        question_text=question_text,
        structure="6max",
        effective_stacks=int(sim.stack_size_bb),
        hero=spot.hero_position,
        action=action,
        pot_size_at_decision=spot.pot_size_bb,
        answer_options=answer_options,
        correct_answers=correct_answers,
        explanations=explanations,
        ev_by_action=spot.ev_by_action,
        action_frequencies=spot.action_frequencies,
        difficulty=difficulty,
        tags=tags,
        created_at=datetime.utcnow(),
        order=slot_order,
        spot_type=spot_type,
    )
    storage.save_scheduled_puzzle(puzzle)

    slot.puzzle_id = puzzle.id
    slot.planned_hero_hand = combo
    slot.status = "complete"
    return None


@app.post("/day-plans/{plan_id}/slots/{slot_id}/walk-line", response_model=DayPlanResponse)
def walk_line_in_slot(plan_id: str, slot_id: str, request: WalkLineRequest):
    """
    Walk an action line in an existing slot's sim tree.

    The slot must already have a sim (status=sim_ready).
    Populates top_combos, tree_path, action_path, line, and decision_idx.
    """
    from deepsolver.spot_extractor import walk_action_line, get_top_combos_at_node

    plan = storage.get_day_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Day plan not found")

    # Find the slot
    target_slot = None
    for config in plan.configs:
        for slot in config.slots:
            if slot.id == slot_id:
                target_slot = slot
                break
        if target_slot:
            break

    if not target_slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    if not target_slot.sim_id:
        raise HTTPException(status_code=400, detail="Slot has no sim. Run a sim first.")

    if target_slot.status not in ("sim_ready",):
        raise HTTPException(status_code=400, detail=f"Slot status must be sim_ready (got: {target_slot.status})")

    # Load the sim tree
    sim = storage.get_sim(target_slot.sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Sim not found")

    tree = parse_tree(sim.tree)

    # Walk to decision node
    line_before = request.line[:request.decision_idx]
    decision_node = walk_action_line(tree, line_before)

    if decision_node is None:
        raise HTTPException(status_code=400, detail=f"Couldn't follow line {line_before} in tree")
    if decision_node.is_terminal():
        raise HTTPException(status_code=400, detail=f"Line {line_before} leads to a terminal node")

    top_combos = get_top_combos_at_node(decision_node, target_slot.board, limit=20)
    target_slot.tree_path = decision_node.path
    target_slot.top_combos = top_combos
    target_slot.line = request.line
    target_slot.decision_idx = request.decision_idx

    # Walk rest of line to get action_path for child sims
    line_after = request.line[request.decision_idx:]
    if line_after:
        resolution_node = walk_action_line(decision_node, line_after)
        if resolution_node is not None:
            target_slot.action_path = resolution_node.path

    storage.save_day_plan(plan)
    return _plan_to_response(plan)


@app.post("/day-plans/{plan_id}/slots/{slot_id}/node-info", response_model=NodeInfoResponse)
def get_slot_node_info(plan_id: str, slot_id: str, request: NodeInfoRequest):
    """
    Walk a partial action line in a slot's sim tree and return node info.

    Returns the acting position, available actions with aggregate GTO frequencies,
    and a 13x13 range grid with per-hand action breakdowns.
    """
    from deepsolver.spot_extractor import walk_action_line, HAND_ORDER, is_combo_blocked
    from deepsolver.tree_parser import format_action

    plan = storage.get_day_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Day plan not found")

    target_slot = None
    for config in plan.configs:
        for slot in config.slots:
            if slot.id == slot_id:
                target_slot = slot
                break
        if target_slot:
            break

    if not target_slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    if not target_slot.sim_id:
        raise HTTPException(status_code=400, detail="Slot has no sim")

    sim = storage.get_sim(target_slot.sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Sim not found")

    tree = parse_tree(sim.tree)
    node = walk_action_line(tree, request.line) if request.line else tree

    if node is None:
        raise HTTPException(status_code=400, detail=f"Couldn't follow line {request.line} in tree")

    if node.is_terminal():
        return NodeInfoResponse(position="", is_terminal=True)

    position = sim.ip_position if node.player_id == 0 else sim.oop_position

    # Build action info with aggregate frequencies
    actions_info = []
    if node.actions and node.strategy and node.ranges:
        player_range = node.ranges[node.player_id]
        board = target_slot.board or ""

        # Total range weight (for normalizing frequencies)
        total_weight = sum(
            player_range[ci]
            for ci in range(1326)
            if player_range[ci] > 0 and not is_combo_blocked(HAND_ORDER[ci], board)
        )

        for i, action in enumerate(node.actions):
            label = format_action(action, node.pot_size)

            # Aggregate frequency: sum(strategy * range) / total_range
            if total_weight > 0:
                action_weight = sum(
                    node.strategy[i][ci] * player_range[ci]
                    for ci in range(1326)
                    if player_range[ci] > 0 and not is_combo_blocked(HAND_ORDER[ci], board)
                )
                freq = action_weight / total_weight
            else:
                freq = 0.0

            # Map solver action to line builder token
            code, amount = action
            if code == "C":
                token = "call" if amount > 0 else "check"
            elif code == "F":
                token = "fold"
            elif code == "B":
                # Determine closest sizing token
                actual_pot = node.pot_size
                if node.bets:
                    actual_pot += sum(node.bets)
                if actual_pot > 0:
                    pct = amount / actual_pot
                    if pct > 1.5:
                        token = "allin"
                    elif pct > 1.0:
                        token = "bet125"
                    elif pct > 0.5:
                        token = "bet75"
                    elif pct > 0.2:
                        token = "bet33"
                    else:
                        token = "bet"
                else:
                    token = "bet"
            else:
                token = "bet"

            actions_info.append(NodeActionInfo(
                label=label,
                token=token,
                freq=round(freq, 3),
            ))

    # Build 13x13 range grid with action breakdowns
    range_grid = None
    combo_details = None
    if node.ranges and node.strategy and node.actions:
        player_range = node.ranges[node.player_id]
        action_names = [format_action(a, node.pot_size) for a in node.actions]
        board = target_slot.board or ""
        range_grid, combo_details = _aggregate_to_grid_with_actions(player_range, node.strategy, action_names, board)

    return NodeInfoResponse(
        position=position,
        is_terminal=False,
        actions=actions_info,
        range_grid=range_grid,
        combo_details=combo_details,
    )


@app.post("/day-plans/{plan_id}/slots/{slot_id}/pick-combo", response_model=DayPlanResponse)
def pick_combo_for_slot(plan_id: str, slot_id: str, request: PickComboRequest):
    """
    Pick a hero combo for a slot chain (flop + turn + river sharing the same board).

    Creates puzzles for ALL sim_ready slots in the chain with the chosen combo.
    """
    plan = storage.get_day_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Day plan not found")

    # Find the slot and its config
    target_config = None
    for config in plan.configs:
        for slot in config.slots:
            if slot.id == slot_id:
                target_config = config
                break

    if target_config is None:
        raise HTTPException(status_code=404, detail="Slot not found")

    # Get the full chain for this board
    chain_slots = _find_chain_slots(target_config, slot_id)
    if not chain_slots:
        raise HTTPException(status_code=404, detail="Could not find slot chain")

    # Create puzzles for all sim_ready slots in the chain
    errors = []
    created = 0
    for chain_slot in chain_slots:
        if chain_slot.status != "sim_ready":
            continue
        err = _create_puzzle_for_slot(chain_slot, request.combo, plan, target_config)
        if err:
            errors.append(err)
        else:
            created += 1

    if created == 0:
        detail = f"No puzzles created. Errors: {'; '.join(errors)}" if errors else "No sim_ready slots in chain"
        raise HTTPException(status_code=400, detail=detail)

    storage.save_day_plan(plan)
    return _plan_to_response(plan)
