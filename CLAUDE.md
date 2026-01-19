# Claude Code Context

Project context for AI-assisted development.

## Project Summary

**Sail Plan Tracker - HTMX Version** (v0.1.0) - FastAPI + HTMX app for logging sail configurations. Mobile-first, touch-optimized interface. Boat-specific settings configured via `boat_config.toml`. Designed to run on Raspberry Pi with OpenPlotter/Signal K/InfluxDB stack.

## Architecture

```
sail-plan-htmx/
├── main.py              # FastAPI app + routes (~350 lines)
├── templates/
│   ├── index.html       # Main page layout
│   └── partials/
│       ├── sail_selector.html   # HTMX-swappable sail controls
│       └── history.html         # History list
├── static/
│   └── app.css          # Mobile-first styles
├── boat_config.toml     # Sail inventory config
└── requirements.txt
```

### Key Patterns

- **HTMX partial updates**: Sail button clicks POST to `/sail/{category}/{value}`, return updated `sail_selector.html`
- **Hidden form state**: Pending selections tracked in hidden inputs, included with each HTMX request
- **Optimistic UX**: CSS `:active` gives immediate tap feedback before server responds
- **Toggle behavior**: Tapping selected sail deselects it (unlike Streamlit pills)

### Data Flow

1. Page loads → fetch committed state from InfluxDB → render full page
2. User taps sail → HTMX POST → server calculates new pending state → returns partial HTML
3. User taps UPDATE → form submits to `/save` → write to InfluxDB → return updated partial
4. History panel loads via `hx-get="/history"` on open

## Development Commands

```bash
make run          # Local dev server (localhost:8501)
make run-network  # Accessible on LAN (0.0.0.0:8501)
make serve        # Production mode
make lint         # Ruff linter
make format       # Ruff formatter
```

## Environment

- **Python**: 3.11+
- **Key deps**: fastapi, uvicorn, jinja2, influxdb-client, htmx (CDN)
- **Services**: InfluxDB (port 8086), Signal K (port 3000), App (port 8501)

## Testing Checklist

1. **Sail toggle**: Tap sail to select, tap again to deselect
2. **Pending state**: Yellow banner + "unsaved" badge when changes pending
3. **UPDATE button**: Disabled when no changes, green when active
4. **History panel**: Slide-out on mobile, inline on tablet/desktop
5. **Delete entry**: Trash icon → confirm → entry removed
6. **Backdate**: Options → check backdate → set date/time → UPDATE
7. **Touch targets**: Buttons large enough for wet/gloved hands

## Common Tasks

### Add New Sail Option

1. Edit `boat_config.toml`
2. Add to appropriate list under `[sails.main]`, `[sails.headsail]`, or `[sails.downwind]`
3. Add display name to `[display]` section

### Modify Styling

Edit `static/app.css`. Key sections:
- `.sail-btn` - Sail selection buttons
- `.state-banner` - Current config display
- `.history-panel` - Slide-out history
- Media queries at bottom for responsive behavior

### Add New Route

1. Add route function in `main.py`
2. If returning HTML partial, create template in `templates/partials/`
3. Use `hx-*` attributes in templates to wire up HTMX behavior
