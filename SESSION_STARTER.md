# Session Starter Prompt Template

Use this prompt when continuing work on the RX project in a new session.

---

## Basic Session Start (No Pending Plan)

```
I'm continuing work on the RX (Regex Tracer) project. This is a high-performance file search and analysis tool built with Python, FastAPI, and ripgrep.

Project location: /Users/wlame/dev/tracer

Key documentation files:
- ARCHITECTURE.md - Complete system architecture and implementation details
- README.md - User-facing documentation
- CHANGELOG.md - Version history

Recent work completed:
[Briefly describe what was done in the last session]

Current task:
[Describe what you want to work on]

Please review the architecture documentation and help me continue from where we left off.
```

---

## Session Start with Implementation Plan

```
I'm continuing work on the RX (Regex Tracer) project from a previous session.

Project location: /Users/wlame/dev/tracer

There is an implementation plan from the previous session that needs to be executed.
The plan should be located at: ~/.claude/plans/

Key context:
- ARCHITECTURE.md contains complete system architecture
- The plan file has detailed implementation steps
- All changes should follow existing patterns in the codebase

Please:
1. Read the implementation plan file
2. Review ARCHITECTURE.md for context on existing features
3. Continue executing the plan step-by-step
4. Run tests after each major change
5. Update the plan file with progress/notes as you go

Note: The plan was created to [brief description of what the plan covers]
```

---

## Session Start for Analyse Enhancement (Current Plan)

```
I'm continuing work on the RX (Regex Tracer) project. We have an implementation plan for enhancing the analyse feature to support compressed file analysis.

Project location: /Users/wlame/dev/tracer

Implementation plan location: ~/.claude/plans/

Context from previous session:
- Created analyse_cache.py module with 19 passing tests (88% coverage)
- Enhanced FileAnalysisResult model with compression and index fields
- Updated CLI output to display compression and index info
- All existing tests passing (670 tests)

Current implementation plan covers:
1. Integrating analyse_cache into analyse.py for automatic caching
2. Adding compression detection and info to analysis results
3. Implementing compressed file analysis (decompress to /tmp, analyze, cleanup)
4. Adding index information detection and display
5. Handling edge cases (disk full, unsupported formats, cleanup failures)
6. Writing comprehensive tests for the new functionality

Please:
1. Read the implementation plan from ~/.claude/plans/
2. Review ARCHITECTURE.md sections on:
   - Section 4: analyse.py (file analysis)
   - Section 21: analyse_cache.py (caching)
   - Section 7: compression.py (compression detection)
   - Section 8: compressed_index.py (compressed file handling)
3. Execute the plan step-by-step
4. Run tests after each implementation step
5. Update me on progress and any issues encountered

The goal is to make analyse work seamlessly with both raw text files and compressed files, with full caching support.
```

---

## Tips for Session Continuity

### Information to Provide

1. **Project location**: Always specify `/Users/wlame/dev/tracer`

2. **Recent context**: Summarize what was done in the last 1-2 sessions
   - Features implemented
   - Tests written
   - Files modified
   - Current test status

3. **Current goal**: Clearly state what you want to accomplish
   - Feature to implement
   - Bug to fix
   - Refactoring to complete
   - Tests to write

4. **Relevant documentation**: Point to specific sections of ARCHITECTURE.md if applicable

5. **Implementation plan**: If a plan exists, mention its location and purpose

### What to Avoid

- Don't ask the AI to "figure out what to do" - always provide clear direction
- Don't omit the project location - context is important
- Don't skip mentioning existing plans or documentation
- Don't forget to mention if there are failing tests or known issues

### Example: Good vs Bad Prompts

**Bad**:
```
Continue working on RX
```

**Good**:
```
I'm continuing work on RX at /Users/wlame/dev/tracer. 

Last session we implemented background task management for compress/index operations (task_manager.py, 3 new HTTP endpoints). All 670 tests are passing.

Current task: Implement the analyse enhancement plan to support compressed file analysis. The plan is at ~/.claude/plans/ and covers:
- Cache integration
- Compression detection
- Temp file handling
- Index info display

Please read the plan and ARCHITECTURE.md sections 4, 7, 8, and 21, then proceed with implementation.
```

---

## Quick Reference: Key Files

### Documentation
- `ARCHITECTURE.md` - Complete architecture reference (read this first!)
- `README.md` - User documentation
- `CHANGELOG.md` - Version history
- `IMPLEMENTATION_PLAN_*.md` - Specific implementation plans

### Core Source Files
- `src/rx/trace.py` - Main search engine
- `src/rx/analyse.py` - File analysis
- `src/rx/web.py` - FastAPI server
- `src/rx/models.py` - All Pydantic models
- `src/rx/index.py` - Large file indexing

### Cache Locations
- `~/.cache/rx/indexes/` - Line-based indexes for large files
- `~/.cache/rx/trace_cache/` - Cached trace results
- `~/.cache/rx/analyse_cache/` - Cached analysis results
- `~/.cache/rx/compressed_indexes/` - Compressed file indexes
- `~/.cache/rx/seekable_indexes/` - Seekable zstd indexes

### Test Commands
```bash
# Run all tests
uv run pytest -v

# Run specific test file
uv run pytest tests/test_analyse_cache.py -v

# Run with coverage
uv run pytest --cov=rx --cov-report=html
```

---

## Common Scenarios

### Scenario 1: Adding a New Feature

```
I'm working on RX at /Users/wlame/dev/tracer.

I want to add a new feature: [describe feature]

This will require:
- New module: src/rx/[name].py
- New endpoint: [if applicable]
- New CLI command: [if applicable]
- Tests in: tests/test_[name].py

Please:
1. Review ARCHITECTURE.md for similar features
2. Design the implementation following existing patterns
3. Implement with comprehensive error handling
4. Write tests before or alongside implementation
5. Update ARCHITECTURE.md if this is a significant feature
```

### Scenario 2: Fixing a Bug

```
I'm working on RX at /Users/wlame/dev/tracer.

Bug description: [describe the bug]

Steps to reproduce:
1. [step 1]
2. [step 2]

Expected behavior: [what should happen]
Actual behavior: [what actually happens]

Suspected location: [file/function if known]

Please:
1. Investigate the issue
2. Write a failing test that reproduces the bug
3. Fix the bug
4. Verify all tests pass
```

### Scenario 3: Writing Tests

```
I'm working on RX at /Users/wlame/dev/tracer.

I need comprehensive tests for: [module/feature]

Current test coverage: [X%] (run: uv run pytest --cov=rx)

Test scenarios needed:
- [scenario 1]
- [scenario 2]
- Edge cases: [list edge cases]

Please write tests following the patterns in tests/ directory, ensuring we cover:
- Happy path
- Error cases
- Edge cases
- Integration with other modules
```

### Scenario 4: Refactoring

```
I'm working on RX at /Users/wlame/dev/tracer.

Refactoring goal: [describe what needs refactoring]

Reason: [why - performance, maintainability, consistency, etc.]

Current implementation: [describe current approach]
Desired implementation: [describe desired approach]

Constraints:
- Must maintain backward compatibility [yes/no]
- All existing tests must continue passing
- No breaking API changes [if applicable]

Please:
1. Review current implementation
2. Propose detailed refactoring steps
3. Execute refactoring incrementally
4. Run tests after each step
```

---

## Environment Variables Reference

Key environment variables you might need to know about:

```bash
RX_DEBUG=1                    # Enable debug mode
RX_LARGE_FILE_MB=100         # Large file threshold (default: 100MB)
RX_MAX_SUBPROCESSES=20       # Parallel workers (default: 20)
NEWLINE_SYMBOL="\n"          # Line separator for testing
```

See ARCHITECTURE.md "Configuration & Environment Variables" section for complete list.

---

## Final Checklist Before Starting Session

- [ ] Specified project location: `/Users/wlame/dev/tracer`
- [ ] Described recent context from last session
- [ ] Clearly stated current goal/task
- [ ] Mentioned any existing implementation plans
- [ ] Referenced relevant ARCHITECTURE.md sections
- [ ] Noted current test status
- [ ] Provided any error messages or issues if applicable

---

**Remember**: The AI doesn't have memory of previous sessions. Provide enough context for it to understand where the project stands and what needs to be done next.
