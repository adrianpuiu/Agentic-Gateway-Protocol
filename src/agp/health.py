"""
Lightweight HTTP health endpoint for gateway monitoring.

Uses raw asyncio — no external dependencies needed.
"""

import asyncio
import json
import time
from typing import Any


class HealthServer:
    """
    Minimal HTTP server exposing GET /health.

    Response includes:
    - status: "ok" or "degraded"
    - uptime_s: seconds since server started
    - channels: per-channel running status
    - queues: inbound/outbound queue depths
    """

    def __init__(
        self,
        bus=None,
        channels=None,
        host: str = "0.0.0.0",
        port: int = 8080,
    ):
        self._bus = bus
        self._channels = channels
        self._host = host
        self._port = port
        self._start_time = time.monotonic()
        self._server: asyncio.Server | None = None

    def _build_health(self) -> dict[str, Any]:
        """Build the health check response payload."""
        uptime = round(time.monotonic() - self._start_time, 1)

        # Channel statuses
        channel_status = {}
        if self._channels:
            channel_status = self._channels.get_status()

        # Determine overall status
        all_ok = (
            all(ch.get("running", False) for ch in channel_status.values())
            if channel_status
            else True
        )
        status = "ok" if all_ok else "degraded"

        # Queue depths
        queues = {}
        if self._bus:
            queues = {
                "inbound": self._bus.inbound_depth,
                "outbound": self._bus.outbound_depth,
            }

        return {
            "status": status,
            "uptime_s": uptime,
            "channels": channel_status,
            "queues": queues,
        }

    async def _handle_request(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle an incoming HTTP request."""
        try:
            # Read request line
            request_line = await asyncio.wait_for(reader.readline(), timeout=5)
            request_str = request_line.decode("utf-8", errors="replace").strip()

            # Drain remaining headers
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=5)
                if line == b"\r\n" or line == b"\n" or not line:
                    break

            # Route
            if request_str.startswith("GET /health"):
                body = json.dumps(self._build_health(), indent=2)
                response = (
                    "HTTP/1.1 200 OK\r\n"
                    "Content-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    "Connection: close\r\n"
                    "\r\n"
                    f"{body}"
                )
            else:
                body = '{"error": "Not found"}'
                response = (
                    "HTTP/1.1 404 Not Found\r\n"
                    "Content-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    "Connection: close\r\n"
                    "\r\n"
                    f"{body}"
                )

            writer.write(response.encode())
            await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def start(self) -> None:
        """Start the health HTTP server."""
        self._start_time = time.monotonic()
        self._server = await asyncio.start_server(
            self._handle_request,
            self._host,
            self._port,
        )
        print(f"✓ Health endpoint listening on http://{self._host}:{self._port}/health")
        await self._server.serve_forever()

    async def stop(self) -> None:
        """Stop the health server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
