"""Data models for puzzle storage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from deepsolver.spot_extractor import SpotCandidate


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
    created_at: datetime

    def to_firestore(self) -> dict:
        """Convert to Firestore document format."""
        return {
            "id": self.id,
            "scheduled_date": self.scheduled_date,
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
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_firestore(cls, doc: dict) -> "ScheduledPuzzle":
        """Create ScheduledPuzzle from Firestore document."""
        return cls(
            id=doc["id"],
            scheduled_date=doc["scheduled_date"],
            title=doc["Title"],
            question_text=doc["QuestionText"],
            structure=doc["Structure"],
            effective_stacks=doc["EffectiveStacks"],
            hero=doc["Hero"],
            action=doc["Action"],
            pot_size_at_decision=doc["PotSizeAtDecision"],
            answer_options=doc["AnswerOptions"],
            correct_answer=doc["CorrectAnswer"],
            explanation=doc["Explanation"],
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
    Build Action dict from SpotCandidate.

    The Action dict shows the preflop and postflop action leading to the decision point.
    """
    # For SRP spots, we assume standard preflop action
    # IP position raised, OOP called
    ip_pos = spot.villain_position if spot.hero_position in ("BB", "SB") else spot.hero_position
    oop_pos = spot.hero_position if spot.hero_position in ("BB", "SB") else spot.villain_position

    action = {
        "preflop": {
            ip_pos: {"Action": "Raise", "Amount": 2.5, "Cards": spot.hero_combo if spot.hero_position == ip_pos else ""},
            oop_pos: {"Action": "Call", "Amount": 2.5, "Cards": spot.hero_combo if spot.hero_position == oop_pos else ""},
        },
    }

    # Add flop action
    if spot.street in ("flop", "turn", "river"):
        action["flop"] = {"Cards": spot.board[:6] if len(spot.board) >= 6 else spot.board}

        # Parse tree path to add actions
        path_parts = spot.tree_path.split(":")[2:]  # Skip "r" and "0"
        current_player = 1  # OOP acts first

        for part in path_parts:
            player_name = oop_pos if current_player == 1 else ip_pos
            if part == "c":
                action["flop"][player_name] = {"Action": "Check"}
            elif part.startswith("b"):
                try:
                    amount = int(part[1:]) / 1_000_000  # Convert to BB
                    action["flop"][player_name] = {"Action": "Bet", "Amount": amount}
                except ValueError:
                    action["flop"][player_name] = {"Action": "Bet"}
            current_player = 1 - current_player

    return action


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
