import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import asyncio
import json
from openai import AsyncOpenAI
import base64
import websockets

# Load environment variables
load_dotenv()

app = FastAPI()

# Initialize OpenAI client
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Configurable initial instructions for the reminder agent
INITIAL_INSTRUCTIONS = """You are a helpful reminder assistant. 

The reminder details are:
Meeting with Elon Musk tomorrow at 3pm, Location: London

When the conversation starts, please greet the user and tell them about their reminder in a friendly and natural way. Then answer any questions they might have about the reminder. Keep your responses concise and conversational."""


@app.get("/")
async def get():
    """Serve the main HTML page"""
    return HTMLResponse(content=open("index.html").read())


@app.websocket("/ws/voice")
async def websocket_endpoint(websocket: WebSocket, reminder: str = ""):
    """WebSocket endpoint for real-time voice communication with OpenAI"""
    await websocket.accept()

    # Create dynamic instructions with the provided reminder
    if reminder:
        instructions = f"""You are a helpful reminder assistant. 

The reminder details are:
{reminder}

When the conversation starts, greet the user briefly and give them a SHORT summary of the reminder (just the main event/meeting in one sentence). Keep it under 10 seconds. Only provide more details if the user asks specific questions. Be conversational and friendly, but concise."""
    else:
        instructions = INITIAL_INSTRUCTIONS

    try:
        # Connect to OpenAI Realtime API via WebSocket
        url = (
            "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17"
        )
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1",
        }

        async with websockets.connect(url, extra_headers=headers) as openai_ws:

            # Send initial session configuration
            await openai_ws.send(
                json.dumps(
                    {
                        "type": "session.update",
                        "session": {
                            "modalities": ["text", "audio"],
                            "instructions": instructions,
                            "voice": "alloy",
                            "input_audio_format": "pcm16",
                            "output_audio_format": "pcm16",
                            "turn_detection": {
                                "type": "server_vad",  # Server-side Voice Activity Detection for interruption
                                "threshold": 0.5,
                                "prefix_padding_ms": 300,
                                "silence_duration_ms": 500,
                            },
                        },
                    }
                )
            )

            # Send initial greeting trigger
            await openai_ws.send(
                json.dumps(
                    {
                        "type": "conversation.item.create",
                        "item": {
                            "type": "message",
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": "Hello, please tell me about my reminder.",
                                }
                            ],
                        },
                    }
                )
            )

            await openai_ws.send(json.dumps({"type": "response.create"}))

            # Track if there's an active response
            response_in_progress = {"active": False}

            # Create tasks for bidirectional communication
            async def forward_client_to_openai():
                """Forward audio from client to OpenAI"""
                try:
                    while True:
                        message = await websocket.receive_json()
                        if message.get("type") == "audio":
                            # Forward audio data to OpenAI
                            await openai_ws.send(
                                json.dumps(
                                    {
                                        "type": "input_audio_buffer.append",
                                        "audio": message["audio"],
                                    }
                                )
                            )
                        elif message.get("type") == "commit":
                            # Commit audio buffer
                            await openai_ws.send(
                                json.dumps({"type": "input_audio_buffer.commit"})
                            )
                            await openai_ws.send(
                                json.dumps({"type": "response.create"})
                            )
                except WebSocketDisconnect:
                    pass

            async def forward_openai_to_client():
                """Forward responses from OpenAI to client"""
                try:
                    async for raw_message in openai_ws:
                        event = json.loads(raw_message)
                        event_type = event.get("type")

                        # Track response state
                        if event_type in ["response.created", "response.audio.delta"]:
                            response_in_progress["active"] = True
                        elif event_type in ["response.done", "response.cancelled"]:
                            response_in_progress["active"] = False

                        # Forward relevant events to client
                        if event_type == "response.audio.delta":
                            await websocket.send_json(
                                {"type": "audio", "audio": event.get("delta")}
                            )
                        elif event_type == "response.audio_transcript.delta":
                            await websocket.send_json(
                                {"type": "transcript", "text": event.get("delta")}
                            )
                        elif event_type == "response.done":
                            await websocket.send_json({"type": "response_done"})
                        elif event_type == "input_audio_buffer.speech_started":
                            # User started speaking - interruption detected
                            # Only cancel if there's an active response
                            if response_in_progress["active"]:
                                await openai_ws.send(
                                    json.dumps({"type": "response.cancel"})
                                )
                            await websocket.send_json({"type": "speech_started"})
                        elif event_type == "input_audio_buffer.speech_stopped":
                            await websocket.send_json({"type": "speech_stopped"})
                        elif event_type == "error":
                            await websocket.send_json(
                                {"type": "error", "error": event.get("error", {})}
                            )
                except Exception as e:
                    print(f"Error in OpenAI to client: {e}")

            # Run both directions concurrently
            await asyncio.gather(forward_client_to_openai(), forward_openai_to_client())

    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
