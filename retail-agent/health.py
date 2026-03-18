"""
Health check and monitoring endpoints.
Optional HTTP server for Docker/k8s health checks.
"""
import asyncio
from aiohttp import web
from datetime import datetime

from config import Limits, Thresholds


class HealthServer:
    """Simple health check server."""
    
    def __init__(self, engine_ref=None, port: int = 8080):
        self.engine = engine_ref
        self.port = port
        self._start_time = datetime.utcnow()
    
    async def health_handler(self, request):
        """Basic health check."""
        return web.json_response({
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "uptime": str(datetime.utcnow() - self._start_time)
        })
    
    async def stats_handler(self, request):
        """Return engine stats if available."""
        if not self.engine:
            return web.json_response({"error": "Engine not available"}, status=503)
        
        return web.json_response({
            "cycles_completed": self.engine._cycle_count,
            "errors_count": self.engine._error_count,
            "start_time": self.engine._start_time.isoformat()
        })
    
    async def start(self):
        """Start health server."""
        app = web.Application()
        app.router.add_get('/health', self.health_handler)
        app.router.add_get('/stats', self.stats_handler)
        
        runner = web.AppRunner(app)
        await runner.setup()
        
        site = web.TCPSite(runner, '0.0.0.0', self.port)
        await site.start()
        
        print(f"[Health] Server running on port {self.port}")
        return runner


async def run_health_server(engine, port: int = 8080):
    """Run health server in background."""
    server = HealthServer(engine, port)
    runner = await server.start()
    return runner
