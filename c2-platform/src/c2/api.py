"""FastAPI app: web UI and REST API for subsystem commands."""
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader

from .config import load_subsystems, SubsystemConfig
from .dispatcher import Dispatcher
from .enc_tiles import fetch_enc_tile
from .models import (
    AddMapPointRequest,
    AddShipRequest,
    CommandRecord,
    CommandStatus,
    MapPoint,
    RouteWaypoint,
    SendCommandRequest,
    SendCommandResponse,
    SetWaypointRequest,
    Ship,
    ShipRoute,
    ShipWaypoint,
    SubsystemInfo,
    ZonePoint,
    ZonePolygon,
)

logger = logging.getLogger(__name__)

# In-memory command history (optional: replace with DB later)
_command_history: list[CommandRecord] = []
_HISTORY_LIMIT = 200

# Map points (lat/lon markers)
_map_points: list[MapPoint] = []
_MAP_POINTS_LIMIT = 500

# Ships (two vessels displayed on the map)
_ships: list[Ship] = [
    Ship(id="ship-01", name="SHIP-01", lat=35.10, lon=129.05, heading=45.0, color="#58a6ff"),
    Ship(id="ship-02", name="SHIP-02", lat=34.90, lon=128.70, heading=200.0, color="#3fb950"),
]
_ship_waypoints: dict[str, ShipWaypoint] = {}
_ship_routes: dict[str, ShipRoute] = {}


def parse_rtz(xml_str: str, ship_id: str) -> ShipRoute:
    """Parse an RTZ 1.0 XML string and return a ShipRoute."""
    root = ET.fromstring(xml_str)

    # Detect namespace from root tag (e.g. {http://www.cirm.org/RTZ/1/0})
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag[1 : root.tag.index("}")]

    def t(name: str) -> str:
        return f"{{{ns}}}{name}" if ns else name

    # Route name
    ri = root.find(t("routeInfo"))
    route_name = ri.get("routeName", "") if ri is not None else ""

    # Waypoints
    waypoints: list[RouteWaypoint] = []
    wps_el = root.find(t("waypoints"))
    if wps_el is not None:
        for wp_el in wps_el.findall(t("waypoint")):
            pos = wp_el.find(t("position"))
            if pos is None:
                continue
            wp_id = int(wp_el.get("id", 0))
            lat = float(pos.get("lat", 0))
            lon = float(pos.get("lon", 0))

            desired_course: Optional[float] = None
            desired_speed: Optional[float] = None
            wp_type: Optional[str] = None

            exts = wp_el.find(t("extensions"))
            if exts is not None:
                for ext in exts.findall(t("extension")):
                    wt = ext.find(t("waypointType"))
                    if wt is not None and wp_type is None:
                        wp_type = wt.get("type")
                    for md in ext.findall(t("missionData")):
                        if desired_course is None and md.get("desiredCourse"):
                            desired_course = float(md.get("desiredCourse"))  # type: ignore[arg-type]
                        if desired_speed is None and md.get("desiredSpeed"):
                            desired_speed = float(md.get("desiredSpeed"))  # type: ignore[arg-type]

            waypoints.append(
                RouteWaypoint(
                    id=wp_id,
                    lat=lat,
                    lon=lon,
                    desired_course=desired_course,
                    desired_speed=desired_speed,
                    waypoint_type=wp_type,
                )
            )

    # Keep-in / keep-out zones from root-level extensions
    keep_in_areas: list[ZonePolygon] = []
    keep_out_areas: list[ZonePolygon] = []

    root_exts = root.find(t("extensions"))
    if root_exts is not None:
        for ext in root_exts.findall(t("extension")):
            ki = ext.find(t("keepInArea"))
            if ki is not None:
                pts = [
                    ZonePoint(lat=float(p.get("lat", 0)), lon=float(p.get("lon", 0)))
                    for p in ki.findall(t("point"))
                ]
                if pts:
                    keep_in_areas.append(ZonePolygon(points=pts))
            ko = ext.find(t("keepOutArea"))
            if ko is not None:
                pts = [
                    ZonePoint(lat=float(p.get("lat", 0)), lon=float(p.get("lon", 0)))
                    for p in ko.findall(t("point"))
                ]
                if pts:
                    keep_out_areas.append(ZonePolygon(points=pts))

    return ShipRoute(
        ship_id=ship_id,
        route_name=route_name,
        waypoints=waypoints,
        keep_in_areas=keep_in_areas,
        keep_out_areas=keep_out_areas,
        loaded_at=datetime.now(timezone.utc),
    )


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

    # ---------- Ships API ----------

    @app.get("/api/ships", response_model=list[Ship])
    def list_ships():
        """List all ships on the map."""
        return list(_ships)

    @app.post("/api/ships", response_model=Ship, status_code=201)
    def add_ship(body: AddShipRequest):
        """Add a new ship to the map."""
        ship_id = "ship-" + str(uuid4())[:8]
        ship = Ship(
            id=ship_id,
            name=body.name,
            lat=body.lat,
            lon=body.lon,
            heading=0.0,
            color=body.color,
            platform_url=body.platform_url or None,
        )
        _ships.append(ship)
        return ship

    @app.delete("/api/ships/{ship_id}")
    def remove_ship(ship_id: str):
        """Remove a ship from the map."""
        ship = next((s for s in _ships if s.id == ship_id), None)
        if not ship:
            raise HTTPException(status_code=404, detail="Ship not found")
        _ships.remove(ship)
        _ship_waypoints.pop(ship_id, None)
        _ship_routes.pop(ship_id, None)
        return {"message": "removed"}

    @app.post("/api/ships/{ship_id}/waypoint", response_model=ShipWaypoint)
    def set_ship_waypoint(ship_id: str, body: SetWaypointRequest):
        """Set a waypoint for a ship."""
        ship = next((s for s in _ships if s.id == ship_id), None)
        if not ship:
            raise HTTPException(status_code=404, detail="Ship not found")
        wp = ShipWaypoint(
            ship_id=ship_id,
            lat=body.lat,
            lon=body.lon,
            label=body.label or f"{ship.name} WP",
            set_at=datetime.now(timezone.utc),
        )
        _ship_waypoints[ship_id] = wp
        return wp

    @app.get("/api/ships/{ship_id}/waypoint", response_model=ShipWaypoint)
    def get_ship_waypoint(ship_id: str):
        """Get the current waypoint for a ship."""
        if ship_id not in _ship_waypoints:
            raise HTTPException(status_code=404, detail="No waypoint set")
        return _ship_waypoints[ship_id]

    @app.get("/api/ships/waypoints/all", response_model=dict[str, ShipWaypoint])
    def get_all_ship_waypoints():
        """Get all ship waypoints keyed by ship id."""
        return dict(_ship_waypoints)

    # ---------- Ship RTZ Route API ----------

    @app.post("/api/ships/{ship_id}/route/rtz", response_model=ShipRoute)
    async def upload_ship_route_rtz(ship_id: str, request: Request):
        """Upload an RTZ XML file (raw body, Content-Type: application/xml) to define the ship's route."""
        ship = next((s for s in _ships if s.id == ship_id), None)
        if not ship:
            raise HTTPException(status_code=404, detail="Ship not found")
        body = await request.body()
        try:
            route = parse_rtz(body.decode("utf-8"), ship_id)
        except ET.ParseError as exc:
            raise HTTPException(status_code=422, detail=f"RTZ XML parse error: {exc}") from exc
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"RTZ processing error: {exc}") from exc
        _ship_routes[ship_id] = route
        return route

    @app.get("/api/ships/{ship_id}/route", response_model=ShipRoute)
    def get_ship_route(ship_id: str):
        """Get the currently loaded RTZ route for a ship."""
        if ship_id not in _ship_routes:
            raise HTTPException(status_code=404, detail="No route loaded for this ship")
        return _ship_routes[ship_id]

    @app.delete("/api/ships/{ship_id}/route")
    def clear_ship_route(ship_id: str):
        """Remove the RTZ route for a ship."""
        _ship_routes.pop(ship_id, None)
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
