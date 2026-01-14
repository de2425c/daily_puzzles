# Deepsolver Puzzle Generation System - Implementation Plan

## Project Goal

Build an end-to-end pipeline that:
1. Calls the Deepsolver API to run GTO poker simulations
2. Parses solver output to extract interesting decision points ("spots")
3. Provides a review interface to approve spots and add puzzle metadata
4. Saves approved puzzles to Firestore for consumption by the iOS app

---

## Current State

### What Exists
- **iOS App**: Consumes puzzles from Firestore `daily_puzzles` collection
- **Puzzle Schema**: Defined format with Action, AnswerOptions, Explanation, etc.
- **Upload Scripts**: Python scripts to push puzzles to Firestore (`backend/upload_puzzles.py`)
- **Sample Files**:
  - `deepsolver-request-flop.json` - example API request
  - `flop-response (1).json` - example API response (~34MB)
  - `solver_hand_order.txt` - canonical 1326 combo ordering

### What's Missing
- API client to communicate with Deepsolver
- Tools to build solver requests programmatically
- Parser to extract spots from solver results
- Storage for spot candidates awaiting review
- Admin interface for curation

---

## Phase 1: Deepsolver API Client

### Objective
Create a reliable Python client to submit solver tasks and retrieve results.

### Deliverables

**File: `deepsolver/client.py`**

```python
class DeepsolverClient:
    def __init__(self, api_token: str, base_url: str = "https://gcp-fn-treebuilder.prod-eu01.deepsolver.cloud")

    def schedule(self, request: dict) -> str:
        """POST /task/binary/cfr/schedule - returns task_id"""

    def get_result(self, task_id: str) -> dict | None:
        """GET /task/binary/cfr/result/files/{task_id} - returns result or None if not ready"""

    def run_and_wait(self, request: dict, timeout_seconds: int = 300, poll_interval: int = 5) -> dict:
        """Schedule task and poll until complete"""
```

### Key Implementation Details
- Auth header: `Authorization: Token <API_TOKEN>`
- 404 response means "still processing" - not an error
- Response includes `queue_pos` and `queue_eta` estimates
- Result endpoints: `/result/{id}` (paths), `/result/url/{id}` (signed URLs), `/result/files/{id}` (inline JSON)

### Test Criteria
- [ ] Submit `deepsolver-request-flop.json` to API
- [ ] Poll until result is ready
- [ ] Verify response structure matches `flop-response (1).json`
- [ ] Handle timeout gracefully
- [ ] Handle API errors (auth, rate limits)

### Dependencies
- `requests` library
- Environment variable or config for API token

---

## Phase 2: Hand & Range Utilities

### Objective
Work with poker hands in the solver's 1326-combo format.

### Deliverables

**File: `deepsolver/hand_utils.py`**

```python
# Load canonical ordering from solver_hand_order.txt
HAND_ORDER: list[str]  # ["2d2c", "2h2c", "2h2d", ...]
HAND_TO_INDEX: dict[str, int]  # {"2d2c": 0, "2h2c": 1, ...}

def combo_to_index(combo: str) -> int:
    """Convert 'AhKh' to index 0-1325"""

def index_to_combo(index: int) -> int:
    """Convert index to combo string"""

def normalize_combo(combo: str) -> str:
    """Ensure consistent format: higher card first, suits in order"""

def is_combo_blocked(combo: str, board: str) -> bool:
    """Check if combo shares cards with board"""
```

**File: `deepsolver/ranges.py`**

```python
def parse_range_string(range_str: str) -> list[int]:
    """
    Convert 'AA,KK,QQ,AKs,AKo' to 1326-element weight array.
    Supports: pairs (AA), suited (AKs), offsuit (AKo), all (AK)
    """

def range_to_string(weights: list[int], threshold: int = 5000) -> str:
    """Convert weight array back to human-readable range"""

# Standard ranges (weights 0-10000)
UTG_RFI: list[int]
HJ_RFI: list[int]
CO_RFI: list[int]
BTN_RFI: list[int]
SB_RFI: list[int]

BB_DEFEND_VS_UTG: list[int]
BB_DEFEND_VS_BTN: list[int]
# ... etc
```

### Key Implementation Details
- Solver uses weights 0-10000 (not 0-1)
- Combos blocked by board cards should have weight 0
- Range strings use standard poker notation

### Test Criteria
- [ ] Round-trip: combo → index → combo
- [ ] Parse "AA,KK,AKs" correctly
- [ ] Blocked combos detected (e.g., "AhKh" blocked by "Ah" on board)
- [ ] Standard ranges have expected combo counts

---

## Phase 3: Request Builder

### Objective
High-level API to construct solver requests for common scenarios.

### Deliverables

**File: `deepsolver/request_builder.py`**

```python
@dataclass
class SpotConfig:
    board: str  # "As7d2c"
    ip_range: list[int]  # 1326 weights
    oop_range: list[int]
    pot_size: int  # in cents (4500000 = $45)
    effective_stack: int  # in cents
    street_id: int  # 1=flop, 2=turn, 3=river
    ip_position: str  # "UTG", "BTN", etc
    oop_position: str

class RequestBuilder:
    def __init__(self, config: SpotConfig)

    def with_sizings(self, ip_sizings: dict, oop_sizings: dict) -> Self:
        """Set bet sizings as pot fractions"""

    def with_iterations(self, iters: int) -> Self:
        """Set solver iterations (default 500)"""

    def build(self) -> dict:
        """Generate complete API request payload"""

# Preset builders
def srp_utg_vs_bb(board: str, stacks_bb: int = 100) -> RequestBuilder:
    """Single raised pot, UTG open, BB defend"""

def srp_btn_vs_bb(board: str, stacks_bb: int = 100) -> RequestBuilder:
    """Single raised pot, BTN open, BB defend"""

def threbet_pot_ip(board: str, opener: str, defender: str) -> RequestBuilder:
    """3bet pot where hero is IP"""
```

### Key Implementation Details
- `pot_fractions` structure: `[IP][OOP] → [preflop, flop, turn, river] → [bet, raise, 3bet, 4+bet] → [sizes]`
- Sizes are pot fractions > 0 (check is automatic, not a sizing)
- `all_in_threshold` collapses large bets into all-in
- Stack sizes in micro-cents (100bb @ $1/$2 = 200 * 100 * 10000 = 200,000,000? Need to verify units)

### Test Criteria
- [ ] Build request matches structure of `deepsolver-request-flop.json`
- [ ] Run built request through API successfully
- [ ] Different presets produce valid trees

---

## Phase 4: Response Parser & Spot Extractor

### Objective
Parse solver output to find interesting decision points suitable for puzzles.

### Deliverables

**File: `deepsolver/tree_parser.py`**

```python
@dataclass
class TreeNode:
    id: str
    path: str  # _pio_path
    player_id: int | None
    street_id: int
    pot_size: int
    actions: list[tuple[str, int]] | None  # [("C", 0), ("B", 1485000)]
    strategy: np.ndarray | None  # shape (num_actions, 1326)
    ev: np.ndarray | None  # shape (2, 1326) for both players
    children: list["TreeNode"]

def parse_tree(raw_tree: dict) -> TreeNode:
    """Convert raw JSON tree to structured TreeNode"""

def find_decision_nodes(tree: TreeNode, player_id: int = None) -> list[TreeNode]:
    """Find all nodes where a decision is made"""

def get_node_by_path(tree: TreeNode, path: str) -> TreeNode:
    """Navigate to specific node by _pio_path"""

def get_strategy_for_combo(node: TreeNode, combo_index: int) -> dict[str, float]:
    """Return action frequencies for a specific hand"""
    # e.g., {"Check": 0.15, "Bet 33%": 0.85}

def get_ev_for_combo(node: TreeNode, player_id: int, combo_index: int) -> float:
    """Return EV for a specific hand at this node"""
```

**File: `deepsolver/spot_extractor.py`**

```python
@dataclass
class SpotCandidate:
    # Identification
    id: str  # UUID
    source_task_id: str

    # Game state
    board: str
    hero_combo: str
    hero_position: str
    villain_position: str
    street: str  # "flop", "turn", "river"
    pot_size_bb: float
    effective_stacks_bb: float
    action_sequence: str  # "UTG raises, BB calls, flop checks to hero"
    tree_path: str

    # Decision info
    available_actions: list[str]  # ["Check", "Bet small", "Bet medium"]
    action_frequencies: dict[str, float]  # {"Check": 0.05, "Bet small": 0.80, "Bet medium": 0.15}
    correct_action: str  # highest frequency action
    ev_by_action: dict[str, float]
    ev_loss_for_second_best: float  # EV difference vs best action

    # Metadata for filtering
    hand_category: str  # "top_pair", "overpair", "draw", "air"
    board_texture: str  # "dry", "wet", "paired"
    spot_type: str  # "cbet", "check_raise", "barrel"

    # Curation status
    status: str  # "pending", "approved", "rejected"
    created_at: datetime

class SpotExtractor:
    def __init__(self, min_frequency: float = 0.75, min_ev_gap: float = 0.5):
        """
        min_frequency: minimum frequency for "correct" action (0.75 = 75%)
        min_ev_gap: minimum EV difference in BB between best and 2nd best
        """

    def extract_spots(self, tree: TreeNode, config: SpotConfig) -> list[SpotCandidate]:
        """Find all interesting spots in the tree"""

    def categorize_hand(self, combo: str, board: str) -> str:
        """Classify hand strength: top_pair, overpair, draw, etc."""

    def categorize_board(self, board: str) -> str:
        """Classify texture: dry, wet, monotone, paired, etc."""
```

### Key Implementation Details
- Strategy array shape: `(num_actions, 1326)` - probabilities for each action per combo
- EV array shape: `(2, 1326)` - EV for both players per combo
- Action codes: "C" = check/call, "F" = fold, "B" = bet/raise, "A" = all-in
- Filter out blocked combos (hero can't hold cards on the board)
- "Clear" spots: one action has significantly higher frequency than others

### Test Criteria
- [ ] Parse `flop-response (1).json` into TreeNode structure
- [ ] Navigate tree using paths
- [ ] Extract strategy for specific combos
- [ ] Find 10+ spot candidates from sample response
- [ ] Hand categorization is reasonable

---

## Phase 5: Candidate Storage

### Objective
Store extracted spots for review and approved puzzles for the iOS app.

### Deliverables

**File: `storage/models.py`**

```python
@dataclass
class SpotCandidate:
    # ... (as defined in Phase 4)

    def to_firestore(self) -> dict:
        """Convert to Firestore document format"""

    @classmethod
    def from_firestore(cls, doc: dict) -> "SpotCandidate":
        """Create from Firestore document"""

@dataclass
class ApprovedPuzzle:
    """Matches the schema consumed by iOS app"""
    puzzle_id: int
    title: str
    question_text: str
    structure: str
    effective_stacks: int
    hero: str
    action: dict  # preflop/flop/turn/river action tree
    pot_size_at_decision: float
    answer_options: list[str]
    correct_answer: str
    explanation: str
    difficulty: int
    tags: list[str]

    def to_firestore(self) -> dict:
        """Convert to format expected by iOS app"""
```

**File: `storage/firestore.py`**

```python
class PuzzleStorage:
    def __init__(self, credentials_path: str = None):
        """Initialize Firestore client"""

    # Spot candidates
    def save_candidate(self, spot: SpotCandidate) -> str:
        """Save to spot_candidates collection, return doc ID"""

    def get_pending_candidates(self, limit: int = 50) -> list[SpotCandidate]:
        """Get candidates awaiting review"""

    def update_candidate_status(self, id: str, status: str):
        """Update status: pending → approved/rejected"""

    # Approved puzzles
    def save_puzzle(self, puzzle: ApprovedPuzzle) -> str:
        """Save to daily_puzzles collection"""

    def get_next_puzzle_id(self) -> int:
        """Get next available puzzle ID"""

    def get_all_puzzles(self) -> list[ApprovedPuzzle]:
        """List all approved puzzles"""
```

### Firestore Collections

```
spot_candidates/
  {doc_id}/
    id: string
    board: string
    hero_combo: string
    ...
    status: "pending" | "approved" | "rejected"
    created_at: timestamp

daily_puzzles/
  {puzzle_id}/
    PuzzleID: number
    Title: string
    QuestionText: string
    ... (matches iOS schema)
```

### Test Criteria
- [ ] Save SpotCandidate to Firestore
- [ ] Retrieve pending candidates
- [ ] Updat
e status to approved
- [ ] Convert candidate to ApprovedPuzzle format
- [ ] Save puzzle in format iOS app expects

---

## Phase 6: Admin CLI

### Objective
Command-line interface for reviewing and approving spot candidates.

### Deliverables

**File: `cli/admin.py`**

```python
# Commands:

# List pending spots
# $ python -m cli.admin list
# Shows: ID, Board, Hero Hand, Correct Action, Frequency

# View spot details
# $ python -m cli.admin view <id>
# Shows: Full spot info, action frequencies, EVs

# Approve spot (interactive)
# $ python -m cli.admin approve <id>
# Prompts for: Title, QuestionText, Explanation, Difficulty, Tags
# Then saves to daily_puzzles

# Reject spot
# $ python -m cli.admin reject <id>
# Marks as rejected

# Bulk operations
# $ python -m cli.admin export --format json
# Exports all approved puzzles

# Stats
# $ python -m cli.admin stats
# Shows: pending count, approved count, by difficulty, etc.
```

### Interactive Approval Flow

```
$ python -m cli.admin approve abc123

=== SPOT DETAILS ===
Board: As7d2c
Hero: UTG (AhKh)
Villain: BB
Pot: 4.5bb | Stacks: 100bb
Action: UTG opens 2.5bb, BB calls

Available Actions:
  [1] Check      - 5%   (EV: 2.15bb)
  [2] Bet small  - 82%  (EV: 2.89bb)  ← RECOMMENDED
  [3] Bet medium - 13%  (EV: 2.67bb)

Enter puzzle details:
Title: Ace-High Autopilot
Question: UTG opens, BB calls. A-7-2 rainbow. BB checks. Your move?
Explanation: This is a classic range-advantage spot...
Difficulty [1-3]: 1
Tags (comma-separated): cash,6max,100bb,flop,cbet,value_bet

Confirm save? [y/n]: y
Saved as puzzle #12!
```

### Test Criteria
- [ ] List shows pending candidates
- [ ] View displays all relevant info
- [ ] Approve flow creates valid puzzle
- [ ] Puzzle appears in iOS app

---

## Phase 7: Batch Generation Pipeline

### Objective
Automate generation of many spot candidates.

### Deliverables

**File: `batch/runner.py`**

```python
@dataclass
class BatchConfig:
    boards: list[str]  # Boards to analyze
    scenarios: list[str]  # ["srp_utg_vs_bb", "srp_btn_vs_bb", ...]
    stacks: list[int]  # [100, 200] (in BB)
    iterations: int  # Solver iterations per request

class BatchRunner:
    def __init__(self, client: DeepsolverClient, storage: PuzzleStorage)

    async def run_batch(self, config: BatchConfig) -> BatchResult:
        """
        1. Generate all request combinations
        2. Submit to API (with rate limiting)
        3. Collect results
        4. Extract spots from each result
        5. Save candidates to storage
        """

    def generate_boards(self, count: int, texture: str = None) -> list[str]:
        """Generate random boards, optionally filtered by texture"""
```

**File: `batch/board_generator.py`**

```python
def random_board(cards: int = 3) -> str:
    """Generate random flop/turn/river"""

def generate_by_texture(texture: str, count: int) -> list[str]:
    """
    Generate boards matching texture:
    - "dry": rainbow, unpaired, unconnected
    - "wet": flush draws, straight draws
    - "paired": board pair
    - "monotone": three of one suit
    """
```

### Example Batch Run

```python
config = BatchConfig(
    boards=generate_by_texture("dry", 20) + generate_by_texture("wet", 20),
    scenarios=["srp_utg_vs_bb", "srp_btn_vs_bb", "srp_co_vs_bb"],
    stacks=[100],
    iterations=500
)

# This would generate 40 boards × 3 scenarios = 120 solver runs
# Each run might produce 20-50 interesting spots
# Result: 2,000-6,000 spot candidates for review
```

### Test Criteria
- [ ] Generate valid random boards
- [ ] Rate limit API requests appropriately
- [ ] Handle partial failures gracefully
- [ ] Candidates appear in storage after batch completes

---

## Phase 8: Web Admin UI (Future)

### Objective
Replace CLI with a web-based review interface.

### Potential Stack
- **Backend**: FastAPI (matches existing poker_backend)
- **Frontend**: React + TailwindCSS
- **Hosting**: Cloud Run (matches existing infra)

### Features
- Visual card rendering
- Drag-and-drop sorting for answer options
- Rich text for explanations
- Preview puzzle as it would appear in app
- Batch approve/reject
- Analytics on puzzle completion rates

*This phase is optional and can be deferred until the CLI-based workflow is proven.*

---

## File Structure

```
daily_puzzles/
├── IMPLEMENTATION_PLAN.md      # This document
├── requirements.txt            # Python dependencies
├── .env.example               # Template for API keys
│
├── deepsolver/
│   ├── __init__.py
│   ├── client.py              # Phase 1: API client
│   ├── hand_utils.py          # Phase 2: Combo/index conversion
│   ├── ranges.py              # Phase 2: Range parsing & presets
│   └── request_builder.py     # Phase 3: Request construction
│   └── tree_parser.py         # Phase 4: Response parsing
│   └── spot_extractor.py      # Phase 4: Spot extraction logic
│
├── storage/
│   ├── __init__.py
│   ├── models.py              # Phase 5: Data models
│   └── firestore.py           # Phase 5: Database operations
│
├── cli/
│   ├── __init__.py
│   └── admin.py               # Phase 6: Admin commands
│
├── batch/
│   ├── __init__.py
│   ├── runner.py              # Phase 7: Batch orchestration
│   └── board_generator.py     # Phase 7: Board generation
│
├── tests/
│   ├── test_client.py
│   ├── test_hand_utils.py
│   ├── test_ranges.py
│   ├── test_request_builder.py
│   ├── test_tree_parser.py
│   ├── test_spot_extractor.py
│   └── test_storage.py
│
├── data/
│   ├── solver_hand_order.txt  # Canonical combo ordering (exists)
│   ├── ranges/                # Standard range definitions
│   │   ├── utg_rfi.txt
│   │   ├── btn_rfi.txt
│   │   └── ...
│   └── sample_responses/      # For testing
│       └── flop-response.json
│
└── scripts/
    ├── run_single_solve.py    # Quick one-off solver run
    └── seed_candidates.py     # Populate initial candidates
```

---

## Dependencies

```
# requirements.txt
requests>=2.28.0
firebase-admin>=6.0.0
numpy>=1.24.0
click>=8.0.0          # CLI framework
python-dotenv>=1.0.0  # Environment variables
pytest>=7.0.0         # Testing
pytest-asyncio>=0.21  # Async test support
```

---

## Environment Variables

```
# .env
DEEPSOLVER_API_TOKEN=your_token_here
GOOGLE_APPLICATION_CREDENTIALS=/path/to/firebase-credentials.json
```

---

## Milestones & Checkpoints

### Milestone 1: "Hello Solver" (Phases 1-2)
- [ ] API client can submit and retrieve results
- [ ] Hand utilities work correctly
- **Deliverable**: Script that runs a solve and prints the root node strategy

### Milestone 2: "Spot Found" (Phases 3-4)
- [ ] Request builder creates valid requests
- [ ] Parser extracts spots from responses
- **Deliverable**: Script that finds 10 puzzle candidates from a solve

### Milestone 3: "Puzzle Created" (Phases 5-6)
- [ ] Candidates stored in Firestore
- [ ] CLI can approve and create puzzles
- **Deliverable**: New puzzle visible in iOS app

### Milestone 4: "Pipeline Running" (Phase 7)
- [ ] Batch generation works
- [ ] 100+ candidates in queue for review
- **Deliverable**: Sustainable puzzle generation workflow

---

## Open Questions

1. **What's the Deepsolver API token?** Need to get this from Deepsolver.

2. **Pot size units in API?** The sample shows `4500000` - need to confirm this is micro-cents or another unit.

3. **Range sources?** Where to get accurate preflop ranges? Options:
   - Use simplified approximations
   - Import from GTO Wizard or similar
   - Run preflop solves

4. **Spot selection criteria?** Need to define what makes a "good" puzzle:
   - Minimum action frequency threshold?
   - Minimum EV difference?
   - Which hand categories are most educational?

5. **Existing puzzle ID scheme?** Current puzzles use sequential IDs 1-11. How to handle:
   - Continue sequence?
   - Use date-based IDs?
   - Use UUIDs?

---

## Next Steps

1. **Set up project structure** - Create directories and files
2. **Get API token** - Obtain from Deepsolver
3. **Implement Phase 1** - API client with tests
4. **Iterate through phases** - Build, test, refine

Ready to begin implementation when you give the go-ahead.
