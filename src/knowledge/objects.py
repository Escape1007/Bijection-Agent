"""Combinatorial objects controlled vocabulary.

Every bijection's ``source_objects`` and ``target_objects`` must resolve to
canonical names from this table.  Aliases handle the many synonyms found in
the literature (e.g. "ballot sequence" → "dyck_path").  The ``base_type`` and
``oeis_cardinality`` fields power fallback search and bridge discovery.

Usage
-----
::

    from src.knowledge.objects import COMBINATORIAL_OBJECTS, normalize_object

    canonical = normalize_object("ballot sequence")   # → "dyck_path"
    info = COMBINATORIAL_OBJECTS[canonical]

Expanding
---------
Add new entries as needed.  When arXiv crawling produces an unknown object
that appears frequently, promote it from ``CUSTOM_*`` to a proper entry.
"""

from __future__ import annotations

from typing import Optional

# ------------------------------------------------------------------
# Core table
# ------------------------------------------------------------------

CombinatorialObject = dict  # {aliases, base_type, oeis_cardinality, default_stats, catalan_family}

COMBINATORIAL_OBJECTS: dict[str, CombinatorialObject] = {

    # === Catalan family (oeis A000108) ===

    "dyck_path": {
        "aliases": ["dyck_word", "ballot_sequence", "dyck_lattice_path", "ballot_path"],
        "base_type": "LatticePath",
        "oeis_cardinality": "A000108",
        "default_stats": ["semilength", "area", "peaks", "valleys", "returns_to_zero"],
        "catalan_family": True,
    },

    "binary_tree": {
        "aliases": ["full_binary_tree", "rooted_binary_tree", "complete_binary_tree",
                    "binary_tree_plane", "ordered_binary_tree"],
        "base_type": "Tree",
        "oeis_cardinality": "A000108",
        "default_stats": ["internal_nodes", "leaves", "left_edges", "right_edges", "height"],
        "catalan_family": True,
    },

    "plane_tree": {
        "aliases": ["ordered_tree", "rooted_tree", "planted_tree", "catalan_tree"],
        "base_type": "Tree",
        "oeis_cardinality": "A000108",
        "default_stats": ["nodes", "leaves", "degree_sequence"],
        "catalan_family": True,
    },

    "noncrossing_partition": {
        "aliases": ["non_crossing_partition", "noncrossing_set_partition", "nc_partition"],
        "base_type": "SetPartition",
        "oeis_cardinality": "A000108",
        "default_stats": ["num_blocks", "block_sizes", "singletons"],
        "catalan_family": True,
    },

    "nonnesting_partition": {
        "aliases": ["non_nesting_partition", "nn_partition"],
        "base_type": "SetPartition",
        "oeis_cardinality": "A000108",
        "default_stats": ["num_blocks", "block_sizes"],
        "catalan_family": True,
    },

    "pattern_avoiding_permutation": {
        "aliases": ["pattern_avoiding_perm", "restricted_permutation"],
        "base_type": "Permutation",
        "oeis_cardinality": "A000108",  # for 312-avoiding, 321-avoiding
        "default_stats": ["length", "inversions", "descents", "pattern"],
        "catalan_family": True,
    },

    "standard_young_tableau": {
        "aliases": ["syt", "standard_tableau", "standard_young_tableaux"],
        "base_type": "Tableau",
        "oeis_cardinality": "A000108",  # when shape is 2×n
        "default_stats": ["shape", "major_index", "charge"],
        "catalan_family": True,
    },

    "noncrossing_matching": {
        "aliases": ["non_crossing_matching", "noncrossing_perfect_matching",
                    "noncrossing_arc_diagram"],
        "base_type": "Matching",
        "oeis_cardinality": "A000108",
        "default_stats": ["num_arcs", "nesting_number"],
        "catalan_family": True,
    },

    # === Permutation / Pattern families ===

    "permutation": {
        "aliases": ["perm", "permutations", "symmetric_group"],
        "base_type": "Permutation",
        "oeis_cardinality": "A000142",  # n!
        "default_stats": ["length", "inversions", "descents", "excedances",
                          "major_index", "fixed_points", "cycles"],
        "catalan_family": False,
    },

    "involution": {
        "aliases": ["involutions", "self_inverse_permutation"],
        "base_type": "Permutation",
        "oeis_cardinality": "A000085",  # telephone numbers
        "default_stats": ["length", "fixed_points", "transpositions"],
        "catalan_family": False,
    },

    "alternating_permutation": {
        "aliases": ["up_down_permutation", "zigzag_permutation", "alternating_perm"],
        "base_type": "Permutation",
        "oeis_cardinality": "A000111",  # Euler zigzag numbers
        "default_stats": ["length", "descents"],
        "catalan_family": False,
    },

    # === Partition / Composition families ===

    "integer_partition": {
        "aliases": ["partition", "integer_partitions", "number_partition",
                    "unrestricted_partition"],
        "base_type": "Partition",
        "oeis_cardinality": "A000041",  # p(n)
        "default_stats": ["size", "num_parts", "largest_part", "durfee_square", "rank"],
        "catalan_family": False,
    },

    "set_partition": {
        "aliases": ["set_partitions", "bell_partition", "set_partitioning"],
        "base_type": "SetPartition",
        "oeis_cardinality": "A000110",  # Bell numbers
        "default_stats": ["num_elements", "num_blocks", "block_sizes"],
        "catalan_family": False,
    },

    "composition": {
        "aliases": ["compositions", "ordered_partition", "integer_composition"],
        "base_type": "Composition",
        "oeis_cardinality": "A011782",  # 2^(n-1)
        "default_stats": ["size", "num_parts", "largest_part"],
        "catalan_family": False,
    },

    "integer_sequence": {
        "aliases": ["integer_sequences", "weighted_composition", "integer_list"],
        "base_type": "Sequence",
        "oeis_cardinality": "",
        "default_stats": ["length", "sum", "max"],
        "catalan_family": False,
    },

    # === Tableau families ===

    "standard_young_tableau_pair": {
        "aliases": ["syt_pair", "rsk_pair", "p_q_tableaux"],
        "base_type": "Tableau",
        "oeis_cardinality": "",  # number of SYT pairs of same shape = n!
        "default_stats": ["shape", "insertion_tableau", "recording_tableau"],
        "catalan_family": False,
    },

    "semistandard_young_tableau": {
        "aliases": ["ssyt", "semistandard_tableau"],
        "base_type": "Tableau",
        "oeis_cardinality": "",
        "default_stats": ["shape", "max_entry", "charge", "cocharge"],
        "catalan_family": False,
    },

    # === Lattice path families ===

    "motzkin_path": {
        "aliases": ["motzkin", "motzkin_lattice_path", "motzkin_word"],
        "base_type": "LatticePath",
        "oeis_cardinality": "A001006",  # Motzkin numbers
        "default_stats": ["length", "area", "peaks", "valleys", "level_steps"],
        "catalan_family": False,
    },

    "schroeder_path": {
        "aliases": ["schröder_path", "schroder_lattice_path", "large_schroeder_path"],
        "base_type": "LatticePath",
        "oeis_cardinality": "A006318",  # large Schröder numbers
        "default_stats": ["length", "area", "diagonal_steps", "peaks"],
        "catalan_family": False,
    },

    # === Graph / Geometric families ===

    "graph": {
        "aliases": ["graphs", "simple_graph", "undirected_graph"],
        "base_type": "Graph",
        "oeis_cardinality": "",
        "default_stats": ["vertices", "edges", "connected_components"],
        "catalan_family": False,
    },

    "spanning_tree": {
        "aliases": ["spanning_trees", "tree_subgraph"],
        "base_type": "Graph",
        "oeis_cardinality": "",
        "default_stats": ["num_vertices", "num_edges"],
        "catalan_family": False,
    },

    "dissection": {
        "aliases": ["polygon_dissection", "triangulation_dual"],
        "base_type": "Geometric",
        "oeis_cardinality": "A000108",  # polygon triangulations
        "default_stats": ["num_vertices", "num_regions"],
        "catalan_family": True,
    },

    # === Parking / Mapping families ===

    "parking_function": {
        "aliases": ["parking_functions", "pf"],
        "base_type": "Parking",
        "oeis_cardinality": "A000272",  # (n+1)^(n-1)
        "default_stats": ["length", "area", "dinv", "lucky_cars"],
        "catalan_family": False,
    },

    "increasing_tree": {
        "aliases": ["recursive_tree", "increasing_binary_tree", "heap_ordered_tree"],
        "base_type": "Tree",
        "oeis_cardinality": "A000142",  # n! (increasing binary trees)
        "default_stats": ["nodes", "leaves", "root_label"],
        "catalan_family": False,
    },
}

# ------------------------------------------------------------------
# Lookup helpers
# ------------------------------------------------------------------

# Build reverse index: alias → canonical name
_alias_to_canonical: dict[str, str] = {}
for _canonical, _meta in COMBINATORIAL_OBJECTS.items():
    _alias_to_canonical[_canonical] = _canonical
    for _a in _meta.get("aliases", []):
        _alias_to_canonical[_a] = _canonical
    # Also register the canonical with underscores replaced
    _alias_to_canonical[_canonical.replace("_", " ")] = _canonical


def normalize_object(raw: str) -> str:
    """Map a raw object name to its canonical form.

    Returns the canonical name if found.  If not found, returns the original
    string — the caller (e.g. the ingestion pipeline) can decide whether to
    add it as ``CUSTOM_<raw>`` or trigger LLM alignment.
    """
    cleaned = raw.strip().lower().replace("-", " ").replace("  ", " ").replace(" ", "_")
    # Try exact alias match
    if cleaned in _alias_to_canonical:
        return _alias_to_canonical[cleaned]
    # Try removing common suffixes
    if cleaned.endswith("s") and cleaned[:-1] in _alias_to_canonical:
        return _alias_to_canonical[cleaned[:-1]]
    return raw  # Unknown — caller handles


def get_object_info(name: str) -> Optional[CombinatorialObject]:
    """Return the metadata dict for a canonical object name, or None."""
    return COMBINATORIAL_OBJECTS.get(name)


def list_canonical_names() -> list[str]:
    """All canonical object names."""
    return list(COMBINATORIAL_OBJECTS.keys())


def list_by_base_type(base_type: str) -> list[str]:
    """All canonical names sharing a base_type."""
    return [n for n, m in COMBINATORIAL_OBJECTS.items()
            if m.get("base_type") == base_type]


def list_by_oeis(oeis_id: str) -> list[str]:
    """All canonical names sharing an OEIS ID."""
    if not oeis_id:
        return []
    return [n for n, m in COMBINATORIAL_OBJECTS.items()
            if m.get("oeis_cardinality") == oeis_id]
