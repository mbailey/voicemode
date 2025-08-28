"""Voice Mode Web API - Backend service for dashboard"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
from datetime import datetime
import asyncio
import json
import subprocess
from pathlib import Path
import livekit_api

app = FastAPI(
    title="Voice Mode Dashboard API",
    version="0.1.0",
    description="Web API for Voice Mode service management and monitoring"
)

# CORS configuration for local development
origins = [
    "http://localhost:3000",
    "http://localhost:5173", 
    "http://localhost:5174",
    "http://localhost:5175",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include LiveKit API router
app.include_router(livekit_api.router)

# In-memory storage for demo (replace with actual service calls)
connected_clients: List[WebSocket] = []

# Service definitions
SERVICES = {
    "whisper": {
        "display_name": "Whisper STT",
        "description": "Speech-to-text service using OpenAI Whisper",
        "port": 8000,
        "config_keys": ["model", "device", "language"]
    },
    "kokoro": {
        "display_name": "Kokoro TTS", 
        "description": "Text-to-speech service with multiple voices",
        "port": 8880,
        "config_keys": ["voices", "default_voice", "speed"]
    }
}

# Mock conversation data (will be replaced with actual data)
mock_conversations = [
    {
        "id": "conv-1",
        "timestamp": "2024-01-20T10:30:00Z",
        "messages": [
            {"role": "user", "content": "Hello Cora", "type": "voice"},
            {"role": "assistant", "content": "Hello! How can I help you today?", "type": "voice"},
        ]
    }
]

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "name": "Voice Mode Dashboard API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health"
    }

@app.get("/api/health")
async def health_check():
    """Overall system health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "whisper": "healthy",
            "kokoro": "healthy"
        }
    }

@app.get("/api/services")
async def list_services():
    """List all services with their current status"""
    services = []
    for name, config in SERVICES.items():
        # TODO: Get actual status from voice_mode service module
        service_info = {
            "name": name,
            "display_name": config["display_name"],
            "description": config["description"],
            "status": "running" if name == "whisper" else "stopped",  # Mock status
            "port": config["port"],
            "uptime": 3600 if name == "whisper" else 0,
            "cpu_usage": 15.2 if name == "whisper" else 0,
            "memory_mb": 512 if name == "whisper" else 0,
        }
        services.append(service_info)
    
    return {"services": services}

@app.get("/api/services/{service_name}")
async def get_service_detail(service_name: str):
    """Get detailed information about a specific service"""
    if service_name not in SERVICES:
        raise HTTPException(status_code=404, detail=f"Service {service_name} not found")
    
    config = SERVICES[service_name]
    # TODO: Get actual status and config from voice_mode
    return {
        "name": service_name,
        "display_name": config["display_name"],
        "description": config["description"],
        "status": "running" if service_name == "whisper" else "stopped",
        "port": config["port"],
        "configuration": {
            "model": "base" if service_name == "whisper" else None,
            "voices": ["af_sky", "am_adam"] if service_name == "kokoro" else None
        },
        "logs": [
            {"timestamp": "2024-01-20T10:00:00Z", "level": "info", "message": f"{service_name} started successfully"},
            {"timestamp": "2024-01-20T10:00:01Z", "level": "info", "message": f"Listening on port {config['port']}"}
        ]
    }

@app.post("/api/services/{service_name}/start")
async def start_service(service_name: str):
    """Start a service"""
    if service_name not in SERVICES:
        raise HTTPException(status_code=404, detail=f"Service {service_name} not found")
    
    # TODO: Actually start the service using voice_mode service module
    await broadcast_status_update(service_name, "starting")
    await asyncio.sleep(1)  # Simulate startup time
    await broadcast_status_update(service_name, "running")
    
    return {
        "success": True,
        "message": f"{SERVICES[service_name]['display_name']} started successfully",
        "service": service_name,
        "status": "running"
    }

@app.post("/api/services/{service_name}/stop")
async def stop_service(service_name: str):
    """Stop a service"""
    if service_name not in SERVICES:
        raise HTTPException(status_code=404, detail=f"Service {service_name} not found")
    
    # TODO: Actually stop the service
    await broadcast_status_update(service_name, "stopping")
    await asyncio.sleep(1)
    await broadcast_status_update(service_name, "stopped")
    
    return {
        "success": True,
        "message": f"{SERVICES[service_name]['display_name']} stopped",
        "service": service_name,
        "status": "stopped"
    }

@app.post("/api/services/{service_name}/restart")
async def restart_service(service_name: str):
    """Restart a service"""
    if service_name not in SERVICES:
        raise HTTPException(status_code=404, detail=f"Service {service_name} not found")
    
    await stop_service(service_name)
    await start_service(service_name)
    return {
        "success": True,
        "message": f"{SERVICES[service_name]['display_name']} restarted",
        "service": service_name,
        "status": "running"
    }

@app.get("/api/services/{service_name}/logs")
async def get_service_logs(service_name: str, lines: int = 100):
    """Get recent logs for a service"""
    if service_name not in SERVICES:
        raise HTTPException(status_code=404, detail=f"Service {service_name} not found")
    
    # TODO: Get actual logs from service
    mock_logs = []
    for i in range(min(lines, 10)):
        mock_logs.append({
            "timestamp": f"2024-01-20T10:00:{i:02d}Z",
            "level": "info" if i % 3 else "debug",
            "message": f"Sample log message {i} for {service_name}"
        })
    
    return {"service": service_name, "logs": mock_logs}

@app.get("/api/conversations")
async def list_conversations():
    """List recent conversations"""
    return {"conversations": mock_conversations}

@app.get("/api/conversations/current")
async def get_current_conversation():
    """Get the current/active conversation"""
    # TODO: Get actual current conversation from voice_mode
    return {
        "active": True,
        "started": "2024-01-20T10:30:00Z",
        "messages": [
            {"role": "user", "content": "What's the weather like?", "type": "voice", "timestamp": "2024-01-20T10:30:00Z"},
            {"role": "assistant", "content": "I don't have access to real-time weather data, but I can help you with other questions!", "type": "voice", "timestamp": "2024-01-20T10:30:02Z"},
        ]
    }

@app.post("/api/conversations/send")
async def send_message(message: Dict[str, str]):
    """Send a text message to the conversation"""
    # TODO: Send to actual voice_mode conversation
    content = message.get("content", "")
    
    # Broadcast to WebSocket clients
    await broadcast_conversation_message({
        "role": "user",
        "content": content,
        "type": "text",
        "timestamp": datetime.utcnow().isoformat()
    })
    
    # Simulate assistant response after a delay
    asyncio.create_task(simulate_assistant_response(content))
    
    return {"success": True, "message": "Message sent"}

async def simulate_assistant_response(user_message: str):
    """Simulate an assistant response (replace with actual voice_mode integration)"""
    await asyncio.sleep(2)
    await broadcast_conversation_message({
        "role": "assistant",
        "content": f"I received your message: '{user_message}'. This is a demo response!",
        "type": "text",
        "timestamp": datetime.utcnow().isoformat()
    })

@app.post("/api/voice/test")
async def test_voice(request: Dict[str, Any]):
    """Test voice synthesis with given text and settings"""
    text = request.get("text", "Hello, this is a test")
    
    # TODO: Actually call voice-mode converse with --no-wait
    # For now, simulate the operation
    
    return {
        "success": True,
        "message": "Voice test completed",
        "text": text,
        "duration_ms": 1500,
        "voice_used": "af_sky",
        "provider": "kokoro"
    }

@app.get("/api/stats/voice")
async def get_voice_stats():
    """Get voice conversation statistics"""
    # TODO: Get actual stats from voice_mode
    return {
        "session": {
            "duration_seconds": 3600,
            "total_interactions": 42,
            "success_rate": 0.95
        },
        "performance": {
            "avg_ttfa_ms": 1200,
            "avg_tts_ms": 800,
            "avg_stt_ms": 2000
        },
        "providers": {
            "tts": {"openai": 30, "kokoro": 12},
            "stt": {"whisper": 42}
        }
    }

@app.websocket("/ws/status")
async def websocket_status(websocket: WebSocket):
    """WebSocket endpoint for real-time status updates"""
    await websocket.accept()
    connected_clients.append(websocket)
    
    try:
        # Send initial status
        for service_name in SERVICES:
            await websocket.send_json({
                "type": "status",
                "service": service_name,
                "status": "running" if service_name == "whisper" else "stopped",
                "timestamp": datetime.utcnow().isoformat()
            })
        
        # Keep connection alive
        while True:
            await asyncio.sleep(1)
            await websocket.send_json({"type": "ping"})
            
    except WebSocketDisconnect:
        connected_clients.remove(websocket)

@app.websocket("/ws/conversation")
async def websocket_conversation(websocket: WebSocket):
    """WebSocket endpoint for real-time conversation updates"""
    await websocket.accept()
    connected_clients.append(websocket)
    
    try:
        while True:
            # Wait for messages from client
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "message":
                # Broadcast to all clients
                await broadcast_conversation_message({
                    "role": "user",
                    "content": message.get("content"),
                    "type": "text",
                    "timestamp": datetime.utcnow().isoformat()
                })
                
    except WebSocketDisconnect:
        connected_clients.remove(websocket)

async def broadcast_status_update(service: str, status: str):
    """Broadcast service status update to all connected WebSocket clients"""
    message = {
        "type": "status",
        "service": service,
        "status": status,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    for client in connected_clients:
        try:
            await client.send_json(message)
        except:
            # Client disconnected, remove from list
            connected_clients.remove(client)

async def broadcast_conversation_message(message: Dict[str, Any]):
    """Broadcast conversation message to all connected WebSocket clients"""
    broadcast_data = {
        "type": "conversation",
        "message": message
    }
    
    for client in connected_clients:
        try:
            await client.send_json(broadcast_data)
        except:
            connected_clients.remove(client)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080, reload=True)