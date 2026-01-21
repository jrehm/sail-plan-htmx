# Sail Plan Tracker

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.10.0-orange.svg)](https://github.com/jrehm/sail-plan-htmx/releases)

A mobile-first web app for logging sail configurations and daggerboard positions on a sailboat. Built with FastAPI and HTMX for a responsive, touch-optimized interface that works well with wet or gloved hands.

## Features

### Sail Management
- **Touch-optimized UI** - Large buttons designed for use underway
- **Toggle selection** - Tap to select, tap again to deselect
- **Color-coded categories** - Red (main), blue (headsail), green (downwind), purple (boards)
- **Mutual exclusivity rules** - Automatic sail conflict resolution (except Jib + Reaching Spinnaker)
- **Staysail mode** - Track when jib is used as staysail with spinnaker

### Daggerboard Tracking
- **Central board** - Track UP/HALF/FULL positions
- **C-foil boards** - Track deployment with rake angle (-1° to 4°)
- **Conditional rake display** - Rake options only shown when C-foil is deployed

### General
- **Unsaved changes indicator** - Yellow banner shows pending changes
- **Notes field** - Log conditions or reasons for changes
- **Backdate entries** - Record past changes with custom timestamps
- **History panel** - View and delete recent entries
- **Dark/light mode** - Adapts to system preference
- **GPS timezone** - Automatic timezone from Signal K position data

## Requirements

- Python 3.11+
- InfluxDB 2.x
- Signal K (optional, for GPS-based timezone)

## Quick Start

```bash
# Clone and setup
git clone https://github.com/jrehm/sail-plan-htmx.git
cd sail-plan-htmx
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your InfluxDB credentials

# Run
make run
```

Access at `http://localhost:8501`

## Configuration

### Environment Variables

Create a `.env` file:

```bash
INFLUX_URL=http://localhost:8086
INFLUX_TOKEN=your-token-here
INFLUX_ORG=your-org
INFLUX_BUCKET=your-bucket
SIGNALK_URL=http://localhost:3000  # Optional
```

### Boat Configuration

Edit `boat_config.toml` to match your boat's sail inventory:

```toml
[boat]
name = "Your Boat"

[sails.main]
options = ["FULL", "R1", "R2", "R3", "R4"]

[sails.headsail]
options = ["JIB", "GENOA", "STORM"]

[sails.downwind]
options = ["SPINNAKER", "GENNAKER"]

[boards.central]
options = ["UP", "HALF", "FULL"]

[boards.cfoil]
options = ["UP", "HALF", "FULL"]

[boards.cfoil_rake]
options = ["-1", "0", "1", "2", "3", "4"]

[display]
FULL = "Full"
R1 = "1st Reef"
UP = "Up"
HALF = "Half"
# ... display names for UI buttons
```

## Usage

### Development

```bash
make run          # Start dev server at localhost:8501
make run-network  # Start dev server accessible on LAN
make lint         # Run ruff linter
make format       # Run ruff formatter
```

### Production

```bash
make serve        # Start production server
```

## Deployment

### Raspberry Pi / OpenPlotter

1. Create systemd service file `/etc/systemd/system/sail-plan.service`:

```ini
[Unit]
Description=Sail Plan Tracker
After=network.target influxdb.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/sail-plan-htmx
Environment=PATH=/home/pi/sail-plan-htmx/venv/bin
ExecStart=/home/pi/sail-plan-htmx/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8501
Restart=always

[Install]
WantedBy=multi-user.target
```

2. Enable and start:

```bash
sudo systemctl enable sail-plan
sudo systemctl start sail-plan
```

3. Access via `http://raspberrypi.local:8501`

## Project Structure

```
sail-plan-htmx/
├── main.py                     # FastAPI application
├── boat_config.toml            # Sail/board inventory
├── templates/
│   ├── index.html              # Main page layout
│   └── partials/
│       ├── sail_selector.html  # Sail/board buttons (HTMX partial)
│       └── history.html        # History list (HTMX partial)
├── static/
│   └── app.css                 # Mobile-first styles
├── requirements.txt
├── Makefile
└── CLAUDE.md                   # AI development context
```

## Data Schema

Data is stored in InfluxDB `sail_config` measurement:

| Field | Type | Description |
|-------|------|-------------|
| `main` | string | Mainsail state (FULL, R1, R2, etc.) |
| `headsail` | string | Headsail selection |
| `downwind` | string | Downwind sail selection |
| `staysail_mode` | boolean | Jib used as staysail |
| `central_board` | string | Central daggerboard position (UP, HALF, FULL) |
| `cfoil_board` | string | C-foil position (UP, HALF, FULL) |
| `cfoil_rake` | string | C-foil rake angle (-1 to 4) |
| `comment` | string | Optional note |

Tagged with `vessel` for multi-boat support.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run linting (`make lint`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## License

MIT License - See [LICENSE](LICENSE) file for details.

## Acknowledgments

Built with:
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [HTMX](https://htmx.org/) - HTML-driven interactivity
- [Jinja2](https://jinja.palletsprojects.com/) - Template engine
- [InfluxDB](https://www.influxdata.com/) - Time-series database
