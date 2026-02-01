"""
Pydantic models for API request/response
"""
from pydantic import BaseModel
from typing import List, Optional


class MeshData(BaseModel):
    """Single mesh/part data"""
    name: str
    vertices: List[float]  # Flat array: [x1,y1,z1, x2,y2,z2, ...]
    normals: List[float]   # Flat array: [nx1,ny1,nz1, ...]
    indices: List[int]     # Triangle indices
    color: List[float]     # RGB [r, g, b] 0-1 range


class ConversionMetadata(BaseModel):
    """Metadata about the conversion"""
    partCount: int
    vertexCount: int
    faceCount: int
    format: str
    fileName: str


class ConversionResponse(BaseModel):
    """Response from /convert endpoint"""
    success: bool
    meshes: List[MeshData]
    metadata: ConversionMetadata
    error: Optional[str] = None


class ErrorResponse(BaseModel):
    """Error response"""
    success: bool = False
    error: str
    detail: Optional[str] = None
