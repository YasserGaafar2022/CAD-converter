"""
FastAPI CAD Conversion Backend
Converts STEP/IGES files to JSON mesh data for web viewing
"""
import os
import logging
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .models import ConversionResponse, ErrorResponse
from .converter import convert_cad_file

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="CAD Conversion API",
    description="Convert STEP/IGES files to JSON mesh data",
    version="1.0.0"
)

# CORS - Allow all origins for mobile app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supported file extensions
SUPPORTED_EXTENSIONS = {'.step', '.stp', '.iges', '.igs'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "CAD Conversion API",
        "version": "1.0.0",
        "supported_formats": list(SUPPORTED_EXTENSIONS)
    }


@app.get("/health")
async def health_check():
    """Health check for deployment platforms"""
    return {"status": "healthy"}


@app.post("/convert", response_model=ConversionResponse)
async def convert_file(file: UploadFile = File(...)):
    """
    Convert a CAD file to JSON mesh data
    
    Accepts STEP (.step, .stp) and IGES (.iges, .igs) files.
    Returns mesh data as JSON with vertices, normals, and indices.
    """
    # Validate file extension
    file_name = file.filename or "unknown.step"
    ext = os.path.splitext(file_name.lower())[1]
    
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format: {ext}. Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
        )
    
    # Read file content
    try:
        content = await file.read()
        
        # Check file size
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)} MB"
            )
        
        if len(content) == 0:
            raise HTTPException(
                status_code=400,
                detail="Empty file received"
            )
            
    except Exception as e:
        logger.error(f"Failed to read file: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")
    
    # Convert the file
    try:
        logger.info(f"Converting file: {file_name} ({len(content)} bytes)")
        
        meshes, metadata = convert_cad_file(content, file_name)
        
        logger.info(f"Conversion successful: {metadata.partCount} parts, {metadata.vertexCount} vertices")
        
        return ConversionResponse(
            success=True,
            meshes=meshes,
            metadata=metadata
        )
        
    except ValueError as e:
        # Format/validation errors
        logger.warning(f"Conversion validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
        
    except RuntimeError as e:
        # Processing errors
        logger.error(f"Conversion runtime error: {e}")
        raise HTTPException(status_code=422, detail=str(e))
        
    except Exception as e:
        # Unexpected errors
        logger.exception(f"Unexpected conversion error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Conversion failed: {str(e)}"
        )


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom error response format"""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            success=False,
            error=exc.detail,
            detail=str(exc.detail)
        ).model_dump()
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
