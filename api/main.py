"""FastAPI backend for puzzle admin GUI."""

import os
import sys
import random
import uuid
from datetime import datetime
from pathlib import Path

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
    PreflopChildNode,
    PreflopNodeResponse,
    PreflopScenarioSummary,
    PreflopSimRequest,
)
from storage.firestore import PuzzleStorage
from storage.models import spot_to_puzzle, ApprovedPuzzle, SolverSim, ScheduledPuzzle
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
        title=request.title,
        explanation="",  # Not used - we have per-action explanations
        difficulty=request.difficulty,
        answer_options=request.answer_options,
    )

    # Create scheduled puzzle with multiple correct answers and per-action explanations
    puzzle = ScheduledPuzzle(
        id=str(uuid.uuid4()),
        scheduled_date=request.scheduled_date,
        title=request.title,
        question_text=request.question_text,
        structure="6max",
        effective_stacks=int(spot.stack_size_bb),
        hero=spot.hero_position,
        action=temp_puzzle.action,
        pot_size_at_decision=spot.pot_size_bb,
        answer_options=request.answer_options,
        correct_answers=request.correct_answers,
        explanations=request.explanations,
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
        title=puzzle.title,
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

    # If we have parent context, prepend it to the spot's street_actions
    if parent_context:
        existing_actions = spot.street_actions

        # Build new actions: parent context + current street actions (skip generic preflop)
        new_actions = parent_context.copy()  # preflop + flop from parent

        for action in existing_actions:
            if action["street"] not in ("preflop",):
                new_actions.append(action)

        spot.street_actions = new_actions

    # Save to spot_candidates
    storage.save_candidate(spot)

    return RandomSpotResponse(
        spot_id=spot.id,
        message=f"Generated {sim.street} spot: {spot.hero_combo} on {spot.board}",
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


@app.get("/workflow/puzzles/{date}", response_model=list[ScheduledPuzzleResponse])
def get_puzzles_for_date(date: str):
    """
    Get all puzzles scheduled for a specific date.

    Args:
        date: Date in YYYY-MM-DD format
    """
    puzzles = storage.get_puzzles_by_date(date)

    return [
        ScheduledPuzzleResponse(
            id=p.id,
            scheduled_date=p.scheduled_date,
            title=p.title,
            question_text=p.question_text,
            hero=p.hero,
            correct_answer=p.correct_answer,
            difficulty=p.difficulty,
            created_at=p.created_at.isoformat(),
        )
        for p in puzzles
    ]


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
