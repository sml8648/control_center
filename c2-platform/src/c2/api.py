"""FastAPI app: web UI and REST API for subsystem commands."""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader

from .config import load_subsystems, SubsystemConfig
from .dispatcher import Dispatcher
from .enc_tiles import fetch_enc_tile
from .models import (
    AddMapPointRequest,
    CommandRecord,
    CommandStatus,
    MapPoint,
    SendCommandRequest,
    SendCommandResponse,
    SubsystemInfo,
)

logger = logging.getLogger(__name__)

# In-memory command history (optional: replace with DB later)
_command_history: list[CommandRecord] = []
_HISTORY_LIMIT = 200

# Map points (lat/lon markers)
_map_points: list[MapPoint] = []
_MAP_POINTS_LIMIT = 500


def _subsystem_to_info(s: SubsystemConfig) -> SubsystemInfo:
    return SubsystemInfo(
        id=s.id,
        name=s.name,
        description=s.description,
        enabled=s.enabled,
        endpoint=s.endpoint,
    )


def create_app(config_path: Optional[Path] = None) -> FastAPI:
    subsystems = load_subsystems(config_path)
    dispatcher = Dispatcher()

    app = FastAPI(
        title="C2 Platform",
        description="Web interface and API to send commands to subsystems",
        version="0.1.0",
    )

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    templates_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(templates_dir)))

    # ---------- Web UI ----------
    @app.get("/", response_class=HTMLResponse)
    def index():
        template = env.get_template("index.html")
        return template.render(
            subsystems=[_subsystem_to_info(s) for s in subsystems],
            history=_command_history[-50:][::-1],
        )

    # ---------- REST API ----------

    @app.get("/api/subsystems", response_model=list[SubsystemInfo])
    def list_subsystems():
        """List all registered subsystems."""
        return [_subsystem_to_info(s) for s in subsystems]

    @app.get("/api/subsystems/{subsystem_id}", response_model=SubsystemInfo)
    def get_subsystem(subsystem_id: str):
        """Get one subsystem by id."""
        for s in subsystems:
            if s.id == subsystem_id:
                return _subsystem_to_info(s)
        raise HTTPException(status_code=404, detail="Subsystem not found")

    @app.post("/api/commands", response_model=SendCommandResponse)
    async def send_command(body: SendCommandRequest):
        """Send a command to one subsystem or broadcast to all."""
        command_id = str(uuid4())
        targets: list[SubsystemConfig] = []
        if body.target.strip().lower() == "broadcast":
            targets = [s for s in subsystems if s.enabled]
        else:
            for s in subsystems:
                if s.id == body.target:
                    targets = [s]
                    break
            if not targets:
                raise HTTPException(status_code=404, detail=f"Subsystem not found: {body.target}")

        results = []
        for sub in targets:
            r = await dispatcher.send_to_subsystem(sub, body.action, body.params)
            results.append(r)

        status = CommandStatus.SENT
        if any(r.get("status") == "failed" for r in results):
            status = CommandStatus.FAILED
        elif any(r.get("status") == "sent" for r in results):
            status = CommandStatus.SENT

        record = CommandRecord(
            command_id=command_id,
            target=body.target,
            action=body.action,
            params=body.params,
            status=status,
            created_at=datetime.now(timezone.utc),
            results=results,
        )
        _command_history.append(record)
        while len(_command_history) > _HISTORY_LIMIT:
            _command_history.pop(0)

        # If command params contain lat/lon, add to map
        p = body.params
        if isinstance(p.get("lat"), (int, float)) and isinstance(p.get("lon"), (int, float)):
            _add_map_point(
                lat=float(p["lat"]),
                lon=float(p["lon"]),
                label=p.get("label") or body.action,
                source="command",
            )

        return SendCommandResponse(
            command_id=command_id,
            target=body.target,
            action=body.action,
            status=status,
            results=results,
        )

    @app.get("/api/commands", response_model=list[CommandRecord])
    def list_commands(limit: int = 50):
        """List recent commands (newest first)."""
        return _command_history[-limit:][::-1]

    @app.get("/api/commands/{command_id}", response_model=CommandRecord)
    def get_command(command_id: str):
        """Get a single command by id."""
        for c in _command_history:
            if c.command_id == command_id:
                return c
        raise HTTPException(status_code=404, detail="Command not found")

    # ---------- Map (coordinates) API ----------

    def _add_map_point(lat: float, lon: float, label: str = "", source: str = "manual"):
        pt = MapPoint(
            id=str(uuid4()),
            lat=lat,
            lon=lon,
            label=label,
            created_at=datetime.now(timezone.utc),
            source=source,
        )
        _map_points.append(pt)
        while len(_map_points) > _MAP_POINTS_LIMIT:
            _map_points.pop(0)

    @app.get("/api/map/points", response_model=list[MapPoint])
    def get_map_points():
        """List all points to display on the map."""
        return list(_map_points)

    @app.post("/api/map/points", response_model=MapPoint)
    def add_map_point(lat: float, lon: float, label: str = ""):
        """Add a point to the map (query params or JSON body)."""
        pt = MapPoint(
            id=str(uuid4()),
            lat=float(lat),
            lon=float(lon),
            label=label,
            created_at=datetime.now(timezone.utc),
            source="manual",
        )
        _map_points.append(pt)
        while len(_map_points) > _MAP_POINTS_LIMIT:
            _map_points.pop(0)
        return pt

    @app.post("/api/map/points/json", response_model=MapPoint)
    def add_map_point_json(body: AddMapPointRequest):
        """Add a point via JSON body: { \"lat\": 37.5, \"lon\": 127.0, \"label\": \"...\" }."""
        pt = MapPoint(
            id=str(uuid4()),
            lat=body.lat,
            lon=body.lon,
            label=body.label,
            created_at=datetime.now(timezone.utc),
            source="manual",
        )
        _map_points.append(pt)
        while len(_map_points) > _MAP_POINTS_LIMIT:
            _map_points.pop(0)
        return pt

    @app.delete("/api/map/points")
    def clear_map_points():
        """Remove all points from the map."""
        _map_points.clear()
        return {"message": "cleared"}

    # ---------- ENC tile proxy (NOAA WMS → tile) ----------

    @app.get("/api/map/enc/tiles/{z:int}/{x:int}/{y:int}.png", response_class=Response)
    async def enc_tile(z: int, x: int, y: int):
        """Proxy ENC (NOAA) tile for Leaflet. US coastal only."""
        if z < 1 or z > 18:
            return Response(status_code=400)
        content = await fetch_enc_tile(z, x, y)
        if content is None:
            return Response(status_code=204)
        return Response(content=content, media_type="image/png")

    return app
