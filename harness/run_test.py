#!/usr/bin/env python3
"""
Test harness for running document comparison tasks with sub-agents.

Supports two agent modes:
- cli: Agent has full tool access (Bash, Read, Write, Edit, Glob, Grep)
       and can use the doccompare CLI interactively.
- diff-only: Agent receives the unified diff and both file contents inline
       in the prompt, with only the Write tool to produce output.

Usage:
    python harness/run_test.py --task task1 [--task task2 ...] [--all]
    python harness/run_test.py --all --runs 3
    python harness/run_test.py --all --mode diff-only
    python harness/run_test.py --all --mode both   # run both modes for comparison
"""

import argparse
import difflib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime

PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(PROJ_ROOT, 'documents')
TASKS_DIR = os.path.join(PROJ_ROOT, 'tasks')
TOOL_DIR = os.path.join(PROJ_ROOT, 'doccompare')
RESULTS_DIR = os.path.join(PROJ_ROOT, 'results')
HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))

# Add parent for grader import
sys.path.insert(0, HARNESS_DIR)
from grader import grade, print_report


def load_task(task_id: str) -> dict:
    """Load task configuration."""
    task_path = os.path.join(TASKS_DIR, task_id, 'task.json')
    with open(task_path) as f:
        return json.load(f)


def setup_work_dir(task_config: dict, run_id: str) -> str:
    """Set up an isolated working directory for a task run."""
    work_dir = os.path.join(RESULTS_DIR, run_id, 'workspace')
    os.makedirs(work_dir, exist_ok=True)

    # Copy source documents
    for doc in task_config['doc_pair']:
        src = os.path.join(DOCS_DIR, doc)
        dst = os.path.join(work_dir, doc)
        shutil.copy2(src, dst)

    return work_dir


def generate_unified_diff(work_dir: str, doc_pair: list) -> str:
    """Generate a unified diff between the two documents."""
    v1_path = os.path.join(work_dir, doc_pair[0])
    v2_path = os.path.join(work_dir, doc_pair[1])

    with open(v1_path) as f:
        v1_lines = f.readlines()
    with open(v2_path) as f:
        v2_lines = f.readlines()

    diff = difflib.unified_diff(
        v1_lines, v2_lines,
        fromfile=doc_pair[0], tofile=doc_pair[1],
        n=3,
    )
    return ''.join(diff)


def build_cli_prompt(task_config: dict, work_dir: str) -> str:
    """Build prompt for CLI mode (agent has full tool access)."""
    description = task_config['description']

    tool_path = os.path.abspath(TOOL_DIR)
    description = description.replace('TOOL_PATH', tool_path)
    description = description.replace('WORK_DIR', os.path.abspath(work_dir))

    prompt = f"""You are performing a document comparison and editing task.

TASK: {task_config['title']}

{description}

IMPORTANT INSTRUCTIONS:
- Use the document comparison tool (python3 {tool_path}/doccompare.py) to analyze the differences between the two files.
- The tool supports these commands:
  - compare: Compare two documents block by block (use --format json for structured output)
  - blocks: List all blocks in a document
  - show: Show content of a specific block
  - anchors: Show anchor points between two documents
  - apply: Apply selected changes (use with caution, may need manual refinement)
- Read both source files carefully before making changes.
- You can use the tool's JSON output mode for programmatic analysis.
- Write your final result to the output path specified in the task.
- Be precise: only apply the changes specified in the task, nothing more, nothing less.
"""
    return prompt


def build_diff_only_prompt(task_config: dict, work_dir: str) -> str:
    """Build prompt for diff-only mode (all content inline, no tool exploration)."""
    description = task_config['description']

    # Strip tool/path references from description - replace with generic output path
    abs_work_dir = os.path.abspath(work_dir)
    description = description.replace('TOOL_PATH', '/not-available')
    description = description.replace('WORK_DIR', abs_work_dir)

    # Read both source files
    doc_pair = task_config['doc_pair']
    v1_path = os.path.join(work_dir, doc_pair[0])
    v2_path = os.path.join(work_dir, doc_pair[1])

    with open(v1_path) as f:
        v1_content = f.read()
    with open(v2_path) as f:
        v2_content = f.read()

    # Generate unified diff
    diff_text = generate_unified_diff(work_dir, doc_pair)

    prompt = f"""You are performing a document comparison and editing task.

TASK: {task_config['title']}

{description}

Below you are given: (1) the full content of both source files, and (2) a unified diff showing all differences between them. You must analyze these and produce the correct output file.

You do NOT have access to any comparison tools. You must work from the diff and file contents provided below.

================================================================================
ORIGINAL FILE: {doc_pair[0]}
================================================================================
{v1_content}

================================================================================
REVISED FILE: {doc_pair[1]}
================================================================================
{v2_content}

================================================================================
UNIFIED DIFF ({doc_pair[0]} -> {doc_pair[1]})
================================================================================
{diff_text}

IMPORTANT INSTRUCTIONS:
- Carefully analyze the diff above and apply ONLY the changes specified in the task.
- Write the complete output file to the path specified in the task description.
- Be precise: only apply the changes specified in the task, nothing more, nothing less.
- Do not use any tools other than Write to produce the output file.
"""
    return prompt


def run_agent(prompt: str, work_dir: str, mode: str = 'cli',
              timeout: int = 600) -> dict:
    """
    Run a sub-agent with the given prompt.
    Returns dict with: success, output, duration
    """
    start_time = time.time()

    # Write the prompt to a file for reference
    prompt_file = os.path.join(work_dir, '.agent_prompt.txt')
    with open(prompt_file, 'w') as f:
        f.write(prompt)

    # Select tools based on mode
    if mode == 'diff-only':
        allowed_tools = 'Write'
    else:
        allowed_tools = 'Bash,Read,Write,Edit,Glob,Grep'

    # Build environment, unsetting CLAUDECODE to allow nested sessions
    env = os.environ.copy()
    env.pop('CLAUDECODE', None)

    try:
        # Use stdin for the prompt to avoid OS argument length limits
        result = subprocess.run(
            ['claude', '--print', '-p', '-',
             '--allowedTools', allowed_tools],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=work_dir,
            env=env,
        )
        duration = time.time() - start_time

        return {
            'success': result.returncode == 0,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'returncode': result.returncode,
            'duration': duration,
        }
    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        return {
            'success': False,
            'stdout': '',
            'stderr': f'Agent timed out after {timeout}s',
            'returncode': -1,
            'duration': duration,
        }
    except FileNotFoundError:
        return {
            'success': False,
            'stdout': '',
            'stderr': 'claude CLI not found. Make sure Claude Code is installed.',
            'returncode': -1,
            'duration': 0,
        }


def grade_result(task_id: str, work_dir: str) -> dict:
    """Grade the agent's output for a task."""
    task_config = load_task(task_id)
    output_file = task_config.get('output_file', 'output.tex')
    expected_file = task_config.get('expected_file', 'expected_output.tex')
    expected_path = os.path.join(TASKS_DIR, task_id, expected_file)
    actual_path = os.path.join(work_dir, output_file)

    if not os.path.exists(expected_path):
        return {'score': 0, 'error': f'Expected output not found: {expected_path}'}

    v1_path = os.path.join(DOCS_DIR, task_config['doc_pair'][0])
    v2_path = os.path.join(DOCS_DIR, task_config['doc_pair'][1])

    return grade(expected_path, actual_path, v1_path, v2_path, verbose=True)


def run_single_task(task_id: str, mode: str = 'cli',
                    run_number: int = 1, timeout: int = 600) -> dict:
    """Run a single task and return results."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_id = f"{task_id}_{mode}_run{run_number}_{timestamp}"

    print(f"\n{'='*60}")
    print(f"Running: {task_id} [{mode}] (run #{run_number})")
    print(f"Run ID: {run_id}")
    print(f"{'='*60}")

    # Load task
    task_config = load_task(task_id)
    print(f"Task: {task_config['title']}")
    print(f"Difficulty: {task_config.get('difficulty', 'unknown')}")
    print(f"Mode: {mode}")

    # Setup
    work_dir = setup_work_dir(task_config, run_id)
    print(f"Work directory: {work_dir}")

    # Build prompt based on mode
    if mode == 'diff-only':
        prompt = build_diff_only_prompt(task_config, work_dir)
    else:
        prompt = build_cli_prompt(task_config, work_dir)

    # Save prompt for reference
    results_dir = os.path.join(RESULTS_DIR, run_id)
    os.makedirs(results_dir, exist_ok=True)
    with open(os.path.join(results_dir, 'prompt.txt'), 'w') as f:
        f.write(prompt)

    # Run agent
    print(f"\nStarting agent (timeout: {timeout}s)...")
    agent_result = run_agent(prompt, work_dir, mode, timeout)

    print(f"Agent completed in {agent_result['duration']:.1f}s")
    print(f"Success: {agent_result['success']}")

    # Save agent output
    with open(os.path.join(results_dir, 'agent_stdout.txt'), 'w') as f:
        f.write(agent_result.get('stdout', ''))
    with open(os.path.join(results_dir, 'agent_stderr.txt'), 'w') as f:
        f.write(agent_result.get('stderr', ''))

    # Grade
    print("\nGrading...")
    grade_result_data = grade_result(task_id, work_dir)

    # Print report
    print_report(grade_result_data, task_id)

    # Save full results
    full_result = {
        'run_id': run_id,
        'task_id': task_id,
        'task_title': task_config['title'],
        'difficulty': task_config.get('difficulty', 'unknown'),
        'mode': mode,
        'timestamp': timestamp,
        'agent_duration': agent_result['duration'],
        'agent_success': agent_result['success'],
        'score': grade_result_data['score'],
        'metrics': grade_result_data.get('metrics', {}),
    }

    with open(os.path.join(results_dir, 'results.json'), 'w') as f:
        json.dump(full_result, indent=2, fp=f)

    return full_result


def print_summary(all_results: list):
    """Print a summary table of all results."""
    print("\n" + "=" * 80)
    print("SUMMARY OF ALL RESULTS")
    print("=" * 80)
    print(f"{'Task':<12} {'Mode':<12} {'Run':<4} {'Score':>7} {'Duration':>10} {'Difficulty':<12}")
    print("-" * 80)

    scores_by_task_mode = {}
    for r in all_results:
        task_id = r['task_id']
        mode = r.get('mode', 'cli')
        key = f"{task_id}:{mode}"
        print(f"{task_id:<12} {mode:<12} {'#' + str(r.get('run_num', 1)):<4} "
              f"{r['score']:>6.1f} {r['agent_duration']:>9.1f}s "
              f"{r.get('difficulty', '?'):<12}")
        if key not in scores_by_task_mode:
            scores_by_task_mode[key] = []
        scores_by_task_mode[key].append(r['score'])

    print("-" * 80)

    # Group by mode for comparison
    modes_seen = sorted(set(r.get('mode', 'cli') for r in all_results))
    tasks_seen = sorted(set(r['task_id'] for r in all_results))

    if len(modes_seen) > 1:
        print("\nMODE COMPARISON:")
        print(f"{'Task':<12}", end='')
        for mode in modes_seen:
            print(f"  {mode:>12}", end='')
        print(f"  {'Delta':>8}")
        print("-" * (14 + 14 * len(modes_seen) + 10))

        deltas = []
        for task_id in tasks_seen:
            print(f"{task_id:<12}", end='')
            task_scores = {}
            for mode in modes_seen:
                key = f"{task_id}:{mode}"
                scores = scores_by_task_mode.get(key, [])
                avg = sum(scores) / len(scores) if scores else 0
                task_scores[mode] = avg
                print(f"  {avg:>11.1f}", end='')
            if len(modes_seen) == 2:
                delta = task_scores[modes_seen[0]] - task_scores[modes_seen[1]]
                deltas.append(delta)
                print(f"  {delta:>+7.1f}", end='')
            print()

        if deltas:
            avg_delta = sum(deltas) / len(deltas)
            print(f"\n{'Average delta':.<30} {avg_delta:>+7.1f}")
            print(f"{'Max delta':.<30} {max(deltas, key=abs):>+7.1f}")

    # Per-mode averages
    for mode in modes_seen:
        mode_scores = [r['score'] for r in all_results if r.get('mode', 'cli') == mode]
        if mode_scores:
            avg = sum(mode_scores) / len(mode_scores)
            print(f"\n{mode} average: {avg:.1f}")

    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description='Run document comparison tasks with sub-agents',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  cli        Agent has full tool access (Bash, Read, Write, Edit, Glob, Grep)
             and can use the doccompare CLI interactively.
  diff-only  Agent receives both files and a unified diff inline in the prompt,
             with only the Write tool to produce output.
  both       Run both modes for head-to-head comparison.
""")
    parser.add_argument('--task', action='append', help='Task ID to run (can specify multiple)')
    parser.add_argument('--all', action='store_true', help='Run all tasks')
    parser.add_argument('--runs', type=int, default=1, help='Number of runs per task')
    parser.add_argument('--timeout', type=int, default=600, help='Agent timeout in seconds')
    parser.add_argument('--mode', choices=['cli', 'diff-only', 'both'], default='cli',
                        help='Agent mode (default: cli)')
    parser.add_argument('--list', action='store_true', help='List available tasks')

    args = parser.parse_args()

    if args.list:
        print("Available tasks:")
        for task_dir in sorted(os.listdir(TASKS_DIR)):
            task_path = os.path.join(TASKS_DIR, task_dir, 'task.json')
            if os.path.exists(task_path):
                with open(task_path) as f:
                    tc = json.load(f)
                print(f"  {tc['task_id']}: {tc['title']} [{tc.get('difficulty', '?')}]")
        return

    # Determine which tasks to run
    task_ids = []
    if args.all:
        for task_dir in sorted(os.listdir(TASKS_DIR)):
            task_path = os.path.join(TASKS_DIR, task_dir, 'task.json')
            if os.path.exists(task_path):
                task_ids.append(task_dir)
    elif args.task:
        task_ids = args.task
    else:
        parser.print_help()
        print("\nError: specify --task TASK_ID or --all")
        sys.exit(1)

    # Validate tasks exist
    for task_id in task_ids:
        task_path = os.path.join(TASKS_DIR, task_id, 'task.json')
        if not os.path.exists(task_path):
            print(f"Error: task '{task_id}' not found at {task_path}")
            sys.exit(1)

    # Determine modes to run
    if args.mode == 'both':
        modes = ['cli', 'diff-only']
    else:
        modes = [args.mode]

    # Run tasks
    os.makedirs(RESULTS_DIR, exist_ok=True)
    all_results = []

    for task_id in task_ids:
        for mode in modes:
            for run_num in range(1, args.runs + 1):
                result = run_single_task(task_id, mode, run_num, args.timeout)
                result['run_num'] = run_num
                all_results.append(result)

    # Print summary
    if len(all_results) > 1:
        print_summary(all_results)

    # Save aggregate results
    mode_tag = args.mode
    agg_path = os.path.join(RESULTS_DIR,
                            f"aggregate_{mode_tag}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(agg_path, 'w') as f:
        json.dump(all_results, indent=2, fp=f)
    print(f"\nAggregate results saved to: {agg_path}")


if __name__ == '__main__':
    main()
