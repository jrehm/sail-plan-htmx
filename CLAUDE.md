# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Reference

- **Stack**: FastAPI + HTMX + Jinja2 + QuestDB (HTTP `/exec`, via `requests`)
- **Python**: 3.11+
- **Port**: 8501
- **Config**: `boat_config.toml` (requires server restart on change)

## Commands

```bash
make run          # Dev server at localhost:8501 (with hot reload)
make run-network  # Dev server accessible on LAN
make serve        # Production server
make lint         # Run ruff linter
make format       # Run ruff formatter
```

## Architecture

### HTMX Patterns

**Partial updates**: Sail buttons POST to server, receive HTML partial in response:
```html
<button
    hx-post="/sail/main/FULL"
    hx-target="#sail-selector"
    hx-swap="innerHTML"
    hx-include="#sail-form"
>
```

**State tracking**: Hidden form inputs track pending (unsaved) selections. Each HTMX request includes these values via `hx-include`.

**Event-driven refresh**: Server sends `HX-Trigger: historyUpdate` header to trigger history panel reload after save.

**Trigger on events**: Elements can listen for custom events:
```html
<div hx-get="/config" hx-trigger="configUpdate from:body">
```

### Key Files

| File | Purpose |
|------|---------|
| `main.py` | FastAPI routes, QuestDB queries, business logic |
| `templates/index.html` | Page layout, JavaScript handlers |
| `templates/partials/sail_selector.html` | Sail buttons, status banner (swapped by HTMX) |
| `templates/partials/history.html` | History entries list |
| `static/app.css` | Mobile-first styles, color-coded categories |
| `boat_config.toml` | Sail inventory (loaded at startup) |

### Data Flow

1. **Page load**: Fetch current config from QuestDB, render full page
2. **Sail tap**: HTMX POST → server updates pending state → returns partial HTML
3. **Save**: Form POST → write to QuestDB → return partial + trigger history refresh
4. **Delete**: DELETE request → soft-delete in QuestDB → trigger config refresh

### Logging

The application uses Python's `logging` module configured at INFO level. Key log points:
- Config loading (INFO)
- QuestDB operations: saves, deletes, errors (INFO/ERROR)
- Signal K and timezone resolution (DEBUG)

## Common Tasks

### Add/modify sail options

Edit `boat_config.toml`, restart server. No code changes needed.

### Change button colors

Edit `static/app.css`, find `.sail-section--main`, `.sail-section--headsail`, `.sail-section--downwind`, `.sail-section--boards`, `.sail-section--rake`.

### Add new route

1. Add route function in `main.py`
2. Create partial template if returning HTML
3. Wire up with `hx-*` attributes

### Debug HTMX

Add to page: `<script>htmx.logAll();</script>`

## Code Conventions

- Routes return `TemplateResponse` for HTML, plain strings for simple content
- Use `HX-Trigger` response header for cross-component updates
- Hidden inputs preserve state across HTMX swaps
- JavaScript only for things HTMX can't do (backdate toggle, haptic feedback)
- CSS uses custom properties (`--bg-primary`, etc.) with light/dark mode support
- Type hints on all functions
- Vessel name "morticia" is hardcoded (`VESSEL`) in the QuestDB queries
- QuestDB has no row DELETE: entries are soft-deleted (`deleted = true`); every read must keep the `coalesce(deleted, false) = false` filter
- WAL writes are visible to SELECT only after apply: keep `_wait_applied()` after any write/update before re-reading
- Never build SQL by string-formatting user input; use `_sql_str()` (quote doubling) like the existing queries
- Set `SAIL_TABLE=<scratch>` to test against a throwaway table instead of the real log

## Testing Checklist

1. Sail toggle: tap to select, tap again to deselect
2. Unsaved indicator: yellow banner + badge when changes pending
3. Notes field: typing enables UPDATE button
4. Save: toast appears, history refreshes, notes cleared
5. Delete: removes entry, status updates to reflect current config
6. Backdate: toggle shows fields, save uses custom timestamp
7. Responsive: slide-out history on mobile, inline on tablet+
8. Central board: UP/HALF/FULL toggles correctly
9. C-foil board: UP/HALF/FULL toggles, rake section appears/hides
10. C-foil rake: only visible when C-foil is HALF or FULL, resets on UP
