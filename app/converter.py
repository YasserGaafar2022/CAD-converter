"""
CAD File Converter
Converts STEP/IGES files to mesh data using OCP (OpenCASCADE Python bindings)
"""
import os
import tempfile
from typing import List, Tuple, Optional
import numpy as np

# Import OCP (OpenCASCADE for Python)
from OCP.STEPControl import STEPControl_Reader
from OCP.IGESControl import IGESControl_Reader
from OCP.IFSelect import IFSelect_RetDone
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE
from OCP.BRep import BRep_Tool
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import topods_Face
from OCP.Poly import Poly_Triangulation
from OCP.gp import gp_Pnt
from OCP.Quantity import Quantity_Color, Quantity_TOC_RGB

from .models import MeshData, ConversionMetadata


class CADConverter:
    """
    Converts CAD files (STEP, IGES) to mesh data
    """
    
    def __init__(self, linear_deflection: float = 0.1, angular_deflection: float = 0.5):
        """
        Initialize converter with mesh quality settings
        
        Args:
            linear_deflection: Max distance from curve to mesh (smaller = finer)
            angular_deflection: Max angle between adjacent triangles
        """
        self.linear_deflection = linear_deflection
        self.angular_deflection = angular_deflection
    
    def convert_file(self, file_path: str, file_name: str) -> Tuple[List[MeshData], ConversionMetadata]:
        """
        Convert a CAD file to mesh data
        
        Args:
            file_path: Path to the CAD file
            file_name: Original file name (for format detection)
            
        Returns:
            Tuple of (list of mesh data, metadata)
        """
        # Determine format
        ext = os.path.splitext(file_name.lower())[1]
        
        if ext in ['.step', '.stp']:
            shape = self._read_step(file_path)
            format_name = 'STEP'
        elif ext in ['.iges', '.igs']:
            shape = self._read_iges(file_path)
            format_name = 'IGES'
        else:
            raise ValueError(f"Unsupported format: {ext}")
        
        # Mesh the shape
        mesh = BRepMesh_IncrementalMesh(
            shape, 
            self.linear_deflection, 
            False, 
            self.angular_deflection, 
            True
        )
        mesh.Perform()
        
        if not mesh.IsDone():
            raise RuntimeError("Failed to mesh the shape")
        
        # Extract mesh data from all faces
        meshes = self._extract_meshes(shape)
        
        # Calculate totals
        total_vertices = sum(len(m.vertices) // 3 for m in meshes)
        total_faces = sum(len(m.indices) // 3 for m in meshes)
        
        metadata = ConversionMetadata(
            partCount=len(meshes),
            vertexCount=total_vertices,
            faceCount=total_faces,
            format=format_name,
            fileName=file_name
        )
        
        return meshes, metadata
    
    def _read_step(self, file_path: str):
        """Read STEP file and return TopoDS_Shape"""
        reader = STEPControl_Reader()
        status = reader.ReadFile(file_path)
        
        if status != IFSelect_RetDone:
            raise RuntimeError(f"Failed to read STEP file: status {status}")
        
        reader.TransferRoots()
        return reader.OneShape()
    
    def _read_iges(self, file_path: str):
        """Read IGES file and return TopoDS_Shape"""
        reader = IGESControl_Reader()
        status = reader.ReadFile(file_path)
        
        if status != IFSelect_RetDone:
            raise RuntimeError(f"Failed to read IGES file: status {status}")
        
        reader.TransferRoots()
        return reader.OneShape()
    
    def _extract_meshes(self, shape) -> List[MeshData]:
        """Extract mesh data from all faces of a shape"""
        meshes = []
        part_index = 0
        
        # Explore all faces
        explorer = TopExp_Explorer(shape, TopAbs_FACE)
        
        # Collect all face data first, then combine into larger meshes
        all_vertices = []
        all_normals = []
        all_indices = []
        vertex_offset = 0
        
        while explorer.More():
            face = topods_Face(explorer.Current())
            location = TopLoc_Location()
            
            # Get triangulation
            triangulation = BRep_Tool.Triangulation_s(face, location)
            
            if triangulation is not None:
                # Get transformation
                transform = location.Transformation()
                
                # Get nodes (vertices)
                nb_nodes = triangulation.NbNodes()
                nb_triangles = triangulation.NbTriangles()
                
                # Extract vertices
                for i in range(1, nb_nodes + 1):
                    node = triangulation.Node(i)
                    # Apply transformation
                    transformed = node.Transformed(transform)
                    all_vertices.extend([transformed.X(), transformed.Y(), transformed.Z()])
                
                # Extract normals (compute from triangles if not available)
                if triangulation.HasNormals():
                    for i in range(1, nb_nodes + 1):
                        normal = triangulation.Normal(i)
                        all_normals.extend([normal.X(), normal.Y(), normal.Z()])
                else:
                    # Simple placeholder normals (will compute properly later)
                    for _ in range(nb_nodes):
                        all_normals.extend([0.0, 0.0, 1.0])
                
                # Extract triangles (indices)
                for i in range(1, nb_triangles + 1):
                    tri = triangulation.Triangle(i)
                    n1, n2, n3 = tri.Get()
                    # Convert from 1-indexed to 0-indexed and add offset
                    all_indices.extend([
                        n1 - 1 + vertex_offset,
                        n2 - 1 + vertex_offset,
                        n3 - 1 + vertex_offset
                    ])
                
                vertex_offset += nb_nodes
            
            explorer.Next()
        
        # Create single combined mesh
        if all_vertices:
            mesh = MeshData(
                name=f"Model",
                vertices=all_vertices,
                normals=all_normals,
                indices=all_indices,
                color=[0.7, 0.7, 0.75]  # Light gray/silver
            )
            meshes.append(mesh)
        
        return meshes


def convert_cad_file(file_content: bytes, file_name: str) -> Tuple[List[MeshData], ConversionMetadata]:
    """
    Convenience function to convert CAD file from bytes
    
    Args:
        file_content: File content as bytes
        file_name: Original file name
        
    Returns:
        Tuple of (list of mesh data, metadata)
    """
    # Write to temp file
    ext = os.path.splitext(file_name)[1]
    
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(file_content)
        tmp_path = tmp.name
    
    try:
        converter = CADConverter()
        return converter.convert_file(tmp_path, file_name)
    finally:
        # Clean up temp file
        os.unlink(tmp_path)
