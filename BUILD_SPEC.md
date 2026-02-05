Build an innovative Prompt Version Control System that disrupts traditional prompt management.

## Core Vision
Go beyond git-style line diffs. Build a system that understands prompts semantically and optimizes them based on real performance data.

## Innovative Features to Build

### 1. Semantic Prompt Diffing
- Not just text changes, but understand INTENT changes
- Detect: scope changes, constraint additions, tone shifts, structure changes
- Visual diff showing semantic categories (not just +/- lines)

### 2. A/B Testing Framework
- Run same input through multiple prompt versions
- Track metrics: success rate, token usage, latency, quality scores
- Statistical significance testing
- Auto-winner selection based on configurable criteria

### 3. Performance Regression Testing
- Test suite of "golden" inputs for each prompt
- Compare new version vs baseline on full test suite
- Catch regressions before deployment
- Generate performance reports

### 4. Prompt Composition Trees
- Track prompt inheritance (base template → specialized variants)
- Visual tree showing relationships
- Propagate changes from parent to children
- Fragment library for reusable prompt components

### 5. Auto-Optimization Suggestions
- Analyze version history for patterns
- Suggest: "Versions with explicit examples perform 23% better"
- Recommend next experiments based on unexplored variants

### 6. Prompt Lineage & Provenance
- Track complete history: who changed what, when, and why
- Tags for versions (production, staging, experimental)
- Branch/merge semantics for prompt experiments
- Compare any two versions side-by-side

## Architecture

```
prompt-vc/
├── CLI tool (primary interface)
├── Local server (for web UI and API)
├── SQLite database (versions, test results, metadata)
├── Config file (.pit.yaml)
└── Web dashboard (optional but nice)
```

## Data Model

- **Prompt**: ID, name, current_version, base_template, variables
- **Version**: prompt_id, version_number, content, semantic_diff, metrics, tags
- **TestSuite**: name, test_cases (input + expected criteria)
- **TestRun**: version_id, test_suite_id, results, timestamp
- **Fragment**: reusable prompt components

## Tech Stack
- Python with FastAPI for server
- Click or Typer for CLI
- SQLite with SQLAlchemy
- Pydantic for data models
- Jinja2 for prompt templating
- pytest for testing

## Must-Have Commands

```bash
pit init                    # Initialize in a project
pit add "summarize"         # Add a new prompt
pit commit -m "Added examples"  # Save new version
pit diff v1 v2              # Semantic diff
pit test summarize          # Run regression tests
pit abtest v3 v4 --suite=qa   # A/B test two versions
pit optimize summarize      # Get optimization suggestions
pit tree summarize          # Show composition tree
```

## Innovation Priorities
1. Semantic understanding of prompt changes
2. Integrated A/B testing with metrics
3. Regression test suite per prompt
4. Composition/inheritance system

Start by creating a detailed plan, then implement. Show me the architecture and data model first.