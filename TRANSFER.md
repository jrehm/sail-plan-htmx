# Sail Plan HTMX - Transfer Document

## Context

This is a migration of the Streamlit-based sail plan tracker to FastAPI + HTMX for better mobile UX. The original Streamlit version is at `~/Documents/GitHub/sail-plan/`. This HTMX version is a working sketch that needs to be fleshed out into a functioning prototype.

## Current State

**Working:**
- FastAPI app structure with all routes defined
- InfluxDB integration code ported from Streamlit version
- Signal K timezone detection ported
- Templates created with HTMX wiring
- CSS with mobile-first dark theme
- boat_config.toml loading

**Not yet tested/verified:**
- Full round-trip sail selection → InfluxDB write → history update
- Backdate functionality (HTML exists but JS incomplete)
- Delete entry flow
- Mobile touch behavior in actual browser

## Environment

The `.env` file has been created with remote InfluxDB credentials. The app should connect to the boat's InfluxDB via Tailscale.

## Files to Review

```
sail-plan-htmx/
├── main.py                    # FastAPI routes + InfluxDB logic
├── templates/
│   ├── index.html             # Main page
│   └── partials/
│       ├── sail_selector.html # Sail buttons (HTMX target)
│       └── history.html       # History list
├── static/app.css             # Styles
├── boat_config.toml           # Sail inventory
└── requirements.txt           # Dependencies
```

## Tasks to Complete

### Priority 1: Get Basic Flow Working
1. Install deps and start server: `pip install -r requirements.txt && make run`
2. Test page load - verify it fetches current config from InfluxDB
3. Test sail button taps - verify HTMX partial updates work
4. Test UPDATE button - verify writes to InfluxDB
5. Test history panel - verify it loads and displays entries

### Priority 2: Fix Known Issues
1. **Backdate toggle JS**: The hidden input `backdate-enabled` needs to be created in the HTML (currently referenced but not defined)
2. **Form comment field**: Verify the comment textarea value is included in the save POST
3. **Error handling**: Add user-visible error states when InfluxDB calls fail

### Priority 3: Polish
1. Add loading states during HTMX requests (hx-indicator)
2. Better delete confirmation (modal instead of browser confirm)
3. Toast for save failures, not just success
4. Pull-to-refresh for history (nice to have)

## Key HTMX Patterns Used

**Sail button click:**
```html
<button 
    hx-post="/sail/main/FULL"      <!-- POST to toggle endpoint -->
    hx-target="#sail-selector"      <!-- Replace this region -->
    hx-swap="innerHTML"             <!-- Swap method -->
    hx-include="#sail-form"         <!-- Include hidden form values -->
>
```

**Pending state tracking:**
Hidden inputs in `#sail-form` track the pending (uncommitted) selections. Each HTMX request includes these values, and the server returns updated HTML with new hidden input values.

**History refresh after save:**
```javascript
htmx.trigger(document.body, 'historyUpdate');
```
The history panel has `hx-trigger="load, historyUpdate from:body"` so it reloads when this event fires.

## Testing Checklist

- [ ] Page loads and shows current sail config from DB
- [ ] Tapping unselected sail selects it (button highlights)
- [ ] Tapping selected sail deselects it (button unhighlights)
- [ ] Pending changes show yellow banner + "unsaved" badge
- [ ] UPDATE button enables when changes pending
- [ ] UPDATE writes to InfluxDB and shows toast
- [ ] History panel opens and shows recent entries
- [ ] History refreshes after save
- [ ] Delete entry works with confirmation
- [ ] Backdate toggle shows date/time fields
- [ ] Backdated save uses correct timestamp
- [ ] Works on mobile Safari and Chrome

## Reference: Original Streamlit App

If you need to check behavior or copy logic, the original is at:
- `~/Documents/GitHub/sail-plan/sail_plan_app.py`
- `~/Documents/GitHub/sail-plan/CLAUDE.md`

The InfluxDB schema and queries are identical between versions.
