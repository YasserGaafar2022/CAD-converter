"""
CAD File Converter
Converts STEP/IGES files to mesh data using trimesh
Falls back to basic parsing for unsupported formats
"""
import os
import tempfile
from typing import List, Tuple
import numpy as np

from .models import MeshData, ConversionMetadata

# Try to import trimesh (may have limited STEP support)
try:
    import trimesh
    HAS_TRIMESH = True
except ImportError:
    HAS_TRIMESH = False


class CADConverter:
    """
    Converts CAD files to mesh data
    Uses trimesh for basic geometry processing
    """
    
    def convert_file(self, file_path: str, file_name: str) -> Tuple[List[MeshData], ConversionMetadata]:
        """
        Convert a CAD file to mesh data
        """
        ext = os.path.splitext(file_name.lower())[1]
        
        if ext in ['.stl', '.obj', '.ply', '.off', '.glb', '.gltf']:
            # Trimesh handles these natively
            return self._convert_with_trimesh(file_path, file_name, ext)
        elif ext in ['.step', '.stp', '.iges', '.igs']:
            # Try trimesh, may work for some files
            try:
                return self._convert_with_trimesh(file_path, file_name, ext)
            except Exception as e:
                raise ValueError(
                    f"Could not convert {ext} file. "
                    f"STEP/IGES support requires additional dependencies. "
                    f"Error: {str(e)}"
                )
        else:
            raise ValueError(f"Unsupported format: {ext}")
    
    def _convert_with_trimesh(self, file_path: str, file_name: str, ext: str) -> Tuple[List[MeshData], ConversionMetadata]:
        """Convert using trimesh library"""
        if not HAS_TRIMESH:
            raise RuntimeError("Trimesh not available")
        
        # Load the mesh
        mesh = trimesh.load(file_path, force='mesh')
        
        # Handle scene vs single mesh
        if isinstance(mesh, trimesh.Scene):
            meshes = []
            for name, geometry in mesh.geometry.items():
                if isinstance(geometry, trimesh.Trimesh):
                    mesh_data = self._trimesh_to_mesh_data(geometry, name)
                    meshes.append(mesh_data)
        else:
            meshes = [self._trimesh_to_mesh_data(mesh, "Model")]
        
        if not meshes:
            raise ValueError("No valid geometry found in file")
        
        # Calculate totals
        total_vertices = sum(len(m.vertices) // 3 for m in meshes)
        total_faces = sum(len(m.indices) // 3 for m in meshes)
        
        format_name = ext.upper().replace('.', '')
        
        metadata = ConversionMetadata(
            partCount=len(meshes),
            vertexCount=total_vertices,
            faceCount=total_faces,
            format=format_name,
            fileName=file_name
        )
        
        return meshes, metadata
    
    def _trimesh_to_mesh_data(self, mesh: 'trimesh.Trimesh', name: str) -> MeshData:
        """Convert trimesh object to MeshData"""
        # Get vertices as flat list
        vertices = mesh.vertices.flatten().tolist()
        
        # Get normals
        if mesh.vertex_normals is not None:
            normals = mesh.vertex_normals.flatten().tolist()
        else:
            normals = [0.0, 0.0, 1.0] * (len(vertices) // 3)
        
        # Get indices
        indices = mesh.faces.flatten().tolist()
        
        return MeshData(
            name=name,
            vertices=vertices,
            normals=normals,
            indices=indices,
            color=[0.7, 0.7, 0.75]  # Light gray
        )


def convert_cad_file(file_content: bytes, file_name: str) -> Tuple[List[MeshData], ConversionMetadata]:
    """
    Convenience function to convert CAD file from bytes
    """
    ext = os.path.splitext(file_name)[1]
    
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(file_content)
        tmp_path = tmp.name
    
    try:
        converter = CADConverter()
        return converter.convert_file(tmp_path, file_name)
    finally:
        os.unlink(tmp_path)
