"""Realistic Building BACnet Simulator using BACpypes3.

Simulates a complete 3-floor office building with:
- 1 AHU (Air Handling Unit) serving all floors
- 6 VAVs (Variable Air Volume boxes) - 2 per floor
- 1 Chiller
- 1 Boiler
- 1 Main Electrical Meter
- Realistic control loops and physics
"""

import asyncio
import logging
import math
import random
import sys
from datetime import datetime
from typing import Any

from bacpypes3.app import Application
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.basetypes import EngineeringUnits
from bacpypes3.debugging import ModuleLogger, bacpypes_debugging
from bacpypes3.local.analog import (
    AnalogInputObject,
    AnalogValueObject,
    AnalogOutputObject,
)
from bacpypes3.local.binary import BinaryInputObject, BinaryOutputObject
from bacpypes3.local.cmd import Commandable

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

_debug = 0
_log = ModuleLogger(globals())

INTERVAL = 5.0  # Update interval in seconds

# --- Custom Object Classes ---


@bacpypes_debugging
class CommandableAnalogValueObject(Commandable, AnalogValueObject):
    """Commandable Analog Value Object."""


# --- Building Physics Simulation ---


class BuildingState:
    """Shared state for the entire building simulation."""

    def __init__(self):
        """Initialize building state with default values."""
        # Time and occupancy
        self.outdoor_temp = 85.0  # °F
        self.is_occupied = True

        # Central plant
        self.chilled_water_supply_temp = 44.0  # °F
        self.chilled_water_return_temp = 54.0  # °F
        self.hot_water_supply_temp = 180.0  # °F
        self.hot_water_return_temp = 160.0  # °F

        # AHU state
        self.ahu_supply_air_temp = 55.0  # °F
        self.ahu_return_air_temp = 72.0  # °F
        self.ahu_mixed_air_temp = 65.0  # °F
        self.ahu_supply_air_flow = 12000.0  # CFM
        self.ahu_fan_speed = 75.0  # %
        self.ahu_cooling_valve = 50.0  # %
        self.ahu_heating_valve = 0.0  # %
        self.ahu_supply_air_setpoint = 55.0  # °F

        # VAV states (6 zones)
        self.vav_zone_temps = [72.0] * 6
        self.vav_zone_setpoints = [72.0] * 6
        self.vav_damper_positions = [50.0] * 6
        self.vav_airflows = [2000.0] * 6
        self.vav_reheat_valves = [0.0] * 6

        # Power consumption
        self.total_power = 0.0
        self.total_energy = 0.0

    def is_business_hours(self) -> bool:
        """Check if current time is business hours (8 AM - 6 PM weekdays)."""
        now = datetime.now()
        if now.weekday() >= 5:  # Weekend
            return False
        return 8 <= now.hour < 18

    def update_occupancy(self):
        """Update occupancy based on time of day."""
        if self.is_business_hours():
            # Occupied with some randomness
            self.is_occupied = random.random() < 0.95
        else:
            # Mostly unoccupied after hours
            self.is_occupied = random.random() < 0.05

    def update_outdoor_temp(self):
        """Simulate outdoor temperature with daily cycle."""
        hour = datetime.now().hour
        # Simple sinusoidal pattern: cooler at night, warmer during day
        base_temp = 75.0
        daily_swing = 15.0
        self.outdoor_temp = base_temp + daily_swing * math.sin(
            (hour - 6) * math.pi / 12
        )
        # Add some randomness
        self.outdoor_temp += random.uniform(-2, 2)

    def update_ahu(self):
        """Update AHU state with realistic control logic."""
        # Mixed air temperature (blend of return and outdoor)
        outdoor_damper = 20.0 if self.is_occupied else 10.0  # % outdoor air
        self.ahu_mixed_air_temp = (
            self.ahu_return_air_temp * (100 - outdoor_damper) / 100
            + self.outdoor_temp * outdoor_damper / 100
        )

        # Cooling valve control (PI controller)
        temp_error = self.ahu_supply_air_temp - self.ahu_supply_air_setpoint
        self.ahu_cooling_valve = max(
            0, min(100, self.ahu_cooling_valve + temp_error * 2)
        )

        # Supply air temperature (affected by cooling valve)
        cooling_effect = self.ahu_cooling_valve * 0.3  # Max 30°F cooling
        self.ahu_supply_air_temp = self.ahu_mixed_air_temp - cooling_effect

        # Return air is average of all zone temps
        self.ahu_return_air_temp = sum(self.vav_zone_temps) / len(self.vav_zone_temps)

        # Fan speed based on demand
        if self.is_occupied:
            self.ahu_fan_speed = 75.0 + random.uniform(-5, 5)
        else:
            self.ahu_fan_speed = 40.0 + random.uniform(-5, 5)

        self.ahu_supply_air_flow = self.ahu_fan_speed * 160  # CFM

    def update_vavs(self):
        """Update all VAV zones with realistic control."""
        for i in range(6):
            # Zone load varies by occupancy
            base_load = 0.5 if self.is_occupied else 0.1
            zone_load = base_load + random.uniform(-0.2, 0.2)

            # Perimeter zones (even indices) have more solar gain
            if i % 2 == 0:
                zone_load += 0.3

            # Temperature control (PI controller)
            temp_error = self.vav_zone_temps[i] - self.vav_zone_setpoints[i]

            # Damper position control
            self.vav_damper_positions[i] = max(
                20, min(100, self.vav_damper_positions[i] + temp_error * 3)
            )

            # Airflow based on damper position
            self.vav_airflows[i] = self.vav_damper_positions[i] * 30  # Max 3000 CFM

            # Zone temperature physics
            # Cooling from supply air
            cooling_effect = (
                (self.vav_airflows[i] / 2000.0)
                * (self.vav_zone_temps[i] - self.ahu_supply_air_temp)
                * 0.1
            )
            # Heat gain from zone load
            heat_gain = zone_load * 2

            self.vav_zone_temps[i] += (heat_gain - cooling_effect) * (INTERVAL / 60.0)

            # Reheat valve (only if zone is too cold)
            if self.vav_zone_temps[i] < self.vav_zone_setpoints[i] - 1:
                self.vav_reheat_valves[i] = min(100, self.vav_reheat_valves[i] + 5)
            else:
                self.vav_reheat_valves[i] = max(0, self.vav_reheat_valves[i] - 5)

    def update_chiller(self):
        """Update chiller state based on cooling load."""
        # Cooling load from AHU
        cooling_load = self.ahu_cooling_valve * 100  # kW (simplified)

        # Chilled water temps respond to load
        if cooling_load > 50:
            self.chilled_water_supply_temp = 42.0 + random.uniform(-1, 1)
            self.chilled_water_return_temp = 52.0 + random.uniform(-1, 1)
        else:
            self.chilled_water_supply_temp = 44.0 + random.uniform(-1, 1)
            self.chilled_water_return_temp = 54.0 + random.uniform(-1, 1)

    def update_power(self):
        """Calculate total building power consumption."""
        # AHU fan power
        ahu_power = (self.ahu_fan_speed / 100) ** 3 * 15  # kW

        # Chiller power (based on cooling valve position)
        chiller_power = (self.ahu_cooling_valve / 100) * 80  # kW

        # VAV reheat power
        reheat_power = sum(self.vav_reheat_valves) / 100 * 2  # kW

        # Lighting and plug loads
        if self.is_occupied:
            misc_power = 50 + random.uniform(-5, 5)
        else:
            misc_power = 10 + random.uniform(-2, 2)

        self.total_power = ahu_power + chiller_power + reheat_power + misc_power
        self.total_energy += self.total_power * (INTERVAL / 3600.0)  # kWh

    def update(self):
        """Update entire building simulation."""
        self.update_occupancy()
        self.update_outdoor_temp()
        self.update_ahu()
        self.update_vavs()
        self.update_chiller()
        self.update_power()


# --- Equipment Profiles ---


class AHUProfile:
    """Air Handling Unit - Main HVAC equipment."""

    def __init__(self, building_state: BuildingState):
        """Initialize AHU profile."""
        self.state = building_state

    def create_objects(self) -> list[Any]:
        """Create BACnet objects for the AHU."""
        return [
            # Supply Air Temperature
            AnalogInputObject(
                objectIdentifier=("analogInput", 1),
                objectName="AHU-1-Supply-Air-Temp",
                presentValue=self.state.ahu_supply_air_temp,
                units=EngineeringUnits.degreesFahrenheit,
                description="AHU Supply Air Temperature",
            ),
            # Return Air Temperature
            AnalogInputObject(
                objectIdentifier=("analogInput", 2),
                objectName="AHU-1-Return-Air-Temp",
                presentValue=self.state.ahu_return_air_temp,
                units=EngineeringUnits.degreesFahrenheit,
                description="AHU Return Air Temperature",
            ),
            # Mixed Air Temperature
            AnalogInputObject(
                objectIdentifier=("analogInput", 3),
                objectName="AHU-1-Mixed-Air-Temp",
                presentValue=self.state.ahu_mixed_air_temp,
                units=EngineeringUnits.degreesFahrenheit,
                description="AHU Mixed Air Temperature",
            ),
            # Supply Air Flow
            AnalogInputObject(
                objectIdentifier=("analogInput", 4),
                objectName="AHU-1-Supply-Air-Flow",
                presentValue=self.state.ahu_supply_air_flow,
                units=EngineeringUnits.cubicFeetPerMinute,
                description="AHU Supply Air Flow",
            ),
            # Supply Air Setpoint
            CommandableAnalogValueObject(
                objectIdentifier=("analogValue", 1),
                objectName="AHU-1-Supply-Air-Temp-SP",
                presentValue=self.state.ahu_supply_air_setpoint,
                units=EngineeringUnits.degreesFahrenheit,
                description="AHU Supply Air Temperature Setpoint",
            ),
            # Fan Speed
            AnalogOutputObject(
                objectIdentifier=("analogOutput", 1),
                objectName="AHU-1-Fan-Speed-Cmd",
                presentValue=self.state.ahu_fan_speed,
                units=EngineeringUnits.percent,
                description="AHU Fan Speed Command",
            ),
            # Cooling Valve
            AnalogOutputObject(
                objectIdentifier=("analogOutput", 2),
                objectName="AHU-1-Cooling-Valve",
                presentValue=self.state.ahu_cooling_valve,
                units=EngineeringUnits.percent,
                description="AHU Cooling Valve Position",
            ),
            # Fan Status
            BinaryInputObject(
                objectIdentifier=("binaryInput", 1),
                objectName="AHU-1-Fan-Status",
                presentValue="active",
                description="AHU Fan Running Status",
            ),
            # Enable/Disable
            BinaryOutputObject(
                objectIdentifier=("binaryOutput", 1),
                objectName="AHU-1-Enable",
                presentValue="active",
                description="AHU Enable Command",
            ),
        ]

    def update_objects(self, objects: list[Any]):
        """Update object values from building state."""
        objects[0].presentValue = self.state.ahu_supply_air_temp
        objects[1].presentValue = self.state.ahu_return_air_temp
        objects[2].presentValue = self.state.ahu_mixed_air_temp
        objects[3].presentValue = self.state.ahu_supply_air_flow
        # Setpoint is commandable, read from object
        self.state.ahu_supply_air_setpoint = objects[4].presentValue
        objects[5].presentValue = self.state.ahu_fan_speed
        objects[6].presentValue = self.state.ahu_cooling_valve


class VAVProfile:
    """Variable Air Volume Box."""

    def __init__(
        self, building_state: BuildingState, zone_index: int, floor: int, zone_name: str
    ):
        """Initialize VAV profile."""
        self.state = building_state
        self.zone_index = zone_index
        self.floor = floor
        self.zone_name = zone_name

    def create_objects(self) -> list[Any]:
        """Create BACnet objects for the VAV."""
        base_id = self.zone_index * 10
        return [
            # Zone Temperature
            AnalogInputObject(
                objectIdentifier=("analogInput", base_id + 1),
                objectName=f"Floor{self.floor}-{self.zone_name}-Zone-Temp",
                presentValue=self.state.vav_zone_temps[self.zone_index],
                units=EngineeringUnits.degreesFahrenheit,
                description=f"Floor {self.floor} {self.zone_name} Zone Temperature",
            ),
            # Zone Setpoint
            CommandableAnalogValueObject(
                objectIdentifier=("analogValue", base_id + 1),
                objectName=f"Floor{self.floor}-{self.zone_name}-Zone-Temp-SP",
                presentValue=self.state.vav_zone_setpoints[self.zone_index],
                units=EngineeringUnits.degreesFahrenheit,
                description=f"Floor {self.floor} {self.zone_name} Zone Temperature Setpoint",
            ),
            # Damper Position
            AnalogOutputObject(
                objectIdentifier=("analogOutput", base_id + 1),
                objectName=f"Floor{self.floor}-{self.zone_name}-Damper-Pos",
                presentValue=self.state.vav_damper_positions[self.zone_index],
                units=EngineeringUnits.percent,
                description=f"Floor {self.floor} {self.zone_name} Damper Position",
            ),
            # Airflow
            AnalogInputObject(
                objectIdentifier=("analogInput", base_id + 2),
                objectName=f"Floor{self.floor}-{self.zone_name}-Airflow",
                presentValue=self.state.vav_airflows[self.zone_index],
                units=EngineeringUnits.cubicFeetPerMinute,
                description=f"Floor {self.floor} {self.zone_name} Airflow",
            ),
            # Reheat Valve
            AnalogOutputObject(
                objectIdentifier=("analogOutput", base_id + 2),
                objectName=f"Floor{self.floor}-{self.zone_name}-Reheat-Valve",
                presentValue=self.state.vav_reheat_valves[self.zone_index],
                units=EngineeringUnits.percent,
                description=f"Floor {self.floor} {self.zone_name} Reheat Valve",
            ),
            # Occupancy
            BinaryInputObject(
                objectIdentifier=("binaryInput", base_id + 1),
                objectName=f"Floor{self.floor}-{self.zone_name}-Occupancy",
                presentValue="active" if self.state.is_occupied else "inactive",
                description=f"Floor {self.floor} {self.zone_name} Occupancy Sensor",
            ),
        ]

    def update_objects(self, objects: list[Any]):
        """Update object values from building state."""
        objects[0].presentValue = self.state.vav_zone_temps[self.zone_index]
        # Setpoint is commandable
        self.state.vav_zone_setpoints[self.zone_index] = objects[1].presentValue
        objects[2].presentValue = self.state.vav_damper_positions[self.zone_index]
        objects[3].presentValue = self.state.vav_airflows[self.zone_index]
        objects[4].presentValue = self.state.vav_reheat_valves[self.zone_index]
        objects[5].presentValue = "active" if self.state.is_occupied else "inactive"


class ChillerProfile:
    """Chiller Plant."""

    def __init__(self, building_state: BuildingState):
        """Initialize Chiller profile."""
        self.state = building_state

    def create_objects(self) -> list[Any]:
        """Create BACnet objects for the Chiller."""
        return [
            # Chilled Water Supply Temperature
            AnalogInputObject(
                objectIdentifier=("analogInput", 100),
                objectName="Chiller-1-CHW-Supply-Temp",
                presentValue=self.state.chilled_water_supply_temp,
                units=EngineeringUnits.degreesFahrenheit,
                description="Chiller Chilled Water Supply Temperature",
            ),
            # Chilled Water Return Temperature
            AnalogInputObject(
                objectIdentifier=("analogInput", 101),
                objectName="Chiller-1-CHW-Return-Temp",
                presentValue=self.state.chilled_water_return_temp,
                units=EngineeringUnits.degreesFahrenheit,
                description="Chiller Chilled Water Return Temperature",
            ),
            # Chiller Status
            BinaryInputObject(
                objectIdentifier=("binaryInput", 100),
                objectName="Chiller-1-Status",
                presentValue="active",
                description="Chiller Running Status",
            ),
            # Chiller Enable
            BinaryOutputObject(
                objectIdentifier=("binaryOutput", 100),
                objectName="Chiller-1-Enable",
                presentValue="active",
                description="Chiller Enable Command",
            ),
        ]

    def update_objects(self, objects: list[Any]):
        """Update object values from building state."""
        objects[0].presentValue = self.state.chilled_water_supply_temp
        objects[1].presentValue = self.state.chilled_water_return_temp


class MeterProfile:
    """Main Electrical Meter."""

    def __init__(self, building_state: BuildingState):
        """Initialize Meter profile."""
        self.state = building_state

    def create_objects(self) -> list[Any]:
        """Create BACnet objects for the Meter."""
        return [
            # Total Power
            AnalogInputObject(
                objectIdentifier=("analogInput", 200),
                objectName="Main-Meter-Total-Power",
                presentValue=self.state.total_power,
                units=EngineeringUnits.kilowatts,
                description="Building Total Power Demand",
            ),
            # Total Energy
            AnalogInputObject(
                objectIdentifier=("analogInput", 201),
                objectName="Main-Meter-Total-Energy",
                presentValue=self.state.total_energy,
                units=EngineeringUnits.kilowattHours,
                description="Building Total Energy Consumption",
            ),
            # Voltage
            AnalogInputObject(
                objectIdentifier=("analogInput", 202),
                objectName="Main-Meter-Voltage",
                presentValue=480.0,
                units=EngineeringUnits.volts,
                description="Main Electrical Voltage",
            ),
        ]

    def update_objects(self, objects: list[Any]):
        """Update object values from building state."""
        objects[0].presentValue = self.state.total_power
        objects[1].presentValue = self.state.total_energy
        objects[2].presentValue = 480.0 + random.uniform(-5, 5)


# --- Main Application ---


class BuildingSimulator:
    """Complete building simulation."""

    def __init__(self, args, equipment_type: str):
        """Initialize simulator application."""
        self.app = Application.from_args(args)
        self.state = BuildingState()
        self.equipment_type = equipment_type
        self.profile: AHUProfile | VAVProfile | ChillerProfile | MeterProfile
        self.objects: list[Any] = []

        # Create equipment based on type
        if equipment_type == "ahu":
            self.profile = AHUProfile(self.state)
        elif equipment_type.startswith("vav"):
            # Parse VAV index from equipment_type (e.g., "vav0", "vav1", ...)
            zone_index = int(equipment_type[3:])
            floor = (zone_index // 2) + 1
            zone_name = "North" if zone_index % 2 == 0 else "South"
            self.profile = VAVProfile(self.state, zone_index, floor, zone_name)
        elif equipment_type == "chiller":
            self.profile = ChillerProfile(self.state)
        elif equipment_type == "meter":
            self.profile = MeterProfile(self.state)
        else:
            raise ValueError(f"Unknown equipment type: {equipment_type}")

        self.objects = self.profile.create_objects()

        for obj in self.objects:
            self.app.add_object(obj)

        logger.info(f"Initialized {equipment_type} with {len(self.objects)} objects")
        asyncio.create_task(self.update_loop())

    async def update_loop(self):
        """Main simulation loop."""
        while True:
            try:
                # Update building physics
                self.state.update()

                # Update BACnet objects
                self.profile.update_objects(self.objects)

                # Log status on every iteration
                if self.equipment_type == "ahu":
                    logger.info(
                        f"AHU: Supply={self.state.ahu_supply_air_temp:.1f}°F, "
                        f"Return={self.state.ahu_return_air_temp:.1f}°F, "
                        f"Fan={self.state.ahu_fan_speed:.0f}%, "
                        f"Cooling={self.state.ahu_cooling_valve:.0f}%"
                    )
                elif self.equipment_type.startswith("vav"):
                    idx = int(self.equipment_type[3:])
                    logger.info(
                        f"VAV{idx}: Zone={self.state.vav_zone_temps[idx]:.1f}°F, "
                        f"SP={self.state.vav_zone_setpoints[idx]:.1f}°F, "
                        f"Damper={self.state.vav_damper_positions[idx]:.0f}%, "
                        f"Flow={self.state.vav_airflows[idx]:.0f}CFM"
                    )
                elif self.equipment_type == "chiller":
                    logger.info(
                        f"Chiller: Supply={self.state.chilled_water_supply_temp:.1f}°F, "
                        f"Return={self.state.chilled_water_return_temp:.1f}°F"
                    )
                elif self.equipment_type == "meter":
                    logger.info(
                        f"Meter: Power={self.state.total_power:.1f}kW, "
                        f"Energy={self.state.total_energy:.1f}kWh"
                    )

            except Exception as e:
                logger.error(f"Error in update loop: {e}")

            await asyncio.sleep(INTERVAL)


async def main():
    """Run the building simulator."""
    parser = SimpleArgumentParser()
    parser.add_argument(
        "--equipment",
        type=str,
        required=True,
        help="Equipment type: ahu, vav0-5, chiller, meter",
    )
    args = parser.parse_args()

    BuildingSimulator(args, args.equipment)
    await asyncio.Future()


def run():
    """Entry point for console_scripts."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    run()
