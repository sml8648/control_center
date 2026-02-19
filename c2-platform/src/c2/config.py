"""C2 platform configuration."""
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class SubsystemConfig(BaseModel):
    """Single subsystem definition."""

    id: str = Field(..., description="Unique subsystem identifier")
    name: str = Field(..., description="Display name")
    endpoint: Optional[str] = Field(None, description="HTTP endpoint to receive commands")
    description: str = Field("", description="Optional description")
    enabled: bool = Field(True, description="Whether subsystem accepts commands")


def load_subsystems(config_path: Optional[Path] = None) -> list[SubsystemConfig]:
    """Load subsystem list from YAML. Returns default in-memory list if file missing."""
    default = [
        SubsystemConfig(id="nav", name="Navigation", description="Course and waypoint commands"),
        SubsystemConfig(id="propulsion", name="Propulsion", description="Throttle and engine commands"),
        SubsystemConfig(id="sensors", name="Sensors", description="Sensor enable/configure"),
    ]
    if not config_path or not config_path.exists():
        return default
    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    subs = data.get("subsystems", [])
    if not subs:
        return default
    return [SubsystemConfig(**s) for s in subs]
