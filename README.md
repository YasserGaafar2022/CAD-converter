# Autodesk Platform Services Backend

A secure Python backend for viewing CAD files using Autodesk Platform Services (formerly Forge).

## Features

- 🔐 **Secure 2-legged OAuth** - Client secrets never exposed to frontend
- 📤 **File Upload** - Upload CAD files to APS bucket storage
- 🔄 **Model Translation** - Automatic conversion to SVF2 format
- 👁️ **3D Viewer** - Interactive Autodesk viewer with dark theme
- 📱 **Mobile Ready** - CORS enabled for mobile app integration

## Supported CAD Formats

- **SolidWorks**: .sldprt, .sldasm
- **AutoCAD**: .dwg, .dxf
- **Neutral**: .step, .stp, .iges, .igs, .stl, .obj
- **Autodesk Inventor**: .ipt, .iam
- **Revit**: .rvt, .rfa
- **Navisworks**: .nwd, .nwc
- **CATIA**: .catpart, .catproduct
- And more...

## Setup

### 1. Get APS Credentials

1. Go to [Autodesk Platform Services](https://aps.autodesk.com/)
2. Create a new application
3. Copy the **Client ID** and **Client Secret**

### 2. Configure Environment

```bash
# Copy the example environment file
copy .env.example .env

# Edit .env with your credentials
notepad .env
```

### 3. Install Dependencies

```bash
# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Install packages
pip install -r requirements.txt
```

### 4. Run the Server

```bash
# Development mode
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Or run directly
python main.py
```

### 5. Access the Viewer

Open <http://localhost:8000/viewer> in your browser.

## API Endpoints

### Authentication

```
GET /api/get_public_token
```

Returns a view-only token for the frontend viewer.

**Response:**

```json
{
  "access_token": "eyJ...",
  "expires_in": 3600
}
```

### Upload Model

```
POST /api/upload_model
Content-Type: multipart/form-data
```

Upload a CAD file and start translation.

**Request:**

- `file`: CAD file (multipart)

**Response:**

```json
{
  "urn": "dXJuOmFkc2s...",
  "object_id": "urn:adsk.objects:...",
  "object_key": "1234567_abcd_model.sldprt",
  "bucket_key": "graviton-cad-viewer-bucket",
  "message": "File uploaded and translation started..."
}
```

### Translation Status

```
GET /api/translation_status/{urn}
```

Check if model is ready for viewing.

**Response:**

```json
{
  "urn": "dXJuOmFkc2s...",
  "status": "success",
  "progress": "100%",
  "messages": []
}
```

### List Models

```
GET /api/models
```

List all uploaded models in the bucket.

### Delete Model

```
DELETE /api/models/{object_key}
```

Delete a model from the bucket.

## Mobile Integration

### React Native / Capacitor

```javascript
// Get token for viewer
const response = await fetch('https://your-backend.com/api/get_public_token');
const { access_token } = await response.json();

// Upload file
const formData = new FormData();
formData.append('file', fileBlob);

const uploadResponse = await fetch('https://your-backend.com/api/upload_model', {
  method: 'POST',
  body: formData
});

const { urn } = await uploadResponse.json();

// Open viewer with URN
webView.loadUrl(`https://your-backend.com/viewer?urn=${urn}`);
```

## Production Deployment

### Environment Variables

Set these in your production environment:

```
APS_CLIENT_ID=xxx
APS_CLIENT_SECRET=xxx
APS_BUCKET_KEY=your-unique-bucket-name
```

### Recommendations

1. **Use Redis** for token caching instead of in-memory
2. **Enable HTTPS** with proper SSL certificates
3. **Restrict CORS** to your mobile app's origin
4. **Set bucket policy** to `persistent` for permanent storage

## Architecture

```
┌────────────────┐     ┌─────────────────┐     ┌──────────────────┐
│  Mobile App    │────▶│ Python Backend  │────▶│ Autodesk APS API │
│                │     │   (FastAPI)     │     │                  │
│ - Upload files │     │ - OAuth tokens  │     │ - Bucket storage │
│ - View models  │     │ - File upload   │     │ - Translation    │
│                │     │ - Translation   │     │ - Viewer data    │
└────────────────┘     └─────────────────┘     └──────────────────┘
```

## License

MIT
