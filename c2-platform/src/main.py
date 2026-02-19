"""Run C2 Platform (web + API)."""
import argparse
import socket
from pathlib import Path

import uvicorn

from c2.api import create_app

def _local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="C2 Platform - Web & API for subsystem commands")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (0.0.0.0 = all interfaces)")
    parser.add_argument("--port", type=int, default=8080, help="Bind port (default 8080)")
    parser.add_argument("--config", default="var/config.yml", help="Config YAML path (subsystems)")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = Path(__file__).resolve().parent.parent / config_path

    app = create_app(config_path)

    port = args.port
    host = args.host
    print("")
    print("  C2 Platform")
    print("  ----------")
    print(f"  로컬:      http://127.0.0.1:{port}")
    print(f"  로컬:      http://localhost:{port}")
    if host == "0.0.0.0":
        ip = _local_ip()
        if ip != "127.0.0.1":
            print(f"  외부:      http://{ip}:{port}")
        print(f"  (외부 접속 시 방화벽에서 TCP {port} 허용 필요)")
    print("")

    uvicorn.run(app, host=host, port=port)
