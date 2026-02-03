"""
Autodesk Platform Services Backend
==================================
A secure Python backend for viewing CAD files using Autodesk Platform Services (APS).

Features:
- 2-legged OAuth authentication
- Secure token management (client secret never exposed to frontend)
- File upload to APS bucket storage
- Model translation to SVF format for web viewing
- View-only token endpoint for frontend viewer
"""

import os
import base64
import hashlib
import time
from typing import Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ============================================================================
# Configuration
# ============================================================================

APS_CLIENT_ID = os.getenv("APS_CLIENT_ID")
APS_CLIENT_SECRET = os.getenv("APS_CLIENT_SECRET")
BUCKET_KEY = os.getenv("APS_BUCKET_KEY", "graviton-cad-viewer-bucket")

# APS API Endpoints
APS_AUTH_URL = "https://developer.api.autodesk.com/authentication/v2/token"
APS_BUCKETS_URL = "https://developer.api.autodesk.com/oss/v2/buckets"
APS_TRANSLATE_URL = "https://developer.api.autodesk.com/modelderivative/v2/designdata/job"

# Validate configuration
if not APS_CLIENT_ID or not APS_CLIENT_SECRET:
    raise EnvironmentError(
        "Missing APS credentials! Set APS_CLIENT_ID and APS_CLIENT_SECRET environment variables."
    )

# ============================================================================
# FastAPI App Setup
# ============================================================================

app = FastAPI(
    title="Autodesk Platform Services Backend",
    description="Secure backend for CAD file viewing with APS",
    version="1.0.0"
)

# CORS configuration for mobile app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# Token Cache (In-memory, use Redis for production)
# ============================================================================

class TokenCache:
    def __init__(self):
        self._internal_token: Optional[str] = None
        self._internal_expires: float = 0
        self._public_token: Optional[str] = None
        self._public_expires: float = 0
    
    def get_internal_token(self) -> Optional[str]:
        if self._internal_token and time.time() < self._internal_expires - 60:
            return self._internal_token
        return None
    
    def set_internal_token(self, token: str, expires_in: int):
        self._internal_token = token
        self._internal_expires = time.time() + expires_in
    
    def get_public_token(self) -> Optional[str]:
        if self._public_token and time.time() < self._public_expires - 60:
            return self._public_token
        return None
    
    def set_public_token(self, token: str, expires_in: int):
        self._public_token = token
        self._public_expires = time.time() + expires_in
    
    def get_public_token_expires_in(self) -> int:
        return max(0, int(self._public_expires - time.time()))

token_cache = TokenCache()

# ============================================================================
# Pydantic Models
# ============================================================================

class TokenResponse(BaseModel):
    access_token: str
    expires_in: int

class UploadResponse(BaseModel):
    urn: str
    object_id: str
    object_key: str
    bucket_key: str
    message: str

class TranslationStatusResponse(BaseModel):
    urn: str
    status: str
    progress: str
    messages: list = []

# ============================================================================
# Helper Functions
# ============================================================================

def get_internal_token() -> str:
    """
    Get an internal 2-legged access token for server-side operations.
    Scopes: bucket:create, bucket:read, data:read, data:write, data:create
    """
    # Check cache first
    cached = token_cache.get_internal_token()
    if cached:
        return cached
    
    # Request new token
    response = requests.post(
        APS_AUTH_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_id": APS_CLIENT_ID,
            "client_secret": APS_CLIENT_SECRET,
            "grant_type": "client_credentials",
            "scope": "bucket:create bucket:read data:read data:write data:create"
        }
    )
    
    if response.status_code != 200:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get internal token: {response.text}"
        )
    
    data = response.json()
    token = data["access_token"]
    expires_in = data.get("expires_in", 3600)
    
    # Cache the token
    token_cache.set_internal_token(token, expires_in)
    
    return token


def get_public_token() -> tuple[str, int]:
    """
    Get a public view-only access token for frontend viewer.
    Scope: viewables:read (read-only, safe to expose to client)
    """
    # Check cache first
    cached = token_cache.get_public_token()
    if cached:
        return cached, token_cache.get_public_token_expires_in()
    
    # Request new token
    response = requests.post(
        APS_AUTH_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_id": APS_CLIENT_ID,
            "client_secret": APS_CLIENT_SECRET,
            "grant_type": "client_credentials",
            "scope": "viewables:read"
        }
    )
    
    if response.status_code != 200:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get public token: {response.text}"
        )
    
    data = response.json()
    token = data["access_token"]
    expires_in = data.get("expires_in", 3600)
    
    # Cache the token
    token_cache.set_public_token(token, expires_in)
    
    return token, expires_in


def ensure_bucket_exists(access_token: str) -> bool:
    """
    Check if the bucket exists, create it if not.
    """
    # First, try to get the bucket
    bucket_url = f"{APS_BUCKETS_URL}/{BUCKET_KEY}/details"
    response = requests.get(
        bucket_url,
        headers={"Authorization": f"Bearer {access_token}"}
    )
    
    if response.status_code == 200:
        return True  # Bucket exists
    
    if response.status_code == 404:
        # Create the bucket
        create_response = requests.post(
            APS_BUCKETS_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            },
            json={
                "bucketKey": BUCKET_KEY,
                "policyKey": "transient"  # Files deleted after 24 hours
            }
        )
        
        if create_response.status_code in [200, 409]:  # 409 = already exists (race condition)
            return True
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create bucket: {create_response.text}"
            )
    
    raise HTTPException(
        status_code=500,
        detail=f"Failed to check bucket: {response.text}"
    )


def upload_file_to_bucket(access_token: str, file_content: bytes, filename: str) -> dict:
    """
    Upload a file to the APS bucket using the new signed URL upload method.
    This replaces the deprecated direct PUT to /oss/v2/buckets/.../objects/...
    """
    # Generate a unique object key
    timestamp = int(time.time())
    file_hash = hashlib.md5(file_content[:1024]).hexdigest()[:8]
    object_key = f"{timestamp}_{file_hash}_{filename}"
    
    # Step 1: Get a signed upload URL
    signeds3_url = f"https://developer.api.autodesk.com/oss/v2/buckets/{BUCKET_KEY}/objects/{object_key}/signeds3upload"
    
    sign_response = requests.get(
        signeds3_url,
        headers={"Authorization": f"Bearer {access_token}"},
        params={"minutesExpiration": 60}
    )
    
    if sign_response.status_code != 200:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get upload URL: {sign_response.text}"
        )
    
    sign_data = sign_response.json()
    upload_url = sign_data.get("urls", [None])[0]
    upload_key = sign_data.get("uploadKey")
    
    if not upload_url:
        raise HTTPException(
            status_code=500,
            detail="Failed to get signed upload URL from response"
        )
    
    # Step 2: Upload file directly to S3 using the signed URL
    upload_response = requests.put(
        upload_url,
        headers={"Content-Type": "application/octet-stream"},
        data=file_content
    )
    
    if upload_response.status_code not in [200, 201]:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload file to S3: {upload_response.status_code}"
        )
    
    # Step 3: Complete the upload by notifying APS
    complete_url = f"https://developer.api.autodesk.com/oss/v2/buckets/{BUCKET_KEY}/objects/{object_key}/signeds3upload"
    
    complete_response = requests.post(
        complete_url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        },
        json={"uploadKey": upload_key}
    )
    
    if complete_response.status_code not in [200, 201]:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to complete upload: {complete_response.text}"
        )
    
    return complete_response.json()


def start_translation(access_token: str, object_id: str, output_format: str = "svf2") -> dict:
    """
    Start the translation job to convert the file to SVF/SVF2 format.
    SVF2 is recommended for better performance.
    """
    # Base64 encode the object ID (required by APS)
    urn = base64.urlsafe_b64encode(object_id.encode()).decode().rstrip("=")
    
    job_payload = {
        "input": {
            "urn": urn
        },
        "output": {
            "formats": [
                {
                    "type": output_format,
                    "views": ["2d", "3d"]
                }
            ]
        }
    }
    
    response = requests.post(
        APS_TRANSLATE_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "x-ads-force": "true"  # Force re-translation if needed
        },
        json=job_payload
    )
    
    if response.status_code not in [200, 201]:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start translation: {response.text}"
        )
    
    return {"urn": urn, **response.json()}


def get_translation_status(access_token: str, urn: str) -> dict:
    """
    Get the status of a translation job.
    """
    status_url = f"https://developer.api.autodesk.com/modelderivative/v2/designdata/{urn}/manifest"
    
    response = requests.get(
        status_url,
        headers={"Authorization": f"Bearer {access_token}"}
    )
    
    if response.status_code != 200:
        if response.status_code == 404:
            return {"status": "pending", "progress": "0%"}
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get translation status: {response.text}"
        )
    
    data = response.json()
    return {
        "status": data.get("status", "unknown"),
        "progress": data.get("progress", "0%"),
        "messages": data.get("derivatives", [])
    }


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "APS CAD Viewer Backend"}


@app.get("/api/get_public_token", response_model=TokenResponse)
async def api_get_public_token():
    """
    Get a view-only token for the frontend viewer.
    This token can only read viewables and cannot modify any data.
    Safe to use in client-side code.
    """
    token, expires_in = get_public_token()
    return TokenResponse(access_token=token, expires_in=expires_in)


@app.post("/api/upload_model", response_model=UploadResponse)
async def api_upload_model(file: UploadFile = File(...)):
    """
    Upload a CAD model and start the translation process.
    
    Supported formats: .dwg, .dxf, .sldprt, .sldasm, .step, .stp, .iges, .igs, .stl, .obj, .fbx, etc.
    
    Returns the URN which can be used to load the model in the viewer.
    """
    # Validate file extension
    allowed_extensions = {
        # AutoCAD
        ".dwg", ".dxf",
        # SolidWorks
        ".sldprt", ".sldasm", ".slddrw",
        # Neutral formats
        ".step", ".stp", ".iges", ".igs", ".stl", ".obj", ".fbx", ".3ds",
        # ACIS
        ".sat", ".sab",
        # Parasolid
        ".x_t", ".x_b", ".xt", ".xmt_txt", ".xmt_bin",
        # Solid Edge
        ".par", ".psm", ".asm", ".pwd",
        # Autodesk Inventor
        ".ipt", ".iam", ".idw", ".dwf", ".dwfx",
        # PTC Creo / Pro/E
        ".prt", ".asm", ".drw", ".neu",
        # CATIA
        ".catpart", ".catproduct", ".catdrawing", ".cgr",
        # Revit / Navisworks
        ".rvt", ".rfa", ".nwd", ".nwc",
        # NX / Unigraphics
        ".prt",
        # JT
        ".jt",
        # 3D PDF
        ".pdf",
        # Other
        ".3dm", ".skp", ".dae", ".gltf", ".glb"
    }

    
    filename = file.filename.lower()
    extension = os.path.splitext(filename)[1]
    
    if extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format: {extension}. Supported: {', '.join(allowed_extensions)}"
        )
    
    # Get internal token
    access_token = get_internal_token()
    
    # Ensure bucket exists
    ensure_bucket_exists(access_token)
    
    # Read file content
    file_content = await file.read()
    
    if len(file_content) == 0:
        raise HTTPException(status_code=400, detail="Empty file uploaded")
    
    # Upload to bucket
    upload_result = upload_file_to_bucket(access_token, file_content, file.filename)
    object_id = upload_result.get("objectId")
    
    if not object_id:
        raise HTTPException(status_code=500, detail="Failed to get object ID from upload")
    
    # Start translation
    translation_result = start_translation(access_token, object_id)
    urn = translation_result.get("urn")
    
    return UploadResponse(
        urn=urn,
        object_id=object_id,
        object_key=upload_result.get("objectKey", ""),
        bucket_key=BUCKET_KEY,
        message="File uploaded and translation started. Use the URN to check status or load the model."
    )


@app.get("/api/translation_status/{urn}", response_model=TranslationStatusResponse)
async def api_translation_status(urn: str):
    """
    Check the translation status of an uploaded model.
    Possible statuses: pending, inprogress, success, failed, timeout
    """
    access_token = get_internal_token()
    status = get_translation_status(access_token, urn)
    
    return TranslationStatusResponse(
        urn=urn,
        status=status.get("status", "unknown"),
        progress=status.get("progress", "0%"),
        messages=status.get("messages", [])
    )


@app.get("/api/models")
async def api_list_models():
    """
    List all models in the bucket.
    """
    access_token = get_internal_token()
    
    objects_url = f"{APS_BUCKETS_URL}/{BUCKET_KEY}/objects"
    response = requests.get(
        objects_url,
        headers={"Authorization": f"Bearer {access_token}"}
    )
    
    if response.status_code != 200:
        if response.status_code == 404:
            return {"models": []}
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list models: {response.text}"
        )
    
    data = response.json()
    models = []
    
    for item in data.get("items", []):
        object_id = item.get("objectId", "")
        urn = base64.urlsafe_b64encode(object_id.encode()).decode().rstrip("=")
        models.append({
            "name": item.get("objectKey", ""),
            "urn": urn,
            "size": item.get("size", 0),
            "sha1": item.get("sha1", "")
        })
    
    return {"models": models}


@app.delete("/api/models/{object_key}")
async def api_delete_model(object_key: str):
    """
    Delete a model from the bucket.
    """
    access_token = get_internal_token()
    
    delete_url = f"{APS_BUCKETS_URL}/{BUCKET_KEY}/objects/{object_key}"
    response = requests.delete(
        delete_url,
        headers={"Authorization": f"Bearer {access_token}"}
    )
    
    if response.status_code not in [200, 204]:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete model: {response.text}"
        )
    
    return {"message": f"Model {object_key} deleted successfully"}


# Serve static files (for the viewer HTML)
# Create a static directory for the frontend
@app.get("/viewer")
async def serve_viewer():
    """Serve the viewer HTML page."""
    return FileResponse("static/index.html")


# ============================================================================
# Run the app
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
