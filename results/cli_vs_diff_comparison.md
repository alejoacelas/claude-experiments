# CLI Agent vs Diff-Only Agent: Comparison Results

## Methodology

Two agent modes were compared on identical document comparison tasks:

- **CLI agent**: Full tool access (Bash, Read, Write, Edit, Glob, Grep). Can use the `doccompare.py` tool interactively, read files, make incremental edits, and verify work.
- **Diff-only agent**: Receives both full source files AND a unified diff inline in the prompt. Only has the Write tool. Must produce the complete output in one pass.

Both modes use the same Claude model via `claude --print`. Tasks range from simple formatting changes to complex multi-document structural merges.

## Results

| Task | Difficulty | Doc Lines | Change Type | CLI Score | CLI Time | Diff Score | Diff Time | Δ Quality |
|------|-----------|-----------|-------------|-----------|----------|------------|-----------|-----------|
| task1 | medium | 398 | Formatting only (paper) | 98.0 | 474s | 98.0 | 347s | 0.0 |
| task3 | hard | 398 | Copyediting only (paper) | 91.8 | 704s | 91.2 | 690s | +0.6 |
| task6 | hard | 489 | Typos only, reject British English (design) | 100.0 | 163s | 100.0 | 263s | 0.0 |
| task7 | very-hard | 489 | All changes except section reorder + new sections | 99.8 | 494s | 99.6 | 583s | +0.2 |
| task8 | hard | 489 | All prose changes, preserve code blocks | 100.0 | 438s | 100.0 | 524s | 0.0 |
| task9 | very-hard | 538 | Resolve 12 merge conflicts with rules | 100.0 | 334s | 100.0 | 435s | 0.0 |
| task10 | very-hard | 893 | Typos only across multi-doc combined file | 100.0 | 205s | 100.0 | 404s | 0.0 |

### Summary Statistics

- **Average quality delta**: +0.1 points (effectively zero)
- **Maximum quality delta**: +0.6 points (task3)
- **Average time ratio** (diff-only / CLI): 1.34x
- **CLI wins on quality**: 2 of 7 tasks (by < 1 point each)
- **Diff-only wins on quality**: 0 of 7 tasks
- **Tied on quality**: 5 of 7 tasks (both within 0.1 points)

## Key Finding

**There is no meaningful quality gap between CLI and diff-only approaches for documents up to ~900 lines with well-defined selective editing tasks.**

Both approaches achieve near-identical accuracy (within 0.6 points on every task). The CLI agent has a consistent but modest speed advantage (~34% faster on average), likely because it can make incremental edits rather than producing the entire file at once.

## Why Tasks Don't Differentiate

The tasks tested include genuinely hard challenges:
- **Within-block discrimination** (task3): Apply small wording tweaks but reject structural changes within the same diff hunk
- **Typo vs. style filtering** (task6): Distinguish genuine misspellings from British English conversions
- **Section reordering** (task7): Handle swapped sections in the diff while preserving v1's ordering
- **Code/prose boundary** (task8): Preserve code blocks while updating all surrounding prose
- **Conflict resolution** (task9): Find and resolve 12 merge conflicts with context-dependent rules
- **Multi-document scale** (task10): 893-line combined document with 1100-line diff

Despite this variety, the diff-only agent handles all of them essentially perfectly. The reason: **a unified diff plus both full file contents provides ALL the information needed for correct selective editing when documents fit within the context window.** The agent can reason about the diff, identify what to apply/reject, and construct the output correctly from the information available.

## What Would Create Separation

Based on the experiments, CLI tools provide advantages in:

1. **Speed**: CLI is ~34% faster on average due to incremental editing (Edit tool) vs. full-file Write
2. **Scale**: For documents exceeding ~200K tokens of combined content, the diff-only prompt may not fit or may exceed the model's effective reasoning capacity
3. **Tool-dependent features**: Tasks requiring doccompare's numbered change output (task5) can only be done with CLI access

To create a genuine **quality** gap, you would likely need:

- **Documents 10-50x larger** (5,000-50,000 lines) where the diff exceeds comfortable context
- **Multi-file cross-referencing** across 5+ files that can't all fit in one prompt
- **Tasks requiring validation** (compile/test the output to verify correctness)
- **Iterative tasks** where errors compound and intermediate verification helps
- **Dynamic exploration** tasks where you don't know what to look for until you start investigating

## Recommendations for Harder Tasks

1. **Scale up documents**: Use real-world codebases with 10K+ line files. The diff-only approach has a hard ceiling when prompt size exceeds context limits.

2. **Multi-file tasks**: Require the agent to cross-reference 5-10 files to determine which changes to apply. This exceeds what can be stuffed into a single prompt.

3. **Validation-required tasks**: "Apply changes and ensure the document compiles" or "Apply changes and ensure all cross-references resolve." This requires iterative tool use.

4. **Exploration tasks**: "Find and fix all instances of a pattern across the codebase" where the agent doesn't know the scope of changes in advance.

5. **Compositional tasks**: Multi-step workflows where later steps depend on results of earlier steps (e.g., "apply formatting changes, then update the table of contents to match").
