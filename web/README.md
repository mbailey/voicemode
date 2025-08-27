# Voice Mode Web Dashboard

A web-based dashboard for managing Voice Mode services with real-time monitoring and control.

## Features

- **Service Management**: Start, stop, and restart Whisper STT and Kokoro TTS services
- **Real-time Monitoring**: Live status updates via WebSocket connections
- **Conversation Interface**: Chat-like UI for voice conversations with text input
- **Statistics Dashboard**: Voice performance metrics and session statistics
- **Service Logs**: View recent logs for each service
- **Dark Mode Support**: Automatic dark/light theme based on system preferences

## Architecture

```
web/
├── backend/          # FastAPI backend
│   ├── main.py      # API server
│   └── requirements.txt
└── frontend/         # React TypeScript frontend
    ├── src/
    │   ├── components/   # React components
    │   └── api/         # API client
    └── package.json
```

## Quick Start

### Backend

1. Install dependencies:
```bash
cd web/backend
pip install -r requirements.txt
```

2. Start the API server:
```bash
python main.py
# or
uvicorn main:app --reload --host 127.0.0.1 --port 8080
```

The API will be available at:
- http://localhost:8080
- API docs: http://localhost:8080/docs
- Alternative docs: http://localhost:8080/redoc

### Frontend

1. Install dependencies:
```bash
cd web/frontend
npm install
```

2. Start the development server:
```bash
npm run dev
```

The dashboard will be available at http://localhost:5173

## API Endpoints

### Service Management
- `GET /api/services` - List all services with status
- `GET /api/services/{name}` - Get service details
- `POST /api/services/{name}/start` - Start a service
- `POST /api/services/{name}/stop` - Stop a service
- `POST /api/services/{name}/restart` - Restart a service
- `GET /api/services/{name}/logs` - Get service logs

### Statistics
- `GET /api/stats/voice` - Voice conversation statistics
- `GET /api/health` - System health check

### Conversations
- `GET /api/conversations` - List conversations
- `GET /api/conversations/current` - Get active conversation
- `POST /api/conversations/send` - Send text message

### WebSocket Endpoints
- `WS /ws/status` - Real-time service status updates
- `WS /ws/conversation` - Real-time conversation updates

## Development

### Technology Stack

**Backend:**
- FastAPI - Modern Python web framework
- Uvicorn - ASGI server
- WebSockets - Real-time communication

**Frontend:**
- React 18 - UI framework
- TypeScript - Type safety
- Vite - Build tool and dev server
- Tailwind CSS - Utility-first CSS
- Tanstack Query - Data fetching and caching
- Heroicons - Icon library

### Next Steps

1. **Integration with Voice Mode**:
   - Connect to actual voice_mode service functions
   - Replace mock data with real service calls
   - Implement actual log streaming

2. **Voice Recording**:
   - Add Web Audio API for voice recording
   - Stream audio to backend
   - Display waveforms and audio levels

3. **Enhanced Features**:
   - Service configuration editor
   - Model selection for Whisper
   - Voice selection for Kokoro
   - Session history and analytics
   - Export conversation transcripts

4. **Production Ready**:
   - Authentication and API keys
   - HTTPS support
   - Docker deployment
   - Error handling and recovery
   - Performance optimizations

## Contributing

This is an initial implementation. Key areas for improvement:
- Replace mock data with actual service integration
- Add comprehensive error handling
- Implement voice recording functionality
- Add test coverage
- Improve accessibility

## License

Part of the Voice Mode project.