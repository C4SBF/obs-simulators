# OBS Simulators

A collection of realistic simulators for building systems and industrial equipment, designed for testing the BACnet discovery and classification systems.

## Available Simulators

### 1. Building Simulator (`simulators/building`)
A BACnet simulator modeling a 3-floor office building with:
- **AHU-1**: Main air handling unit
- **Chiller-1**: Central cooling plant
- **VAVs**: 6 variable air volume terminal units (2 per floor)
- **Meter**: Main electrical meter

Features realistic physics, control loops, and equipment relationships.

## Quick Start (Make)

This repository includes a `Makefile` to simplify running simulations.

### Building Simulator

Start the full building simulation (9 BACnet devices):
```bash
# Start all building containers
make building

# Stop the simulation
make stop
```

### Custom Network
By default, devices run on the `bacnet_net` Docker network. You can override this:
```bash
NETWORK=my_custom_net make building
```

## Development

Each simulator is self-contained in `simulators/<name>`.

### Dependencies
- **Docker**: Required for running simulations
- **Python 3.12+**: For local development
- **uv**: Used for Python dependency management
- **pre-commit**: For ensuring code quality before committing

### Local Setup
```bash
# Install dependencies
uv sync

# Install pre-commit hooks
uv run pre-commit install
```

### Project Structure
```
.
├── simulators/
│   └── building/       # Building BACnet simulator
└── Makefile            # Main project Makefile
```
