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


def create_instructions(reminder: str) -> str:
    """Create instructions for the AI assistant with the given reminder"""
    return f"""You are a helpful AI reminder assistant built by Farolabs. 

The reminder details are:
{reminder}

When the conversation starts, greet the user briefly and give them a SHORT summary of the reminder (just the main event/meeting in one sentence). Keep it under 10 seconds. After this first summary, you MAY ask "Would you like to know more?" to offer additional details.

You can:
- Answer questions about the reminder details (who, what, when, where, why)
- Provide context and suggestions related to the meeting topic
- Help with preparations and what to bring
- Handle cancellations (confirm and acknowledge the cancellation)
- Handle rescheduling requests (acknowledge and suggest confirming new time)
- Discuss meeting strategies, talking points, or related topics
- Answer general questions related to the meeting subject

Be conversational, helpful, and concise. Keep responses under 15 seconds unless asked for more detail.

IMPORTANT:
- You may ask "Would you like to know more?" ONLY after the very first greeting/summary
- After that first exchange, do NOT ask any follow-up questions like "Would you like to know more?" or "Anything else?"
- Do NOT offer additional help unprompted in subsequent responses
- Only respond to direct questions from the user
- Keep all responses brief and natural"""


@app.get("/")
async def get():
    """Serve the main HTML page"""
    return HTMLResponse(content=open("index.html").read())


@app.websocket("/ws/voice")
async def websocket_endpoint(websocket: WebSocket, reminder: str = ""):
    """WebSocket endpoint for real-time voice communication with OpenAI"""
    await websocket.accept()

    # Create instructions with the provided reminder
    instructions = create_instructions(reminder)

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
                                "type": "server_vad",
                                "threshold": 0.3,
                                "prefix_padding_ms": 300,
                                "silence_duration_ms": 200,
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
                        elif message.get("type") == "cancel":
                            # Cancel current response
                            await openai_ws.send(
                                json.dumps({"type": "response.cancel"})
                            )
                except WebSocketDisconnect:
                    pass

            async def forward_openai_to_client():
                """Forward responses from OpenAI to client"""
                try:
                    async for raw_message in openai_ws:
                        event = json.loads(raw_message)
                        event_type = event.get("type")

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
                            # User started speaking
                            await websocket.send_json({"type": "speech_started"})
                        elif event_type == "input_audio_buffer.speech_stopped":
                            await websocket.send_json({"type": "speech_stopped"})
                        elif event_type == "error":
                            await websocket.send_json(
                                {"type": "error", "error": event.get("error", {})}
                            )
                except Exception:
                    pass

            # Run both directions concurrently
            await asyncio.gather(forward_client_to_openai(), forward_openai_to_client())

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
