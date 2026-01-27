"""Data models for puzzle storage."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from deepsolver.spot_extractor import SpotCandidate


# =============================================================================
# Day Plan Models
# =============================================================================


@dataclass
class PuzzleSlot:
    """A single puzzle slot within a day plan."""

    id: str  # UUID
    street: str  # "flop", "turn", "river"
    sim_id: str | None = None  # Reference to solver_sims
    puzzle_id: str | None = None  # Reference to new_daily_puzzles
    parent_slot_id: str | None = None  # Parent flop/turn slot
    action_path: str | None = None  # Path taken in parent sim (e.g., "r:0:c:b1650000:c")
    board: str | None = None  # Board cards
    status: str = "empty"  # "empty", "sim_ready", "complete"

    def to_dict(self) -> dict:
        """Convert to dictionary for Firestore storage."""
        return {
            "id": self.id,
            "street": self.street,
            "sim_id": self.sim_id,
            "puzzle_id": self.puzzle_id,
            "parent_slot_id": self.parent_slot_id,
            "action_path": self.action_path,
            "board": self.board,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PuzzleSlot":
        """Create PuzzleSlot from dictionary."""
        return cls(
            id=data["id"],
            street=data["street"],
            sim_id=data.get("sim_id"),
            puzzle_id=data.get("puzzle_id"),
            parent_slot_id=data.get("parent_slot_id"),
            action_path=data.get("action_path"),
            board=data.get("board"),
            status=data.get("status", "empty"),
        )


@dataclass
class PreflopConfig:
    """A preflop configuration with its 5 puzzle slots."""

    id: str  # UUID
    preflop_path: list[str]  # e.g., ["BTN_RFI", "BB_Call"]
    ip_position: str
    oop_position: str
    description: str  # Human-readable description
    slots: list[PuzzleSlot] = field(default_factory=list)  # 5 slots

    def to_dict(self) -> dict:
        """Convert to dictionary for Firestore storage."""
        return {
            "id": self.id,
            "preflop_path": self.preflop_path,
            "ip_position": self.ip_position,
            "oop_position": self.oop_position,
            "description": self.description,
            "slots": [slot.to_dict() for slot in self.slots],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PreflopConfig":
        """Create PreflopConfig from dictionary."""
        return cls(
            id=data["id"],
            preflop_path=data["preflop_path"],
            ip_position=data["ip_position"],
            oop_position=data["oop_position"],
            description=data["description"],
            slots=[PuzzleSlot.from_dict(s) for s in data.get("slots", [])],
        )


@dataclass
class DayPlan:
    """Day plan containing 2 preflop configs with 5 puzzles each."""

    id: str  # UUID
    scheduled_date: str  # YYYY-MM-DD
    configs: list[PreflopConfig] = field(default_factory=list)  # 2 configs
    status: str = "draft"  # "draft", "in_progress", "complete"
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_firestore(self) -> dict:
        """Convert to Firestore document format."""
        return {
            "id": self.id,
            "scheduled_date": self.scheduled_date,
            "configs": [config.to_dict() for config in self.configs],
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_firestore(cls, doc: dict) -> "DayPlan":
        """Create DayPlan from Firestore document."""
        return cls(
            id=doc["id"],
            scheduled_date=doc["scheduled_date"],
            configs=[PreflopConfig.from_dict(c) for c in doc.get("configs", [])],
            status=doc.get("status", "draft"),
            created_at=datetime.fromisoformat(doc["created_at"]),
        )


@dataclass
class SolverSim:
    """Stored solver simulation."""

    id: str
    board: str
    scenario: str
    ip_position: str
    oop_position: str
    stack_size_bb: float
    iterations: int
    tree_gcs_path: str  # GCS path to tree JSON
    created_at: datetime
    street: str = "flop"  # flop, turn, or river
    tree: dict[str, Any] | None = None  # Loaded lazily from GCS
    # Chained sim fields - for turn/river sims created from parent
    parent_sim_id: str | None = None  # ID of the parent flop/turn sim
    parent_action_path: str | None = None  # Action path taken in parent tree
    pot_size_bb: float | None = None  # Pot size at start of this sim

    def to_firestore(self) -> dict:
        """Convert to Firestore document format (without tree - stored in GCS)."""
        doc = {
            "id": self.id,
            "board": self.board,
            "scenario": self.scenario,
            "ip_position": self.ip_position,
            "oop_position": self.oop_position,
            "stack_size_bb": self.stack_size_bb,
            "iterations": self.iterations,
            "tree_gcs_path": self.tree_gcs_path,
            "created_at": self.created_at.isoformat(),
            "street": self.street,
        }
        # Include chained sim fields if present
        if self.parent_sim_id is not None:
            doc["parent_sim_id"] = self.parent_sim_id
        if self.parent_action_path is not None:
            doc["parent_action_path"] = self.parent_action_path
        if self.pot_size_bb is not None:
            doc["pot_size_bb"] = self.pot_size_bb
        return doc

    @classmethod
    def from_firestore(cls, doc: dict) -> "SolverSim":
        """Create SolverSim from Firestore document (tree loaded separately)."""
        return cls(
            id=doc["id"],
            board=doc["board"],
            scenario=doc["scenario"],
            ip_position=doc["ip_position"],
            oop_position=doc["oop_position"],
            stack_size_bb=doc["stack_size_bb"],
            iterations=doc["iterations"],
            tree_gcs_path=doc["tree_gcs_path"],
            created_at=datetime.fromisoformat(doc["created_at"]),
            street=doc.get("street", "flop"),  # Default to flop for older sims
            tree=None,
            parent_sim_id=doc.get("parent_sim_id"),
            parent_action_path=doc.get("parent_action_path"),
            pot_size_bb=doc.get("pot_size_bb"),
        )


@dataclass
class ApprovedPuzzle:
    """Puzzle in the format consumed by iOS app."""

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

    def to_firestore(self) -> dict:
        """Convert to iOS app format with PascalCase keys."""
        return {
            "PuzzleID": self.puzzle_id,
            "Title": self.title,
            "QuestionText": self.question_text,
            "Structure": self.structure,
            "EffectiveStacks": self.effective_stacks,
            "Hero": self.hero,
            "Action": self.action,
            "PotSizeAtDecision": self.pot_size_at_decision,
            "AnswerOptions": self.answer_options,
            "CorrectAnswer": self.correct_answer,
            "Explanation": self.explanation,
            "Difficulty": self.difficulty,
            "Tags": self.tags,
        }


@dataclass
class ScheduledPuzzle:
    """Puzzle scheduled for a specific date in new_daily_puzzles collection."""

    id: str  # UUID
    scheduled_date: str  # YYYY-MM-DD format
    question_text: str
    structure: str
    effective_stacks: int
    hero: str
    action: dict
    pot_size_at_decision: float
    answer_options: list[str]
    correct_answers: list[str]  # Can have multiple correct answers
    explanations: dict[str, str]  # Per-action explanations: {"Check": "...", "Bet 1.5bb": "..."}
    ev_by_action: dict[str, float]  # EV in bb for each action: {"Check": 1.2, "Bet 1.5bb": 1.5}
    action_frequencies: dict[str, float]  # GTO frequency for each action: {"Check": 0.45, "Bet": 0.55}
    difficulty: int
    tags: list[str]
    created_at: datetime

    def to_firestore(self) -> dict:
        """Convert to Firestore document format."""
        return {
            "id": self.id,
            "scheduled_date": self.scheduled_date,
            "QuestionText": self.question_text,
            "Structure": self.structure,
            "EffectiveStacks": self.effective_stacks,
            "Hero": self.hero,
            "Action": self.action,
            "PotSizeAtDecision": self.pot_size_at_decision,
            "AnswerOptions": self.answer_options,
            "CorrectAnswers": self.correct_answers,
            "Explanations": self.explanations,
            "EvByAction": self.ev_by_action,
            "ActionFrequencies": self.action_frequencies,
            "Difficulty": self.difficulty,
            "Tags": self.tags,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_firestore(cls, doc: dict) -> "ScheduledPuzzle":
        """Create ScheduledPuzzle from Firestore document."""
        # Handle both old format (single answer) and new format (multiple answers)
        correct_answers = doc.get("CorrectAnswers")
        if correct_answers is None:
            # Legacy single answer format
            correct_answers = [doc["CorrectAnswer"]] if doc.get("CorrectAnswer") else []

        explanations = doc.get("Explanations")
        if explanations is None:
            # Legacy single explanation format - map to first correct answer
            old_explanation = doc.get("Explanation", "")
            if correct_answers and old_explanation:
                explanations = {correct_answers[0]: old_explanation}
            else:
                explanations = {}

        return cls(
            id=doc["id"],
            scheduled_date=doc["scheduled_date"],
            question_text=doc["QuestionText"],
            structure=doc["Structure"],
            effective_stacks=doc["EffectiveStacks"],
            hero=doc["Hero"],
            action=doc["Action"],
            pot_size_at_decision=doc["PotSizeAtDecision"],
            answer_options=doc["AnswerOptions"],
            correct_answers=correct_answers,
            explanations=explanations,
            ev_by_action=doc.get("EvByAction", {}),
            action_frequencies=doc.get("ActionFrequencies", {}),
            difficulty=doc["Difficulty"],
            tags=doc["Tags"],
            created_at=datetime.fromisoformat(doc["created_at"]),
        )


def spot_to_firestore(spot: SpotCandidate) -> dict:
    """Convert SpotCandidate to Firestore document format."""
    return {
        "id": spot.id,
        "source_task_id": spot.source_task_id,
        "board": spot.board,
        "hero_combo": spot.hero_combo,
        "hero_position": spot.hero_position,
        "villain_position": spot.villain_position,
        "street": spot.street,
        "pot_size_bb": spot.pot_size_bb,
        "stack_size_bb": spot.stack_size_bb,
        "action_sequence": spot.action_sequence,
        "tree_path": spot.tree_path,
        "available_actions": spot.available_actions,
        "action_frequencies": spot.action_frequencies,
        "correct_action": spot.correct_action,
        "correct_frequency": spot.correct_frequency,
        "ev_by_action": spot.ev_by_action,
        "hand_category": spot.hand_category,
        "board_texture": spot.board_texture,
        "street_actions": spot.street_actions,
        "status": "pending",
        "created_at": spot.created_at.isoformat(),
    }


def spot_from_firestore(doc: dict) -> SpotCandidate:
    """Create SpotCandidate from Firestore document."""
    from deepsolver.spot_extractor import SpotCandidate

    return SpotCandidate(
        id=doc["id"],
        source_task_id=doc.get("source_task_id", ""),
        board=doc["board"],
        hero_combo=doc["hero_combo"],
        hero_position=doc["hero_position"],
        villain_position=doc["villain_position"],
        street=doc["street"],
        pot_size_bb=doc["pot_size_bb"],
        stack_size_bb=doc["stack_size_bb"],
        action_sequence=doc["action_sequence"],
        tree_path=doc["tree_path"],
        available_actions=doc["available_actions"],
        action_frequencies=doc["action_frequencies"],
        correct_action=doc["correct_action"],
        correct_frequency=doc["correct_frequency"],
        ev_by_action=doc["ev_by_action"],
        hand_category=doc["hand_category"],
        board_texture=doc["board_texture"],
        street_actions=doc.get("street_actions", []),
        created_at=datetime.fromisoformat(doc["created_at"]),
    )


def spot_to_puzzle(
    spot: SpotCandidate,
    puzzle_id: int,
    title: str,
    explanation: str,
    difficulty: int,
    answer_options: list[str] | None = None,
) -> ApprovedPuzzle:
    """
    Convert SpotCandidate to ApprovedPuzzle for iOS app.

    Args:
        spot: The spot candidate to convert
        puzzle_id: Sequential puzzle ID
        title: Short catchy title for the puzzle
        explanation: Explanation of the correct answer
        difficulty: 1-3 difficulty rating
        answer_options: Custom answer options (defaults to spot's available actions)

    Returns:
        ApprovedPuzzle ready for Firestore
    """
    # Build action tree from spot data
    action = _build_action_tree(spot)

    # Generate question text
    question_text = _build_question_text(spot)

    # Default answer options if not provided
    if answer_options is None:
        answer_options = spot.available_actions

    # Generate tags
    tags = _generate_tags(spot)

    return ApprovedPuzzle(
        puzzle_id=puzzle_id,
        title=title,
        question_text=question_text,
        structure="6max",
        effective_stacks=int(spot.stack_size_bb),
        hero=spot.hero_position,
        action=action,
        pot_size_at_decision=spot.pot_size_bb,
        answer_options=answer_options,
        correct_answer=spot.correct_action,
        explanation=explanation,
        difficulty=difficulty,
        tags=tags,
    )


def _build_action_tree(spot: SpotCandidate) -> dict:
    """
    Build Action dict from SpotCandidate in iOS app format.

    Converts plaintext actions like "LJ raises 2.5bb, BB calls" into
    structured format:
    {
        "preflop": {
            "LJ": {"Action": "Raise", "Amount": 2.5, "Cards": "Ac7c"},
            "BB": {"Action": "Call", "Amount": 2.5}
        },
        "flop": {
            "Cards": "AhKhTc",
            "BB": {"Action": "Check"}
        }
    }
    """
    import re

    action = {}

    for street_action in spot.street_actions:
        street = street_action["street"]
        cards = street_action.get("cards", "")
        actions_text = street_action.get("actions", "")

        street_data = {}

        # Add cards for postflop streets (remove dashes)
        if street != "preflop" and cards:
            street_data["Cards"] = cards.replace("-", "")

        # Parse individual actions from text like "LJ raises 2.5bb, BB calls"
        # Remove "to act" suffix if present (e.g., "BB checks, BTN bets 1.5bb, BB to act")
        if actions_text:
            # Remove the "X to act" part if present
            clean_actions = actions_text
            if "to act" in actions_text.lower():
                # Remove everything from the last comma before "to act"
                parts = actions_text.split(",")
                clean_parts = [p for p in parts if "to act" not in p.lower()]
                clean_actions = ",".join(clean_parts)

            if clean_actions.strip():
                # Track how many times each position has acted for unique keys
                position_counts: dict[str, int] = {}
                # Track the last bet/raise amount for "calls" without explicit amount
                last_bet_amount: float | None = None

                # Split by comma and parse each action
                action_parts = [a.strip() for a in clean_actions.split(",")]

                for part in action_parts:
                    parsed = _parse_action_text(part, last_bet_amount)
                    if not parsed:
                        continue

                    pos, action_type, amount = parsed

                    # Update last_bet_amount for bets/raises
                    if action_type in ("Raise", "3Bet", "4Bet", "5Bet", "Bet") and amount is not None:
                        last_bet_amount = amount

                    # Generate unique key for position
                    if pos in position_counts:
                        position_counts[pos] += 1
                        key = f"{pos}_{position_counts[pos]}"
                    else:
                        position_counts[pos] = 1
                        key = pos

                    # Build action entry
                    entry: dict = {"Action": action_type}
                    if amount is not None:
                        entry["Amount"] = amount

                    # Add hero's cards on their first preflop action
                    if street == "preflop" and pos == spot.hero_position and position_counts[pos] == 1:
                        entry["Cards"] = spot.hero_combo

                    street_data[key] = entry

        action[street] = street_data

    return action


def _parse_action_text(text: str, last_bet_amount: float | None = None) -> tuple[str, str, float | None] | None:
    """
    Parse action text like "LJ raises 2.5bb" into (position, action, amount).

    Args:
        text: Action text like "HJ opens 2.5bb" or "BTN 3-bets to 7.5bb"
        last_bet_amount: The last bet/raise amount (used for "calls" without explicit amount)

    Returns None if the text can't be parsed.
    """
    import re

    text = text.strip().lower()
    if not text:
        return None

    # Pattern: "POSITION action [amount]"
    # Actions: opens, raises, bets, calls, checks, folds, 3-bets, 4-bets, 5-bets

    # Match position at start (letters and numbers for positions like UTG1)
    pos_match = re.match(r"^([a-z0-9]+)\s+", text, re.IGNORECASE)
    if not pos_match:
        return None

    position = pos_match.group(1).upper()
    rest = text[pos_match.end():].strip()

    # Parse action and amount
    if rest.startswith("opens") or rest.startswith("open"):
        # "opens 2.5bb" -> Raise
        amount = _extract_amount(rest)
        return (position, "Raise", amount)
    elif rest.startswith("raises") or rest.startswith("raise"):
        amount = _extract_amount(rest)
        return (position, "Raise", amount)
    elif rest.startswith("5-bets") or rest.startswith("5bets") or rest.startswith("5-bet") or rest.startswith("5bet"):
        amount = _extract_amount(rest)
        return (position, "5Bet", amount)
    elif rest.startswith("4-bets") or rest.startswith("4bets") or rest.startswith("4-bet") or rest.startswith("4bet"):
        amount = _extract_amount(rest)
        return (position, "4Bet", amount)
    elif rest.startswith("3-bets") or rest.startswith("3bets") or rest.startswith("3-bet") or rest.startswith("3bet"):
        amount = _extract_amount(rest)
        return (position, "3Bet", amount)
    elif rest.startswith("bets") or rest.startswith("bet"):
        amount = _extract_amount(rest)
        return (position, "Bet", amount)
    elif rest.startswith("calls") or rest.startswith("call"):
        # "calls" without amount -> use last bet amount
        amount = _extract_amount(rest)
        if amount is None:
            amount = last_bet_amount
        return (position, "Call", amount)
    elif rest.startswith("checks") or rest.startswith("check"):
        return (position, "Check", None)
    elif rest.startswith("folds") or rest.startswith("fold"):
        return (position, "Fold", None)
    elif rest.startswith("all-in") or rest.startswith("allin"):
        amount = _extract_amount(rest)
        return (position, "All-in", amount)

    return None


def _extract_amount(text: str) -> float | None:
    """Extract bb amount from text like 'raises 2.5bb' or 'bets 1.6bb'."""
    import re

    match = re.search(r"(\d+(?:\.\d+)?)\s*bb", text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None


def _build_question_text(spot: SpotCandidate) -> str:
    """Generate question text from spot."""
    # Format: "UTG opens, BB calls. Flop: 7h-Th-3d. BB checks. Your move?"
    board_formatted = "-".join(
        spot.board[i : i + 2] for i in range(0, len(spot.board), 2)
    )

    # Determine scenario based on positions
    ip_pos = spot.villain_position if spot.hero_position in ("BB", "SB") else spot.hero_position
    oop_pos = spot.hero_position if spot.hero_position in ("BB", "SB") else spot.villain_position

    parts = [f"{ip_pos} opens, {oop_pos} calls."]
    parts.append(f"{spot.street.capitalize()}: {board_formatted}.")
    parts.append(spot.action_sequence.replace(" to act", "."))
    parts.append("Your move?")

    return " ".join(parts)


def _generate_tags(spot: SpotCandidate) -> list[str]:
    """Generate tags from spot metadata."""
    tags = [
        "cash",
        "6max",
        f"{int(spot.stack_size_bb)}bb",
        "srp",  # Single raised pot
        f"{spot.hero_position.lower()}_vs_{spot.villain_position.lower()}",
        spot.street,
        spot.board_texture,
        spot.hand_category,
    ]

    # Add action-based tags
    correct = spot.correct_action.lower()
    if "bet" in correct:
        tags.append("bet")
        if "small" in correct or "25" in correct or "33" in correct:
            tags.append("small_bet")
        elif "pot" in correct or "75" in correct:
            tags.append("big_bet")
        elif "overbet" in correct or "all-in" in correct:
            tags.append("overbet")
    elif "check" in correct:
        tags.append("check")
    elif "call" in correct:
        tags.append("call")
    elif "fold" in correct:
        tags.append("fold")

    return tags
