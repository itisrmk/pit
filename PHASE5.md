# PHASE 5 Implementation Plan

## 10 New Core Version Control Features

Following the claude-code-workflow skill: Plan → Auto-accept → Verification loops

---

## Phase 1: Prompt Bisect ⭐
Binary search through prompt versions to find which change broke behavior.

**Commands:**
- `pit bisect start --failing-input "..." [--prompt name]`
- `pit bisect good [version]`
- `pit bisect bad [version]`
- `pit bisect run [--command "..."]` (automated testing)
- `pit bisect reset`
- `pit bisect log` (show current state)

**State Storage:**
- `.pit/bisect_state.json` - tracks bad/good bounds, current test, prompt

**Algorithm:**
1. User marks known good and bad versions
2. Check out middle version
3. User tests or --command tests
4. Mark good/bad, repeat until found
5. Report first bad version with semantic diff

**New Files:**
- `pit/cli/commands/bisect.py` - CLI commands
- `pit/core/bisect.py` - Core bisect logic
- `tests/test_cli/test_bisect.py` - Tests

---

## Phase 2: Semantic Merge & Conflict Resolution

**Smart merge that understands prompt semantics:**

**Conflict Categories:**
- `tone` - changes to personality/voice
- `constraints` - rules and limitations  
- `examples` - few-shot examples
- `structure` - output format/instructions
- `variables` - template variable changes
- `context` - background information

**Auto-merge Rules:**
- Orthogonal categories = auto-merge
- Same category = manual resolution
- Add vs Remove in same category = conflict

**Commands:**
- Enhanced `pit diff --semantic-categories`
- New merge detection in commit flow
- `pit merge --prompt name --version v1` (simulated)

**New Files:**
- `pit/core/semantic_merge.py` - Category detection
- Update `pit/core/semantic_diff.py` - Add categorization

---

## Phase 3: Prompt Worktrees

**Multiple prompt contexts without switching:**

**Commands:**
- `pit worktree add <path> <prompt[@version]>`
- `pit worktree list`
- `pit worktree remove <path>`
- `pit worktree prune` (clean up stale)

**Storage:**
- `.pit/worktrees.json` - maps paths to (prompt, version, HEAD)
- Worktrees are symlinks/copy-on-write to prompt files

**Behavior:**
- Each worktree has independent HEAD
- Shares underlying version database
- Can commit from any worktree

**New Files:**
- `pit/cli/commands/worktree.py`
- `pit/core/worktree.py`
- `tests/test_cli/test_worktree.py`

---

## Phase 4: Shareable Patches

**Export/import prompt changes:**

**Commands:**
- `pit diff v1 v2 --patch > change.patch`
- `pit patch apply <file> --to <prompt>`
- `pit patch show <file>` (preview)

**Patch Format (.promptpatch):**
```json
{
  "format": "pit-patch-v1",
  "source": {"prompt": "name", "versions": [1, 2]},
  "semantic_diff": {...},
  "text_diff": "...",
  "author": "...",
  "created_at": "..."
}
```

**New Files:**
- `pit/core/patch.py`
- Update `pit/cli/commands/version.py` - add --patch flag

---

## Phase 5: Time-Travel Replay

**Replay same input across all versions:**

**Commands:**
- `pit replay --input "..." --prompt name --versions v1..v5`
- `pit replay --input-file test.txt --prompt name --all`
- `pit replay --compare v1,v3,v5` (side-by-side)

**Output:**
- Rich table: Version | Output | Latency | Tokens
- Requires LLM provider (Anthropic/OpenAI)
- Cached results in .pit/replay_cache/

**New Files:**
- `pit/cli/commands/replay.py`
- `pit/core/replay.py`
- `tests/test_cli/test_replay.py`

---

## Phase 6: Prompt Hooks

**Git-style hooks with prompt awareness:**

**Hook Types:**
- `pre-commit` - validate before commit
- `post-commit` - notification, metrics
- `pre-checkout` - warn about uncommitted changes
- `post-checkout` - auto-run regression tests
- `pre-merge` - check semantic compatibility
- `post-merge` - update downstream

**Commands:**
- `pit hooks list`
- `pit hooks install <hook-name> [--script path]`
- `pit hooks uninstall <hook-name>`

**Storage:**
- `.pit/hooks/` directory
- Executable scripts receive env vars: PROMPT_NAME, VERSION, SEMANTIC_DIFF_JSON

**New Files:**
- `pit/cli/commands/hooks.py`
- `pit/core/hooks.py`
- `tests/test_cli/test_hooks.py`

---

## Phase 7: Prompt Bundles

**Package and share prompts:**

**Commands:**
- `pit bundle create <name> [--prompts p1,p2] [--with-tests] [--with-history]`
- `pit bundle install <file.bundle> [--prefix name]`
- `pit bundle inspect <file.bundle>`
- `pit bundle export <name> --format json|yaml`

**Bundle Format (.bundle = tar.gz):**
```
manifest.json
prompts/
  prompt1/
    versions/
    config.yaml
test-suites/
```

**New Files:**
- `pit/cli/commands/bundle.py`
- `pit/core/bundle.py`
- `tests/test_cli/test_bundle.py`

---

## Phase 8: Query Language for Versions

**Query versions by behavior, not just metadata:**

**Commands:**
- `pit log --where "success_rate > 0.9"`
- `pit log --where "avg_latency_ms < 500"`
- `pit log --where "tags contains 'production'"`
- `pit log --where "content contains 'be concise'"`
- `pit log --where "created_after '2024-01-01'"`

**Query Syntax:**
- Field operators: `>`, `<`, `>=`, `<=`, `=`, `!=`, `contains`
- Boolean: `AND`, `OR`, `NOT`
- Fields: all Version model fields + content search

**New Files:**
- `pit/core/query.py` - Query parser
- Update `pit/cli/commands/version.py` - add --where flag

---

## Phase 9: Prompt Stash with Context

**Save WIP with full context:**

**Commands:**
- `pit stash save "message" [--with-test <file>] [--with-input "..."]`
- `pit stash list`
- `pit stash pop [index]`
- `pit stash apply [index]` (keep in stash)
- `pit stash drop [index]`
- `pit stash clear`

**Stash Content:**
- Current prompt content (even uncommitted)
- Draft commit message
- Associated test case (if provided)
- Timestamp, author

**Storage:**
- `.pit/stash/` directory
- Each stash = JSON file with full context

**New Files:**
- `pit/cli/commands/stash.py`
- `pit/core/stash.py`
- `tests/test_cli/test_stash.py`

---

## Phase 10: Subprompts (Dependencies)

**External prompt dependencies:**

**.pit.yaml additions:**
```yaml
dependencies:
  - source: github
    repo: anthropic/prompts
    path: citation-format
    version: v2.1
  - source: local
    path: ../shared/brand-voice
    version: main
  - source: url
    url: https://prompts.pit.dev/rag-v1.bundle
```

**Commands:**
- `pit deps install` - fetch all dependencies
- `pit deps update` - update to latest
- `pit deps list` - show tree
- `pit deps add <source> --as <name>`
- `pit deps remove <name>`

**Storage:**
- `.pit/deps/` - cached dependencies
- Lock file: `.pit/deps.lock`

**New Files:**
- `pit/cli/commands/deps.py`
- `pit/core/dependencies.py`
- `tests/test_cli/test_deps.py`

---

## Implementation Order

1. Phase 1: Bisect (core algorithm, sets pattern)
2. Phase 3: Worktrees (infrastructure for contexts)
3. Phase 9: Stash (quick win, builds on worktree concepts)
4. Phase 4: Patches (export/import infrastructure)
5. Phase 7: Bundles (packaging, uses patches)
6. Phase 6: Hooks (integration points)
7. Phase 2: Semantic Merge (complex logic)
8. Phase 8: Query Language (parser + SQL)
9. Phase 5: Replay (requires LLM integration)
10. Phase 10: Dependencies (most complex, uses bundles)

## Test Strategy

- Each phase: ~15-20 tests
- Total: 150+ new tests (280+ total)
- Integration tests for multi-phase features

## Dependencies to Add

None new for core features. Phase 5 (Replay) may need anthropic/openai if not already present.
