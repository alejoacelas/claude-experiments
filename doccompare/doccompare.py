#!/usr/bin/env python3
"""
doccompare - A block-based document comparison tool designed for AI agent consumption.

Unlike standard diff tools that show line-by-line changes, doccompare:
1. Splits documents into semantic blocks (sections, paragraphs, code blocks)
2. Identifies anchor points - shared text that exists in both documents
3. Aligns blocks between documents using anchors
4. Presents differences block-by-block with clear labeling
5. Supports selective application of changes from one document to another

This tool is designed to give AI agents a structured, manageable view of
document differences, especially for complex edits involving rearrangements,
insertions, deletions, and rewrites.
"""

import argparse
import difflib
import hashlib
import json
import os
import re
import sys
import textwrap
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class BlockType(Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    CODE = "code"
    LIST = "list"
    TABLE = "table"
    EQUATION = "equation"
    ENVIRONMENT = "environment"  # LaTeX environments
    METADATA = "metadata"  # frontmatter, preamble
    BLANK = "blank"
    COMMENT = "comment"


class ChangeType(Enum):
    UNCHANGED = "unchanged"
    MODIFIED = "modified"
    ADDED = "added"
    DELETED = "deleted"
    MOVED = "moved"
    MOVED_AND_MODIFIED = "moved_and_modified"


@dataclass
class Block:
    """A semantic block within a document."""
    id: str
    block_type: str  # BlockType value
    content: str
    line_start: int
    line_end: int
    heading_level: int = 0  # For heading blocks
    section_path: str = ""  # e.g. "Section 2 > Subsection 2.1"
    fingerprint: str = ""  # Content hash for matching

    def __post_init__(self):
        if not self.fingerprint:
            # Normalize whitespace for fingerprinting
            normalized = re.sub(r'\s+', ' ', self.content.strip())
            self.fingerprint = hashlib.md5(normalized.encode()).hexdigest()[:12]

    def normalized_content(self) -> str:
        """Return whitespace-normalized content for comparison."""
        return re.sub(r'\s+', ' ', self.content.strip())


@dataclass
class BlockAlignment:
    """Alignment between blocks in two documents."""
    change_type: str  # ChangeType value
    block_a: Optional[dict] = None  # Block from doc A (as dict)
    block_b: Optional[dict] = None  # Block from doc B (as dict)
    similarity: float = 0.0
    diff_summary: str = ""
    char_changes: int = 0
    move_info: str = ""  # Description of where block moved from/to


@dataclass
class ComparisonResult:
    """Full comparison result between two documents."""
    file_a: str
    file_b: str
    doc_type: str
    total_blocks_a: int
    total_blocks_b: int
    summary: dict = field(default_factory=dict)
    alignments: list = field(default_factory=list)
    anchors: list = field(default_factory=list)


# ─── Document Parsing ────────────────────────────────────────────────────────

def detect_doc_type(content: str) -> str:
    """Detect whether document is LaTeX, Markdown, or plain text."""
    if r'\documentclass' in content or r'\begin{document}' in content:
        return 'latex'
    if re.search(r'^#{1,6}\s', content, re.MULTILINE):
        return 'markdown'
    return 'text'


def parse_latex(content: str) -> list[Block]:
    """Parse LaTeX document into semantic blocks."""
    lines = content.split('\n')
    blocks = []
    block_id = 0
    current_section_path = []

    # Identify preamble (before \begin{document})
    in_preamble = True
    preamble_lines = []
    body_start = 0

    for i, line in enumerate(lines):
        if r'\begin{document}' in line:
            in_preamble = False
            body_start = i + 1
            preamble_lines.append(line)
            break
        preamble_lines.append(line)

    if preamble_lines:
        blocks.append(Block(
            id=f"B{block_id:03d}",
            block_type=BlockType.METADATA.value,
            content='\n'.join(preamble_lines),
            line_start=1,
            line_end=body_start,
        ))
        block_id += 1

    # Parse body
    i = body_start
    current_block_lines = []
    current_block_start = i + 1
    current_block_type = BlockType.PARAGRAPH

    # LaTeX environment tracking
    env_stack = []

    def flush_block():
        nonlocal block_id, current_block_lines, current_block_start, current_block_type
        text = '\n'.join(current_block_lines).strip()
        if text:
            blocks.append(Block(
                id=f"B{block_id:03d}",
                block_type=current_block_type.value,
                content=text,
                line_start=current_block_start,
                line_end=current_block_start + len(current_block_lines) - 1,
                section_path=' > '.join(current_section_path) if current_section_path else '',
            ))
            block_id += 1
        current_block_lines = []
        current_block_type = BlockType.PARAGRAPH

    heading_pattern = re.compile(
        r'\\(section|subsection|subsubsection|paragraph|chapter)\*?\{(.+?)\}'
    )
    env_begin = re.compile(r'\\begin\{(\w+)\}')
    env_end = re.compile(r'\\end\{(\w+)\}')
    math_envs = {'equation', 'align', 'gather', 'multline', 'eqnarray'}
    code_envs = {'verbatim', 'lstlisting', 'minted'}
    list_envs = {'itemize', 'enumerate', 'description'}
    table_envs = {'table', 'tabular', 'tabularx'}
    special_envs = math_envs | code_envs | list_envs | table_envs | {
        'algorithm', 'algorithmic', 'figure', 'abstract', 'theorem',
        'lemma', 'proof', 'definition', 'corollary', 'proposition'
    }

    heading_levels = {
        'chapter': 0, 'section': 1, 'subsection': 2,
        'subsubsection': 3, 'paragraph': 4
    }

    while i < len(lines):
        line = lines[i]

        # Check for heading
        heading_match = heading_pattern.match(line.strip())
        if heading_match and not env_stack:
            flush_block()
            level_name = heading_match.group(1)
            heading_text = heading_match.group(2)
            level = heading_levels.get(level_name, 1)

            # Update section path
            while len(current_section_path) >= level:
                current_section_path.pop()
            current_section_path.append(heading_text)

            blocks.append(Block(
                id=f"B{block_id:03d}",
                block_type=BlockType.HEADING.value,
                content=line.strip(),
                line_start=i + 1,
                line_end=i + 1,
                heading_level=level,
                section_path=' > '.join(current_section_path),
            ))
            block_id += 1
            current_block_start = i + 2
            i += 1
            continue

        # Check for environment start
        env_match = env_begin.search(line)
        if env_match and not env_stack:
            env_name = env_match.group(1)
            if env_name in special_envs or env_name == 'document':
                if env_name != 'document':
                    flush_block()
                    # Collect entire environment
                    env_lines = [line]
                    env_start = i + 1
                    depth = 1
                    i += 1
                    while i < len(lines) and depth > 0:
                        if env_begin.search(lines[i]):
                            depth += 1
                        if env_end.search(lines[i]):
                            depth -= 1
                        env_lines.append(lines[i])
                        i += 1

                    # Determine block type
                    if env_name in math_envs:
                        bt = BlockType.EQUATION
                    elif env_name in code_envs:
                        bt = BlockType.CODE
                    elif env_name in list_envs:
                        bt = BlockType.LIST
                    elif env_name in table_envs:
                        bt = BlockType.TABLE
                    else:
                        bt = BlockType.ENVIRONMENT

                    blocks.append(Block(
                        id=f"B{block_id:03d}",
                        block_type=bt.value,
                        content='\n'.join(env_lines),
                        line_start=env_start,
                        line_end=env_start + len(env_lines) - 1,
                        section_path=' > '.join(current_section_path) if current_section_path else '',
                    ))
                    block_id += 1
                    current_block_start = i + 1
                    continue
                else:
                    i += 1
                    current_block_start = i + 1
                    continue

        # Check for end of document
        if r'\end{document}' in line:
            flush_block()
            i += 1
            continue

        # Blank line = paragraph break
        if line.strip() == '' and not env_stack:
            if current_block_lines:
                flush_block()
            current_block_start = i + 2
            i += 1
            continue

        # Regular content line
        current_block_lines.append(line)
        i += 1

    flush_block()
    return blocks


def parse_markdown(content: str) -> list[Block]:
    """Parse Markdown document into semantic blocks."""
    lines = content.split('\n')
    blocks = []
    block_id = 0
    current_section_path = []

    i = 0
    current_block_lines = []
    current_block_start = 1
    current_block_type = BlockType.PARAGRAPH

    # Check for frontmatter
    if lines and lines[0].strip() == '---':
        fm_lines = [lines[0]]
        j = 1
        while j < len(lines) and lines[j].strip() != '---':
            fm_lines.append(lines[j])
            j += 1
        if j < len(lines):
            fm_lines.append(lines[j])
            blocks.append(Block(
                id=f"B{block_id:03d}",
                block_type=BlockType.METADATA.value,
                content='\n'.join(fm_lines),
                line_start=1,
                line_end=j + 1,
            ))
            block_id += 1
            i = j + 1
            current_block_start = i + 1

    def flush_block():
        nonlocal block_id, current_block_lines, current_block_start, current_block_type
        text = '\n'.join(current_block_lines).strip()
        if text:
            blocks.append(Block(
                id=f"B{block_id:03d}",
                block_type=current_block_type.value,
                content=text,
                line_start=current_block_start,
                line_end=current_block_start + len(current_block_lines) - 1,
                section_path=' > '.join(current_section_path) if current_section_path else '',
            ))
            block_id += 1
        current_block_lines = []
        current_block_type = BlockType.PARAGRAPH

    heading_pattern = re.compile(r'^(#{1,6})\s+(.+)')

    while i < len(lines):
        line = lines[i]

        # Heading
        heading_match = heading_pattern.match(line)
        if heading_match:
            flush_block()
            level = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()

            while len(current_section_path) >= level:
                current_section_path.pop()
            current_section_path.append(heading_text)

            blocks.append(Block(
                id=f"B{block_id:03d}",
                block_type=BlockType.HEADING.value,
                content=line.strip(),
                line_start=i + 1,
                line_end=i + 1,
                heading_level=level,
                section_path=' > '.join(current_section_path),
            ))
            block_id += 1
            current_block_start = i + 2
            i += 1
            continue

        # Code block
        if line.strip().startswith('```'):
            flush_block()
            code_lines = [line]
            code_start = i + 1
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            if i < len(lines):
                code_lines.append(lines[i])
                i += 1

            blocks.append(Block(
                id=f"B{block_id:03d}",
                block_type=BlockType.CODE.value,
                content='\n'.join(code_lines),
                line_start=code_start,
                line_end=code_start + len(code_lines) - 1,
                section_path=' > '.join(current_section_path) if current_section_path else '',
            ))
            block_id += 1
            current_block_start = i + 1
            continue

        # Table (lines starting with |)
        if line.strip().startswith('|'):
            flush_block()
            table_lines = []
            table_start = i + 1
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i])
                i += 1

            blocks.append(Block(
                id=f"B{block_id:03d}",
                block_type=BlockType.TABLE.value,
                content='\n'.join(table_lines),
                line_start=table_start,
                line_end=table_start + len(table_lines) - 1,
                section_path=' > '.join(current_section_path) if current_section_path else '',
            ))
            block_id += 1
            current_block_start = i + 1
            continue

        # List items
        if re.match(r'^[\s]*[-*+]\s|^[\s]*\d+\.\s', line):
            if current_block_type != BlockType.LIST:
                flush_block()
                current_block_type = BlockType.LIST
                current_block_start = i + 1
            current_block_lines.append(line)
            i += 1
            continue

        # Blank line = paragraph break
        if line.strip() == '':
            if current_block_lines:
                flush_block()
            current_block_start = i + 2
            i += 1
            continue

        # Regular paragraph line
        if current_block_type == BlockType.LIST:
            flush_block()
            current_block_start = i + 1
        current_block_type = BlockType.PARAGRAPH
        current_block_lines.append(line)
        i += 1

    flush_block()
    return blocks


def parse_document(content: str, doc_type: str = None) -> list[Block]:
    """Parse a document into semantic blocks."""
    if doc_type is None:
        doc_type = detect_doc_type(content)

    if doc_type == 'latex':
        return parse_latex(content)
    elif doc_type == 'markdown':
        return parse_markdown(content)
    else:
        # Plain text: split on blank lines
        blocks = []
        block_id = 0
        paragraphs = re.split(r'\n\s*\n', content)
        line = 1
        for para in paragraphs:
            if para.strip():
                para_lines = para.count('\n') + 1
                blocks.append(Block(
                    id=f"B{block_id:03d}",
                    block_type=BlockType.PARAGRAPH.value,
                    content=para.strip(),
                    line_start=line,
                    line_end=line + para_lines - 1,
                ))
                block_id += 1
                line += para_lines + 1
            else:
                line += 1
        return blocks


# ─── Block Alignment ─────────────────────────────────────────────────────────

def compute_similarity(block_a: Block, block_b: Block) -> float:
    """Compute similarity between two blocks using SequenceMatcher."""
    if block_a.fingerprint == block_b.fingerprint:
        return 1.0

    a_norm = block_a.normalized_content()
    b_norm = block_b.normalized_content()

    if not a_norm or not b_norm:
        return 0.0

    return difflib.SequenceMatcher(None, a_norm, b_norm).ratio()


def find_anchors(blocks_a: list[Block], blocks_b: list[Block],
                 threshold: float = 0.85) -> list[tuple[int, int, float]]:
    """
    Find anchor pairs — blocks that are highly similar between documents.
    Returns list of (index_a, index_b, similarity) tuples.
    """
    # First pass: exact matches by fingerprint
    fp_to_a = {}
    for i, block in enumerate(blocks_a):
        fp_to_a.setdefault(block.fingerprint, []).append(i)

    exact_matches = []
    used_a = set()
    used_b = set()

    for j, block in enumerate(blocks_b):
        if block.fingerprint in fp_to_a:
            for i in fp_to_a[block.fingerprint]:
                if i not in used_a:
                    exact_matches.append((i, j, 1.0))
                    used_a.add(i)
                    used_b.add(j)
                    break

    # Second pass: fuzzy matches for unmatched blocks
    fuzzy_matches = []
    for i, ba in enumerate(blocks_a):
        if i in used_a:
            continue
        best_j = -1
        best_sim = threshold
        for j, bb in enumerate(blocks_b):
            if j in used_b:
                continue
            # Quick filter: same block type preferred
            sim = compute_similarity(ba, bb)
            if sim > best_sim:
                best_sim = sim
                best_j = j
        if best_j >= 0:
            fuzzy_matches.append((i, best_j, best_sim))
            used_a.add(i)
            used_b.add(best_j)

    all_matches = exact_matches + fuzzy_matches
    # Sort by position in doc A to maintain order
    all_matches.sort(key=lambda x: x[0])
    return all_matches


def detect_moves(anchors: list[tuple[int, int, float]],
                 blocks_a: list[Block], blocks_b: list[Block]) -> dict[int, str]:
    """
    Detect blocks that have been moved (present in both docs but at different
    relative positions). Returns dict mapping anchor index to move description.
    """
    moves = {}
    if len(anchors) < 2:
        return moves

    # Check if relative order is preserved
    b_positions = [a[1] for a in anchors]
    for idx in range(len(anchors)):
        i_a, i_b, sim = anchors[idx]
        # Check if this block's position in B is out of order relative to neighbors
        is_moved = False
        if idx > 0 and b_positions[idx] < b_positions[idx - 1]:
            is_moved = True
        if idx < len(anchors) - 1 and b_positions[idx] > b_positions[idx + 1]:
            is_moved = True

        if is_moved:
            ba = blocks_a[i_a]
            bb = blocks_b[i_b]
            move_desc = (
                f"Moved from {ba.section_path or f'line {ba.line_start}'} "
                f"to {bb.section_path or f'line {bb.line_start}'}"
            )
            moves[idx] = move_desc

    return moves


def build_alignment(blocks_a: list[Block], blocks_b: list[Block],
                    similarity_threshold: float = 0.4) -> list[BlockAlignment]:
    """
    Build a full alignment between two document's blocks.
    This is the core algorithm that produces the comparison.
    """
    anchors = find_anchors(blocks_a, blocks_b, threshold=similarity_threshold)
    moves = detect_moves(anchors, blocks_a, blocks_b)

    # Build lookup maps
    a_matched = {a[0]: (a[1], a[2], idx) for idx, a in enumerate(anchors)}
    b_matched = {a[1]: (a[0], a[2], idx) for idx, a in enumerate(anchors)}

    alignments = []

    # Walk through both documents using anchors as synchronization points
    # Process unmatched blocks from A (deleted) and B (added) between anchors
    prev_a = -1
    prev_b = -1

    # Create sorted anchor list by doc A position
    sorted_anchors = sorted(anchors, key=lambda x: x[0])

    # Add sentinel anchors at start and end
    sentinel_anchors = [(-1, -1, 0.0)] + sorted_anchors + [
        (len(blocks_a), len(blocks_b), 0.0)
    ]

    for anchor_idx in range(len(sentinel_anchors) - 1):
        curr_a, curr_b, _ = sentinel_anchors[anchor_idx]
        next_a, next_b, _ = sentinel_anchors[anchor_idx + 1]

        # Process unmatched blocks between anchors
        unmatched_a = []
        unmatched_b = []

        for i in range(curr_a + 1, next_a):
            if i not in a_matched:
                unmatched_a.append(i)

        for j in range(curr_b + 1, next_b):
            if j not in b_matched:
                unmatched_b.append(j)

        # Try to match unmatched blocks with lower threshold
        matched_pairs = []
        remaining_a = list(unmatched_a)
        remaining_b = list(unmatched_b)

        for i in remaining_a[:]:
            best_j = -1
            best_sim = 0.3
            for j in remaining_b:
                sim = compute_similarity(blocks_a[i], blocks_b[j])
                if sim > best_sim:
                    best_sim = sim
                    best_j = j
            if best_j >= 0:
                matched_pairs.append((i, best_j, best_sim))
                remaining_a.remove(i)
                remaining_b.remove(best_j)

        # Emit deleted blocks
        for i in remaining_a:
            ba = blocks_a[i]
            alignments.append(BlockAlignment(
                change_type=ChangeType.DELETED.value,
                block_a=asdict(ba),
                similarity=0.0,
                diff_summary=f"Block deleted from {ba.section_path or f'line {ba.line_start}'}",
            ))

        # Emit added blocks
        for j in remaining_b:
            bb = blocks_b[j]
            alignments.append(BlockAlignment(
                change_type=ChangeType.ADDED.value,
                block_b=asdict(bb),
                similarity=0.0,
                diff_summary=f"Block added at {bb.section_path or f'line {bb.line_start}'}",
            ))

        # Emit modified pairs from local matching
        for i, j, sim in matched_pairs:
            ba = blocks_a[i]
            bb = blocks_b[j]
            diff_lines = list(difflib.unified_diff(
                ba.content.splitlines(), bb.content.splitlines(),
                lineterm='', n=1
            ))
            char_changes = sum(1 for c1, c2 in zip(ba.content, bb.content) if c1 != c2)
            char_changes += abs(len(ba.content) - len(bb.content))

            alignments.append(BlockAlignment(
                change_type=ChangeType.MODIFIED.value,
                block_a=asdict(ba),
                block_b=asdict(bb),
                similarity=sim,
                diff_summary='\n'.join(diff_lines[:20]),  # First 20 diff lines
                char_changes=char_changes,
            ))

        # Emit the next anchor itself (if not sentinel)
        if anchor_idx + 1 < len(sentinel_anchors) - 1:
            real_anchor_idx = anchor_idx  # offset by sentinel
            na, nb, nsim = sentinel_anchors[anchor_idx + 1]

            # Check if this anchor is in moves
            anchor_list_idx = None
            for aidx, anch in enumerate(anchors):
                if anch[0] == na and anch[1] == nb:
                    anchor_list_idx = aidx
                    break

            ba = blocks_a[na]
            bb = blocks_b[nb]

            if nsim >= 0.999:
                is_moved = anchor_list_idx is not None and anchor_list_idx in moves
                if is_moved:
                    alignments.append(BlockAlignment(
                        change_type=ChangeType.MOVED.value,
                        block_a=asdict(ba),
                        block_b=asdict(bb),
                        similarity=nsim,
                        move_info=moves[anchor_list_idx],
                    ))
                else:
                    alignments.append(BlockAlignment(
                        change_type=ChangeType.UNCHANGED.value,
                        block_a=asdict(ba),
                        block_b=asdict(bb),
                        similarity=1.0,
                    ))
            else:
                is_moved = anchor_list_idx is not None and anchor_list_idx in moves
                diff_lines = list(difflib.unified_diff(
                    ba.content.splitlines(), bb.content.splitlines(),
                    lineterm='', n=1
                ))
                char_changes = sum(1 for c1, c2 in zip(ba.content, bb.content) if c1 != c2)
                char_changes += abs(len(ba.content) - len(bb.content))

                if is_moved:
                    ct = ChangeType.MOVED_AND_MODIFIED.value
                    move_info = moves[anchor_list_idx]
                else:
                    ct = ChangeType.MODIFIED.value
                    move_info = ""

                alignments.append(BlockAlignment(
                    change_type=ct,
                    block_a=asdict(ba),
                    block_b=asdict(bb),
                    similarity=nsim,
                    diff_summary='\n'.join(diff_lines[:20]),
                    char_changes=char_changes,
                    move_info=move_info,
                ))

    return alignments


# ─── Output Formatting ────────────────────────────────────────────────────────

def format_block_header(block_dict: dict, label: str) -> str:
    """Format a block header for display."""
    parts = [f"[{label}]"]
    parts.append(f"ID={block_dict['id']}")
    parts.append(f"type={block_dict['block_type']}")
    parts.append(f"lines={block_dict['line_start']}-{block_dict['line_end']}")
    if block_dict.get('section_path'):
        parts.append(f"section=\"{block_dict['section_path']}\"")
    return ' '.join(parts)


def format_text_output(result: ComparisonResult, show_unchanged: bool = False,
                       max_content_lines: int = 0, block_range: str = None) -> str:
    """Format comparison result as human/agent-readable text."""
    lines = []
    lines.append("=" * 78)
    lines.append("DOCUMENT COMPARISON REPORT")
    lines.append("=" * 78)
    lines.append(f"File A: {result.file_a}")
    lines.append(f"File B: {result.file_b}")
    lines.append(f"Document type: {result.doc_type}")
    lines.append(f"Blocks in A: {result.total_blocks_a}")
    lines.append(f"Blocks in B: {result.total_blocks_b}")
    lines.append("")

    # Summary
    s = result.summary
    lines.append("SUMMARY")
    lines.append("-" * 40)
    lines.append(f"  Unchanged blocks: {s.get('unchanged', 0)}")
    lines.append(f"  Modified blocks:  {s.get('modified', 0)}")
    lines.append(f"  Added blocks:     {s.get('added', 0)}")
    lines.append(f"  Deleted blocks:   {s.get('deleted', 0)}")
    lines.append(f"  Moved blocks:     {s.get('moved', 0)}")
    lines.append(f"  Moved+Modified:   {s.get('moved_and_modified', 0)}")
    total_changes = s.get('modified', 0) + s.get('added', 0) + s.get('deleted', 0) + \
                    s.get('moved', 0) + s.get('moved_and_modified', 0)
    lines.append(f"  Total changes:    {total_changes}")
    lines.append("")

    # Parse block range filter
    range_start, range_end = 0, len(result.alignments)
    if block_range:
        parts = block_range.split('-')
        range_start = int(parts[0]) - 1
        range_end = int(parts[1]) if len(parts) > 1 else range_start + 1

    # Alignments
    lines.append("BLOCK-BY-BLOCK COMPARISON")
    lines.append("=" * 78)

    change_num = 0
    for idx, alignment in enumerate(result.alignments):
        if idx < range_start or idx >= range_end:
            continue

        al = alignment if isinstance(alignment, dict) else asdict(alignment)
        ct = al['change_type']

        if ct == 'unchanged' and not show_unchanged:
            continue

        change_num += 1
        lines.append("")
        lines.append(f"--- Change #{change_num} [{ct.upper()}] " + "-" * (50 - len(ct)))

        if al.get('block_a'):
            lines.append(format_block_header(al['block_a'], 'A'))
        if al.get('block_b'):
            lines.append(format_block_header(al['block_b'], 'B'))

        if al.get('similarity') and 0 < al['similarity'] < 1:
            lines.append(f"Similarity: {al['similarity']:.1%}")
        if al.get('char_changes'):
            lines.append(f"Character changes: {al['char_changes']}")
        if al.get('move_info'):
            lines.append(f"Move: {al['move_info']}")

        if ct == 'deleted':
            lines.append("")
            lines.append("Content removed:")
            content = al['block_a']['content']
            content_lines = content.split('\n')
            if max_content_lines and len(content_lines) > max_content_lines:
                for cl in content_lines[:max_content_lines]:
                    lines.append(f"  - {cl}")
                lines.append(f"  ... ({len(content_lines) - max_content_lines} more lines)")
            else:
                for cl in content_lines:
                    lines.append(f"  - {cl}")

        elif ct == 'added':
            lines.append("")
            lines.append("Content added:")
            content = al['block_b']['content']
            content_lines = content.split('\n')
            if max_content_lines and len(content_lines) > max_content_lines:
                for cl in content_lines[:max_content_lines]:
                    lines.append(f"  + {cl}")
                lines.append(f"  ... ({len(content_lines) - max_content_lines} more lines)")
            else:
                for cl in content_lines:
                    lines.append(f"  + {cl}")

        elif ct in ('modified', 'moved_and_modified'):
            lines.append("")
            if al.get('diff_summary'):
                lines.append("Diff:")
                for dl in al['diff_summary'].split('\n'):
                    lines.append(f"  {dl}")
            else:
                # Show full before/after
                lines.append("Before (A):")
                for cl in al['block_a']['content'].split('\n')[:max_content_lines or 999]:
                    lines.append(f"  - {cl}")
                lines.append("After (B):")
                for cl in al['block_b']['content'].split('\n')[:max_content_lines or 999]:
                    lines.append(f"  + {cl}")

        elif ct == 'moved':
            lines.append("")
            lines.append("Content (unchanged, repositioned):")
            content = al['block_a']['content']
            content_lines = content.split('\n')
            if max_content_lines and len(content_lines) > max_content_lines:
                for cl in content_lines[:max_content_lines]:
                    lines.append(f"  = {cl}")
                lines.append(f"  ... ({len(content_lines) - max_content_lines} more lines)")
            else:
                for cl in content_lines:
                    lines.append(f"  = {cl}")

        elif ct == 'unchanged' and show_unchanged:
            lines.append("")
            lines.append("Content (unchanged):")
            content = al['block_a']['content']
            content_lines = content.split('\n')
            if max_content_lines and len(content_lines) > max_content_lines:
                for cl in content_lines[:max_content_lines]:
                    lines.append(f"  = {cl}")
                lines.append(f"  ... ({len(content_lines) - max_content_lines} more lines)")
            else:
                for cl in content_lines:
                    lines.append(f"  = {cl}")

    lines.append("")
    lines.append("=" * 78)
    lines.append(f"End of comparison. {change_num} change(s) shown.")
    return '\n'.join(lines)


def format_json_output(result: ComparisonResult) -> str:
    """Format comparison result as JSON."""
    output = {
        'file_a': result.file_a,
        'file_b': result.file_b,
        'doc_type': result.doc_type,
        'total_blocks_a': result.total_blocks_a,
        'total_blocks_b': result.total_blocks_b,
        'summary': result.summary,
        'alignments': [
            a if isinstance(a, dict) else asdict(a)
            for a in result.alignments
        ],
    }
    return json.dumps(output, indent=2)


# ─── Block Listing ────────────────────────────────────────────────────────────

def format_block_list(blocks: list[Block], filename: str) -> str:
    """Format a listing of all blocks in a document."""
    lines = []
    lines.append(f"BLOCKS IN: {filename}")
    lines.append(f"Total blocks: {len(blocks)}")
    lines.append("-" * 70)
    lines.append(f"{'ID':<8} {'Type':<12} {'Lines':<12} {'Section':<30} {'Preview'}")
    lines.append("-" * 70)

    for block in blocks:
        preview = block.content[:50].replace('\n', ' ')
        if len(block.content) > 50:
            preview += '...'
        section = block.section_path[:30] if block.section_path else ''
        lines.append(
            f"{block.id:<8} {block.block_type:<12} "
            f"{block.line_start}-{block.line_end:<7} "
            f"{section:<30} {preview}"
        )

    return '\n'.join(lines)


def format_block_content(blocks: list[Block], block_id: str) -> str:
    """Show full content of a specific block."""
    for block in blocks:
        if block.id == block_id:
            lines = []
            lines.append(f"BLOCK {block.id}")
            lines.append(f"  Type: {block.block_type}")
            lines.append(f"  Lines: {block.line_start}-{block.line_end}")
            lines.append(f"  Section: {block.section_path or '(none)'}")
            lines.append(f"  Fingerprint: {block.fingerprint}")
            lines.append("-" * 40)
            lines.append(block.content)
            return '\n'.join(lines)
    return f"Block {block_id} not found."


# ─── Apply Changes ────────────────────────────────────────────────────────────

def apply_changes(file_a_content: str, file_b_content: str,
                  alignments: list, change_indices: list[int],
                  doc_type: str) -> str:
    """
    Apply selected changes from document B to document A.

    change_indices: list of 1-based change numbers to apply
    Returns the modified content of document A with selected changes applied.
    """
    blocks_a = parse_document(file_a_content, doc_type)
    blocks_b = parse_document(file_b_content, doc_type)

    # Filter to only actual changes (non-unchanged)
    changes = []
    for al in alignments:
        al_dict = al if isinstance(al, dict) else asdict(al)
        if al_dict['change_type'] != 'unchanged':
            changes.append(al_dict)

    # Build a map of which blocks in A to replace/delete, and what to insert
    lines_a = file_a_content.split('\n')
    operations = []  # (priority, line_start, line_end, new_content_or_None)

    for idx in change_indices:
        if idx < 1 or idx > len(changes):
            print(f"Warning: change index {idx} out of range (1-{len(changes)}), skipping.",
                  file=sys.stderr)
            continue

        change = changes[idx - 1]
        ct = change['change_type']

        if ct == 'deleted':
            # Remove this block from A
            ba = change['block_a']
            operations.append((ba['line_start'], ba['line_end'], None))

        elif ct == 'added':
            # Insert this block into A
            bb = change['block_b']
            # Find insertion point: after the previous block in B's context
            # For simplicity, we insert at the line position in B
            # This is approximate; for better results, use anchor context
            insert_after = bb['line_start']
            operations.append((insert_after, insert_after - 1, bb['content']))

        elif ct in ('modified', 'moved_and_modified'):
            # Replace A's version with B's version
            ba = change['block_a']
            bb = change['block_b']
            operations.append((ba['line_start'], ba['line_end'], bb['content']))

        elif ct == 'moved':
            # This is complex: need to delete from old position and insert at new
            ba = change['block_a']
            bb = change['block_b']
            operations.append((ba['line_start'], ba['line_end'], None))  # Delete
            operations.append((bb['line_start'], bb['line_start'] - 1, ba['content']))  # Insert

    # Sort operations by line number (reverse to apply from bottom up)
    operations.sort(key=lambda x: x[0], reverse=True)

    # Apply operations
    for line_start, line_end, new_content in operations:
        # Convert to 0-indexed
        start_idx = line_start - 1
        end_idx = line_end  # exclusive

        if new_content is None:
            # Delete
            lines_a[start_idx:end_idx] = []
        elif start_idx >= end_idx:
            # Insert
            new_lines = new_content.split('\n')
            lines_a[start_idx:start_idx] = new_lines
        else:
            # Replace
            new_lines = new_content.split('\n')
            lines_a[start_idx:end_idx] = new_lines

    return '\n'.join(lines_a)


# ─── Main CLI ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog='doccompare',
        description='Block-based document comparison tool for AI agents.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
        Commands:
          compare     Compare two documents block by block
          blocks      List all blocks in a document
          show        Show content of a specific block
          apply       Apply selected changes from doc B to doc A
          anchors     Show anchor points between two documents

        Examples:
          doccompare compare paper_v1.tex paper_v2.tex
          doccompare compare paper_v1.tex paper_v2.tex --format json
          doccompare compare paper_v1.tex paper_v2.tex --range 1-10
          doccompare compare paper_v1.tex paper_v2.tex --show-unchanged
          doccompare blocks paper_v1.tex
          doccompare show paper_v1.tex B005
          doccompare apply paper_v1.tex paper_v2.tex --changes 1,3,5,7-10
          doccompare anchors paper_v1.tex paper_v2.tex
        """)
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # compare command
    compare_parser = subparsers.add_parser('compare', help='Compare two documents')
    compare_parser.add_argument('file_a', help='First document (base/original)')
    compare_parser.add_argument('file_b', help='Second document (modified)')
    compare_parser.add_argument('--format', choices=['text', 'json'], default='text',
                               help='Output format (default: text)')
    compare_parser.add_argument('--show-unchanged', action='store_true',
                               help='Include unchanged blocks in output')
    compare_parser.add_argument('--max-lines', type=int, default=0,
                               help='Max content lines per block (0=unlimited)')
    compare_parser.add_argument('--range', dest='block_range',
                               help='Show only alignment range N-M (1-indexed)')
    compare_parser.add_argument('--threshold', type=float, default=0.4,
                               help='Similarity threshold for matching (0-1)')
    compare_parser.add_argument('--changes-only', action='store_true',
                               help='Only show changed blocks (same as not using --show-unchanged)')

    # blocks command
    blocks_parser = subparsers.add_parser('blocks', help='List blocks in a document')
    blocks_parser.add_argument('file', help='Document to parse')

    # show command
    show_parser = subparsers.add_parser('show', help='Show a specific block')
    show_parser.add_argument('file', help='Document to parse')
    show_parser.add_argument('block_id', help='Block ID (e.g., B005)')

    # apply command
    apply_parser = subparsers.add_parser('apply', help='Apply selected changes')
    apply_parser.add_argument('file_a', help='Base document')
    apply_parser.add_argument('file_b', help='Modified document')
    apply_parser.add_argument('--changes', required=True,
                             help='Comma-separated change numbers to apply (e.g., 1,3,5,7-10)')
    apply_parser.add_argument('--output', '-o', help='Output file (default: stdout)')

    # anchors command
    anchors_parser = subparsers.add_parser('anchors', help='Show anchor points')
    anchors_parser.add_argument('file_a', help='First document')
    anchors_parser.add_argument('file_b', help='Second document')
    anchors_parser.add_argument('--threshold', type=float, default=0.85,
                               help='Similarity threshold for anchors')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == 'compare':
        with open(args.file_a) as f:
            content_a = f.read()
        with open(args.file_b) as f:
            content_b = f.read()

        doc_type = detect_doc_type(content_a)
        blocks_a = parse_document(content_a, doc_type)
        blocks_b = parse_document(content_b, doc_type)

        alignments = build_alignment(blocks_a, blocks_b, args.threshold)

        # Build summary
        summary = {}
        for al in alignments:
            ct = al.change_type if isinstance(al, BlockAlignment) else al['change_type']
            summary[ct] = summary.get(ct, 0) + 1

        result = ComparisonResult(
            file_a=args.file_a,
            file_b=args.file_b,
            doc_type=doc_type,
            total_blocks_a=len(blocks_a),
            total_blocks_b=len(blocks_b),
            summary=summary,
            alignments=alignments,
        )

        if args.format == 'json':
            print(format_json_output(result))
        else:
            print(format_text_output(
                result,
                show_unchanged=args.show_unchanged,
                max_content_lines=args.max_lines,
                block_range=args.block_range,
            ))

    elif args.command == 'blocks':
        with open(args.file) as f:
            content = f.read()
        blocks = parse_document(content)
        print(format_block_list(blocks, args.file))

    elif args.command == 'show':
        with open(args.file) as f:
            content = f.read()
        blocks = parse_document(content)
        print(format_block_content(blocks, args.block_id.upper()))

    elif args.command == 'apply':
        with open(args.file_a) as f:
            content_a = f.read()
        with open(args.file_b) as f:
            content_b = f.read()

        doc_type = detect_doc_type(content_a)
        blocks_a = parse_document(content_a, doc_type)
        blocks_b = parse_document(content_b, doc_type)
        alignments = build_alignment(blocks_a, blocks_b)

        # Parse change indices
        change_indices = []
        for part in args.changes.split(','):
            part = part.strip()
            if '-' in part:
                start, end = part.split('-')
                change_indices.extend(range(int(start), int(end) + 1))
            else:
                change_indices.append(int(part))

        result = apply_changes(content_a, content_b, alignments, change_indices, doc_type)

        if args.output:
            with open(args.output, 'w') as f:
                f.write(result)
            print(f"Applied {len(change_indices)} change(s) to {args.output}", file=sys.stderr)
        else:
            print(result)

    elif args.command == 'anchors':
        with open(args.file_a) as f:
            content_a = f.read()
        with open(args.file_b) as f:
            content_b = f.read()

        doc_type = detect_doc_type(content_a)
        blocks_a = parse_document(content_a, doc_type)
        blocks_b = parse_document(content_b, doc_type)

        anchors = find_anchors(blocks_a, blocks_b, args.threshold)

        print(f"ANCHOR POINTS ({len(anchors)} found)")
        print(f"Threshold: {args.threshold}")
        print("-" * 78)
        print(f"{'#':<4} {'A-ID':<8} {'B-ID':<8} {'Sim':<8} {'Type':<12} {'Preview'}")
        print("-" * 78)

        for i, (ia, ib, sim) in enumerate(anchors):
            ba = blocks_a[ia]
            bb = blocks_b[ib]
            preview = ba.content[:45].replace('\n', ' ')
            if len(ba.content) > 45:
                preview += '...'
            print(f"{i+1:<4} {ba.id:<8} {bb.id:<8} {sim:<8.2f} {ba.block_type:<12} {preview}")


if __name__ == '__main__':
    main()
