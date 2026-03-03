"""Request/response models for C2 API."""
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class CommandStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    ACK = "ack"
    FAILED = "failed"


class SendCommandRequest(BaseModel):
    """Request to send a command to subsystem(s)."""

    target: str = Field(..., description="Subsystem id or 'broadcast' for all")
    action: str = Field(..., description="Command action name")
    params: dict[str, Any] = Field(default_factory=dict, description="Command parameters")
    idempotency_key: Optional[str] = Field(None, description="Optional idempotency key")


class SendCommandResponse(BaseModel):
    """Response after sending command(s)."""

    command_id: str
    target: str
    action: str
    status: CommandStatus
    results: list[dict[str, Any]] = Field(default_factory=list)
    message: Optional[str] = None


class SubsystemInfo(BaseModel):
    """Subsystem info for API/UI."""

    id: str
    name: str
    description: str
    enabled: bool
    endpoint: Optional[str] = None


class CommandRecord(BaseModel):
    """Stored command for history."""

    command_id: str
    target: str
    action: str
    params: dict[str, Any]
    status: CommandStatus
    created_at: datetime
    results: list[dict[str, Any]] = Field(default_factory=list)


class MapPoint(BaseModel):
    """A point to display on the map."""

    id: str
    lat: float
    lon: float
    label: str = ""
    created_at: datetime
    source: str = "manual"  # "manual" | "command"


class AddMapPointRequest(BaseModel):
    """Request to add a point to the map."""

    lat: float
    lon: float
    label: str = ""


class Ship(BaseModel):
    """A vessel displayed on the map."""

    id: str
    name: str
    lat: float
    lon: float
    heading: float = 0.0  # degrees, 0=North
    color: str = "#58a6ff"
    platform_url: Optional[str] = None
    # "manual" = no URL, "connected" = polling OK, "disconnected" = poll failed
    connection_status: str = "manual"
    last_position_at: Optional[datetime] = None


class PositionPollConfig(BaseModel):
    """Configuration for polling ship position from platform URLs."""

    interval_sec: float = 5.0
    timeout_sec: float = 3.0
    enabled: bool = True


class AddShipRequest(BaseModel):
    """Request to add a new ship to the map."""

    name: str
    lat: float
    lon: float
    color: str = "#58a6ff"
    platform_url: Optional[str] = None


class SetWaypointRequest(BaseModel):
    """Request to set a waypoint for a ship."""

    lat: float
    lon: float
    label: str = ""


class ShipWaypoint(BaseModel):
    """Waypoint assigned to a ship."""

    ship_id: str
    lat: float
    lon: float
    label: str = ""
    set_at: datetime


class RouteWaypoint(BaseModel):
    """A single waypoint inside an RTZ route."""

    id: int
    lat: float
    lon: float
    desired_course: Optional[float] = None
    desired_speed: Optional[float] = None
    waypoint_type: Optional[str] = None


class ZonePoint(BaseModel):
    lat: float
    lon: float


class ZonePolygon(BaseModel):
    """A polygon zone (keep-in or keep-out) from an RTZ file."""

    points: list[ZonePoint]


class ShipRoute(BaseModel):
    """RTZ-based route loaded for a ship."""

    ship_id: str
    route_name: str
    waypoints: list[RouteWaypoint]
    keep_in_areas: list[ZonePolygon]
    keep_out_areas: list[ZonePolygon]
    loaded_at: datetime


class HbtConfig(BaseModel):
    """IEC 61162-1 HBT transmission configuration."""

    interval_sec: float = 5.0   # HBT repeat interval in seconds
    talker_id: str = "II"       # Talker ID (II = Integrated Instrumentation)
    udp_port: int = 10110       # NMEA-over-UDP standard port
    enabled: bool = True


class HbtRecord(BaseModel):
    """Record of a single HBT sentence transmission attempt."""

    ship_id: str
    ship_name: str
    sentence: str               # Full NMEA sentence (without CRLF)
    target_host: Optional[str]  # Resolved hostname/IP, None if no platform_url
    sent_at: datetime
    status: str                 # "ok" | "error" | "no_target"
    error: Optional[str] = None
