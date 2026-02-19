"""Dispatch commands to subsystems (HTTP callback)."""
import logging
from typing import Any

import httpx
from pydantic import BaseModel

from .config import SubsystemConfig
from .models import CommandStatus

logger = logging.getLogger(__name__)


class Dispatcher:
    """Sends commands to subsystem endpoints."""

    def __init__(self, timeout_seconds: float = 10.0):
        self.timeout = timeout_seconds

    async def send_to_subsystem(
        self,
        subsystem: SubsystemConfig,
        action: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Send command to one subsystem. Returns result dict with status and optional body."""
        if not subsystem.enabled:
            return {"subsystem_id": subsystem.id, "status": "disabled", "error": "Subsystem disabled"}
        if not subsystem.endpoint:
            # No endpoint: record as "sent" locally (simulated ack)
            logger.info("Command for %s (no endpoint): action=%s params=%s", subsystem.id, action, params)
            return {"subsystem_id": subsystem.id, "status": "sent", "message": "No endpoint configured"}
        payload = {"action": action, "params": params}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(subsystem.endpoint, json=payload)
                r.raise_for_status()
                body = r.json() if r.content else {}
                return {
                    "subsystem_id": subsystem.id,
                    "status": "sent",
                    "status_code": r.status_code,
                    "response": body,
                }
        except httpx.TimeoutException as e:
            logger.warning("Timeout sending to %s: %s", subsystem.endpoint, e)
            return {"subsystem_id": subsystem.id, "status": "failed", "error": "timeout"}
        except Exception as e:
            logger.exception("Failed to send to %s: %s", subsystem.endpoint, e)
            return {"subsystem_id": subsystem.id, "status": "failed", "error": str(e)}
