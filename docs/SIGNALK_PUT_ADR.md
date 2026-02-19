# ADR: Signal K PUT Integration
## sail-plan-htmx — Architectural Decision Record

**Status:** Rejected — not worth the complexity
**Date:** 2026-02
**Supersedes:** SIGNALK_INTEGRATION_PLANNING.md

---

## Context

The current InfluxDB schema stores sail configuration as state-change events, not a
continuous time series. To determine what sail configuration was active at an arbitrary
timestamp T, a query must look backwards for the most recent `sail_config` record with
timestamp ≤ T.

The question was whether to add a Signal K PUT on save to create a continuous sail-state
series in InfluxDB via the existing `signalk-influxdb` plugin — simplifying future polar
generation queries.

---

## Proposed Approach (evaluated and rejected)

On save, the app would PUT sail state to Signal K REST API in addition to the existing
InfluxDB write. The `signalk-influxdb` plugin would then subscribe to those paths and
write a continuous series to InfluxDB.

---

## Research Findings

### Signal K PUT authentication

- Security is enabled on OpenPlotter by default once an admin account is created
- Unauthenticated GET requests work (allow-readonly mode) — this is how the existing
  timezone lookup works
- PUT requests require a valid token
- Best option for a local service: pre-generate a long-lived token on the machine:
  ```bash
  signalk-generate-token -u admin -e 1y -s ~/.signalk/security.json
  ```
- **Header format gotcha:** must use `Authorization: JWT <token>` — not `Bearer`.
  The spec says Bearer but the server implementation requires JWT. Known discrepancy.

### PUT handler requirement — the architectural blocker

A Signal K REST PUT to a path returns **405 Method Not Allowed** unless a plugin has
registered a PUT handler for that specific path. This is by design — Signal K PUT is
intended for actuators (e.g. "turn on anchor light"), not data ingestion.

Custom paths like `vessels/self/sails/main` have no registered handler. The
`sailsconfiguration` plugin has handlers but enforces the standard Signal K sails
inventory schema, which does not accommodate Morticia's C-foil boards and rake angles.

The workaround is WebSocket delta messages, which bypass the PUT handler requirement
and can write to any path. This would require adding the `websockets` library and
async handling to the app.

### The core problem is already solved

`pandas.merge_asof()` handles "last known value before T" joins in one line:

```python
merged = pd.merge_asof(
    performance_df.sort_values("time"),   # BSP, TWS, TWA, heel
    sail_config_df.sort_values("time"),   # sail event log
    on="time",
    direction="backward"
)
```

The event log is already the right structure for Python-based polar analysis. A
continuous series in InfluxDB only simplifies queries in Flux/Grafana workflows —
which are not part of the planned analysis path.

---

## Decision

**Rejected.** The proposed Signal K integration adds meaningful complexity (WebSocket
library, auth token management, async fire-and-forget, two InfluxDB series to maintain,
known divergence on backdated/deleted entries) to solve a problem that `pandas.merge_asof()`
already handles cleanly with the existing data.

The current event log architecture is sufficient for the intended polar analysis use case.

---

## Alternatives Considered

**Direct periodic InfluxDB write (app-side heartbeat):** The app could write a `sail_state`
record on a schedule (e.g. every 5 minutes) to create a continuous series without Signal K
involvement. Rejected for the same reason — `merge_asof()` makes this unnecessary.

**sailsconfiguration plugin REST API:** Has registered PUT handlers but enforces standard
Signal K sails schema. Morticia's boards and rake angles don't map to the standard schema,
leaving the same custom path problem for a significant portion of the state.

---

## Known Limitations of Current Architecture

These are accepted, not action items:

- Polar analysis requires a backward join ("last known value before T") rather than a
  simple time-range filter. `pandas.merge_asof()` handles this.
- Backdated saves write an event record with a past timestamp. Any analysis code must
  account for the possibility that events are not strictly append-ordered in wall-clock time.
- Deleted entries are removed from InfluxDB entirely, which may create apparent
  configuration gaps in analysis. In practice the dataset is large enough that brief
  gaps are negligible for polar purposes.
