# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- LICENSE file (MIT) — README already referenced an MIT license and badge,
  but the actual file was missing from the repo until now
- Structured logging throughout the application
  - INFO level logs for config loading, saves, and deletes
  - ERROR level logs for InfluxDB and Signal K failures
  - DEBUG level logs for timezone resolution and query results
- Type hints for all functions and route handlers

### Changed
- Silent `except: pass` blocks now log actual errors for debugging
- Improved code documentation with enhanced docstrings

### Removed
- Unused imports (`Annotated`, `Form`, `Query`)

## [0.11.0] - 2026-11-15

### Changed
- **Storage moved from InfluxDB to QuestDB** (table `sail_config`, created on
  startup). Configure with `QUESTDB_URL` (default `http://localhost:9000`); the
  `INFLUX_*` settings and the `influxdb-client` dependency are gone.
- Deleting a log entry is now a soft delete (`deleted = true`), because QuestDB
  has no row `DELETE`. All reads filter deleted rows out.
- After a save or delete the app waits for QuestDB to apply the WAL write before
  re-reading, so the UI never shows a stale list.
- User text (the comment) enters SQL only as a quoted string literal; verified
  with quotes, backslashes, newlines and `; DROP TABLE` in a comment.
- Unchanged behaviour: "current config" looks back 30 days, history 7 days.

### Migration
- The 17 existing entries (2026-07-29 to 2026-09-28) were copied from the InfluxDB
  `signalk` bucket (1-year retention) into QuestDB on 2026-11-15, verified field by
  field. QuestDB keeps them indefinitely.

## [0.10.0] - 2025-01-21

### Added
- Daggerboard configuration tracking (central board and C-foil)
- C-foil rake angle control (only visible when C-foil deployed)
- Board state display in status summary and history

### Fixed
- InfluxDB timestamp collisions on backdated entries (random microseconds)
- Sail toggle logic and field merging issues
- None value handling in sail config display

## [0.9.0] - 2025-01-15

### Added
- Initial HTMX-based sail plan tracker
- Main sail state tracking (DOWN, 1ST REEF, 2ND REEF, FULL)
- Headsail selection (Jib, Genoa, Code 0)
- Downwind sail selection (Asymmetric Spinnaker, Reaching Spinnaker)
- Staysail mode toggle (Jib + Reaching Spinnaker combo)
- History panel with recent entries
- Backdate functionality for logging past configurations
- GPS-based timezone detection via Signal K
- InfluxDB storage backend
- Mobile-first responsive design
- Dark/light mode support

[Unreleased]: https://github.com/jrehm/sail-plan-htmx/compare/v0.10.0...HEAD
[0.10.0]: https://github.com/jrehm/sail-plan-htmx/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/jrehm/sail-plan-htmx/releases/tag/v0.9.0
