"""Production server for serving built Next.js frontend without Node.js."""

import asyncio
import json
import logging
import mimetypes
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingMixIn
from threading import Thread
from typing import Optional, Dict, Any
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger("voice-mode")


class ProductionFrontendHandler(SimpleHTTPRequestHandler):
    """HTTP handler for serving production Next.js frontend."""
    
    def __init__(self, *args, frontend_dir: Path, **kwargs):
        self.frontend_dir = frontend_dir
        self.static_dir = frontend_dir / ".next" / "static"
        self.build_dir = frontend_dir / ".next"
        super().__init__(*args, directory=str(frontend_dir), **kwargs)
    
    def do_GET(self):
        """Handle GET requests with Next.js routing."""
        try:
            # Parse the request path
            parsed_path = urlparse(self.path)
            path = parsed_path.path
            
            # Handle API routes
            if path.startswith('/api/'):
                return self.handle_api_route(path, parsed_path.query)
            
            # Handle static assets
            if path.startswith('/_next/static/'):
                return self.serve_static_asset(path)
            
            # Handle special Next.js files
            if path in ['/favicon.ico', '/robots.txt', '/sitemap.xml']:
                return self.serve_special_file(path)
            
            # Handle page routes (serve index.html for SPA routing)
            return self.serve_page()
            
        except Exception as e:
            logger.error(f"Error handling request {self.path}: {e}")
            self.send_error(500, str(e))
    
    def serve_static_asset(self, path: str):
        """Serve static assets from .next/static directory."""
        # Remove /_next/static/ prefix and serve from static directory
        asset_path = path[14:]  # Remove "/_next/static/"
        file_path = self.static_dir / asset_path
        
        if file_path.exists() and file_path.is_file():
            return self.serve_file(file_path)
        else:
            self.send_error(404, "Static asset not found")
    
    def serve_special_file(self, path: str):
        """Serve special files like favicon.ico."""
        file_path = self.frontend_dir / "public" / path[1:]  # Remove leading slash
        
        if file_path.exists():
            return self.serve_file(file_path)
        else:
            self.send_error(404, "File not found")
    
    def serve_page(self):
        """Serve the main page (index.html for all routes)."""
        # Look for built page or fallback to index.html
        index_path = self.frontend_dir / ".next" / "server" / "pages" / "index.html"
        
        if not index_path.exists():
            # Fallback to static index.html
            index_path = self.frontend_dir / "public" / "index.html"
        
        if not index_path.exists():
            # Generate a minimal HTML page
            return self.serve_minimal_page()
        
        return self.serve_file(index_path, content_type="text/html")
    
    def serve_minimal_page(self):
        """Serve a minimal HTML page if no built version exists."""
        html = '''<!DOCTYPE html>
<html>
<head>
    <title>Voice Assistant</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body>
    <div id="root">
        <h1>Voice Assistant Frontend</h1>
        <p>The frontend is running in development mode.</p>
        <p>For full functionality, ensure Node.js dependencies are installed.</p>
    </div>
</body>
</html>'''
        
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html.encode())))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(html.encode())
    
    def serve_file(self, file_path: Path, content_type: Optional[str] = None):
        """Serve a file with appropriate headers."""
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
            
            if not content_type:
                content_type, _ = mimetypes.guess_type(str(file_path))
                if not content_type:
                    content_type = "application/octet-stream"
            
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            
            # Add caching for static assets
            if "/_next/static/" in str(file_path):
                self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            else:
                self.send_header("Cache-Control", "no-cache")
            
            self.end_headers()
            self.wfile.write(content)
            
        except Exception as e:
            logger.error(f"Error serving file {file_path}: {e}")
            self.send_error(500, str(e))
    
    def handle_api_route(self, path: str, query: str):
        """Handle API routes like /api/connection-details."""
        if path == "/api/connection-details":
            return self.handle_connection_details(query)
        else:
            self.send_error(404, f"API route not found: {path}")
    
    def handle_connection_details(self, query: str):
        """Handle the connection-details API endpoint."""
        try:
            # Parse query parameters
            params = parse_qs(query)
            password = params.get('password', [''])[0]
            
            # Get environment variables
            API_KEY = os.environ.get("LIVEKIT_API_KEY", "devkey")
            API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "secret")
            LIVEKIT_URL = os.environ.get("LIVEKIT_URL", "ws://localhost:7880")
            ACCESS_PASSWORD = os.environ.get("LIVEKIT_ACCESS_PASSWORD", "voicemode123")
            
            # Check password
            if password != ACCESS_PASSWORD:
                self.send_error(401, "Unauthorized")
                return
            
            # Generate connection details (simplified version)
            if not all([LIVEKIT_URL, API_KEY, API_SECRET]):
                self.send_error(500, "LiveKit configuration not complete")
                return
            
            # This is a simplified version - in production you'd want to 
            # import and use the full connection-details logic
            response_data = {
                "serverUrl": LIVEKIT_URL,
                "roomName": f"voice_assistant_room_{os.getpid()}",
                "participantToken": "dummy-token",  # Would generate real token
                "participantName": f"user_{os.getpid()}"
            }
            
            response_json = json.dumps(response_data)
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response_json)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(response_json.encode())
            
        except Exception as e:
            logger.error(f"Error handling connection-details API: {e}")
            self.send_error(500, str(e))
    
    def log_message(self, format, *args):
        """Override to use our logger."""
        logger.debug(format % args)


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """HTTP server that handles requests in separate threads."""
    daemon_threads = True
    allow_reuse_address = True


class ProductionFrontendServer:
    """Production server for serving built Next.js frontend."""
    
    def __init__(self, frontend_dir: Path, port: int = 3000, host: str = "127.0.0.1"):
        self.frontend_dir = frontend_dir
        self.port = port
        self.host = host
        self.server = None
        self.server_thread = None
    
    def start(self) -> Dict[str, Any]:
        """Start the production server."""
        try:
            # Check if frontend build exists
            build_dir = self.frontend_dir / ".next"
            has_build = build_dir.exists()
            
            if not has_build:
                logger.warning(f"No built frontend found at {build_dir}")
                logger.info("Starting minimal server (development mode may be needed)")
            
            # Create server with custom handler
            def handler(*args, **kwargs):
                return ProductionFrontendHandler(*args, frontend_dir=self.frontend_dir, **kwargs)
            
            self.server = ThreadedHTTPServer((self.host, self.port), handler)
            
            # Start server in background thread
            self.server_thread = Thread(target=self.server.serve_forever, daemon=True)
            self.server_thread.start()
            
            logger.info(f"Production frontend server started on http://{self.host}:{self.port}")
            
            return {
                "success": True,
                "host": self.host,
                "port": self.port,
                "url": f"http://{self.host}:{self.port}",
                "has_build": has_build,
                "mode": "production" if has_build else "minimal",
                "pid": os.getpid()
            }
            
        except Exception as e:
            logger.error(f"Failed to start production server: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def stop(self):
        """Stop the production server."""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        
        if self.server_thread:
            self.server_thread.join(timeout=5)
            self.server_thread = None
        
        logger.info("Production frontend server stopped")
    
    def is_running(self) -> bool:
        """Check if the server is running."""
        return self.server is not None and self.server_thread is not None and self.server_thread.is_alive()