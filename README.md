# Python CAD Conversion Backend

A FastAPI backend for converting CAD files (STEP, IGES) to JSON mesh data.

## Setup

```bash
pip install -r requirements.txt
```

## Run locally

```bash
uvicorn app.main:app --reload --port 8000
```

## Docker

```bash
docker build -t cad-backend .
docker run -p 8000:8000 cad-backend
```

## API

### POST /convert

Upload a CAD file (STEP, IGES, STP, IGS) and get JSON mesh data back.

**Request:**

- Method: POST
- Content-Type: multipart/form-data
- Body: `file` (the CAD file)

**Response:**

```json
{
  "success": true,
  "meshes": [...],
  "metadata": {...}
}
```

## Deploy to Render

1. Push to GitHub
2. Connect repo to Render.com
3. Deploy as Web Service (Docker)
