# B2B Accelerator Appointment Assistant

An AI voice appointment assistant using OpenAI's Realtime API for B2B Accelerator consultations.

## Features

- Voice-based appointment booking
- Real-time conversation with AI assistant
- Client information integration
- Automatic appointment capture and external API posting
- Interruption handling for natural conversations

## Setup

1. Create virtual environment:

```bash
python3.10 -m venv venv
source venv/bin/activate  # On macOS/Linux
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create `.env` file:

```bash
cp .env.example .env
```

Then add your OpenAI API key and external API URL to the `.env` file.

4. Run the server:

```bash
python main.py
```

## Usage

### Create a Client

POST to `/clients` with client information:

```bash
curl -X POST http://localhost:8000/clients \
  -H "Content-Type: application/json" \
  -d '{"info": "Tech startup looking to scale sales operations"}'
```

This returns a `clientId`.

### Access Appointment Assistant

Open your browser to `http://localhost:8000/{clientId}` and click "Start Conversation" to begin booking an appointment.

The AI assistant will:

- Greet the client
- Answer questions about B2B Accelerator programs
- Help schedule a consultation appointment
- Automatically POST appointment data to your configured external API

## API Endpoints

- `POST /clients` - Create a new client
- `GET /{client_id}` - Access appointment assistant for a client
- `WS /ws/voice/{client_id}` - WebSocket for voice communication
