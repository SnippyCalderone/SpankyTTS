# Spanky TTS Backend

Minimal FastAPI backend that provides:
- `GET /health`
- `POST /tts` (OpenAI `gpt-4o-mini-tts`, raw PCM output)

## Setup (Windows PowerShell)

From repository root:

Create virtual environment:

```powershell
python -m venv backend\.venv
```

Activate:

```powershell
backend\.venv\Scripts\Activate.ps1
```

Install:

```powershell
pip install -r backend\requirements.txt
```

Create local environment file:

```powershell
Copy-Item backend\.env.example backend\.env
```

Then edit `backend\.env` and set your real `OPENAI_API_KEY`.

`backend\.env` is ignored by Git and must never be committed.

## Run Development Server (LAN)

```powershell
uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

## Health Check

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected response:

```json
{
  "status": "ok",
  "service": "spanky-tts-backend"
}
```

## TTS Request Example (save raw PCM)

Use PowerShell to post JSON and write raw bytes directly to file:

```powershell
$body = @{
  text = "Hello from Spanky backend"
  voice = "cedar"
  instructions = "Read naturally as a professional audiobook narrator."
} | ConvertTo-Json

Invoke-WebRequest -Method Post `
  -Uri "http://127.0.0.1:8000/tts" `
  -ContentType "application/json" `
  -Body $body `
  -OutFile "backend\test_output.pcm"
```

Alternative curl example:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/tts" -H "Content-Type: application/json" --data-raw "{\"text\":\"Hello from Spanky backend\",\"voice\":\"cedar\",\"instructions\":\"Read naturally as a professional audiobook narrator.\"}" --output "backend\test_output.pcm"
```

The output file contains raw PCM (`s16le`, mono, 24000 Hz) with no WAV header.

For Phase 2B.2A, `/tts` also accepts optional `previous_context` and
`following_context` strings of at most 240 characters each. The backend uses
them only in narration instructions. Only `text` is sent to OpenAI as speech
input, including any leading or trailing whitespace. Requests without context
retain the Phase 2B.1 behavior. Context-aware playback has been physically
checked on the BOOX; it improves some fragments but still has audible resets
between independently generated requests.

Optional playback with ffplay (if installed):

```powershell
ffplay -f s16le -ar 24000 -ac 1 backend\test_output.pcm
```

`ffplay` is optional and not required for backend operation.
