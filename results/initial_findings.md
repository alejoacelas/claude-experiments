# Initial Test Results

## First Run Results (using doccompare tool)

| Task | Difficulty | Score | Key Observations |
|------|-----------|-------|-----------------|
| task1 | Medium | 97.4 | Very strong. 9 under-applied formatting changes, 3 corrupted lines. |
| task3 | Hard | 96.5 | Surprisingly good. 12 under-applied copyediting changes, 15 kept-wrong v1 lines. |
| task5 | Easy-Medium | 93.1 | Good but 8 over-applied changes. Agent applied some changes it shouldn't have. |

**Average score: 95.7/100**

## Error Patterns

### Task 1 (Formatting Only) - Score: 97.4
- **Under-application**: Agent missed some `\,` number formatting fixes and `\` abbreviation fixes
- **Corruption**: 3 lines didn't match either source - likely minor editing artifacts
- Agent correctly avoided applying content changes, new sections, and new authors
- 99.6% overall similarity - very clean output

### Task 3 (Copyediting Only) - Score: 96.5
- **Under-application**: 12 small wording changes from v2 were not applied
- **Kept wrong**: 15 v1 lines that should have been updated with small tweaks
- **Corruption**: 3 lines modified incorrectly
- Zero over-application - agent correctly avoided all structural changes
- This task requires distinguishing small wording tweaks within blocks that also contain large changes

### Task 5 (Cherry-Pick Numbered Changes) - Score: 93.1
- **Over-application**: Agent applied 8 changes from v2 that weren't in the specified list
- **Under-application**: 2 specified changes were not applied
- Block-level accuracy at 85.5% exact match suggests some blocks were modified incorrectly
- The agent struggled somewhat with inserting new content at exactly the right location
- 5 v1 lines were incorrectly removed

## Tool Observations

1. The `doccompare compare` output provides good structure for the agent to work with
2. JSON output mode is useful for programmatic analysis
3. The block numbering is consistent and agents can reference specific changes
4. The main challenge is that agents tend to be imprecise about which changes within a modified block to apply
5. All 3 tested tasks scored above 93, showing the tool provides a solid foundation
6. Under-application is more common than over-application - agents tend to be conservative

## Next Steps for Tool Improvement

1. Add a `--change-details N` flag to show granular within-block diffs for a specific change
2. Add word-level diff highlighting within modified blocks
3. Consider adding a `preview` command that shows what applying specific changes would produce
4. The `apply` command could be made more reliable for agents to use directly
5. Test with the markdown document pairs (design_v1.md / design_v2.md) which have 137 changes
6. Test with the report document pairs which have different edit patterns
7. Run multiple iterations to measure variance across runs
