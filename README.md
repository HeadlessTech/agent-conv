# AI Voice Assistant Demo

A reminder agent using ChatGPT voice stream APIs with interruption handling.

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

Then add your OpenAI API key to the `.env` file.

4. Run the server:

```bash
python main.py
```

5. Open your browser to `http://localhost:8000`

## Usage

- Click "Start Demo" to begin
- The agent will speak the reminder
- Ask questions about the reminder
- The agent supports interruption handling
