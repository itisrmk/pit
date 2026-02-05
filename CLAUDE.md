# CLAUDE.md - PIT (Prompt Information Tracker)

## Project Context

**Project:** PIT (Prompt Information Tracker) - formerly PIT (Prompt Information Tracker)  
**Tech Stack:** Python 3.11+, Typer, SQLAlchemy, Pydantic, Rich  
**Package Name:** `pit` (was `pit`)  
**CLI Command:** `pit` (was `pit`)

## Rules

### Code Quality
- Always run tests before committing changes
- Use type hints consistently
- Follow PEP 8 with ruff linting (line-length: 100)
- Import order: stdlib, third-party, local

### Testing
- Use pytest for all tests
- Run `pytest` to verify all tests pass
- Maintain test coverage

### CLI Design
- Use Typer for CLI commands
- Rich for formatted output
- Keep commands intuitive and well-documented

### Database
- SQLAlchemy 2.0+ for ORM
- Alembic for migrations (future)
- SQLite default, but support PostgreSQL

## Common Mistakes to Avoid

- Don't hardcode package names in strings - use constants
- Don't forget to update both directory names AND import paths
- Always test the CLI entry point after renaming
- Update config directories (was `.pit/`, now `.pit/`)

## Lessons Learned

### Rename Project Workflow
1. Create new package directory structure first
2. Copy files with content replacement using sed/grep
3. Update pyproject.toml (name, scripts, packages)
4. Run tests to verify imports work
5. Remove old directory only after tests pass
6. Verify no old references remain with `grep -r "oldname"`

### Fun CLI Elements
- ASCII banners add personality
- Interactive menus when no args provided
- Random fun messages enhance user experience
- Use Rich panels and styling for visual appeal
