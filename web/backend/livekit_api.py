"""LiveKit API endpoints for Voice Mode web dashboard"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
import jwt
import time
import os
import random
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/livekit")

# Configuration - can be overridden by environment variables
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "ws://localhost:7880")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "secret")
ACCESS_PASSWORD = os.getenv("LIVEKIT_ACCESS_PASSWORD", "voicemode123")

class ConnectionRequest(BaseModel):
    """Request model for getting LiveKit connection details"""
    password: str

class ConnectionDetails(BaseModel):
    """Response model for LiveKit connection details"""
    serverUrl: str
    roomName: str
    participantName: str
    participantToken: str

@router.post("/connection-details", response_model=ConnectionDetails)
async def get_connection_details(request: ConnectionRequest):
    """
    Generate LiveKit connection details for a new voice chat session.
    Requires password authentication.
    """
    # Verify password
    if request.password != ACCESS_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid password")
    
    # Generate unique room and participant names
    room_name = f"voice_assistant_room_{random.randint(10000, 99999)}"
    participant_name = f"voice_assistant_user_{random.randint(10000, 99999)}"
    
    try:
        # Create JWT token manually
        # LiveKit uses JWT tokens with specific claims
        now = int(time.time())
        
        claims = {
            "exp": now + 3600,  # Expire in 1 hour
            "iat": now,
            "nbf": now,
            "iss": LIVEKIT_API_KEY,
            "sub": participant_name,
            "name": participant_name,
            "metadata": "",
            "video": {
                "room": room_name,
                "roomJoin": True,
                "canPublish": True,
                "canPublishData": True,
                "canSubscribe": True,
                "canPublishSources": [],
                "canUpdateOwnMetadata": False,
                "hidden": False,
                "recorder": False
            },
            "identity": participant_name,
            "jti": f"{participant_name}-{now}"
        }
        
        # Generate JWT token
        jwt_token = jwt.encode(claims, LIVEKIT_API_SECRET, algorithm='HS256')
        
        logger.info(f"Generated LiveKit connection for room: {room_name}")
        
        return ConnectionDetails(
            serverUrl=LIVEKIT_URL,
            roomName=room_name,
            participantName=participant_name,
            participantToken=jwt_token
        )
        
    except Exception as e:
        logger.error(f"Error generating LiveKit connection details: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate connection details")

@router.get("/status")
async def get_livekit_status():
    """Get the current LiveKit configuration status"""
    return {
        "configured": bool(LIVEKIT_API_KEY and LIVEKIT_API_SECRET),
        "server_url": LIVEKIT_URL,
        "has_api_key": bool(LIVEKIT_API_KEY),
        "has_api_secret": bool(LIVEKIT_API_SECRET),
        "password_protected": bool(ACCESS_PASSWORD)
    }