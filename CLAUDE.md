# Claude Code Context

Development context for AI-assisted coding on this project.

## Quick Reference

- **Stack**: FastAPI + HTMX + Jinja2 + InfluxDB
- **Port**: 8501
- **Config**: `boat_config.toml` (requires server restart on change)
- **Dev server**: `make run`

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
| `main.py` | FastAPI routes, InfluxDB queries, business logic |
| `templates/index.html` | Page layout, JavaScript handlers |
| `templates/partials/sail_selector.html` | Sail buttons, status banner (swapped by HTMX) |
| `templates/partials/history.html` | History entries list |
| `static/app.css` | Mobile-first styles, color-coded categories |
| `boat_config.toml` | Sail inventory (loaded at startup) |

### Data Flow

1. **Page load**: Fetch current config from InfluxDB, render full page
2. **Sail tap**: HTMX POST → server updates pending state → returns partial HTML
3. **Save**: Form POST → write to InfluxDB → return partial + trigger history refresh
4. **Delete**: DELETE request → remove from InfluxDB → trigger config refresh

## Common Tasks

### Add/modify sail options

Edit `boat_config.toml`, restart server. No code changes needed.

### Change button colors

Edit `static/app.css`, find `.sail-section--main`, `.sail-section--headsail`, `.sail-section--downwind`.

### Add new route

1. Add route function in `main.py`
2. Create partial template if returning HTML
3. Wire up with `hx-*` attributes

### Debug HTMX

Add to page: `<script>htmx.logAll();</script>`

## Code Conventions

- Routes return `TemplateResponse` for HTML, plain strings for simple content
- Use `HX-Trigger` response header for reliable cross-component updates
- Hidden inputs preserve state across HTMX swaps
- JavaScript only for things HTMX can't do (backdate toggle, haptic feedback)
- CSS uses custom properties (`--bg-primary`, etc.) with light/dark mode support

## Testing Checklist

1. Sail toggle: tap to select, tap again to deselect
2. Unsaved indicator: yellow banner + badge when changes pending
3. Notes field: typing enables UPDATE button
4. Save: toast appears, history refreshes, notes cleared
5. Delete: removes entry, status updates to reflect current config
6. Backdate: toggle shows fields, save uses custom timestamp
7. Responsive: slide-out history on mobile, inline on tablet+
