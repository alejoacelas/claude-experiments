#!/usr/bin/env python3
"""
Test harness for running document comparison tasks with sub-agents.

This script:
1. Sets up isolated working directories for each task run
2. Provides the agent with the task description and tool access
3. Collects the agent's output
4. Grades the result using the auto-grader
5. Saves transcripts and results for analysis

Usage:
    python harness/run_test.py --task task1 [--task task2 ...] [--all]
    python harness/run_test.py --all --runs 3
"""

import argparse
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


def build_agent_prompt(task_config: dict, work_dir: str) -> str:
    """Build the prompt to send to the sub-agent."""
    description = task_config['description']

    # Replace placeholders
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


def run_agent(prompt: str, work_dir: str, timeout: int = 600) -> dict:
    """
    Run a sub-agent with the given prompt.
    Returns dict with: success, output, duration, transcript_path
    """
    start_time = time.time()

    # Write the prompt to a file for the agent
    prompt_file = os.path.join(work_dir, '.agent_prompt.txt')
    with open(prompt_file, 'w') as f:
        f.write(prompt)

    # Use Claude CLI to run the agent
    # The agent gets its own working directory and the prompt
    try:
        result = subprocess.run(
            ['claude', '--print', '-p', prompt,
             '--allowedTools', 'Bash,Read,Write,Edit,Glob,Grep'],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=work_dir,
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
    expected_path = os.path.join(TASKS_DIR, task_id, 'expected_output.tex')
    actual_path = os.path.join(work_dir, 'output.tex')

    if not os.path.exists(expected_path):
        return {'score': 0, 'error': f'Expected output not found: {expected_path}'}

    v1_path = os.path.join(DOCS_DIR, task_config['doc_pair'][0])
    v2_path = os.path.join(DOCS_DIR, task_config['doc_pair'][1])

    return grade(expected_path, actual_path, v1_path, v2_path, verbose=True)


def run_single_task(task_id: str, run_number: int = 1, timeout: int = 600) -> dict:
    """Run a single task and return results."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_id = f"{task_id}_run{run_number}_{timestamp}"

    print(f"\n{'='*60}")
    print(f"Running: {task_id} (run #{run_number})")
    print(f"Run ID: {run_id}")
    print(f"{'='*60}")

    # Load task
    task_config = load_task(task_id)
    print(f"Task: {task_config['title']}")
    print(f"Difficulty: {task_config.get('difficulty', 'unknown')}")

    # Setup
    work_dir = setup_work_dir(task_config, run_id)
    print(f"Work directory: {work_dir}")

    # Build prompt
    prompt = build_agent_prompt(task_config, work_dir)

    # Save prompt for reference
    results_dir = os.path.join(RESULTS_DIR, run_id)
    os.makedirs(results_dir, exist_ok=True)
    with open(os.path.join(results_dir, 'prompt.txt'), 'w') as f:
        f.write(prompt)

    # Run agent
    print(f"\nStarting agent (timeout: {timeout}s)...")
    agent_result = run_agent(prompt, work_dir, timeout)

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
    print("\n" + "=" * 70)
    print("SUMMARY OF ALL RESULTS")
    print("=" * 70)
    print(f"{'Task':<12} {'Run':<4} {'Score':>7} {'Duration':>10} {'Difficulty':<12}")
    print("-" * 70)

    scores_by_task = {}
    for r in all_results:
        task_id = r['task_id']
        print(f"{task_id:<12} {'#' + str(r.get('run_num', 1)):<4} "
              f"{r['score']:>6.1f} {r['agent_duration']:>9.1f}s "
              f"{r.get('difficulty', '?'):<12}")
        if task_id not in scores_by_task:
            scores_by_task[task_id] = []
        scores_by_task[task_id].append(r['score'])

    print("-" * 70)
    if scores_by_task:
        avg_scores = {k: sum(v)/len(v) for k, v in scores_by_task.items()}
        overall_avg = sum(sum(v) for v in scores_by_task.values()) / sum(len(v) for v in scores_by_task.values())
        print(f"\nPer-task averages:")
        for task_id, avg in sorted(avg_scores.items()):
            print(f"  {task_id}: {avg:.1f}")
        print(f"\nOverall average: {overall_avg:.1f}")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description='Run document comparison tasks with sub-agents')
    parser.add_argument('--task', action='append', help='Task ID to run (can specify multiple)')
    parser.add_argument('--all', action='store_true', help='Run all tasks')
    parser.add_argument('--runs', type=int, default=1, help='Number of runs per task')
    parser.add_argument('--timeout', type=int, default=600, help='Agent timeout in seconds')
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

    # Run tasks
    os.makedirs(RESULTS_DIR, exist_ok=True)
    all_results = []

    for task_id in task_ids:
        for run_num in range(1, args.runs + 1):
            result = run_single_task(task_id, run_num, args.timeout)
            result['run_num'] = run_num
            all_results.append(result)

    # Print summary
    if len(all_results) > 1:
        print_summary(all_results)

    # Save aggregate results
    agg_path = os.path.join(RESULTS_DIR, f"aggregate_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(agg_path, 'w') as f:
        json.dump(all_results, indent=2, fp=f)
    print(f"\nAggregate results saved to: {agg_path}")


if __name__ == '__main__':
    main()
