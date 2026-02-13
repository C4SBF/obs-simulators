# Realistic Building BACnet Simulator

A comprehensive BACnet simulator that models a complete 3-floor office building with proper HVAC physics, control loops, and equipment relationships.

## Overview

This simulator creates 9 interconnected BACnet devices representing a realistic commercial building HVAC system. Unlike simple random simulators, this implements actual building physics and control strategies used in real Building Management Systems (BMS).

## Equipment (9 Devices)

### 1. AHU-1 (Air Handling Unit) - Device ID: 400001
Main HVAC system serving all floors with **9 BACnet points**:
- Supply Air Temperature (°F)
- Return Air Temperature (°F)
- Mixed Air Temperature (°F)
- Supply Air Flow (CFM)
- Supply Air Temperature Setpoint (°F) - *commandable*
- Fan Speed Command (%) - *commandable*
- Cooling Valve Position (%)
- Fan Status
- Enable/Disable - *commandable*

### 2. VAVs (Variable Air Volume Boxes) - Device IDs: 400010-400015
6 zone controllers (2 per floor) with **6 points each**:
- **Floor 1**: North (400010), South (400011)
- **Floor 2**: North (400012), South (400013)
- **Floor 3**: North (400014), South (400015)

Each VAV has:
- Zone Temperature (°F)
- Zone Temperature Setpoint (°F) - *commandable*
- Damper Position (%)
- Airflow (CFM)
- Reheat Valve (%)
- Occupancy Sensor

### 3. Chiller-1 - Device ID: 400020
Central cooling plant with **4 points**:
- Chilled Water Supply Temperature (°F)
- Chilled Water Return Temperature (°F)
- Running Status
- Enable/Disable - *commandable*

### 4. Main Meter - Device ID: 400030
Building electrical monitoring with **3 points**:
- Total Power Demand (kW)
- Total Energy Consumption (kWh)
- Voltage (V)

**Total: 9 devices, ~50 BACnet points**

## Realistic Physics & Control

### Temperature Control
- **AHU Supply Air**: PI controller maintains 55°F setpoint
- **VAV Zones**: Independent PI controllers for each zone (default 72°F)
- **Cooling Valve**: Modulates 0-100% based on supply air temperature error
- **Reheat Valves**: Activate when zones drop below setpoint

### Airflow Dynamics
- **AHU Fan Speed**: 75% during occupied hours, 40% unoccupied
- **VAV Dampers**: Modulate 20-100% based on zone temperature error
- **Airflow**: Calculated from damper position (max 3000 CFM per VAV)
- **Supply Air Flow**: Total AHU flow based on fan speed

### Building Physics
- **Zone Heat Gain**: Varies by occupancy and location
- **Perimeter Zones** (North): Higher solar gain
- **Interior Zones** (South): Lower heat gain
- **Cooling Effect**: Heat transfer from supply air to zones
- **Return Air**: Average of all zone temperatures

### Schedules & Occupancy
- **Business Hours**: 8 AM - 6 PM, Monday-Friday
- **Occupancy**: 95% probability during business hours, 5% after hours
- **Equipment Response**: Fan speeds and loads adjust based on occupancy

### Environmental Conditions
- **Outdoor Temperature**: Daily sinusoidal cycle (75°F ± 15°F)
- **Cooler at Night**: Minimum around 6 AM
- **Warmer Midday**: Maximum around 6 PM
- **Random Variation**: ±2°F noise

### Power Consumption
- **AHU Fan**: Cubic relationship to speed (realistic fan laws)
- **Chiller**: Proportional to cooling load (max 80 kW)
- **Reheat**: Sum of all VAV reheat valves
- **Lighting & Plugs**: 50 kW occupied, 10 kW unoccupied
- **Energy**: Integrated power consumption over time


## Usage

### Start Building Simulation

Using Docker:
```bash
# Build the image
docker build -t simulator-building .

# Run equipment (must be on the same network)
docker network create bacnet_net

docker run -d --network bacnet_net simulator-building --equipment ahu
docker run -d --network bacnet_net simulator-building --equipment vav0
# ... add other equipment as needed
```

Using uv (Local):
```bash
# Install dependencies and sync
uv sync

# Run specific equipment
uv run building-simulator --equipment ahu
uv run building-simulator --equipment vav0
uv run building-simulator --equipment chiller
```

## Point Naming Conventions

Follows realistic BMS patterns:
- `{Equipment}-{Instance}-{Point-Description}`

Examples:
- `AHU-1-Supply-Air-Temp`
- `Floor2-North-Zone-Temp`
- `Floor2-North-Zone-Temp-SP`
- `Chiller-1-CHW-Supply-Temp`
- `Main-Meter-Total-Power`

## Technical Details

### Update Interval
- 5 seconds between physics updates
- All equipment shares a common `BuildingState` object
- Physics calculated first, then BACnet objects updated

### Container Names
- Pattern: `simulator-building-{equipment}`
- Examples:
  - `simulator-building-ahu`
  - `simulator-building-vav0` (Floor 1 North)
  - `simulator-building-vav1` (Floor 1 South)
  - `simulator-building-chiller`
  - `simulator-building-meter`

### Docker Network
- All devices must be on the same network to support BACnet/IP broadcast discovery

## Benefits for Testing

1. **Classification Testing**: Realistic point names for ontology matching
2. **Equipment Grouping**: Related points can be grouped into equipment
3. **Relationship Discovery**: Infer AHU→VAV relationships from data
4. **Control Sequence Testing**: Realistic control loops for analytics
5. **Load Testing**: 50+ points with dynamic values
6. **Reproducibility**: Deterministic physics with controlled randomness

## Implementation

- **Language**: Python 3.13
- **BACnet Library**: bacpypes3
- **Protocol**: BACnet/IP (UDP port 47808)
- **Container**: Docker with automatic restart
- **State Management**: Shared BuildingState class
- **Control**: PI controllers for temperature regulation
