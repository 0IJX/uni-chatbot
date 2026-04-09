# UNI Chatbot

This is a ready template for a local AI chatbot.
You can copy this project and make your own version.

It is simple:
- backend API
- frontend website
- local AI model with Ollama
- file upload
- link ingestion
- chat history

## What this app can do
- answer from your own files
- answer from your catalog folder
- stream chat replies
- ingest normal links
- ingest Google Sheets links
- keep conversation history
- let you clear files and chats from settings

## Project folders
- `backend/` API and core logic
- `frontend/` website
- `scripts/` start stop reset clean scripts

## What you need first
Install these on your computer:
- Python 3.11 or 3.12
- Node.js 18+
- Ollama

## Setup step by step

### 1) Open project folder
If you copied this project as zip, extract it first and open the folder.

### 2) Create env files
Run:
```powershell
Copy-Item backend/.env.example backend/.env
Copy-Item frontend/.env.example frontend/.env
```

### 3) Edit backend env
Open `backend/.env` and change these:
- `APP_NAME=Your-App-Name`
- `ADMIN_PASSWORD=your_strong_password`
- `CORS_ALLOW_ORIGINS=http://your-frontend-domain`
- `OLLAMA_BASE_URL=http://localhost:11434` (or your real Ollama url)

### 4) Install AI models
```powershell
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
```

### 5) Install backend packages
```powershell
python -m venv .venv312
.\.venv312\Scripts\Activate.ps1
pip install -r backend/requirements.txt
```

### 6) Install frontend packages
```powershell
cd frontend
npm install
cd ..
```

### 7) Start app
```powershell
./start
```

Open this in browser:
- `http://127.0.0.1:5173`

## Commands
- `./start` start backend and frontend
- `./status` show if app is running
- `./stop` stop app
- `./reset` clear runtime data, keep catalog folder
- `./clean` reset plus extra cleanup

## Add your own data
Put your files in:
- `backend/data/catalog/`

You can add PDF or other supported files.
Then restart app.

## Google Sheets support
In settings page, paste a Google Sheets link.

It supports:
- public links
- private links (only if backend credentials are set)

Private mode env keys:
- `GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE`
- `GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON`
- `GOOGLE_SHEETS_API_TIMEOUT_SECONDS`

If credentials are missing for private sheet, app shows a clear error.

## Main API routes
- `GET /api/health`
- `POST /api/chat`
- `POST /api/chat/stream`
- `POST /api/upload`
- `POST /api/upload-url`
- `GET /api/conversations`
- `POST /api/conversations`
- `DELETE /api/conversations?conversation_id=...`
- `DELETE /api/sources?source_id=...`
- `POST /api/settings/actions`

## Test commands
```powershell
.\.venv312\Scripts\Activate.ps1
pytest backend/tests -vv
cd frontend
npm run build
cd ..
```

## Make it fully yours
Change these:
- app title text in frontend
- logo in `frontend/public/`
- env values in `backend/.env`
- README name and text

Now it is your own chatbot project.
