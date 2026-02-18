import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import asyncio
import json
import httpx
from openai import AsyncOpenAI
import websockets
from sqlalchemy.orm import Session
from database import init_db, get_db
from models import Client

# Load environment variables
load_dotenv()

app = FastAPI()


# Initialize database on startup
@app.on_event("startup")
def startup_event():
    init_db()
    print("Database initialized successfully")


# Initialize OpenAI client
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# Pydantic models
class CreateClientRequest(BaseModel):
    info: str


class CreateClientResponse(BaseModel):
    clientId: int
    agentLink: str


async def handle_appointment_capture(
    client_id: int, took_appointment: bool, appointment_data: str = None
):
    """Handle appointment capture and POST to external API"""
    external_api_url = os.getenv("EXTERNAL_API_URL")

    if not external_api_url:
        print("Warning: EXTERNAL_API_URL not configured")
        return

    payload = {
        "clientId": client_id,
        "tookAppointment": took_appointment,
        "appointmentData": appointment_data,
    }

    # Log appointment details
    if took_appointment:
        print(f"\n{'='*60}")
        print(f"📅 APPOINTMENT CAPTURED")
        print(f"{'='*60}")
        print(f"Client ID: {client_id}")
        print(f"Appointment Date/Time: {appointment_data}")
        print(f"Status: Appointment Scheduled")
    else:
        print(f"\n{'='*60}")
        print(f"❌ APPOINTMENT DECLINED")
        print(f"{'='*60}")
        print(f"Client ID: {client_id}")
        print(f"Status: User declined appointment")

    try:
        async with httpx.AsyncClient() as http_client:
            response = await http_client.post(
                external_api_url, json=payload, timeout=10.0
            )
            print(f"✅ External API call successful: {response.status_code}")
            print(f"{'='*60}\n")
    except Exception as e:
        print(f"❌ External API call failed: {e}")
        print(f"{'='*60}\n")


@app.post("/clients", response_model=CreateClientResponse)
def create_client(request: CreateClientRequest, db: Session = Depends(get_db)):
    """Create a new client with info"""
    new_client = Client(info=request.info)
    db.add(new_client)
    db.commit()
    db.refresh(new_client)

    # Generate agent link
    server_url = os.getenv("SERVER_URL", "http://localhost:8000")
    agent_link = f"{server_url}/{new_client.id}"

    return CreateClientResponse(clientId=new_client.id, agentLink=agent_link)


def create_instructions(client_info: str) -> str:
    """Create instructions for the AI assistant with client information"""
    client_context = (
        f"\n\nClient Information:\n{client_info}"
        if client_info
        else "\n\nNo specific client information provided."
    )

    return f"""You are a helpful AI appointment assistant for B2B Accelerator.

About B2B Accelerator:
B2B Accelerator is a growth consulting and enablement firm that helps B2B companies build predictable revenue and scale sustainably. We work mainly with small and mid-sized businesses that want to strengthen their sales pipeline, improve marketing effectiveness, and create structured systems for long-term growth. Our approach focuses on practical frameworks, strategic guidance, and leadership development to help businesses move from unstable growth to scalable performance.

Our Programs:
1. BUILD Program - For early-stage companies
   - Develop customer acquisition systems
   - Structure sales processes
   - Foundation building for growth

2. GROW Program (Profit-DNA) - For scaling companies
   - Scale operations effectively
   - Improve profitability
   - Strengthen market positioning
   - Build strong teams and leadership systems

3. SCALE Program - For established companies
   - Strategic mentorship
   - High-level growth strategies
   - Organizational alignment
   - Advanced performance optimization

Onboarding Process:
We start with an assessment of the company's growth stage, goals, and challenges. Based on this evaluation, businesses are placed into the most suitable program. We then develop a strategic roadmap, followed by guided implementation using tools, coaching, and peer learning, with ongoing mentorship and performance reviews.{client_context}

Your Role:
You are here to help schedule a consultation appointment with B2B Accelerator. The client already has some knowledge about our services.

When the conversation starts, greet the client warmly and say something like: "Hello! I'm here to help you book an appointment with B2B Accelerator. When would you like to schedule your consultation?"

Guidelines:
- Be friendly, professional, and conversational
- Answer questions about B2B Accelerator's programs and services
- Help the client choose an appointment time
- Suggest weekday appointments if asked for recommendations
- Appointments are 30 minutes long
- Accept the date and time provided by the client
- Keep responses concise and under 15 seconds unless detailed explanation is requested
- Focus on being helpful while guiding toward appointment booking

Remember: Your primary goal is to schedule the appointment while providing helpful information about B2B Accelerator."""


@app.get("/{client_id}")
async def get(client_id: int):
    """Serve the main HTML page with clientId"""
    html_content = open("index.html", encoding="utf-8").read()
    # Inject clientId into HTML
    html_content = html_content.replace("{{CLIENT_ID}}", str(client_id))
    return HTMLResponse(content=html_content)


@app.websocket("/ws/voice/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: int):
    """WebSocket endpoint for real-time voice communication with OpenAI"""
    await websocket.accept()

    # Fetch client info from database
    db = next(get_db())
    client_info = ""
    try:
        client_record = db.query(Client).filter(Client.id == client_id).first()
        if client_record and client_record.info:
            client_info = client_record.info
    except Exception as e:
        print(f"Database error fetching client: {e}")
    finally:
        db.close()

    # Create instructions with the client info
    instructions = create_instructions(client_info)

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
                            "tools": [
                                {
                                    "type": "function",
                                    "name": "capture_appointment",
                                    "description": "Capture the appointment decision and datetime. Call this when the user agrees to an appointment and provides a date/time, or explicitly declines.",
                                    "parameters": {
                                        "type": "object",
                                        "properties": {
                                            "tookAppointment": {
                                                "type": "boolean",
                                                "description": "Whether the user agreed to take an appointment",
                                            },
                                            "appointmentData": {
                                                "type": "string",
                                                "description": "The appointment date and time in ISO format (e.g., 2026-02-20T14:00:00). Only required if tookAppointment is true.",
                                            },
                                        },
                                        "required": ["tookAppointment"],
                                    },
                                }
                            ],
                            "tool_choice": "auto",
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
                                    "text": "Hello, I would like to schedule an appointment.",
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

                        # Handle function calls
                        if event_type == "response.function_call_arguments.done":
                            function_name = event.get("name")
                            if function_name == "capture_appointment":
                                arguments = json.loads(event.get("arguments", "{}"))
                                await handle_appointment_capture(
                                    client_id,
                                    arguments.get("tookAppointment", False),
                                    arguments.get("appointmentData"),
                                )
                                # Send function response
                                await openai_ws.send(
                                    json.dumps(
                                        {
                                            "type": "conversation.item.create",
                                            "item": {
                                                "type": "function_call_output",
                                                "call_id": event.get("call_id"),
                                                "output": json.dumps(
                                                    {"status": "success"}
                                                ),
                                            },
                                        }
                                    )
                                )

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
