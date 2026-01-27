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
    CompatibleSimResponse,
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
cors_origins_env = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
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

        # Aggregate hero grid with strategy (actions)
        hero_grid = _aggregate_to_grid_with_actions(hero_range, strategy, action_names)
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
    action_names: list[str] | None
) -> dict[str, dict]:
    """
    Aggregate 1326 combo weights to 13x13 grid format with action frequencies.

    Returns dict like:
    {
        "AA": {"weight": 1.0, "actions": {"Bet 1.6bb": 0.85, "Check": 0.15}},
        "AKs": {"weight": 0.95, "actions": {"Bet 1.6bb": 1.0}},
        ...
    }
    """
    from deepsolver.hand_utils import HAND_ORDER

    RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']

    # Initialize grid with totals and counts
    grid_totals = {}  # hand_key -> total weight
    grid_counts = {}  # hand_key -> count of combos
    grid_actions = {}  # hand_key -> {action_name -> total frequency}

    for combo_idx, weight in enumerate(range_1326):
        if combo_idx >= len(HAND_ORDER):
            break

        combo = HAND_ORDER[combo_idx]
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

        grid_totals[hand_key] += weight
        grid_counts[hand_key] += 1

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

    return grid


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
        created_at=updated.created_at.isoformat(),
    )


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
        status=slot.status,
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
    return _plan_to_response(plan)


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
