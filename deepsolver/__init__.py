"""Deepsolver API client for poker GTO simulations."""

from .client import DeepsolverClient
from .config import get_api_token
from .hand_utils import (
    HAND_ORDER,
    HAND_TO_INDEX,
    combo_to_index,
    index_to_combo,
    normalize_combo,
    is_combo_blocked,
    get_unblocked_combos,
)
from .ranges import (
    parse_range_string,
    range_to_string,
    empty_range,
    full_range,
    count_combos,
    get_combos_in_range,
)
from .preflop_ranges import (
    get_rfi_range,
    get_defend_range,
)
from .request_builder import (
    SpotConfig,
    RequestBuilder,
    srp_utg_vs_bb,
    srp_co_vs_bb,
    srp_btn_vs_bb,
    describe_request,
)
from .tree_parser import (
    TreeNode,
    parse_tree,
    get_node_by_path,
    find_decision_nodes,
    get_strategy_for_combo,
    get_ev_for_combo,
    get_ev_by_action,
    format_action,
    count_nodes,
    get_actions_at_node,
    get_ranges_at_node,
)
from .spot_extractor import (
    SpotCandidate,
    SpotExtractor,
    categorize_hand,
    categorize_board,
    extract_random_river_spot,
    extract_random_spot_same_street,
)

__all__ = [
    # Client
    "DeepsolverClient",
    "get_api_token",
    # Hand utilities
    "HAND_ORDER",
    "HAND_TO_INDEX",
    "combo_to_index",
    "index_to_combo",
    "normalize_combo",
    "is_combo_blocked",
    "get_unblocked_combos",
    # Ranges
    "parse_range_string",
    "range_to_string",
    "empty_range",
    "full_range",
    "count_combos",
    "get_combos_in_range",
    # Preflop ranges
    "get_rfi_range",
    "get_defend_range",
    # Request builder
    "SpotConfig",
    "RequestBuilder",
    "srp_utg_vs_bb",
    "srp_co_vs_bb",
    "srp_btn_vs_bb",
    "describe_request",
    # Tree parser
    "TreeNode",
    "parse_tree",
    "get_node_by_path",
    "find_decision_nodes",
    "get_strategy_for_combo",
    "get_ev_for_combo",
    "get_ev_by_action",
    "format_action",
    "count_nodes",
    "get_actions_at_node",
    "get_ranges_at_node",
    # Spot extractor
    "SpotCandidate",
    "SpotExtractor",
    "categorize_hand",
    "categorize_board",
    "extract_random_river_spot",
    "extract_random_spot_same_street",
]
