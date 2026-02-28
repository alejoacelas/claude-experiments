# AI Document Comparison Tool - Testing Suite

A testing framework for evaluating how well AI agents perform document comparison and selective editing tasks. The project includes:

1. **`doccompare`** - A block-based document comparison CLI tool designed for AI agent consumption
2. **`tasks/`** - A suite of 5 realistic tasks with varying difficulty
3. **`harness/`** - Test runner, auto-grader, and gold standard generator
4. **`documents/`** - Realistic document pairs (LaTeX papers, Markdown design docs) with many types of edits

## Quick Start

```bash
# Compare two documents
python3 doccompare/doccompare.py compare documents/paper_v1.tex documents/paper_v2.tex

# List blocks in a document
python3 doccompare/doccompare.py blocks documents/paper_v1.tex

# Show anchor points
python3 doccompare/doccompare.py anchors documents/paper_v1.tex documents/paper_v2.tex

# Run all tasks
python3 harness/run_test.py --all

# Run a specific task
python3 harness/run_test.py --task task1

# Grade an output manually
python3 harness/grader.py tasks/task1/expected_output.tex path/to/output.tex --v1 documents/paper_v1.tex --v2 documents/paper_v2.tex
```

## Project Structure

```
.
├── doccompare/          # The document comparison tool
│   └── doccompare.py    # CLI tool with block-based diffing
├── documents/           # Test document pairs
│   ├── paper_v1.tex     # ML paper - original
│   ├── paper_v2.tex     # ML paper - revised (82 differences)
│   ├── design_v1.md     # Design doc - original
│   ├── design_v2.md     # Design doc - revised
│   ├── report_v1.tex    # Grant proposal - original
│   └── report_v2.tex    # Grant proposal - revised
├── tasks/               # Task definitions
│   ├── task1/           # Formatting-only changes (medium)
│   ├── task2/           # Add all new content, reject removals (hard)
│   ├── task3/           # Copyediting-only changes (hard)
│   ├── task4/           # Full merge except one section (medium)
│   └── task5/           # Cherry-pick numbered changes (easy-medium)
├── harness/             # Test infrastructure
│   ├── run_test.py      # Main test runner
│   ├── grader.py        # Auto-grader with multiple metrics
│   └── generate_gold.py # Gold standard output generator
└── results/             # Test run outputs and scores
```

## Tasks

| Task | Difficulty | Description |
|------|-----------|-------------|
| task1 | Medium | Apply only formatting/LaTeX improvements (tables, packages, en-dashes) |
| task2 | Hard | Add all new content from v2, reject all removals and modifications |
| task3 | Hard | Apply only small wording tweaks, reject structural changes |
| task4 | Medium | Apply all changes except in the Experiments section |
| task5 | Easy-Medium | Cherry-pick specific numbered changes from comparison output |

## The doccompare Tool

Unlike standard diff which shows line-by-line changes, `doccompare`:

- **Parses documents semantically** into blocks (headings, paragraphs, equations, tables, code, etc.)
- **Identifies anchor points** between documents using content fingerprinting
- **Detects moved blocks** that appear in both documents at different positions
- **Presents changes block-by-block** with similarity scores and diff summaries
- **Supports selective application** of changes from one document to another

### Commands

- `compare file_a file_b` - Full block-by-block comparison
- `blocks file` - List all semantic blocks in a document
- `show file BLOCK_ID` - Show full content of a specific block
- `anchors file_a file_b` - Show matched anchor points
- `apply file_a file_b --changes 1,3,5-10` - Apply selected changes

### Output Formats

- `--format text` (default) - Human/agent-readable text report
- `--format json` - Structured JSON for programmatic use

## Grading

The auto-grader evaluates agent output using multiple metrics:

- **Overall similarity** - Character-level SequenceMatcher ratio
- **Line-level precision/recall/F1** - Which lines match the expected output
- **Block-level accuracy** - Semantic block matching with fuzzy similarity
- **Error categorization** - Over-applied, under-applied, corrupted content

Final score is a weighted combination (0-100).

## Running Tests

```bash
# Run all tasks once
python3 harness/run_test.py --all

# Run specific tasks multiple times
python3 harness/run_test.py --task task1 --task task5 --runs 3

# Longer timeout for hard tasks
python3 harness/run_test.py --task task3 --timeout 900
```

Results are saved to `results/` with full transcripts, scores, and metrics.
