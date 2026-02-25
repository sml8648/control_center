"""ENC (NOAA) tile proxy: fetch WMTS tile and return (for CORS fallback)."""
import httpx

# NOAA Charts WMTS (GoogleMapsCompatible = Leaflet z/x/y)
NOAA_WMTS_TEMPLATE = (
    "https://gis.charttools.noaa.gov/arcgis/rest/services/MarineChart_Services/"
    "NOAACharts/MapServer/WMTS/tile/1.0.0/MarineChart_Services_NOAACharts/"
    "default/GoogleMapsCompatible/{z}/{y}/{x}.png"
)


async def fetch_enc_tile(z: int, x: int, y: int) -> bytes | None:
    """Fetch one ENC tile from NOAA WMTS; returns PNG bytes or None."""
    # WMTS order: TileMatrix(z), TileRow(y), TileCol(x)
    url = NOAA_WMTS_TEMPLATE.format(z=z, y=y, x=x)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(url)
            if r.status_code == 200 and r.content:
                return r.content
    except Exception:
        pass
    return None
