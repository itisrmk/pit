# PIT Skill - Prompt Information Tracker

> **Git for Prompts** — Enable LLM agents to help developers version control their LLM prompts.

## Overview

PIT is a semantic version control system designed specifically for managing LLM prompts. Unlike traditional Git workflows, PIT understands the *semantics* of prompts—tracking not just what changed, but *why* it matters for AI behavior.

## When to Use This Skill

Use PIT when the developer is:
- Managing multiple versions of LLM prompts
- Collaborating on prompt engineering
- Debugging which prompt change broke behavior
- Needing to track prompt performance metrics
- Sharing prompts across teams/projects
- Building production AI systems with prompt dependencies

## Installation

```bash
pip install prompt-pit
```

## Core Commands

### Initialize a Project
```bash
pit init
```
Creates `.pit/` directory with database and config.

### Add a Prompt
```bash
pit add system-prompt.md --name "customer-support" --description "AI assistant for support"
```

### Commit Changes
```bash
pit commit customer-support --message "Added empathy guidelines"
```

### View History
```bash
pit log customer-support                    # All versions
pit log customer-support --limit 5          # Last 5 versions
pit log customer-support --where "success_rate > 0.9"
```

### Compare Versions
```bash
pit diff customer-support --v1 1 --v2 5     # Text diff
pit diff customer-support --v1 1 --v2 5 --semantic  # LLM-powered semantic diff
```

### Checkout a Version
```bash
pit checkout customer-support --version 3
```

### Tag Important Versions
```bash
pit tag customer-support --version 5 --tag production
pit tag customer-support --version 5 --tag stable
```

## Advanced Features

### 1. Binary Search (Bisect)
Find which version broke behavior:
```bash
pit bisect start --prompt customer-support --failing-input "problematic query"
pit bisect good v1
pit bisect bad v10
pit bisect log
pit bisect reset
```

### 2. Time-Travel Replay
Test same input across versions:
```bash
pit replay run customer-support --input "Hello" --versions 1-10
pit replay compare customer-support --input "Hello" --versions 1,5,10
```

### 3. Shareable Patches
Export/import prompt changes:
```bash
pit patch create customer-support v1 v2 --output fix.patch
pit patch show fix.patch
pit patch apply fix.patch --to other-prompt
pit patch preview fix.patch --on other-prompt
```

### 4. Git-Style Hooks
```bash
pit hooks install pre-commit    # Run security scan before commit
pit hooks install post-checkout # Auto-run tests on version switch
pit hooks list
pit hooks run pre-commit --prompt customer-support
```

### 5. Query Language
Find versions by behavior:
```bash
pit log --where "success_rate > 0.9"
pit log --where "avg_latency_ms < 500"
pit log --where "content contains 'be concise'"
pit log --where "tags contains 'production' AND success_rate > 0.95"
```

### 6. Dependencies
Manage prompt dependencies:
```bash
pit deps add shared-prompts github org/repo/prompts --version v1.0
pit deps add local-shared local ../shared/prompts
pit deps install
pit deps list
pit deps tree
```

### 7. Worktrees
Multiple prompt contexts:
```bash
pit worktree add ./experiment customer-support@v5
pit worktree list
pit worktree remove ./experiment
```

### 8. Stash
Save work-in-progress:
```bash
pit stash save "WIP: improving tone" --with-test test-input.txt
pit stash list
pit stash pop 0
pit stash apply 0
pit stash drop 0
```

### 9. Bundles
Package and share prompts:
```bash
pit bundle create my-bundle --prompts "p1,p2" --with-history
pit bundle inspect my-bundle.bundle
pit bundle install my-bundle.bundle
pit bundle export my-bundle.bundle --format json
```

## Configuration

Create `.pit.yaml` in project root:
```yaml
llm:
  provider: anthropic  # or openai, ollama
  api_key: ${ANTHROPIC_API_KEY}

defaults:
  auto_commit: false
  require_tests: true

security:
  max_severity: medium

performance:
  max_latency_ms: 2000
  min_success_rate: 0.95
```

## Project Structure

```
my-project/
├── .pit/                   # PIT database and config
│   ├── config.yaml
│   └── pit.db
├── prompts/               # Your prompt files
│   ├── customer-support.md
│   └── summarizer.md
└── .pit.yaml             # Optional global config
```

## Common Workflows

### Workflow 1: Debug a Broken Prompt
```bash
# Start bisect session
pit bisect start --prompt my-prompt --failing-input "test case"

# Mark known good/bad versions
pit bisect good v1
pit bisect bad v10

# Test middle versions until found
pit bisect log  # Shows result

# View what changed
pit diff my-prompt --v1 <good> --v2 <bad>

# Reset when done
pit bisect reset
```

### Workflow 2: Share Prompt Improvements
```bash
# Create patch from improvements
pit patch create my-prompt v5 v7 --output improvements.patch

# Share patch with team (email, slack, PR)

# Team member applies it
git clone <repo>
cd repo
pit patch apply improvements.patch --to my-prompt
```

### Workflow 3: A/B Test Prompts
```bash
# Create test suite
pit test create-suite --name "core-tests"
pit test add-case core-tests --name "greeting" --input "Hello" --expected "friendly"

# Run against versions
pit test run my-prompt --suite core-tests --version 5
pit test run my-prompt --suite core-tests --version 7

# Compare metrics
pit stats show my-prompt
```

### Workflow 4: Production Deployment
```bash
# Tag stable version
pit tag my-prompt --version 10 --tag production

# Install in production
pip install prompt-pit
pit init
pit add prod-prompt.md --name "production-prompt"
pit checkout production-prompt --version 10

# Verify
pit show production-prompt
```

## Integration with Development Workflows

### With Git
```bash
# Pre-commit hook in .git/hooks/pre-commit
pit hooks run pre-commit --prompt customer-support

# Commit prompt changes with code
pit commit customer-support --message "Updated tone guidelines"
git add .
git commit -m "feat: improve customer support tone"
```

### With CI/CD
```yaml
# .github/workflows/prompt-validation.yml
- name: Validate Prompts
  run: |
    pip install prompt-pit
    pit validate customer-support --fail-on medium
    pit test run customer-support --suite regression-tests
```

### With LangChain
```python
from pit import get_prompt

# Load versioned prompt
prompt = get_prompt("customer-support", version="production")

# Use in chain
chain = prompt | llm | output_parser
```

## Best Practices

1. **Commit often** - Small, semantic changes are easier to bisect
2. **Tag releases** - Mark production/stable versions clearly
3. **Write tests** - Use test suites to catch regressions
4. **Use semantic messages** - "Added empathy" not "Updated prompt"
5. **Query by metrics** - Find your best performing versions
6. **Share patches** - Distribute improvements like code reviews

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Not a pit project" | Run `pit init` first |
| Can't find version | Use `pit log` to see available versions |
| Merge conflicts | Use `pit diff` to understand semantic changes |
| Slow queries | Add indexes or use `--limit` flag |
| Hook not running | Check `pit hooks list` and install with `pit hooks install` |

## Examples

See `examples/` directory for:
- Customer support prompt evolution
- RAG prompt version control
- Multi-model prompt testing
- Team collaboration workflows

## Resources

- GitHub: https://github.com/itisrmk/pit
- PyPI: https://pypi.org/project/prompt-pit/
- Issues: https://github.com/itisrmk/pit/issues
- Documentation: README.md in repo

## License

MIT License - Open source and free to use.

---

**Quick Start for Agents:**

When a user wants to version control prompts:
1. Check if `pit` is installed: `which pit`
2. If not, suggest: `pip install prompt-pit`
3. Guide through `pit init` and `pit add`
4. Show `pit commit`, `pit log`, `pit diff`
5. Introduce advanced features based on their needs
