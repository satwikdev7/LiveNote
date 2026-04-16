# LiveNote

LiveNote is an AI-driven live meeting intelligence system that captures meeting audio in the browser, streams chunks to a FastAPI backend over WebSocket, and incrementally builds toward transcription, diarization, summarization, action item extraction, and final meeting reports.

This repository currently includes:

- Phase 0: foundation setup
- Phase 1: session lifecycle and WebSocket skeleton
- Phase 2: browser audio capture and chunk transport
- Phase 3: audio normalization and faster-whisper ASR
- Phase 4: asynchronous diarization backfill
- Phase 5: noise filtering and rolling transcript buffers
- Phase 6: intelligence extraction for summary, actions, decisions, and risks
- Phase 7: trust validation and verified merge
- Phase 8: human-in-the-loop edits and lock-aware preservation
- Phase 9: meeting-end consolidation and export
- Phase 10: optional Supabase persistence for reports
- Phase 11: demo mode and deployment-ready polish

The current build now gives you a working speech pipeline where:

- the frontend starts a meeting session
- the browser opens a WebSocket connection to the backend
- microphone audio is captured in 15-second chunks
- chunks are sent to the backend with sequence numbers
- the backend converts browser audio into wav
- faster-whisper produces transcript segments with timestamps
- transcript segments are rendered in the UI
- diarization attempts speaker backfill asynchronously when configured
- rolling display and LLM-ready buffers are tracked in memory
- validated intelligence updates are generated every 60 seconds
- users can edit summary, action items, decisions, and risks without AI overwriting those locked edits
- meeting end generates downloadable JSON and PDF exports

## Repository Structure

```text
LiveNote/
├── frontend/
├── backend/
├── docs/
└── README.md
```

## Tech Stack in This Phase

- Frontend: Next.js 14, TypeScript, TailwindCSS
- Backend: FastAPI, Python 3.10+, WebSocket support
- Transport: WebSocket
- Audio capture: MediaRecorder in Chrome

## Prerequisites

- Python 3.10+
- Node.js 20+
- npm 10+
- Chrome
- ffmpeg

For diarization specifically, use a clean Python `3.11` virtual environment. In this workspace, a compatible backend env was created at `backend/.venv311`.

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The frontend runs on `http://localhost:3000` by default.

## Backend Setup

```bash
cd backend
/opt/homebrew/bin/python3.11 -m venv .venv311
source .venv311/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The backend runs on `http://localhost:8000`.

## Environment Files

Copy the example environment files and fill them in as needed:

```bash
cp frontend/.env.example frontend/.env.local
cp backend/.env.example backend/.env
```

For Phases 3-7:

- `NEXT_PUBLIC_BACKEND_WS_URL` should point to `ws://localhost:8000/ws/meeting`
- ASR works after backend dependencies are installed
- diarization additionally requires `HUGGINGFACE_TOKEN` in `backend/.env`
- the Hugging Face account tied to that token must have accepted the `pyannote/speaker-diarization-3.1` model terms
- live intelligence additionally requires `DEEPSEEK_API_KEY` in `backend/.env`

For Phases 8-11:

- manual edits are sent to the backend over WebSocket and preserved with human locks
- ending a meeting triggers final consolidation plus JSON/PDF export creation
- Supabase persistence is optional and activates when `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are set
- demo mode supports prerecorded audio playback through the same chunking pipeline

## Current Demo Flow

1. Start the backend
2. Start the frontend
3. Open `http://localhost:3000` in Chrome
4. Choose either live microphone mode or demo audio mode
5. Click `Start Meeting`
6. Allow microphone access if you are using live mode
7. Wait for transcript segments and live intelligence updates
8. Edit any summary, action item, decision, or risk if needed
9. Click `End Meeting`
10. Download the final JSON or PDF report

## What Is Implemented

- Next.js frontend scaffold with app router
- FastAPI backend scaffold with `/health` and `/ws/meeting`
- one-active-meeting session manager keyed by `meeting_id`
- typed frontend/backend WebSocket message contracts
- meeting start and end lifecycle
- browser microphone capture in 15-second chunks
- audio normalization for uploaded chunks
- faster-whisper ASR transcription with timestamped utterances
- transcript rendering in the UI
- asynchronous diarization backfill with graceful failure handling
- noise filtering for display vs LLM transcript streams
- rolling in-memory buffer tracking for the 60-second intelligence cadence
- DeepSeek-compatible intelligence extraction with local heuristic fallback when no API key is set
- trust validation for summary, action items, decisions, and risks before merge
- lock-aware manual edits for summary, action items, decisions, and risks
- meeting-end consolidation into final exportable report artifacts
- downloadable JSON and PDF report bundles in the UI
- optional Supabase persistence for meeting reports and export files
- demo-mode playback from a prerecorded local audio file

## Deployment

- Frontend deployment guidance: [docs/deployment.md](/Users/satwik/Documents/GitHub/LiveNote/docs/deployment.md)
- Supabase schema: [docs/supabase.sql](/Users/satwik/Documents/GitHub/LiveNote/docs/supabase.sql)
- Render backend manifest: [render.yaml](/Users/satwik/Documents/GitHub/LiveNote/render.yaml)
