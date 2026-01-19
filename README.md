# Sail Plan Tracker

A mobile-first web app for logging sail configurations on a sailboat. Built with FastAPI and HTMX for a responsive, touch-optimized interface that works well with wet or gloved hands.

## Features

- **Touch-optimized UI** - Large buttons designed for use underway
- **Toggle selection** - Tap to select, tap again to deselect
- **Color-coded categories** - Red (main), blue (headsail), green (downwind)
- **Unsaved changes indicator** - Yellow banner shows pending changes
- **Notes field** - Log conditions or reasons for sail changes
- **Backdate entries** - Record past sail changes with custom timestamps
- **History panel** - View and delete recent entries
- **Dark/light mode** - Adapts to system preference
- **Offline-friendly** - Minimal dependencies, fast loading

## Requirements

- Python 3.11+
- InfluxDB 2.x (for data storage)
- Signal K (optional, for GPS-based timezone)

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/jrehm/sail-plan-htmx.git
   cd sail-plan-htmx
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Configure environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your InfluxDB credentials
   ```

4. Customize sail options for your boat:
   ```bash
   # Edit boat_config.toml with your sail inventory
   ```

## Configuration

### Environment Variables (.env)

```bash
INFLUX_URL=http://localhost:8086
INFLUX_TOKEN=your-token-here
INFLUX_ORG=your-org
INFLUX_BUCKET=your-bucket
SIGNALK_URL=http://localhost:3000  # Optional
```

### Boat Configuration (boat_config.toml)

```toml
[boat]
name = "Your Boat"

[sails.main]
options = ["FULL", "R1", "R2", "R3"]

[sails.headsail]
options = ["JIB", "GENOA", "STORM"]

[sails.downwind]
options = ["SPINNAKER", "GENNAKER"]

[display]
FULL = "Full"
R1 = "1st Reef"
# ... display names for UI
```

## Usage

### Development

```bash
make run          # Start dev server at localhost:8501
make run-network  # Start dev server accessible on LAN
```

### Production

```bash
make serve        # Start production server
```

Or with systemd (see deployment section below).

## Development

### Project Structure

```
sail-plan-htmx/
├── main.py                 # FastAPI application
├── templates/
│   ├── index.html          # Main page layout
│   └── partials/
│       ├── sail_selector.html  # Sail buttons (HTMX partial)
│       └── history.html        # History list (HTMX partial)
├── static/
│   └── app.css             # Mobile-first styles
├── boat_config.toml        # Sail inventory
└── requirements.txt
```

### Code Quality

```bash
make lint         # Run ruff linter
make format       # Run ruff formatter
```

## Deployment

### Raspberry Pi with OpenPlotter

1. Install as a systemd service:

   ```bash
   sudo cp sail-plan.service /etc/systemd/system/
   sudo systemctl enable sail-plan
   sudo systemctl start sail-plan
   ```

2. Example service file (`sail-plan.service`):

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

3. Access via local network at `http://raspberrypi.local:8501`

## InfluxDB Schema

Data is stored in the `sail_config` measurement:

| Field | Type | Description |
|-------|------|-------------|
| main | string | Mainsail state (FULL, R1, etc.) |
| headsail | string | Headsail selection |
| downwind | string | Downwind sail selection |
| staysail_mode | boolean | Jib used as staysail |
| comment | string | Optional note |

Tagged with `vessel` for multi-boat support.

## License

MIT License - See LICENSE file for details.

## Acknowledgments

Built with:
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [HTMX](https://htmx.org/) - HTML-driven interactivity
- [InfluxDB](https://www.influxdata.com/) - Time-series database
