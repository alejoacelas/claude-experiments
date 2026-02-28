#!/usr/bin/env python3
"""
Auto-grader for document comparison tasks.

Evaluates agent output by comparing it against the expected result.
Uses multiple metrics:
1. Block-level accuracy: For each block, did the agent make the right decision?
2. Content similarity: How close is the output to the expected result?
3. Error categorization: What types of mistakes did the agent make?
"""

import argparse
import difflib
import json
import os
import re
import sys

# Add parent dir to path for doccompare imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'doccompare'))
from doccompare import parse_document, compute_similarity, Block


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace for comparison."""
    # Normalize line endings
    text = text.replace('\r\n', '\n')
    # Remove trailing whitespace from lines
    text = '\n'.join(line.rstrip() for line in text.split('\n'))
    # Remove trailing newlines
    text = text.rstrip('\n')
    return text


def compute_line_level_metrics(expected: str, actual: str) -> dict:
    """Compute line-level precision, recall, and accuracy."""
    expected_lines = set(normalize_whitespace(expected).split('\n'))
    actual_lines = set(normalize_whitespace(actual).split('\n'))

    true_positives = len(expected_lines & actual_lines)
    false_positives = len(actual_lines - expected_lines)
    false_negatives = len(expected_lines - actual_lines)

    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    return {
        'line_precision': precision,
        'line_recall': recall,
        'line_f1': f1,
        'lines_correct': true_positives,
        'lines_extra': false_positives,
        'lines_missing': false_negatives,
        'total_expected_lines': len(expected_lines),
        'total_actual_lines': len(actual_lines),
    }


def compute_block_level_metrics(expected: str, actual: str) -> dict:
    """Compare at the semantic block level."""
    expected_blocks = parse_document(expected)
    actual_blocks = parse_document(actual)

    # Match blocks between expected and actual
    matched = 0
    close_matches = 0
    missing = 0
    extra = 0

    used_actual = set()
    block_details = []

    for eb in expected_blocks:
        best_sim = 0
        best_idx = -1
        for j, ab in enumerate(actual_blocks):
            if j in used_actual:
                continue
            sim = compute_similarity(eb, ab)
            if sim > best_sim:
                best_sim = sim
                best_idx = j

        if best_sim >= 0.99:
            matched += 1
            used_actual.add(best_idx)
            block_details.append({
                'expected_id': eb.id,
                'actual_id': actual_blocks[best_idx].id,
                'type': eb.block_type,
                'similarity': best_sim,
                'status': 'exact_match',
            })
        elif best_sim >= 0.8:
            close_matches += 1
            used_actual.add(best_idx)
            block_details.append({
                'expected_id': eb.id,
                'actual_id': actual_blocks[best_idx].id,
                'type': eb.block_type,
                'similarity': best_sim,
                'status': 'close_match',
                'preview': eb.content[:80],
            })
        elif best_sim >= 0.5:
            close_matches += 1
            used_actual.add(best_idx)
            block_details.append({
                'expected_id': eb.id,
                'actual_id': actual_blocks[best_idx].id if best_idx >= 0 else None,
                'type': eb.block_type,
                'similarity': best_sim,
                'status': 'partial_match',
                'preview': eb.content[:80],
            })
        else:
            missing += 1
            block_details.append({
                'expected_id': eb.id,
                'type': eb.block_type,
                'similarity': best_sim,
                'status': 'missing',
                'preview': eb.content[:80],
            })

    extra = len(actual_blocks) - len(used_actual)

    total = len(expected_blocks)
    accuracy = matched / total if total > 0 else 0
    close_accuracy = (matched + close_matches) / total if total > 0 else 0

    return {
        'block_exact_accuracy': accuracy,
        'block_close_accuracy': close_accuracy,
        'blocks_exact_match': matched,
        'blocks_close_match': close_matches,
        'blocks_missing': missing,
        'blocks_extra': extra,
        'total_expected_blocks': total,
        'total_actual_blocks': len(actual_blocks),
        'block_details': block_details,
    }


def compute_diff_metrics(expected: str, actual: str) -> dict:
    """Compute diff-based metrics."""
    expected_norm = normalize_whitespace(expected)
    actual_norm = normalize_whitespace(actual)

    # Overall similarity
    similarity = difflib.SequenceMatcher(None, expected_norm, actual_norm).ratio()

    # Count diff hunks
    diff = list(difflib.unified_diff(
        expected_norm.split('\n'),
        actual_norm.split('\n'),
        lineterm='',
        n=0,
    ))
    hunks = sum(1 for line in diff if line.startswith('@@'))
    added_lines = sum(1 for line in diff if line.startswith('+') and not line.startswith('+++'))
    removed_lines = sum(1 for line in diff if line.startswith('-') and not line.startswith('---'))

    return {
        'overall_similarity': similarity,
        'diff_hunks': hunks,
        'diff_added_lines': added_lines,
        'diff_removed_lines': removed_lines,
    }


def categorize_errors(expected: str, actual: str, v1_content: str, v2_content: str) -> dict:
    """
    Categorize errors relative to the source documents.
    Determines whether errors are:
    - Over-application: Applied a change that shouldn't have been applied
    - Under-application: Failed to apply a change that should have been applied
    - Corruption: Introduced content that exists in neither v1 nor v2
    """
    expected_lines = set(normalize_whitespace(expected).split('\n'))
    actual_lines = set(normalize_whitespace(actual).split('\n'))
    v1_lines = set(normalize_whitespace(v1_content).split('\n'))
    v2_lines = set(normalize_whitespace(v2_content).split('\n'))

    # Lines in actual but not in expected
    extra_lines = actual_lines - expected_lines
    # Lines in expected but not in actual
    missing_lines = expected_lines - actual_lines

    over_applied = 0  # Extra lines that come from v2
    under_applied = 0  # Missing lines that come from v2
    kept_wrong = 0  # Extra lines that come from v1 (should have been changed)
    removed_wrong = 0  # Missing lines that come from v1 (should have been kept)
    corrupted = 0  # Lines in neither v1 nor v2

    for line in extra_lines:
        if not line.strip():
            continue
        if line in v2_lines:
            over_applied += 1
        elif line in v1_lines:
            kept_wrong += 1
        else:
            corrupted += 1

    for line in missing_lines:
        if not line.strip():
            continue
        if line in v2_lines:
            under_applied += 1
        elif line in v1_lines:
            removed_wrong += 1
        else:
            # This line was in expected but not in any source — possibly a hybrid
            corrupted += 1

    return {
        'over_applied': over_applied,
        'under_applied': under_applied,
        'kept_wrong_v1_lines': kept_wrong,
        'removed_wrong_v1_lines': removed_wrong,
        'corrupted': corrupted,
        'error_summary': (
            f"Over-applied: {over_applied}, Under-applied: {under_applied}, "
            f"Kept wrong v1: {kept_wrong}, Removed wrong v1: {removed_wrong}, "
            f"Corrupted: {corrupted}"
        )
    }


def compute_final_score(metrics: dict) -> float:
    """
    Compute a single 0-100 score from all metrics.
    Weighted combination favoring content correctness.
    """
    weights = {
        'overall_similarity': 0.3,
        'block_close_accuracy': 0.25,
        'line_f1': 0.25,
        'error_penalty': 0.2,
    }

    # Error penalty: penalize corrupted content heavily
    error_cat = metrics.get('error_categorization', {})
    total_errors = (
        error_cat.get('over_applied', 0) +
        error_cat.get('under_applied', 0) +
        error_cat.get('corrupted', 0) * 3  # Triple penalty for corruption
    )
    total_lines = metrics.get('line_metrics', {}).get('total_expected_lines', 1)
    error_rate = min(1.0, total_errors / max(total_lines, 1))
    error_score = 1.0 - error_rate

    score = (
        weights['overall_similarity'] * metrics.get('diff_metrics', {}).get('overall_similarity', 0) +
        weights['block_close_accuracy'] * metrics.get('block_metrics', {}).get('block_close_accuracy', 0) +
        weights['line_f1'] * metrics.get('line_metrics', {}).get('line_f1', 0) +
        weights['error_penalty'] * error_score
    ) * 100

    return round(score, 1)


def grade(expected_path: str, actual_path: str,
          v1_path: str = None, v2_path: str = None,
          verbose: bool = False) -> dict:
    """
    Grade an agent's output against expected output.

    Args:
        expected_path: Path to the expected/gold output
        actual_path: Path to the agent's output
        v1_path: Path to original document (for error categorization)
        v2_path: Path to modified document (for error categorization)
        verbose: Include detailed block-level information
    """
    if not os.path.exists(actual_path):
        return {
            'score': 0,
            'error': f'Output file not found: {actual_path}',
            'metrics': {},
        }

    with open(expected_path) as f:
        expected = f.read()
    with open(actual_path) as f:
        actual = f.read()

    metrics = {}

    # Line-level metrics
    metrics['line_metrics'] = compute_line_level_metrics(expected, actual)

    # Block-level metrics
    block_metrics = compute_block_level_metrics(expected, actual)
    if not verbose:
        del block_metrics['block_details']
    metrics['block_metrics'] = block_metrics

    # Diff metrics
    metrics['diff_metrics'] = compute_diff_metrics(expected, actual)

    # Error categorization (if source documents provided)
    if v1_path and v2_path and os.path.exists(v1_path) and os.path.exists(v2_path):
        with open(v1_path) as f:
            v1_content = f.read()
        with open(v2_path) as f:
            v2_content = f.read()
        metrics['error_categorization'] = categorize_errors(expected, actual, v1_content, v2_content)

    # Compute final score
    score = compute_final_score(metrics)

    return {
        'score': score,
        'metrics': metrics,
    }


def print_report(result: dict, task_id: str = None):
    """Print a human-readable grading report."""
    print("=" * 60)
    if task_id:
        print(f"GRADING REPORT: {task_id}")
    else:
        print("GRADING REPORT")
    print("=" * 60)

    print(f"\nFinal Score: {result['score']}/100")

    m = result.get('metrics', {})

    if 'diff_metrics' in m:
        dm = m['diff_metrics']
        print(f"\nOverall Similarity: {dm['overall_similarity']:.1%}")
        print(f"Diff hunks: {dm['diff_hunks']}")
        print(f"Lines added vs expected: {dm['diff_added_lines']}")
        print(f"Lines removed vs expected: {dm['diff_removed_lines']}")

    if 'line_metrics' in m:
        lm = m['line_metrics']
        print(f"\nLine-level:")
        print(f"  Precision: {lm['line_precision']:.1%}")
        print(f"  Recall:    {lm['line_recall']:.1%}")
        print(f"  F1:        {lm['line_f1']:.1%}")
        print(f"  Correct lines: {lm['lines_correct']}/{lm['total_expected_lines']}")
        print(f"  Extra lines:   {lm['lines_extra']}")
        print(f"  Missing lines: {lm['lines_missing']}")

    if 'block_metrics' in m:
        bm = m['block_metrics']
        print(f"\nBlock-level:")
        print(f"  Exact match:  {bm['block_exact_accuracy']:.1%} ({bm['blocks_exact_match']}/{bm['total_expected_blocks']})")
        print(f"  Close match:  {bm['block_close_accuracy']:.1%}")
        print(f"  Missing:      {bm['blocks_missing']}")
        print(f"  Extra:        {bm['blocks_extra']}")

    if 'error_categorization' in m:
        ec = m['error_categorization']
        print(f"\nError Categorization:")
        print(f"  Over-applied (took v2 changes that should be v1): {ec['over_applied']}")
        print(f"  Under-applied (kept v1 when should be v2):        {ec['under_applied']}")
        print(f"  Kept wrong v1 lines:                              {ec['kept_wrong_v1_lines']}")
        print(f"  Removed wrong v1 lines:                           {ec['removed_wrong_v1_lines']}")
        print(f"  Corrupted (content from neither source):          {ec['corrupted']}")

    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description='Grade document comparison task output')
    parser.add_argument('expected', help='Path to expected/gold output')
    parser.add_argument('actual', help='Path to agent output')
    parser.add_argument('--v1', help='Path to original document')
    parser.add_argument('--v2', help='Path to modified document')
    parser.add_argument('--verbose', '-v', action='store_true', help='Include block details')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--task-id', help='Task identifier for report')

    args = parser.parse_args()

    result = grade(args.expected, args.actual, args.v1, args.v2, args.verbose)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_report(result, args.task_id)


if __name__ == '__main__':
    main()
