# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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
