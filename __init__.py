# -*- coding: utf-8 -*-
"""
Blender to Meta Horizon Exporter - Blender Add-on for Meta Horizon Worlds

This add-on provides material analysis and export tools specifically designed 
for Meta Horizon Worlds asset creation. It analyzes materials for naming 
convention compliance and provides recommendations based on the official 
Meta Horizon Worlds documentation.

Features:
- Material analysis with shader type detection
- Naming convention validation (removes invalid characters: - . , / * $ &)
- Intelligent suffix recommendations based on material properties
- Support for all Meta Horizon material types:
  * Base PBR, Metal PBR, Transparent, Unlit, Blend, Masked
  * Vertex Color materials (_VXC, _VXM)
  * UI Optimized materials (_UIO)
- Glass BSDF to Principled BSDF conversion for Meta Horizon compatibility
- Empty material handling and setup assistance
- Mesh analysis with polygon/vertex counts, modifiers, and UV channel information
- Geometry modifier application and Smart UV Project workflow for optimal asset preparation
- Ultimate Export Wizard for guided workflow
"""

import bpy
from bpy.props import (StringProperty, BoolProperty, EnumProperty, 
                      IntProperty, FloatProperty, CollectionProperty)
from bpy.types import PropertyGroup, Operator, Panel
import bmesh
import os
import time
import math
from collections import defaultdict
from mathutils import Vector

bl_info = {
    "name": "Blender to Meta Horizon Exporter",
    "author": "SimLabs101",
    "version": (1, 0, 0),
    "blender": (4, 4, 0),
    "location": "View3D > N-Panel > Horizon Worlds",
    "description": "Export tools and material analysis for Meta Horizon Worlds with guided workflow wizard",
    "warning": "",
    "doc_url": "",
    "category": "Import-Export",
}

# === UTILITY FUNCTIONS ===

def collect_children_objects(obj, all_objects=None):
    """Utility function to recursively collect an object and all its children"""
    if all_objects is None:
        all_objects = set()
    all_objects.add(obj)
    for child in obj.children:
        collect_children_objects(child, all_objects)
    return all_objects

# === WIZARD STATE MANAGEMENT ===

class HorizonExportWizardState(PropertyGroup):
    """Property group for storing export wizard state and progress"""
    
    # Wizard progress
    current_step: IntProperty(
        name="Current Step",
        description="Current step in the export wizard",
        default=0,
        min=0
    )
    
    total_steps: IntProperty(
        name="Total Steps",
        description="Total number of steps in the wizard",
        default=6
    )
    
    # Step completion status
    step_analysis_complete: BoolProperty(name="Analysis Complete", default=False)
    step_materials_complete: BoolProperty(name="Materials Complete", default=False)
    step_meshes_complete: BoolProperty(name="Meshes Complete", default=False)
    step_uvs_complete: BoolProperty(name="UVs Complete", default=False)
    step_baking_complete: BoolProperty(name="Baking Complete", default=False)
    step_export_complete: BoolProperty(name="Export Complete", default=False)
    
    # Analysis results summary
    total_objects: IntProperty(name="Total Objects", default=0)
    mesh_objects: IntProperty(name="Mesh Objects", default=0)
    materials_with_issues: IntProperty(name="Materials With Issues", default=0)
    objects_with_modifiers: IntProperty(name="Objects With Modifiers", default=0)
    objects_needing_uvs: IntProperty(name="Objects Needing UVs", default=0)
    materials_for_baking: IntProperty(name="Materials For Baking", default=0)
    
    # Original selection preservation for export
    original_selected_objects: StringProperty(
        name="Original Selected Objects",
        description="Comma-separated list of originally selected object names",
        default=""
    )
    
    original_active_object: StringProperty(
        name="Original Active Object",
        description="Name of the originally active object",
        default=""
    )
    
    export_selected_only: BoolProperty(
        name="Export Selected Only",
        description="Whether to export only the originally selected objects",
        default=False
    )
    
    # User preferences for wizard
    auto_fix_materials: BoolProperty(
        name="Auto-fix Materials",
        description="Automatically apply recommended naming and fixes",
        default=True
    )
    
    auto_apply_modifiers: BoolProperty(
        name="Auto-apply Modifiers",
        description="Automatically apply geometry-adding modifiers",
        default=True
    )
    
    auto_unwrap_uvs: BoolProperty(
        name="Auto-unwrap UVs",
        description="Automatically unwrap UVs for objects that need it",
        default=True
    )
    
    bake_textures: BoolProperty(
        name="Bake Textures",
        description="Bake textures for materials",
        default=True
    )
    
    # Export settings - Meta Horizon Worlds only accepts FBX
    export_format: EnumProperty(
        name="Export Format",
        description="Export format for Meta Horizon Worlds",
        items=[
            ('FBX', "FBX", "Export as FBX (required for Meta Horizon Worlds)"),
        ],
        default='FBX'
    )
    
    # Progress tracking
    current_task: StringProperty(
        name="Current Task",
        description="Description of current task being performed",
        default=""
    )
    
    progress_percentage: IntProperty(
        name="Progress Percentage",
        description="Overall progress percentage",
        default=0,
        min=0,
        max=100
    )

# === EXISTING PROPERTY GROUPS ===

class HorizonBakeSettings(PropertyGroup):
    """Property group for storing texture baking settings"""
    
    # Bake output settings
    output_directory: StringProperty(
        name="Bake Output Directory",
        description="Directory where baked textures will be saved",
        default="//baked_textures/",
        subtype='DIR_PATH'
    )
    
    # Image settings
    image_width: IntProperty(
        name="Image Width",
        description="Width of the baked texture",
        default=1024,
        min=64,
        max=8192
    )
    
    image_height: IntProperty(
        name="Image Height", 
        description="Height of the baked texture",
        default=1024,
        min=64,
        max=8192
    )
    
    # Bake type
    bake_type: EnumProperty(
        name="Bake Type",
        description="Type of texture to bake",
        items=[
            ('COMBINED', "Combined", "Bake combined color and lighting information"),
            ('DIFFUSE', "Diffuse", "Bake diffuse color only"),
            ('GLOSSY', "Glossy", "Bake glossy reflection"),
            ('TRANSMISSION', "Transmission", "Bake transmission"),
            ('EMIT', "Emit", "Bake emission"),
            ('NORMAL', "Normal", "Bake normal map"),
            ('ROUGHNESS', "Roughness", "Bake roughness map"),
            ('SHADOW', "Shadow", "Bake shadow information"),
            ('AO', "Ambient Occlusion", "Bake ambient occlusion"),
        ],
        default='COMBINED'
    )
    
    # Cycles sampling settings
    samples: IntProperty(
        name="Samples",
        description="Number of samples for baking (higher = better quality, slower)",
        default=128,
        min=1,
        max=4096
    )
    
    # Bake settings
    use_pass_direct: BoolProperty(
        name="Direct",
        description="Add direct lighting contribution",
        default=True
    )
    
    use_pass_indirect: BoolProperty(
        name="Indirect", 
        description="Add indirect lighting contribution",
        default=True
    )
    
    use_pass_color: BoolProperty(
        name="Color",
        description="Add color contribution",
        default=True
    )
    
    # Margin and cage settings
    margin: IntProperty(
        name="Margin",
        description="Margin in pixels to extend baked result",
        default=16,
        min=0,
        max=64
    )
    
    use_cage: BoolProperty(
        name="Use Cage",
        description="Cast rays to active object from a cage",
        default=False
    )
    
    cage_extrusion: FloatProperty(
        name="Cage Extrusion",
        description="Distance to extrude the cage from the base mesh",
        default=0.0,
        min=0.0,
        max=1.0
    )
    
    # Denoising
    use_denoising: BoolProperty(
        name="Use Denoising",
        description="Use denoising for cleaner results",
        default=True
    )
    
    denoising_input_passes: EnumProperty(
        name="Denoising Input Passes",
        description="Passes used by the denoiser",
        items=[
            ('RGB', "Color", "Use only color pass"),
            ('RGB_ALBEDO', "Color + Albedo", "Use color and albedo passes"),
            ('RGB_ALBEDO_NORMAL', "Color + Albedo + Normal", "Use color, albedo and normal passes"),
        ],
        default='RGB_ALBEDO_NORMAL'
    )
    
    # File format
    file_format: EnumProperty(
        name="File Format",
        description="Format to save baked textures",
        items=[
            ('PNG', "PNG", "Save as PNG (lossless, good for most textures)"),
            ('TIFF', "TIFF", "Save as TIFF (lossless, high quality)"),
            ('OPEN_EXR', "OpenEXR", "Save as OpenEXR (HDR, best for normal/roughness maps)"),
            ('JPEG', "JPEG", "Save as JPEG (lossy, smaller files)"),
        ],
        default='PNG'
    )
    
    # Color depth
    color_depth: EnumProperty(
        name="Color Depth",
        description="Bit depth for baked textures",
        items=[
            ('8', "8-bit", "8-bit per channel (smaller files)"),
            ('16', "16-bit", "16-bit per channel (higher precision)"),
            ('32', "32-bit", "32-bit per channel (highest precision, HDR)"),
        ],
        default='8'
    )
    
    # Batch processing options
    clear_existing: BoolProperty(
        name="Clear Existing Images",
        description="Clear existing bake images before starting new bake",
        default=True
    )
    
    auto_save: BoolProperty(
        name="Auto Save",
        description="Automatically save images after baking",
        default=True
    )
    
    show_progress: BoolProperty(
        name="Show Progress",
        description="Show baking progress in console",
        default=True
    )
    
    # GPU acceleration settings
    use_gpu: BoolProperty(
        name="Use GPU",
        description="Use GPU acceleration for baking (faster when available)",
        default=True
    )
    
    device: EnumProperty(
        name="Device",
        description="Processing device for baking",
        items=[
            ('CPU', "CPU", "Use CPU for processing"),
            ('GPU', "GPU", "Use GPU for processing (requires CUDA/OpenCL)"),
            ('AUTO', "Auto", "Automatically choose best available device"),
        ],
        default='GPU'
    )


class HorizonExportSettings(PropertyGroup):
    """Property group for storing basic export settings"""
    export_location: StringProperty(
        name="Export Location",
        description="Directory where files will be exported",
        default="//exports/",
        subtype='DIR_PATH'
    )
    
    # UI state properties for scrollable lists
    materials_list_expanded: BoolProperty(
        name="Materials List Expanded",
        description="Whether the detailed materials list is expanded",
        default=True
    )
    
    meshes_list_expanded: BoolProperty(
        name="Meshes List Expanded", 
        description="Whether the detailed meshes list is expanded",
        default=True
    )
    
    materials_page_size: IntProperty(
        name="Materials Page Size",
        description="Number of materials to show per page",
        default=10,
        min=5,
        max=50
    )
    
    materials_current_page: IntProperty(
        name="Materials Current Page",
        description="Current page number for materials list",
        default=0,
        min=0
    )
    
    meshes_page_size: IntProperty(
        name="Meshes Page Size",
        description="Number of meshes to show per page", 
        default=10,
        min=5,
        max=50
    )
    
    meshes_current_page: IntProperty(
        name="Meshes Current Page",
        description="Current page number for meshes list",
        default=0,
        min=0
    )
    
    analyze_all_materials: BoolProperty(
        name="Analyze All Materials",
        description="Analyze all materials in the scene, not just those on selected objects",
        default=False
    )
    
    # Decimation settings
    decimate_ratio: FloatProperty(
        name="Decimation Ratio",
        description="Ratio of faces to keep (0.1 = 10% of original faces)",
        default=0.5,
        min=0.01,
        max=1.0
    )
    
    decimate_type: EnumProperty(
        name="Decimation Type",
        description="Type of decimation to apply",
        items=[
            ('COLLAPSE', "Collapse", "Merge vertices together (good general purpose)"),
            ('UNSUBDIV', "Un-Subdivide", "Remove edge loops (good for over-subdivided meshes)"),
            ('PLANAR', "Planar", "Dissolve geometry in planar areas"),
        ],
        default='COLLAPSE'
    )
    
    decimate_preserve_boundaries: BoolProperty(
        name="Preserve Boundaries",
        description="Keep boundary edges unchanged during decimation",
        default=True
    )
    
    decimate_symmetry: BoolProperty(
        name="Symmetry",
        description="Maintain symmetry on meshes with mirror modifier",
        default=False
    )


class HorizonAtlasSettings(PropertyGroup):
    """Property group for storing UV atlas creation settings"""
    
    # Atlas output settings
    atlas_name: StringProperty(
        name="Atlas Name",
        description="Base name for the atlas material and textures",
        default="CombinedAtlas"
    )
    
    atlas_size: EnumProperty(
        name="Atlas Size",
        description="Size of the UV atlas texture",
        items=[
            ('512', "512×512", "Small atlas for low-detail objects"),
            ('1024', "1024×1024", "Medium atlas for most objects"),
            ('2048', "2048×2048", "Large atlas for high-detail objects"),
            ('4096', "4096×4096", "Very large atlas for maximum detail"),
        ],
        default='2048'
    )
    
    # UV packing settings
    island_margin: FloatProperty(
        name="Island Margin",
        description="Space between UV islands in the atlas",
        default=0.005,
        min=0.001,
        max=0.1
    )
    
    angle_limit: FloatProperty(
        name="Angle Limit",
        description="Angle limit for automatic seam detection",
        default=66.0,
        min=1.0,
        max=89.0,
        subtype='ANGLE'
    )
    
    # Atlas creation options
    combine_materials: BoolProperty(
        name="Combine Materials",
        description="Create a single material for all objects using the atlas",
        default=True
    )
    
    preserve_original_materials: BoolProperty(
        name="Preserve Originals",
        description="Keep original materials (creates copies instead of replacing)",
        default=True
    )
    
    auto_unwrap: BoolProperty(
        name="Auto Re-unwrap",
        description="Automatically re-unwrap UVs before creating atlas",
        default=True
    )
    
    # Texture baking for atlas
    bake_textures: BoolProperty(
        name="Bake Textures",
        description="Bake existing textures into the atlas to preserve visual appearance",
        default=True
    )
    
    bake_samples: IntProperty(
        name="Bake Samples",
        description="Number of samples for texture baking",
        default=128,
        min=1,
        max=1024
    )
    
    # Texture baking types for atlas
    bake_diffuse: BoolProperty(
        name="Bake Diffuse",
        description="Bake diffuse/base color textures into atlas",
        default=True
    )
    
    bake_normal: BoolProperty(
        name="Bake Normal",
        description="Bake normal maps into atlas",
        default=False
    )
    
    bake_roughness: BoolProperty(
        name="Bake Roughness",
        description="Bake roughness maps into atlas",
        default=False
    )
    
    # Atlas texture output
    save_atlas_textures: BoolProperty(
        name="Save Atlas Textures",
        description="Save baked atlas textures to disk",
        default=True
    )
    
    atlas_output_directory: StringProperty(
        name="Atlas Output Directory",
        description="Directory where atlas textures will be saved",
        default="//atlas_textures/",
        subtype='DIR_PATH'
    )
    
    # Atlas organization
    pack_method: EnumProperty(
        name="Packing Method",
        description="Method for packing UV islands into the atlas",
        items=[
            ('ANGLE_BASED', "Angle Based", "Pack based on UV angles (default)"),
            ('CONFORMAL', "Conformal", "Minimize distortion (slower)"),
            ('LIGHTMAP', "Lightmap", "Optimize for lightmapping"),
        ],
        default='ANGLE_BASED'
    )
    
    rotate_islands: BoolProperty(
        name="Rotate Islands",
        description="Allow rotation of UV islands for better packing",
        default=True
    )
    
    # Output options
    create_atlas_material: BoolProperty(
        name="Create Atlas Material",
        description="Create a new material using the atlas texture",
        default=True
    )
    
    atlas_material_type: EnumProperty(
        name="Atlas Material Type",
        description="Type of material to create for the atlas",
        items=[
            ('BASE_PBR', "Base PBR", "Standard Principled BSDF material"),
            ('UNLIT', "Unlit (_Unlit)", "Emission-based unlit material"),
            ('VERTEX_COLOR', "Vertex Color (_VXC)", "Material using vertex colors"),
        ],
        default='BASE_PBR'
    )


class MeshAnalysisData(PropertyGroup):
    """Property group for storing mesh analysis results"""
    object_name: StringProperty(name="Object Name")
    mesh_name: StringProperty(name="Mesh Name")
    
    # Geometry counts
    polygon_count: IntProperty(name="Polygon Count", default=0)
    vertex_count: IntProperty(name="Vertex Count", default=0)
    polygon_count_final: IntProperty(name="Final Polygon Count", default=0)
    vertex_count_final: IntProperty(name="Final Vertex Count", default=0)
    
    # Modifiers
    modifier_count: IntProperty(name="Modifier Count", default=0)
    modifier_list: StringProperty(name="Modifier List", default="")
    has_destructive_modifiers: BoolProperty(name="Has Destructive Modifiers", default=False)
    has_geometry_adding_modifiers: BoolProperty(name="Has Geometry Adding Modifiers", default=False)
    geometry_adding_modifiers: StringProperty(name="Geometry Adding Modifiers", default="")
    
    # UV channels
    uv_channel_count: IntProperty(name="UV Channel Count", default=0)
    uv_channel_list: StringProperty(name="UV Channel List", default="")
    has_multiple_uv_channels: BoolProperty(name="Has Multiple UV Channels", default=False)
    
    # Performance warnings
    is_high_poly: BoolProperty(name="Is High Poly", default=False)
    performance_warnings: StringProperty(name="Performance Warnings", default="")


class MaterialAnalysisData(PropertyGroup):
    """Property group for storing material analysis results"""
    material_name: StringProperty(name="Material Name")
    shader_type: StringProperty(name="Shader Type")
    using_objects: StringProperty(name="Using Objects")
    
    # New properties for naming analysis
    has_naming_issues: BoolProperty(name="Has Naming Issues", default=False)
    naming_issues: StringProperty(name="Naming Issues", default="")
    recommended_name: StringProperty(name="Recommended Name", default="")
    recommended_suffix: StringProperty(name="Recommended Suffix", default="")
    
    # Properties for empty material handling
    is_empty_material: BoolProperty(name="Is Empty Material", default=False)
    empty_material_purpose: EnumProperty(
        name="Empty Material Purpose",
        items=[
            ('PLACEHOLDER', "Placeholder", "Placeholder material to be filled later"),
            ('ORGANIZATIONAL', "Organizational", "Used for object organization/selection"),
            ('EXTERNAL', "External System", "Material handled by external system"),
            ('VERTEX_COLOR', "Vertex Color Only", "Relies purely on vertex colors"),
            ('UNKNOWN', "Unknown", "Purpose unclear")
        ],
        default='UNKNOWN'
    )
    can_be_setup: BoolProperty(name="Can Be Setup", default=True)
    
    # Properties for UV map conflict detection
    has_uv_conflicts: BoolProperty(name="Has UV Conflicts", default=False)
    uv_conflict_details: StringProperty(name="UV Conflict Details", default="")
    conflicting_objects: StringProperty(name="Conflicting Objects", default="")

    # Properties for UV mapping node detection (triggers material simplification)
    has_uv_mapping_nodes: BoolProperty(name="Has UV Mapping Nodes", default=False)
    uv_mapping_node_details: StringProperty(name="UV Mapping Node Details", default="")
    needs_uv_correction: BoolProperty(name="Needs UV Correction", default=False)





def get_material_naming_recommendation(material_name, shader_type, material):
    """
    Analyze material name and shader setup to recommend proper naming
    according to Meta Horizon Worlds conventions
    """
    issues = []
    recommended_suffix = ""
    
    # Characters to avoid: - . , / * $ &
    invalid_chars = ['-', '.', ',', '/', '*', '$', '&']
    found_invalid_chars = [char for char in invalid_chars if char in material_name]
    
    if found_invalid_chars:
        issues.append(f"Contains invalid characters: {', '.join(found_invalid_chars)}")
    
    # Check for spaces
    if ' ' in material_name:
        issues.append("Contains spaces")
    
    # Check for unnecessary underscores (except for valid suffixes)
    valid_suffixes = ['_Metal', '_Unlit', '_Blend', '_Transparent', '_Masked', '_VXC', '_VXM', '_UIO']
    has_valid_suffix = any(material_name.endswith(suffix) for suffix in valid_suffixes)
    
    # Check for underscores in the base name (excluding valid suffix)
    base_name_for_check = material_name
    if has_valid_suffix:
        for suffix in valid_suffixes:
            if material_name.endswith(suffix):
                base_name_for_check = material_name[:-len(suffix)]
                break
    
    if '_' in base_name_for_check or ' ' in base_name_for_check:
        if '_' in base_name_for_check and ' ' in base_name_for_check:
            issues.append("Contains underscores and spaces not used for valid suffixes")
        elif '_' in base_name_for_check:
            issues.append("Contains underscores not used for valid suffixes")
        elif ' ' in base_name_for_check:
            # This case is already handled by the space check above, but keeping for clarity
            pass  # Space issue already added above
    elif '_' in material_name and not has_valid_suffix:
        issues.append("Contains underscores not used for valid suffixes")
    
    # Recommend suffix based on shader type and material properties
    if material and material.use_nodes and material.node_tree:
        # Check for various material properties
        is_transparent = False
        is_emission = False
        has_vertex_colors = False
        is_metallic = False
        alpha_cutoff = False
        
        # Check material blend method
        if hasattr(material, 'blend_method'):
            if material.blend_method in ['BLEND', 'ALPHA']:
                is_transparent = True
            elif material.blend_method == 'CLIP':
                alpha_cutoff = True
        
        # Analyze the node tree for more detailed information
        principled_node = None
        has_emission_node = False
        has_transparent_shader = False
        
        for node in material.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                principled_node = node
            elif node.type == 'EMISSION':
                has_emission_node = True
            elif node.type in ['BSDF_TRANSPARENT', 'BSDF_GLASS']:
                has_transparent_shader = True
            elif node.type == 'ATTRIBUTE' and hasattr(node, 'attribute_name'):
                if 'Col' in node.attribute_name or 'Color' in node.attribute_name:
                    has_vertex_colors = True
        
        # Analyze Principled BSDF properties if present
        if principled_node:
            # Check metallic value - only suggest _Metal if explicitly > 0
            if principled_node.inputs['Metallic'].is_linked:
                # Metallic input is connected to a node, but we don't automatically assume it's metallic
                # Only suggest _Metal suffix if we can determine the value is actually > 0
                # For now, we don't suggest _Metal for node-connected metallic inputs unless we can evaluate the value
                is_metallic = False
            else:
                metallic_value = principled_node.inputs['Metallic'].default_value
                if metallic_value > 0.0:  # Any metallic value > 0
                    is_metallic = True
            
            # Check alpha value for transparency
            if principled_node.inputs['Alpha'].is_linked:
                is_transparent = True
            else:
                alpha_value = principled_node.inputs['Alpha'].default_value
                if alpha_value < 1.0:
                    is_transparent = True
            
            # Check emission for unlit materials
            if principled_node.inputs['Emission Strength'].is_linked:
                has_emission_node = True
            else:
                emission_strength = principled_node.inputs['Emission Strength'].default_value
                if emission_strength > 0:
                    has_emission_node = True
        
        # Determine the most appropriate suffix based on analysis
        if has_vertex_colors:
            if principled_node:
                recommended_suffix = "_VXM"  # Vertex Color with double-texture PBR
            else:
                recommended_suffix = "_VXC"  # Pure vertex color
        elif alpha_cutoff:
            recommended_suffix = "_Masked"
        elif is_transparent or has_transparent_shader:
            recommended_suffix = "_Transparent"
        elif has_emission_node and not principled_node:
            # Pure emission shader
            recommended_suffix = "_Unlit"
        elif has_emission_node and is_transparent:
            # Emission with transparency
            recommended_suffix = "_Transparent"
        elif shader_type == "EMISSION":
            recommended_suffix = "_Unlit"
        elif is_metallic:
            recommended_suffix = "_Metal"
        elif shader_type == "BSDF_PRINCIPLED":
            # Standard PBR material - no suffix needed unless metallic
            recommended_suffix = "None (Base PBR)"
        elif shader_type in ["BSDF_DIFFUSE", "BSDF_GLOSSY"]:
            # Legacy shader types that should be unlit
            recommended_suffix = "_Unlit"
        elif shader_type == "Legacy Material":
            recommended_suffix = "_Unlit"
        else:
            # For unknown shader types, default to no suffix (Base PBR) instead of _Unlit
            # This is more appropriate since most materials should be standard PBR
            recommended_suffix = "None (Base PBR)"
    else:
        # No nodes or legacy material
        if shader_type == "Legacy Material":
            recommended_suffix = "_Unlit"
        else:
            recommended_suffix = "_Unlit"
    
    # Create clean name recommendation
    clean_name = material_name
    
    # Remove invalid characters
    for char in found_invalid_chars:
        clean_name = clean_name.replace(char, '')
    
    # Handle underscores and spaces: preserve valid suffixes, remove all other separators
    valid_suffixes = ['_Metal', '_Unlit', '_Blend', '_Transparent', '_Masked', '_VXC', '_VXM', '_UIO']
    
    # Check if the name ends with a valid suffix
    current_suffix = ""
    base_name = clean_name
    
    for suffix in valid_suffixes:
        if clean_name.endswith(suffix):
            current_suffix = suffix
            base_name = clean_name[:-len(suffix)]
            break
    
    # Remove ALL underscores and spaces from the base name, convert to camelCase
    if '_' in base_name or ' ' in base_name:
        # Split by both underscore and space, then rejoin without separators using camelCase
        # First replace spaces with underscores for uniform processing
        base_name = base_name.replace(' ', '_')
        parts = base_name.split('_')
        base_name = ''.join(part.capitalize() for part in parts if part)
        # Make first letter lowercase to follow camelCase convention
        if base_name:
            base_name = base_name[0].lower() + base_name[1:]
    
    # Rebuild the clean name
    clean_name = base_name
    
    # Add the recommended suffix if it's not "None"
    if recommended_suffix and recommended_suffix != "None (Base PBR)":
        # If there was already a valid suffix but it's different from recommended
        if current_suffix and current_suffix != recommended_suffix:
            clean_name = base_name + recommended_suffix
        elif not current_suffix:
            clean_name = base_name + recommended_suffix
        else:
            # Current suffix matches recommended, keep it
            clean_name = base_name + current_suffix
    else:
        # No suffix recommended, just use the clean base name
        clean_name = base_name
    
    return issues, clean_name, recommended_suffix


def detect_uv_conflicts(objects_using_material):
    """
    Detect materials shared by multiple objects (potential UV conflicts).
    Returns tuple: (has_conflicts, conflict_details, conflicting_objects)
    """
    if len(objects_using_material) < 2:
        return False, "", ""
    
    # Get valid mesh objects
    mesh_objects = []
    for obj_name in objects_using_material:
        obj = bpy.data.objects.get(obj_name)
        if obj and obj.type == 'MESH' and obj.data:
            mesh_objects.append(obj)
    
    if len(mesh_objects) < 2:
        return False, "", ""
    
    # Any material shared by multiple mesh objects is considered a potential conflict
    # This allows users to resolve shared materials even if UV maps are different
    
    # Check if any objects have UV layers for detailed conflict information
    objects_with_uvs = [obj for obj in mesh_objects if obj.data.uv_layers]
    objects_without_uvs = [obj for obj in mesh_objects if not obj.data.uv_layers]
    
    conflict_details = []
    
    # Group objects by UV similarity if they have UV maps
    identical_uv_groups = []
    if len(objects_with_uvs) >= 2:
        # Compare UV maps between all pairs of objects with UVs
        for i, obj1 in enumerate(objects_with_uvs):
            for j, obj2 in enumerate(objects_with_uvs[i+1:], i+1):
                if compare_uv_maps(obj1, obj2):
                    # Found identical UV maps - this is a critical conflict
                    # Check if these objects are already in a conflict group
                    group_found = False
                    for group in identical_uv_groups:
                        if obj1.name in group or obj2.name in group:
                            group.update([obj1.name, obj2.name])
                            group_found = True
                            break
                    
                    if not group_found:
                        identical_uv_groups.append({obj1.name, obj2.name})
    
    # Build conflict details
    if identical_uv_groups:
        for i, group in enumerate(identical_uv_groups, 1):
            group_list = sorted(list(group))
            conflict_details.append(f"Identical UVs: {', '.join(group_list)}")
    
    # List all objects sharing the material
    all_object_names = [obj.name for obj in mesh_objects]
    
    # Add information about different UV situations
    if objects_without_uvs:
        conflict_details.append(f"No UVs: {', '.join([obj.name for obj in objects_without_uvs])}")
    
    # Count objects that are in identical UV groups
    objects_in_identical_groups = set()
    for group in identical_uv_groups:
        objects_in_identical_groups.update(group)
    
    if len(objects_with_uvs) > len(objects_in_identical_groups):
        # Some objects have different UV maps - this is still a sharing situation
        different_uv_objects = [obj.name for obj in objects_with_uvs 
                               if obj.name not in objects_in_identical_groups]
        if different_uv_objects:
            conflict_details.append(f"Different UVs: {', '.join(different_uv_objects)}")
    
    # If no detailed conflicts were found, just indicate it's a shared material
    if not conflict_details:
        conflict_details.append(f"Shared by {len(mesh_objects)} objects")
    
    details_str = "; ".join(conflict_details)
    objects_str = ", ".join(sorted(all_object_names))
    
    return True, details_str, objects_str


def detect_uv_mapping_nodes(material):
    """
    Detect if a material has UV mapping nodes that dynamically transform UV coordinates.
    These nodes cause baking issues because the baked texture doesn't match the final appearance.
    
    Only flags problematic UV transformation chains, not simple direct UV connections.
    
    Returns: tuple (has_mapping_nodes: bool, node_details: str)
    """
    if not material or not material.use_nodes or not material.node_tree:
        return False, ""
    
    problematic_chains = []
    
    # Find all texture nodes and check their UV input chains
    texture_nodes = [node for node in material.node_tree.nodes if node.type == 'TEX_IMAGE']
    
    for tex_node in texture_nodes:
        # Check if this texture node has a problematic UV transformation chain
        vector_input = tex_node.inputs.get('Vector')
        if vector_input and vector_input.is_linked:
            # Analyze the UV input chain
            uv_chain_nodes = []
            current_node = vector_input.links[0].from_node
            
            # Follow the chain backward to find UV transformation nodes
            while current_node:
                if current_node.bl_idname in ['ShaderNodeMapping', 'ShaderNodeUVMap', 'ShaderNodeVectorTransform', 'ShaderNodeVectorRotate', 'ShaderNodeVectorMath']:
                    uv_chain_nodes.append(current_node)
                    
                    # Check if this node has an input that's also a UV transformation
                    if hasattr(current_node, 'inputs') and len(current_node.inputs) > 0:
                        vector_input_node = None
                        for input_socket in current_node.inputs:
                            if input_socket.is_linked and input_socket.type == 'VECTOR':
                                vector_input_node = input_socket.links[0].from_node
                                break
                        
                        if vector_input_node:
                            current_node = vector_input_node
                        else:
                            break
                    else:
                        break
                elif current_node.bl_idname == 'NodeReroute':
                    # Follow through reroute nodes (they're just pass-through nodes)
                    if hasattr(current_node, 'inputs') and len(current_node.inputs) > 0:
                        reroute_input = current_node.inputs[0]
                        if reroute_input.is_linked:
                            current_node = reroute_input.links[0].from_node
                            continue
                        else:
                            break
                    else:
                        break
                elif current_node.bl_idname == 'ShaderNodeTexCoord':
                    # Texture coordinate node is fine - it's the source of UV data
                    # Only flag if it's part of a transformation chain (i.e., we found transform nodes)
                    if uv_chain_nodes:
                        # This is a problematic chain: TexCoord → [Transform nodes] → Texture
                        chain_description = f"Texture '{tex_node.name}' ← "
                        transform_nodes = []
                        for chain_node in reversed(uv_chain_nodes):
                            if chain_node.bl_idname == 'ShaderNodeMapping':
                                # Check if the mapping node is actually transforming UVs
                                if (chain_node.inputs['Location'].default_value != (0, 0, 0) or 
                                    chain_node.inputs['Rotation'].default_value != (0, 0, 0) or 
                                    chain_node.inputs['Scale'].default_value != (1, 1, 1)):
                                    transform_nodes.append(f"Mapping '{chain_node.name}' (transforms UVs)")
                                else:
                                    transform_nodes.append(f"Mapping '{chain_node.name}' (no transform)")
                            elif chain_node.bl_idname == 'ShaderNodeUVMap':
                                if chain_node.uv_map and chain_node.uv_map != "":
                                    transform_nodes.append(f"UV Map '{chain_node.name}' (uses '{chain_node.uv_map}')")
                                else:
                                    transform_nodes.append(f"UV Map '{chain_node.name}' (active UV map)")
                            else:
                                transform_nodes.append(f"{chain_node.bl_idname.replace('ShaderNode', '')} '{chain_node.name}'")
                        
                        chain_description += " ← ".join(transform_nodes)
                        chain_description += f" ← Texture Coordinate '{current_node.name}'"
                        problematic_chains.append(chain_description)
                    # If no transform nodes found, it's just a direct connection - not problematic
                    break
                else:
                    break
    
    has_mapping_nodes = len(problematic_chains) > 0
    node_details = "; ".join(problematic_chains) if problematic_chains else ""
    
    return has_mapping_nodes, node_details


def generate_unique_material_name(base_name, exclude_material=None):
    """Generate a unique material name by adding numeric suffix if needed"""
    if not base_name:
        base_name = "Material"
    
    # Check if the base name is already unique
    existing_material = bpy.data.materials.get(base_name)
    if not existing_material or existing_material == exclude_material:
        return base_name
    
    # Try with numeric suffixes
    counter = 1
    while counter < 9999:  # Prevent infinite loop
        test_name = f"{base_name}_{counter:03d}"
        existing_material = bpy.data.materials.get(test_name)
        if not existing_material or existing_material == exclude_material:
            return test_name
        counter += 1
    
    # If all numbered variants are taken, use timestamp
    timestamp = int(time.time())
    return f"{base_name}_{timestamp}"


def get_meta_horizon_texture_info(material_name, material=None):
    """
    Determine the correct texture naming and bake types for Meta Horizon Worlds
    based on material naming conventions from the documentation.
    
    Returns: list of (texture_suffix, bake_type, description) tuples
    """
    
    # Clean material name (remove the base name part before suffix)
    base_name = material_name
    material_type = "BASE_PBR"  # Default
    
    # Detect material type by suffix
    meta_horizon_suffixes = ['_Metal', '_Unlit', '_Blend', '_Transparent', '_Masked', '_VXC', '_VXM', '_UIO']
    
    for suffix in meta_horizon_suffixes:
        if material_name.endswith(suffix):
            base_name = material_name[:-len(suffix)]
            material_type = suffix[1:]  # Remove the underscore
            break
    
    # Define texture requirements based on material type
    texture_info = []
    
    if material_type == "Metal":
        # Single-Texture Metal PBR: MyMaterialName_BR.png
        texture_info.append(("_BR", "COMBINED", "BaseColor + Roughness + Metalness"))
        
    elif material_type == "Unlit":
        # Unlit Materials: MyMaterialName_B.png
        texture_info.append(("_B", "DIFFUSE", "BaseColor only (unlit)"))
        
    elif material_type == "Blend":
        # Unlit Blend Materials: MyMaterialName_BA.png
        texture_info.append(("_BA", "DIFFUSE", "BaseColor + Alpha (unlit blend)"))
        
    elif material_type == "Transparent":
        # Transparent Materials: Two textures
        texture_info.append(("_BR", "COMBINED", "BaseColor + Roughness"))
        texture_info.append(("_MESA", "COMBINED", "Metal + Emissive + Specular + Alpha"))
        
    elif material_type == "Masked":
        # Masked Materials: MyMaterialName_BA.png
        texture_info.append(("_BA", "COMBINED", "BaseColor + Alpha (masked)"))
        
    elif material_type == "VXC":
        # Vertex Color PBR: No textures needed
        texture_info = []  # Empty - vertex colors only
        
    elif material_type == "VXM":
        # Vertex Color Double-Texture PBR: MyMaterialName_BR.png + MyMaterialName_MEO.png
        # Texture A: BaseColor (sRGB) + Roughness (linear) - vertex color multiplied
        texture_info.append(("_BR", "COMBINED", "BaseColor + Roughness (vertex color multiplied)"))
        
        # Check if material has properties that require _MEO texture (Texture B)
        if material:  # material parameter is passed to this function
            needs_meo = False
            
            if material.use_nodes and material.node_tree:
                for node in material.node_tree.nodes:
                    if node.type == 'BSDF_PRINCIPLED':
                        # Check metalness
                        if 'Metallic' in node.inputs:
                            if node.inputs['Metallic'].is_linked or node.inputs['Metallic'].default_value > 0.0:
                                needs_meo = True
                                break
                        
                        # Check emission
                        if 'Emission Strength' in node.inputs:
                            if node.inputs['Emission Strength'].is_linked or node.inputs['Emission Strength'].default_value > 0.0:
                                needs_meo = True
                                break
                        
                        # Check emission color
                        if 'Emission Color' in node.inputs:
                            if node.inputs['Emission Color'].is_linked:
                                needs_meo = True
                                break
                    
                    elif node.type == 'EMISSION':
                        # Has emission shader
                        needs_meo = True
                        break
                    
                    elif node.type == 'AMBIENT_OCCLUSION':
                        # Has ambient occlusion
                        needs_meo = True
                        break
            
            # If material needs MEO texture, add it (Texture B: Metalness + Emissive + AmbientOcclusion)
            if needs_meo:
                texture_info.append(("_MEO", "COMBINED", "Metalness + Emissive + AmbientOcclusion (vertex color multiplied)"))
        
    elif material_type == "UIO":
        # UI Optimized Materials: MyMaterialName_BA.png
        texture_info.append(("_BA", "EMIT", "BaseColor + Alpha (UI optimized)"))
        
    else:
        # Default: Check if material needs MEO texture (Metalness + Emissive + AmbientOcclusion)
        # Always create _BR texture for BaseColor + Roughness
        texture_info.append(("_BR", "COMBINED", "BaseColor + Roughness (standard PBR)"))
        
        # Check if material has properties that require _MEO texture
        if material:  # material parameter is passed to this function
            needs_meo = False
            
            if material.use_nodes and material.node_tree:
                for node in material.node_tree.nodes:
                    if node.type == 'BSDF_PRINCIPLED':
                        # Check metalness
                        if 'Metallic' in node.inputs:
                            if node.inputs['Metallic'].is_linked or node.inputs['Metallic'].default_value > 0.0:
                                needs_meo = True
                                break
                        
                        # Check emission
                        if 'Emission Strength' in node.inputs:
                            if node.inputs['Emission Strength'].is_linked or node.inputs['Emission Strength'].default_value > 0.0:
                                needs_meo = True
                                break
                        
                        # Check emission color
                        if 'Emission Color' in node.inputs:
                            if node.inputs['Emission Color'].is_linked:
                                needs_meo = True
                                break
                    
                    elif node.type == 'EMISSION':
                        # Has emission shader
                        needs_meo = True
                        break
                    
                    elif node.type == 'AMBIENT_OCCLUSION':
                        # Has ambient occlusion
                        needs_meo = True
                        break
            
            # If material needs MEO texture, add it
            if needs_meo:
                texture_info.append(("_MEO", "COMBINED", "Metalness + Emissive + AmbientOcclusion"))
    
    return base_name, material_type, texture_info


def setup_temp_diffuse_shader_for_unlit(material):
    """
    Temporarily replace emission shader with Principled BSDF for DIFFUSE baking of _Unlit and _Blend materials.
    Returns data needed to restore the original shader.
    """
    if not material or not material.node_tree:
        return None
    
    # Find emission shader and output nodes
    emission_node = None
    output_node = None
    
    for node in material.node_tree.nodes:
        if node.type == 'EMISSION':
            emission_node = node
        elif node.type == 'OUTPUT_MATERIAL':
            output_node = node
    
    if not emission_node or not output_node:
        return None
    
    # Store original connection info
    original_connection = None
    if output_node.inputs['Surface'].is_linked:
        original_connection = output_node.inputs['Surface'].links[0].from_socket
    
    # Get emission color and strength
    emission_color = emission_node.inputs['Color'].default_value[:]
    emission_strength = emission_node.inputs['Strength'].default_value
    
    # Create temporary Principled BSDF
    temp_principled = material.node_tree.nodes.new(type='ShaderNodeBsdfPrincipled')
    temp_principled.name = "TEMP_PRINCIPLED_FOR_BAKE"
    temp_principled.location = emission_node.location
    
    # Set up the Principled BSDF for unlit-like behavior
    temp_principled.inputs['Base Color'].default_value = emission_color
    temp_principled.inputs['Metallic'].default_value = 0.0
    temp_principled.inputs['Roughness'].default_value = 1.0  # Fully rough for unlit look
    temp_principled.inputs['Specular'].default_value = 0.0  # No specularity
    
    # Connect to output
    material.node_tree.links.new(temp_principled.outputs['BSDF'], output_node.inputs['Surface'])
    
    # Return restoration data
    return {
        'temp_principled': temp_principled,
        'original_connection': original_connection,
        'emission_node': emission_node,
        'output_node': output_node
    }


def restore_original_shader_from_temp(material, temp_shader_data):
    """
    Restore the original emission shader setup after temporary DIFFUSE baking.
    """
    if not material or not material.node_tree or not temp_shader_data:
        return
    
    try:
        # Remove temporary Principled BSDF
        temp_principled = temp_shader_data['temp_principled']
        if temp_principled and temp_principled.name in material.node_tree.nodes:
            material.node_tree.nodes.remove(temp_principled)
        
        # Restore original connection
        output_node = temp_shader_data['output_node']
        original_connection = temp_shader_data['original_connection']
        
        if output_node and original_connection:
            material.node_tree.links.new(original_connection, output_node.inputs['Surface'])
    
    except Exception as e:
        print(f"Warning: Failed to restore original shader: {e}")


def setup_and_bake_material(context, material, objects, bake_settings):
    """
    Shared function to setup material and objects for baking with Meta Horizon Worlds naming conventions.
    Returns tuple: (success: bool, error_message: str)
    """
    
    try:
        # Get Meta Horizon texture info for this material
        base_name, material_type, texture_info = get_meta_horizon_texture_info(material.name, material)
        
        print(f"Meta Horizon material analysis:")
        print(f"  Material: '{material.name}' -> Base: '{base_name}', Type: '{material_type}'")
        
        # Handle vertex color materials (no textures needed)
        if material_type == "VXC":
            print("  Vertex Color PBR material - no textures needed")
            return True, "Vertex Color material (no textures required)"
        
        if not texture_info:
            return False, f"No texture requirements defined for material type: {material_type}"
        
        print(f"  Required textures: {len(texture_info)}")
        for suffix, bake_type, description in texture_info:
            print(f"    {base_name}{suffix}.png - {description}")
        
        # Check for UV mapping nodes that might cause baking issues
        has_uv_mapping_nodes, uv_mapping_details = detect_uv_mapping_nodes(material)
        if has_uv_mapping_nodes:
            print(f"  Warning: Material has UV mapping nodes that may cause baking issues:")
            print(f"    {uv_mapping_details}")
            print(f"  Attempting to correct UV mapping during baking...")
        
        # Store original settings
        original_engine = context.scene.render.engine
        original_samples = getattr(context.scene.cycles, 'samples', 128)
        original_use_denoising = getattr(context.scene.cycles, 'use_denoising', False)
        original_device = getattr(context.scene.cycles, 'device', 'CPU')
        
        # Set render engine to Cycles
        context.scene.render.engine = 'CYCLES'
        
        # Ensure Cycles is properly initialized
        if not hasattr(context.scene, 'cycles'):
            print("Warning: Cycles settings not available, some settings may not apply")
            return False, "Cycles render engine not properly initialized"
        
        # Configure Cycles settings
        context.scene.cycles.samples = bake_settings.samples
        context.scene.cycles.use_denoising = bake_settings.use_denoising
        
        # Configure GPU acceleration if requested
        if bake_settings.use_gpu and bake_settings.device in ['GPU', 'AUTO']:
            try:
                # Try to set GPU device for Cycles
                context.scene.cycles.device = 'GPU'
                print("GPU acceleration enabled for baking")
                
                # Try to configure compute device type if preferences are accessible
                try:
                    prefs = context.preferences
                    cycles_prefs = prefs.addons['cycles'].preferences
                    
                    # Enable GPU devices if available
                    gpu_devices = [d for d in cycles_prefs.devices if d.type in ('CUDA', 'OPTIX', 'OPENCL', 'HIP', 'ONEAPI')]
                    if gpu_devices:
                        for device in gpu_devices:
                            device.use = True
                        print(f"Enabled {len(gpu_devices)} GPU device(s) for Cycles")
                    else:
                        print("No GPU devices found in Cycles preferences")
                except Exception as pref_error:
                    print(f"Note: Could not access GPU preferences: {pref_error}")
                    print("GPU device setting applied, but preferences not modified")
                    
            except Exception as e:
                print(f"Warning: Could not enable GPU acceleration: {e}")
                print("Falling back to CPU rendering")
                context.scene.cycles.device = 'CPU'
        else:
            # Use CPU when GPU is disabled
            context.scene.cycles.device = 'CPU'
            print("Using CPU for baking")
        
        # Configure denoising (simplified to avoid version conflicts)
        if bake_settings.use_denoising:
            try:
                # Set basic denoising - this should work across Blender versions
                context.scene.cycles.use_denoising = True
                
                # Try to set denoiser type if available (safer approach)
                if hasattr(context.scene.cycles, 'denoiser'):
                    try:
                        context.scene.cycles.denoiser = 'OPENIMAGEDENOISE'
                    except:
                        print("Note: Using default denoiser")
                        
                print(f"Denoising enabled with denoiser: {getattr(context.scene.cycles, 'denoiser', 'default')}")
                    
            except Exception as e:
                print(f"Warning: Could not enable denoising: {e}")
                print("Continuing without denoising")
        
        # Setup material for baking
        if not material.use_nodes:
            material.use_nodes = True
        
        # Ensure objects have UV maps
        valid_objects = []
        for obj in objects:
            if obj.data and not obj.data.uv_layers:
                print(f"Warning: Object '{obj.name}' has no UV map, skipping")
                continue
            
            # Make sure UV map is active
            if obj.data.uv_layers:
                obj.data.uv_layers.active = obj.data.uv_layers[0]
                valid_objects.append(obj)
        
        if not valid_objects:
            return False, "No objects with UV maps found"
        
        # Store original selection to restore later
        original_selection = []
        original_active = context.view_layer.objects.active
        for obj in context.scene.objects:
            if obj.select_get():
                original_selection.append(obj)
        
        # Select objects for baking
        bpy.ops.object.select_all(action='DESELECT')
        for obj in valid_objects:
            obj.select_set(True)
        
        if valid_objects:
            context.view_layer.objects.active = valid_objects[0]
        
        # Configure bake settings
        bake_settings_scene = context.scene.render.bake
        bake_settings_scene.use_pass_direct = bake_settings.use_pass_direct
        bake_settings_scene.use_pass_indirect = bake_settings.use_pass_indirect
        bake_settings_scene.use_pass_color = bake_settings.use_pass_color
        bake_settings_scene.margin = bake_settings.margin
        bake_settings_scene.use_cage = bake_settings.use_cage
        bake_settings_scene.cage_extrusion = bake_settings.cage_extrusion
        
        print(f"Starting Meta Horizon bake for material '{material.name}' with {bake_settings.samples} samples...")
        print(f"Selected objects: {[obj.name for obj in valid_objects]}")
        print(f"Active object: {context.view_layer.objects.active.name if context.view_layer.objects.active else 'None'}")
        
        # Set up UV correction if needed
        uv_correction_data = None
        if has_uv_mapping_nodes:
            corrected_material, uv_correction_data = create_uv_corrected_material(material, valid_objects)
            if corrected_material:
                print(f"  Created UV-corrected material for baking: '{corrected_material.name}'")
                # Use the corrected material for baking
                bake_material = corrected_material
            else:
                print(f"  Failed to create UV-corrected material, using original")
                bake_material = material
        else:
            bake_material = material
        
        # Bake each required texture
        baked_textures = []
        total_start_time = time.time()
        
        for texture_suffix, bake_type, description in texture_info:
            # Configure bake passes based on bake type for optimal results
            if bake_type == 'COMBINED':
                # For COMBINED bake, we want the full appearance including textures
                bake_settings_scene.use_pass_direct = True
                bake_settings_scene.use_pass_indirect = False  # No indirect lighting for cleaner result
                bake_settings_scene.use_pass_color = True  # Include material colors and textures
            elif bake_type == 'DIFFUSE':
                # For DIFFUSE bake (used by _Unlit and _Blend materials), color only
                bake_settings_scene.use_pass_direct = False
                bake_settings_scene.use_pass_indirect = False
                bake_settings_scene.use_pass_color = True  # Color only
            elif bake_type == 'NORMAL':
                # For normal maps, no lighting passes needed
                bake_settings_scene.use_pass_direct = False
                bake_settings_scene.use_pass_indirect = False
                bake_settings_scene.use_pass_color = False
            elif bake_type == 'ROUGHNESS':
                # For roughness, no lighting passes needed
                bake_settings_scene.use_pass_direct = False
                bake_settings_scene.use_pass_indirect = False
                bake_settings_scene.use_pass_color = False
            elif bake_type == 'EMIT':
                # For EMIT bake (used by _Unlit materials), emission only
                # Note: EMIT baking captures emission shader output directly
                bake_settings_scene.use_pass_direct = False
                bake_settings_scene.use_pass_indirect = False
                bake_settings_scene.use_pass_color = True  # Color pass needed for emission
            else:
                # Default settings - preserve original user settings
                bake_settings_scene.use_pass_direct = bake_settings.use_pass_direct
                bake_settings_scene.use_pass_indirect = bake_settings.use_pass_indirect
                bake_settings_scene.use_pass_color = bake_settings.use_pass_color
            print(f"\n--- Baking texture: {base_name}{texture_suffix}.png ---")
            print(f"Bake type: {bake_type} ({description})")
            
            # Create properly named image for Meta Horizon Worlds
            image_name = f"{base_name}{texture_suffix}_baked"
            if bake_settings.clear_existing and bpy.data.images.get(image_name):
                bpy.data.images.remove(bpy.data.images[image_name])
            
            if not bpy.data.images.get(image_name):
                # Determine image creation parameters based on color depth
                if bake_settings.color_depth == '32':
                    # 32-bit float
                    bake_image = bpy.data.images.new(
                        name=image_name,
                        width=bake_settings.image_width,
                        height=bake_settings.image_height,
                        alpha=True,
                        float_buffer=True
                    )
                else:
                    # 8-bit or 16-bit (Note: Blender typically uses 8-bit for standard images)
                    bake_image = bpy.data.images.new(
                        name=image_name,
                        width=bake_settings.image_width,
                        height=bake_settings.image_height,
                        alpha=True,
                        float_buffer=False
                    )
            else:
                bake_image = bpy.data.images[image_name]
            
            # Add image texture node for baking
            if bake_material.node_tree:
                # Find or create an Image Texture node for baking
                bake_node = None
                for node in bake_material.node_tree.nodes:
                    if node.type == 'TEX_IMAGE' and node.name.startswith('BAKE_'):
                        bake_node = node
                        break
                
                if not bake_node:
                    bake_node = bake_material.node_tree.nodes.new(type='ShaderNodeTexImage')
                    bake_node.name = f'BAKE_{bake_material.name}'
                    bake_node.location = (0, -300)  # Place below other nodes
                
                bake_node.image = bake_image
                bake_node.select = True
                bake_material.node_tree.nodes.active = bake_node
            
            start_time = time.time()
            
            # Special handling for _Unlit and _Blend materials with DIFFUSE bake
            temp_shader_data = None
            if bake_type == 'DIFFUSE' and material_type in ["Unlit", "Blend"]:
                temp_shader_data = setup_temp_diffuse_shader_for_unlit(bake_material)
            
            # Perform the bake
            try:
                bpy.ops.object.bake(
                    type=bake_type,
                    margin=bake_settings.margin,
                    use_selected_to_active=False
                )
            except Exception as bake_error:
                print(f"Bake operation failed for {texture_suffix}: {bake_error}")
                # Restore original shader if temp setup was done
                if temp_shader_data:
                    restore_original_shader_from_temp(bake_material, temp_shader_data)
                raise bake_error
            
            # Restore original shader if temp setup was done
            if temp_shader_data:
                restore_original_shader_from_temp(bake_material, temp_shader_data)
            
            end_time = time.time()
            bake_duration = end_time - start_time
            print(f"Texture {texture_suffix} baked in {bake_duration:.2f} seconds")
            
            # Save the image if auto save is enabled
            if bake_settings.auto_save:
                save_meta_horizon_texture(bake_image, base_name, texture_suffix, bake_settings)
            
            baked_textures.append((texture_suffix, description))
        
        total_end_time = time.time()
        total_duration = total_end_time - total_start_time
        
        print(f"\n=== Meta Horizon Bake Complete for '{material.name}' ===")
        print(f"Total time: {total_duration:.2f} seconds")
        print(f"Baked {len(baked_textures)} textures:")
        for suffix, desc in baked_textures:
            print(f"  ✓ {base_name}{suffix}.png - {desc}")
        
        # Restore original materials and clean up UV correction
        if uv_correction_data:
            restore_original_materials(uv_correction_data)
            print(f"  Restored original materials after UV-corrected baking")
        
        # Restore original settings
        context.scene.render.engine = original_engine
        context.scene.cycles.samples = original_samples
        context.scene.cycles.use_denoising = original_use_denoising
        context.scene.cycles.device = original_device
        
        # Restore original selection
        bpy.ops.object.select_all(action='DESELECT')
        for obj in original_selection:
            if obj.name in bpy.data.objects:  # Check if object still exists
                obj.select_set(True)
        if original_active and original_active.name in bpy.data.objects:
            context.view_layer.objects.active = original_active
        
        return True, ""
        
    except Exception as e:
        error_msg = f"Error during baking: {str(e)}"
        print(error_msg)
        
        # Restore original materials and settings on error
        if uv_correction_data:
            restore_original_materials(uv_correction_data)
            print(f"  Restored original materials after baking error")
        
        try:
            context.scene.render.engine = original_engine
            context.scene.cycles.samples = original_samples
            context.scene.cycles.use_denoising = original_use_denoising
            context.scene.cycles.device = original_device
            
            # Restore original selection even on error
            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selection:
                if obj.name in bpy.data.objects:  # Check if object still exists
                    obj.select_set(True)
            if original_active and original_active.name in bpy.data.objects:
                context.view_layer.objects.active = original_active
        except:
            pass
        
        return False, error_msg


def create_uv_corrected_material(material, objects):
    """
    Create a temporary material that bypasses UV mapping nodes for accurate baking.
    
    Returns: tuple (corrected_material, restoration_data)
    """
    if not material or not material.use_nodes:
        return None, None
    
    # Create a temporary material for baking
    temp_material_name = f"_TEMP_BAKE_{material.name}"
    
    # Remove existing temp material if it exists
    if bpy.data.materials.get(temp_material_name):
        bpy.data.materials.remove(bpy.data.materials[temp_material_name])
    
    # Create a clean copy of the material
    temp_material = material.copy()
    temp_material.name = temp_material_name
    
    # Store restoration data
    restoration_data = {
        'original_material': material,
        'temp_material': temp_material,
        'object_material_assignments': {}
    }
    
    # Replace UV mapping nodes with direct UV input
    if temp_material.node_tree:
        # Find all texture nodes that are connected to UV mapping nodes
        texture_nodes = [node for node in temp_material.node_tree.nodes if node.type == 'TEX_IMAGE']
        
        for tex_node in texture_nodes:
            # Check if this texture node is connected to UV mapping nodes
            vector_input = tex_node.inputs.get('Vector')
            if vector_input and vector_input.is_linked:
                # Find the chain of UV transformation nodes
                uv_chain = []
                current_node = vector_input.links[0].from_node
                
                while current_node:
                    if current_node.bl_idname in ['ShaderNodeMapping', 'ShaderNodeUVMap', 'ShaderNodeTexCoord', 'ShaderNodeVectorTransform', 'ShaderNodeVectorRotate', 'ShaderNodeVectorMath']:
                        uv_chain.append(current_node)
                        # Follow the chain backwards
                        if current_node.inputs and current_node.inputs[0].is_linked:
                            current_node = current_node.inputs[0].links[0].from_node
                        else:
                            break
                    else:
                        break
                
                # If we found UV transformation nodes, replace them with direct UV input
                if uv_chain:
                    print(f"    Bypassing UV transformation chain for texture '{tex_node.name}'")
                    
                    # Create a new texture coordinate node for direct UV input
                    tex_coord_node = temp_material.node_tree.nodes.new(type='ShaderNodeTexCoord')
                    tex_coord_node.location = (tex_node.location[0] - 300, tex_node.location[1])
                    tex_coord_node.name = f"Direct_UV_{tex_node.name}"
                    
                    # Connect UV output directly to texture node
                    temp_material.node_tree.links.new(tex_coord_node.outputs['UV'], tex_node.inputs['Vector'])
                    
                    # Remove the old connections
                    for link in vector_input.links:
                        temp_material.node_tree.links.remove(link)
    
    # Temporarily assign the corrected material to objects
    for obj in objects:
        if obj.data and obj.data.materials:
            restoration_data['object_material_assignments'][obj.name] = []
            for i, mat_slot in enumerate(obj.data.materials):
                if mat_slot == material:
                    restoration_data['object_material_assignments'][obj.name].append(i)
                    obj.data.materials[i] = temp_material
                    print(f"    Temporarily assigned corrected material to object '{obj.name}' slot {i}")
    
    return temp_material, restoration_data


def restore_original_materials(restoration_data):
    """
    Restore original materials and clean up temporary materials.
    """
    if not restoration_data:
        return
    
    # Restore original material assignments
    for obj_name, slot_indices in restoration_data['object_material_assignments'].items():
        obj = bpy.data.objects.get(obj_name)
        if obj and obj.data and obj.data.materials:
            for slot_index in slot_indices:
                if slot_index < len(obj.data.materials):
                    obj.data.materials[slot_index] = restoration_data['original_material']
                    print(f"    Restored original material to object '{obj_name}' slot {slot_index}")
    
    # Clean up temporary material - check if it's still valid and exists
    temp_material = restoration_data.get('temp_material')
    if temp_material:
        try:
            # Check if the material object is still valid by trying to access its name
            temp_material_name = temp_material.name
            # Check if the material still exists in bpy.data.materials
            if temp_material_name in bpy.data.materials:
                bpy.data.materials.remove(temp_material)
                print(f"    Cleaned up temporary material '{temp_material_name}'")
        except ReferenceError:
            # The material was already removed or is invalid
            print(f"    Temporary material was already cleaned up or is invalid")
        except Exception as e:
            print(f"    Error cleaning up temporary material: {str(e)}")


def save_meta_horizon_texture(image, base_name, texture_suffix, bake_settings):
    """Save baked image with Meta Horizon Worlds naming convention"""
    try:
        # Ensure output directory exists
        output_dir = bpy.path.abspath(bake_settings.output_directory)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Generate Meta Horizon compatible filename
        file_extension = {
            'PNG': '.png',
            'TIFF': '.tiff', 
            'OPEN_EXR': '.exr',
            'JPEG': '.jpg'
        }.get(bake_settings.file_format, '.png')
        
        # Use Meta Horizon naming convention: BaseName_SUFFIX.png
        filename = f"{base_name}{texture_suffix}{file_extension}"
        filepath = os.path.join(output_dir, filename)
        
        # Set image format
        image.file_format = bake_settings.file_format
        
        # Note: Color depth is set during image creation, not during save
        print(f"Saving Meta Horizon texture as {bake_settings.file_format} format")
        
        # Save image
        image.filepath_raw = filepath
        image.save()
        
        print(f"✓ Saved Meta Horizon texture: {filepath}")
        
    except Exception as e:
        print(f"Error saving Meta Horizon texture: {str(e)}")


def save_baked_image(image, material_name, bake_settings):
    """Save baked image to disk (legacy function - kept for compatibility)"""
    try:
        # Ensure output directory exists
        output_dir = bpy.path.abspath(bake_settings.output_directory)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Generate filename
        file_extension = {
            'PNG': '.png',
            'TIFF': '.tiff', 
            'OPEN_EXR': '.exr',
            'JPEG': '.jpg'
        }.get(bake_settings.file_format, '.png')
        
        filename = f"{material_name}_{bake_settings.bake_type.lower()}{file_extension}"
        filepath = os.path.join(output_dir, filename)
        
        # Set image format
        image.file_format = bake_settings.file_format
        
        # Note: Color depth is set during image creation, not during save
        print(f"Saving as {bake_settings.file_format} format")
        
        # Save image
        image.filepath_raw = filepath
        image.save()
        
        print(f"Saved baked texture: {filepath}")
        
    except Exception as e:
        print(f"Error saving baked image: {str(e)}")


def compare_uv_maps(obj1, obj2):
    """
    Compare UV coordinates between two mesh objects to detect identical UV layouts.
    Returns True if UV maps are identical (within tolerance).
    """
    if not (obj1.data and obj2.data and obj1.data.uv_layers and obj2.data.uv_layers):
        return False
    
    # Get the active UV layer for both objects
    uv_layer1 = obj1.data.uv_layers.active
    uv_layer2 = obj2.data.uv_layers.active
    
    if not (uv_layer1 and uv_layer2):
        return False
    
    # Check if both meshes have the same topology
    if (len(obj1.data.vertices) != len(obj2.data.vertices) or 
        len(obj1.data.polygons) != len(obj2.data.polygons) or
        len(obj1.data.loops) != len(obj2.data.loops)):
        return False
    
    # Compare UV coordinates with tolerance
    tolerance = 0.0001
    uv_data1 = uv_layer1.data
    uv_data2 = uv_layer2.data
    
    if len(uv_data1) != len(uv_data2):
        return False
    
    # Sample a subset of UV coordinates for performance
    # Check every nth UV coordinate, or all if the mesh is small
    step = max(1, len(uv_data1) // 100)  # Sample up to 100 points
    
    for i in range(0, len(uv_data1), step):
        uv1 = uv_data1[i].uv
        uv2 = uv_data2[i].uv
        
        # Check if UV coordinates are different beyond tolerance
        if (abs(uv1.x - uv2.x) > tolerance or abs(uv1.y - uv2.y) > tolerance):
            return False
    
    # If we've made it here, the UV maps are likely identical
    # Do a more thorough check on a larger sample if the initial check passed
    if step > 1:
        # Check every 10th coordinate for a more thorough verification
        fine_step = max(1, len(uv_data1) // 1000)
        for i in range(0, len(uv_data1), fine_step):
            uv1 = uv_data1[i].uv
            uv2 = uv_data2[i].uv
            
            if (abs(uv1.x - uv2.x) > tolerance or abs(uv1.y - uv2.y) > tolerance):
                return False
    
    return True


def create_uv_atlas(objects, atlas_settings):
    """
    Create a UV atlas by combining multiple objects into a single UV layout.
    Returns: (success: bool, atlas_material: Material, error_message: str)
    """
    try:
        if not objects:
            return False, None, "No objects provided for atlas creation"
        
        # Filter to mesh objects only
        mesh_objects = [obj for obj in objects if obj.type == 'MESH' and obj.data]
        if not mesh_objects:
            return False, None, "No mesh objects found in selection"
        
        print(f"\n=== Creating UV Atlas ===")
        print(f"Processing {len(mesh_objects)} objects:")
        for obj in mesh_objects:
            print(f"  • {obj.name}")
        
        # Store original state
        original_active = bpy.context.view_layer.objects.active
        original_selection = bpy.context.selected_objects.copy()
        
        # Preserve original material information BEFORE any modifications
        original_materials_info = {}
        if atlas_settings.bake_textures:
            print("Preserving original material information...")
            for obj in mesh_objects:
                if obj.data and obj.data.materials:
                    original_materials_info[obj.name] = {
                        'materials': [mat for mat in obj.data.materials if mat],
                        'uv_layers': [uv.name for uv in obj.data.uv_layers] if obj.data.uv_layers else []
                    }
                    print(f"  Preserved {len(original_materials_info[obj.name]['materials'])} materials from '{obj.name}'")
        
        # Auto re-unwrap if requested
        if atlas_settings.auto_unwrap:
            print("Auto re-unwrapping UVs...")
            for obj in mesh_objects:
                try:
                    # Clear selection and select only current object
                    bpy.ops.object.select_all(action='DESELECT')
                    obj.select_set(True)
                    bpy.context.view_layer.objects.active = obj
                    
                    # Enter Edit mode
                    bpy.ops.object.mode_set(mode='EDIT')
                    
                    # Select all faces
                    bpy.ops.mesh.select_all(action='SELECT')
                    
                    # Create UV layer if it doesn't exist
                    if not obj.data.uv_layers:
                        obj.data.uv_layers.new(name="UVMap")
                    
                    # Make sure we have an active UV layer
                    if obj.data.uv_layers:
                        obj.data.uv_layers.active = obj.data.uv_layers[0]
                    
                    # Clear existing UVs and start fresh
                    bpy.ops.uv.select_all(action='SELECT')
                    
                    # Apply Smart UV Project with better settings
                    bpy.ops.uv.smart_project(
                        angle_limit=math.radians(atlas_settings.angle_limit),
                        island_margin=0.02,  # Consistent margin
                        area_weight=0.0,
                        correct_aspect=True,
                        scale_to_bounds=True  # Scale to use full UV space
                    )
                    
                    # Check UV bounds after unwrapping
                    mesh = obj.data
                    uv_layer = mesh.uv_layers.active
                    if uv_layer:
                        out_of_bounds_count = 0
                        total_uvs = 0
                        for face in mesh.polygons:
                            for loop_index in face.loop_indices:
                                uv = uv_layer.data[loop_index].uv
                                total_uvs += 1
                                if uv.x < 0 or uv.x > 1 or uv.y < 0 or uv.y > 1:
                                    out_of_bounds_count += 1
                        
                        if out_of_bounds_count > 0:
                            print(f"  Warning: {out_of_bounds_count}/{total_uvs} UVs are outside 0-1 range for '{obj.name}'")
                        else:
                            print(f"  ✓ All UVs within bounds for '{obj.name}'")
                    
                    # Return to Object mode
                    bpy.ops.object.mode_set(mode='OBJECT')
                    
                except Exception as e:
                    print(f"Warning: Failed to re-unwrap '{obj.name}': {e}")
                    try:
                        bpy.ops.object.mode_set(mode='OBJECT')
                    except:
                        pass
        
        # Join objects for atlas creation (if multiple objects)
        atlas_object = None
        if len(mesh_objects) == 1:
            atlas_object = mesh_objects[0]
            print(f"Using single object '{atlas_object.name}' for atlas")
        else:
            print("Joining objects for atlas creation...")
            
            # Select all mesh objects
            bpy.ops.object.select_all(action='DESELECT')
            for obj in mesh_objects:
                obj.select_set(True)
            
            # Set the first object as active
            bpy.context.view_layer.objects.active = mesh_objects[0]
            
            # Store materials before joining
            materials_before_join = []
            for obj in mesh_objects:
                if obj.data and obj.data.materials:
                    for mat in obj.data.materials:
                        if mat and mat not in materials_before_join:
                            materials_before_join.append(mat)
            
            # Join objects
            try:
                bpy.ops.object.join()
                atlas_object = bpy.context.active_object
                print(f"Objects joined into '{atlas_object.name}'")
            except Exception as e:
                return False, None, f"Failed to join objects: {str(e)}"
        
        # Create UV atlas layout
        print("Creating UV atlas layout...")
        
        # Enter Edit mode for UV operations
        bpy.ops.object.select_all(action='DESELECT')
        atlas_object.select_set(True)
        bpy.context.view_layer.objects.active = atlas_object
        bpy.ops.object.mode_set(mode='EDIT')
        
        # Select all faces
        bpy.ops.mesh.select_all(action='SELECT')
        
        # Ensure we have a UV layer - this is critical after joining objects
        if not atlas_object.data.uv_layers:
            print("No UV layers found after joining - creating new UV layer")
            atlas_object.data.uv_layers.new(name="UVMap")
            print("Created new UV layer for atlas object")
            
            # Since we have no UV data, we need to unwrap the entire object
            print("Unwrapping entire atlas object since no UV data exists...")
            bpy.ops.uv.smart_project(
                angle_limit=math.radians(atlas_settings.angle_limit),
                island_margin=0.02,
                area_weight=0.0,
                correct_aspect=True,
                scale_to_bounds=True
            )
            print("Completed initial UV unwrapping of atlas object")
        else:
            print(f"Found {len(atlas_object.data.uv_layers)} UV layer(s) after joining")
        
        # Make sure we have an active UV layer
        if atlas_object.data.uv_layers:
            atlas_object.data.uv_layers.active = atlas_object.data.uv_layers[0]
            print(f"Set active UV layer: '{atlas_object.data.uv_layers.active.name}'")
        else:
            print("ERROR: Still no UV layers available!")
            return False, None, "Failed to create or access UV layers for atlas object"
        
        # Check for faces without UV coordinates and fix them
        mesh = atlas_object.data
        uv_layer = mesh.uv_layers.active
        faces_without_uvs = 0
        
        if uv_layer and len(uv_layer.data) > 0:
            print(f"Checking UV coordinates for {len(mesh.polygons)} faces...")
            
            try:
                for face in mesh.polygons:
                    face_has_uvs = True
                    for loop_index in face.loop_indices:
                        if loop_index < len(uv_layer.data):
                            uv = uv_layer.data[loop_index].uv
                            # Check if UV is at origin (likely unassigned)
                            if uv.x == 0.0 and uv.y == 0.0:
                                face_has_uvs = False
                                break
                        else:
                            print(f"Warning: Loop index {loop_index} out of range for UV data")
                            face_has_uvs = False
                            break
                    if not face_has_uvs:
                        faces_without_uvs += 1
                
                if faces_without_uvs > 0:
                    print(f"Found {faces_without_uvs} faces without proper UVs, re-unwrapping...")
                    # Re-unwrap the entire object to ensure all faces have UVs
                    bpy.ops.uv.smart_project(
                        angle_limit=math.radians(atlas_settings.angle_limit),
                        island_margin=0.02,
                        area_weight=0.0,
                        correct_aspect=True,
                        scale_to_bounds=True
                    )
                    print("Re-unwrapped atlas object to fix missing UVs")
                else:
                    print("All faces have UV coordinates")
                    
            except Exception as e:
                print(f"Error checking UV coordinates: {e}")
                print("Performing full re-unwrap as fallback...")
                bpy.ops.uv.smart_project(
                    angle_limit=math.radians(atlas_settings.angle_limit),
                    island_margin=0.02,
                    area_weight=0.0,
                    correct_aspect=True,
                    scale_to_bounds=True
                )
                print("Completed fallback UV unwrapping")
        else:
            print("No UV data available - performing full unwrap...")
            bpy.ops.uv.smart_project(
                angle_limit=math.radians(atlas_settings.angle_limit),
                island_margin=0.02,
                area_weight=0.0,
                correct_aspect=True,
                scale_to_bounds=True
            )
            print("Completed full UV unwrapping")
        
        # Ensure all faces are selected and pack UV islands properly
        try:
            # Select all faces first
            bpy.ops.mesh.select_all(action='SELECT')
            
            # Switch to UV editing mode for proper packing
            bpy.context.area.ui_type = 'UV'
            
            # Select all UV islands
            bpy.ops.uv.select_all(action='SELECT')
            
            # Average the island scale first to make them more uniform
            bpy.ops.uv.average_islands_scale()
            print("Averaged UV island scales")
            
            # Pack islands with better settings for atlas creation
            bpy.ops.uv.pack_islands(
                margin=atlas_settings.island_margin,
                rotate=atlas_settings.rotate_islands
            )
            print("UV islands packed for atlas")
            
            # Scale islands up to fill more of the UV space (reduce empty areas)
            bpy.ops.uv.select_all(action='SELECT')
            
            # Get the current UV bounds to see how much space we're using
            # Check UV bounds before scaling
            mesh = atlas_object.data
            uv_layer = mesh.uv_layers.active
            if uv_layer:
                # Calculate UV bounds
                min_u = min_v = 1.0
                max_u = max_v = 0.0
                uv_count = 0
                
                for face in mesh.polygons:
                    for loop_index in face.loop_indices:
                        uv = uv_layer.data[loop_index].uv
                        min_u = min(min_u, uv.x)
                        max_u = max(max_u, uv.x)
                        min_v = min(min_v, uv.y)
                        max_v = max(max_v, uv.y)
                        uv_count += 1
                
                uv_width = max_u - min_u
                uv_height = max_v - min_v
                coverage = (uv_width * uv_height) * 100
                
                print(f"UV bounds before scaling: {min_u:.3f}-{max_u:.3f} x {min_v:.3f}-{max_v:.3f}")
                print(f"UV coverage: {coverage:.1f}% of texture space used")
                
                # Only scale if we're using less than 80% of the space
                if coverage < 80.0:
                    # Scale factor to use more space but leave margin
                    target_coverage = 0.85  # Target 85% coverage
                    scale_factor = (target_coverage / (coverage/100)) ** 0.5  # Square root for 2D scaling
                    scale_factor = min(scale_factor, 2.0)  # Cap scaling to avoid too much stretching
                    
                    # Apply scaling to fill UV space better
                    bpy.ops.transform.resize(
                        value=(scale_factor, scale_factor, 1.0),
                        orient_type='GLOBAL',
                        orient_matrix=((1, 0, 0), (0, 1, 0), (0, 0, 1)),
                        orient_matrix_type='GLOBAL',
                        constraint_axis=(False, False, False),
                        mirror=False,
                        use_proportional_edit=False
                    )
                    print(f"Scaled UV islands by {scale_factor:.2f} to maximize atlas usage")
                else:
                    print("UV coverage already good, no scaling needed")
                
                # Final validation: check for UVs outside 0-1 range
                out_of_bounds_count = 0
                total_uvs = 0
                for face in mesh.polygons:
                    for loop_index in face.loop_indices:
                        uv = uv_layer.data[loop_index].uv
                        total_uvs += 1
                        if uv.x < 0 or uv.x > 1 or uv.y < 0 or uv.y > 1:
                            out_of_bounds_count += 1
                
                if out_of_bounds_count > 0:
                    print(f"WARNING: {out_of_bounds_count}/{total_uvs} UVs are outside 0-1 range!")
                    print("This will cause black areas in the atlas texture")
                    
                    # Try to fix by clamping UVs to 0-1 range
                    print("Attempting to fix out-of-bounds UVs...")
                    for face in mesh.polygons:
                        for loop_index in face.loop_indices:
                            uv = uv_layer.data[loop_index].uv
                            uv.x = max(0.0, min(1.0, uv.x))
                            uv.y = max(0.0, min(1.0, uv.y))
                    print("Clamped UVs to 0-1 range")
                else:
                    print(f"✓ All {total_uvs} UVs are within 0-1 range")
            else:
                print("Warning: No active UV layer found for bounds checking")
            
            # Switch back to 3D viewport
            bpy.context.area.ui_type = 'VIEW_3D'
                
        except Exception as e:
            print(f"Warning: UV packing failed: {e}")
            # Fallback: basic packing
            try:
                bpy.ops.uv.select_all(action='SELECT')
                bpy.ops.uv.pack_islands(margin=atlas_settings.island_margin)
                print("Used basic UV packing fallback")
            except Exception as e2:
                print(f"Warning: All UV packing methods failed: {e2}")
        
        # Return to Object mode
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # Bake the combined appearance into a single atlas texture
        atlas_textures = {}
        if atlas_settings.combine_materials:
            print("Baking combined appearance into single atlas texture...")
            atlas_textures = bake_combined_atlas_texture(atlas_object, atlas_settings)
        else:
            print("Keeping original materials (no baking needed)")
        
        # Create atlas material if requested
        atlas_material = None
        if atlas_settings.create_atlas_material:
            print("Creating atlas material...")
            
            # Generate unique material name
            base_name = atlas_settings.atlas_name
            material_name = base_name
            counter = 1
            while bpy.data.materials.get(material_name):
                material_name = f"{base_name}_{counter:03d}"
                counter += 1
            
            # Add appropriate suffix based on material type
            if atlas_settings.atlas_material_type == 'UNLIT':
                material_name += "_Unlit"
            elif atlas_settings.atlas_material_type == 'VERTEX_COLOR':
                material_name += "_VXC"
            
            # Create the material
            atlas_material = bpy.data.materials.new(name=material_name)
            atlas_material.use_nodes = True
            atlas_material.node_tree.nodes.clear()
            
            # Create material output node
            output_node = atlas_material.node_tree.nodes.new(type='ShaderNodeOutputMaterial')
            output_node.location = (300, 0)
            
            if atlas_settings.atlas_material_type == 'BASE_PBR':
                # Create Principled BSDF
                principled_node = atlas_material.node_tree.nodes.new(type='ShaderNodeBsdfPrincipled')
                principled_node.location = (0, 0)
                atlas_material.node_tree.links.new(principled_node.outputs['BSDF'], output_node.inputs['Surface'])
                
                # Connect baked atlas textures
                if 'diffuse' in atlas_textures:
                    diffuse_tex_node = atlas_material.node_tree.nodes.new(type='ShaderNodeTexImage')
                    diffuse_tex_node.location = (-300, 100)
                    diffuse_tex_node.image = atlas_textures['diffuse']
                    atlas_material.node_tree.links.new(diffuse_tex_node.outputs['Color'], principled_node.inputs['Base Color'])
                    print(f"  Connected diffuse atlas texture: '{diffuse_tex_node.image.name}'")
                else:
                    # Set default color if no texture
                    principled_node.inputs['Base Color'].default_value = (0.8, 0.8, 0.8, 1.0)

                if 'normal' in atlas_textures:
                    normal_tex_node = atlas_material.node_tree.nodes.new(type='ShaderNodeTexImage')
                    normal_tex_node.location = (-300, -100)
                    normal_tex_node.image = atlas_textures['normal']
                    normal_tex_node.image.colorspace_settings.name = 'Non-Color'
                    
                    normal_map_node = atlas_material.node_tree.nodes.new(type='ShaderNodeNormalMap')
                    normal_map_node.location = (-100, -100)
                    atlas_material.node_tree.links.new(normal_tex_node.outputs['Color'], normal_map_node.inputs['Color'])
                    atlas_material.node_tree.links.new(normal_map_node.outputs['Normal'], principled_node.inputs['Normal'])
                    print(f"  Connected normal atlas texture: '{normal_tex_node.image.name}'")
                
                if 'roughness' in atlas_textures:
                    roughness_tex_node = atlas_material.node_tree.nodes.new(type='ShaderNodeTexImage')
                    roughness_tex_node.location = (-300, -300)
                    roughness_tex_node.image = atlas_textures['roughness']
                    roughness_tex_node.image.colorspace_settings.name = 'Non-Color'
                    atlas_material.node_tree.links.new(roughness_tex_node.outputs['Color'], principled_node.inputs['Roughness'])
                    print(f"  Connected roughness atlas texture: '{roughness_tex_node.image.name}'")
                else:
                    # Set default roughness if no texture
                    principled_node.inputs['Roughness'].default_value = 0.5
                
                # Set default values for non-textured inputs
                principled_node.inputs['Metallic'].default_value = 0.0
                
            elif atlas_settings.atlas_material_type == 'UNLIT':
                # Create Emission shader
                emission_node = atlas_material.node_tree.nodes.new(type='ShaderNodeEmission')
                emission_node.location = (0, 0)
                atlas_material.node_tree.links.new(emission_node.outputs['Emission'], output_node.inputs['Surface'])
                
                # Connect diffuse atlas texture for unlit materials
                if 'diffuse' in atlas_textures:
                    diffuse_tex_node = atlas_material.node_tree.nodes.new(type='ShaderNodeTexImage')
                    diffuse_tex_node.location = (-300, 0)
                    diffuse_tex_node.image = atlas_textures['diffuse']
                    atlas_material.node_tree.links.new(diffuse_tex_node.outputs['Color'], emission_node.inputs['Color'])
                    print(f"  Connected diffuse atlas texture: '{diffuse_tex_node.image.name}'")
                else:
                    # Set default emission color if no texture
                    emission_node.inputs['Color'].default_value = (0.8, 0.8, 0.8, 1.0)
                
                emission_node.inputs['Strength'].default_value = 1.0
                
            elif atlas_settings.atlas_material_type == 'VERTEX_COLOR':
                # Create Principled BSDF with vertex color input
                principled_node = atlas_material.node_tree.nodes.new(type='ShaderNodeBsdfPrincipled')
                principled_node.location = (0, 0)
                
                # Create Vertex Color attribute node
                vertex_color_node = atlas_material.node_tree.nodes.new(type='ShaderNodeAttribute')
                vertex_color_node.location = (-300, 200)
                vertex_color_node.attribute_name = "Col"  # Default vertex color attribute
                
                # Mix vertex colors with atlas texture if available
                if 'diffuse' in atlas_textures:
                    diffuse_tex_node = atlas_material.node_tree.nodes.new(type='ShaderNodeTexImage')
                    diffuse_tex_node.location = (-300, 0)
                    diffuse_tex_node.image = atlas_textures['diffuse']
                    
                    # Create mix node to combine vertex color and texture
                    mix_node = atlas_material.node_tree.nodes.new(type='ShaderNodeMix')
                    mix_node.location = (-100, 100)
                    mix_node.data_type = 'RGBA'
                    mix_node.blend_type = 'MULTIPLY'
                    mix_node.inputs['Fac'].default_value = 1.0
                    
                    atlas_material.node_tree.links.new(vertex_color_node.outputs['Color'], mix_node.inputs['Color1'])
                    atlas_material.node_tree.links.new(diffuse_tex_node.outputs['Color'], mix_node.inputs['Color2'])
                    atlas_material.node_tree.links.new(mix_node.outputs['Color'], principled_node.inputs['Base Color'])
                    print(f"  Connected vertex color + diffuse atlas texture: '{diffuse_tex_node.image.name}'")
                else:
                    # Use only vertex colors
                    atlas_material.node_tree.links.new(vertex_color_node.outputs['Color'], principled_node.inputs['Base Color'])
                
                atlas_material.node_tree.links.new(principled_node.outputs['BSDF'], output_node.inputs['Surface'])
                
                # Set default PBR values
                principled_node.inputs['Metallic'].default_value = 0.0
                principled_node.inputs['Roughness'].default_value = 0.5
            
            # Apply atlas material to the object if combining materials
            if atlas_settings.combine_materials:
                # Clear existing materials and add the new atlas material
                atlas_object.data.materials.clear()
                atlas_object.data.materials.append(atlas_material)
                print(f"Applied atlas material '{material_name}' to object")
            else:
                # Keep existing materials - textures are automatically preserved
                print(f"Created atlas material '{material_name}' but keeping existing materials")
            
            print(f"Created atlas material: '{material_name}'")
        
        # Restore selection - atlas object should be selected and active
        bpy.ops.object.select_all(action='DESELECT')
        if atlas_object and atlas_object.name in [obj.name for obj in bpy.context.scene.objects]:
            try:
                atlas_object.select_set(True)
                bpy.context.view_layer.objects.active = atlas_object
                print(f"Atlas object '{atlas_object.name}' selected and active")
            except:
                pass  # Object might not exist
        
        print(f"✓ UV Atlas creation complete!")
        print(f"  Atlas object: '{atlas_object.name}'")
        if atlas_material:
            print(f"  Atlas material: '{atlas_material.name}'")
        
        return True, atlas_material, ""
        
    except Exception as e:
        error_msg = f"Error creating UV atlas: {str(e)}"
        print(error_msg)
        
        # Ensure we're back in Object mode
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except:
            pass
        
        return False, None, error_msg


def bake_textures_to_atlas(atlas_object, atlas_settings, original_materials_info):
    """
    Bake existing textures from the original materials into new atlas textures.
    Returns: dict of baked atlas images {'diffuse': Image, 'normal': Image, etc.}
    """
    try:
        atlas_textures = {}
        
        if not atlas_object or not atlas_object.data:
            print("No atlas object found for texture baking")
            return atlas_textures
        
        if not original_materials_info:
            print("No original material information preserved for texture baking")
            return atlas_textures
        
        # Store original render settings
        original_engine = bpy.context.scene.render.engine
        original_samples = getattr(bpy.context.scene.cycles, 'samples', 128)
        
        # Set render engine to Cycles for baking
        bpy.context.scene.render.engine = 'CYCLES'
        
        # Configure Cycles settings for baking
        if hasattr(bpy.context.scene, 'cycles'):
            bpy.context.scene.cycles.samples = atlas_settings.bake_samples
            bpy.context.scene.cycles.use_denoising = True
        
        # Ensure we have proper lighting for baking (add basic lighting if none exists)
        world = bpy.context.scene.world
        if world and world.use_nodes:
            # Make sure world has some emission for baking
            for node in world.node_tree.nodes:
                if node.type == 'BACKGROUND':
                    # Ensure background has some brightness
                    if node.inputs['Strength'].default_value < 0.1:
                        node.inputs['Strength'].default_value = 1.0
                    break
        else:
            # Create basic world setup if none exists
            if world:
                world.use_nodes = True
                world.node_tree.nodes.clear()
                bg_node = world.node_tree.nodes.new(type='ShaderNodeBackground')
                bg_node.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0)
                bg_node.inputs['Strength'].default_value = 1.0
                output_node = world.node_tree.nodes.new(type='ShaderNodeOutputWorld')
                world.node_tree.links.new(bg_node.outputs['Background'], output_node.inputs['Surface'])
        
        # Get atlas size
        atlas_size = int(atlas_settings.atlas_size)
        
        # Determine what to bake
        bake_types = []
        if atlas_settings.bake_diffuse:
            bake_types.append(('diffuse', 'COMBINED'))  # Use COMBINED to get actual appearance
        if atlas_settings.bake_normal:
            bake_types.append(('normal', 'NORMAL'))
        if atlas_settings.bake_roughness:
            bake_types.append(('roughness', 'ROUGHNESS'))
        
        # If no specific types selected, default to diffuse
        if not bake_types:
            bake_types = [('diffuse', 'COMBINED')]  # Use COMBINED instead of DIFFUSE
        
        print(f"Baking {len(bake_types)} texture types into {atlas_size}×{atlas_size} atlas...")
        
        # Collect all original materials that have textures
        original_materials = []
        for obj_name, info in original_materials_info.items():
            for material in info['materials']:
                if material and material not in original_materials:
                    original_materials.append(material)
        
        print(f"Found {len(original_materials)} original materials to bake from")
        
        # Debug: Print material information
        for material in original_materials:
            if material and material.use_nodes and material.node_tree:
                texture_nodes = [node for node in material.node_tree.nodes if node.type == 'TEX_IMAGE']
                shader_nodes = [node for node in material.node_tree.nodes if node.type in ['BSDF_PRINCIPLED', 'EMISSION', 'BSDF_DIFFUSE']]
                print(f"  Material '{material.name}': {len(texture_nodes)} textures, {len(shader_nodes)} shaders")
                for tex_node in texture_nodes:
                    if tex_node.image:
                        print(f"    - Texture: '{tex_node.image.name}' ({tex_node.image.size[0]}×{tex_node.image.size[1]})")
        
        # Store original selection to restore later
        original_selection = []
        original_active = bpy.context.view_layer.objects.active
        for obj in bpy.context.scene.objects:
            if obj.select_get():
                original_selection.append(obj)
        
        # Temporarily restore original materials to the atlas object for baking
        atlas_object.data.materials.clear()
        for material in original_materials:
            atlas_object.data.materials.append(material)
        
        # Select the atlas object for baking
        bpy.ops.object.select_all(action='DESELECT')
        atlas_object.select_set(True)
        bpy.context.view_layer.objects.active = atlas_object
        
        for texture_type, bake_type in bake_types:
            print(f"\nBaking {texture_type} texture...")
            
            # Create atlas texture image
            if texture_type in ['diffuse', 'combined']:
                atlas_image_name = f"{atlas_settings.atlas_name}_BR"
            else:
                atlas_image_name = f"{atlas_settings.atlas_name}_{texture_type}_BR"
            if bpy.data.images.get(atlas_image_name):
                bpy.data.images.remove(bpy.data.images[atlas_image_name])
            
            # Create new image for atlas
            atlas_image = bpy.data.images.new(
                name=atlas_image_name,
                width=atlas_size,
                height=atlas_size,
                alpha=True,
                float_buffer=(texture_type == 'normal')  # Use float for normal maps
            )
            
            # Fill with appropriate default color based on bake type
            if texture_type == 'diffuse':
                atlas_image.pixels[:] = [0.8, 0.8, 0.8, 1.0] * (atlas_size * atlas_size)
            elif texture_type == 'normal':
                atlas_image.pixels[:] = [0.5, 0.5, 1.0, 1.0] * (atlas_size * atlas_size)  # Default normal map
            elif texture_type == 'roughness':
                atlas_image.pixels[:] = [0.5, 0.5, 0.5, 1.0] * (atlas_size * atlas_size)  # Default roughness
            
            # Setup bake target nodes in ALL materials
            bake_nodes_created = []
            for material in atlas_object.data.materials:
                if material and material.use_nodes and material.node_tree:
                    # Create image texture node for baking target
                    bake_node = material.node_tree.nodes.new(type='ShaderNodeTexImage')
                    bake_node.name = f'ATLAS_BAKE_{texture_type}'
                    bake_node.image = atlas_image
                    bake_node.location = (1000, 0)  # Place it far away
                    bake_node.select = True
                    material.node_tree.nodes.active = bake_node
                    bake_nodes_created.append((material, bake_node))
                    print(f"  Created bake target in material: '{material.name}'")
            
            if not bake_nodes_created:
                print(f"Warning: No materials with nodes found for {texture_type} baking")
                continue
            
            # Configure bake settings for better results
            bake_settings_scene = bpy.context.scene.render.bake
            
            if bake_type == 'COMBINED':
                # For COMBINED bake, we want the full appearance including textures
                bake_settings_scene.use_pass_direct = True
                bake_settings_scene.use_pass_indirect = False  # No indirect lighting for cleaner result
                bake_settings_scene.use_pass_color = True  # Include material colors and textures
            elif bake_type == 'DIFFUSE':
                # For DIFFUSE bake (used by _Unlit and _Blend materials), color only
                bake_settings_scene.use_pass_direct = False
                bake_settings_scene.use_pass_indirect = False
                bake_settings_scene.use_pass_color = True  # Color only
            elif bake_type == 'NORMAL':
                # For normal maps, no lighting passes needed
                bake_settings_scene.use_pass_direct = False
                bake_settings_scene.use_pass_indirect = False
                bake_settings_scene.use_pass_color = False
            elif bake_type == 'ROUGHNESS':
                # For roughness, no lighting passes needed
                bake_settings_scene.use_pass_direct = False
                bake_settings_scene.use_pass_indirect = False
                bake_settings_scene.use_pass_color = False
            elif bake_type == 'EMIT':
                # For EMIT bake (used by _Unlit materials), emission only
                # Note: EMIT baking captures emission shader output directly
                bake_settings_scene.use_pass_direct = False
                bake_settings_scene.use_pass_indirect = False
                bake_settings_scene.use_pass_color = True  # Color pass needed for emission
            else:
                # Default settings
                bake_settings_scene.use_pass_direct = True
                bake_settings_scene.use_pass_indirect = True
                bake_settings_scene.use_pass_color = True
            
            bake_settings_scene.margin = 4  # Slightly larger margin for better edges
            bake_settings_scene.use_cage = False
            
            try:
                print(f"  Performing {bake_type} bake...")
                
                # Special handling for COMBINED bake to get textures properly
                if bake_type == 'COMBINED':
                    # Switch to Material Preview shading to ensure textures are visible
                    for area in bpy.context.screen.areas:
                        if area.type == 'VIEW_3D':
                            for space in area.spaces:
                                if space.type == 'VIEW_3D':
                                    space.shading.type = 'MATERIAL'
                                    break
                    
                    # Ensure all materials are set to use material output
                    for material in atlas_object.data.materials:
                        if material and material.use_nodes:
                            # Make sure there's a material output connected
                            output_nodes = [node for node in material.node_tree.nodes if node.type == 'OUTPUT_MATERIAL']
                            if output_nodes:
                                output_node = output_nodes[0]
                                # Ensure something is connected to the output
                                if not output_node.inputs['Surface'].is_linked:
                                    # Find a shader node to connect
                                    shader_nodes = [node for node in material.node_tree.nodes if node.type in ['BSDF_PRINCIPLED', 'EMISSION', 'BSDF_DIFFUSE']]
                                    if shader_nodes:
                                        material.node_tree.links.new(shader_nodes[0].outputs[0], output_node.inputs['Surface'])
                
                # Perform the actual bake
                bpy.ops.object.bake(
                    type=bake_type,
                    margin=4,
                    use_selected_to_active=False
                )
                
                atlas_textures[texture_type] = atlas_image
                print(f"  ✓ Successfully baked {texture_type} atlas texture")
                
                # Save atlas texture if requested
                if atlas_settings.save_atlas_textures:
                    save_atlas_texture(atlas_image, texture_type, atlas_settings)
                
            except Exception as e:
                print(f"  ✗ Failed to bake {texture_type}: {str(e)}")
                # Don't add failed texture to atlas_textures
            
            # Clean up bake nodes from all materials
            for material, bake_node in bake_nodes_created:
                try:
                    material.node_tree.nodes.remove(bake_node)
                except:
                    pass  # Node might already be removed
        
        # Restore original render settings
        bpy.context.scene.render.engine = original_engine
        if hasattr(bpy.context.scene, 'cycles'):
            bpy.context.scene.cycles.samples = original_samples
        
        # Restore original selection
        bpy.ops.object.select_all(action='DESELECT')
        for obj in original_selection:
            if obj.name in bpy.data.objects:  # Check if object still exists
                obj.select_set(True)
        if original_active and original_active.name in bpy.data.objects:
            bpy.context.view_layer.objects.active = original_active
        
        print(f"✓ Atlas texture baking complete! Created {len(atlas_textures)} atlas textures")
        if atlas_textures:
            for tex_type, image in atlas_textures.items():
                print(f"  • {tex_type}: '{image.name}' ({image.size[0]}×{image.size[1]})")
        
        return atlas_textures
        
    except Exception as e:
        error_msg = f"Error baking textures to atlas: {str(e)}"
        print(error_msg)
        
        # Restore original render settings
        try:
            bpy.context.scene.render.engine = original_engine
            if hasattr(bpy.context.scene, 'cycles'):
                bpy.context.scene.cycles.samples = original_samples
            
            # Restore original selection even on error
            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selection:
                if obj.name in bpy.data.objects:  # Check if object still exists
                    obj.select_set(True)
            if original_active and original_active.name in bpy.data.objects:
                bpy.context.view_layer.objects.active = original_active
        except:
            pass
        
        return {}


def bake_combined_atlas_texture(atlas_object, atlas_settings):
    """
    Simple function to bake the combined appearance of all materials into a single atlas texture.
    Returns: dict with the baked atlas texture
    """
    try:
        if not atlas_object or not atlas_object.data:
            print("No atlas object for baking")
            return {}
        
        # Store original settings
        original_engine = bpy.context.scene.render.engine
        original_samples = getattr(bpy.context.scene.cycles, 'samples', 128)
        
        # Set up Cycles for baking
        bpy.context.scene.render.engine = 'CYCLES'
        if hasattr(bpy.context.scene, 'cycles'):
            bpy.context.scene.cycles.samples = atlas_settings.bake_samples
            bpy.context.scene.cycles.use_denoising = True
        
        # Get atlas size
        atlas_size = int(atlas_settings.atlas_size)
        
        # Create the atlas texture
        atlas_image_name = f"{atlas_settings.atlas_name}_BR"
        if bpy.data.images.get(atlas_image_name):
            bpy.data.images.remove(bpy.data.images[atlas_image_name])
        
        atlas_image = bpy.data.images.new(
            name=atlas_image_name,
            width=atlas_size,
            height=atlas_size,
            alpha=True
        )
        
        # Store original selection to restore later
        original_selection = []
        original_active = bpy.context.view_layer.objects.active
        for obj in bpy.context.scene.objects:
            if obj.select_get():
                original_selection.append(obj)
        
        # Select the atlas object
        bpy.ops.object.select_all(action='DESELECT')
        atlas_object.select_set(True)
        bpy.context.view_layer.objects.active = atlas_object
        
        # Add bake target nodes to all materials
        bake_nodes = []
        for material in atlas_object.data.materials:
            if material and material.use_nodes:
                bake_node = material.node_tree.nodes.new(type='ShaderNodeTexImage')
                bake_node.name = 'ATLAS_BAKE_TARGET'
                bake_node.image = atlas_image
                bake_node.location = (1000, 0)
                bake_node.select = True
                material.node_tree.nodes.active = bake_node
                bake_nodes.append((material, bake_node))
        
        if not bake_nodes:
            print("No materials found for baking")
            return {}
        
        # Set up bake settings
        bake_settings = bpy.context.scene.render.bake
        bake_settings.use_pass_direct = True
        bake_settings.use_pass_indirect = False  # Avoid complex lighting
        bake_settings.use_pass_color = True
        bake_settings.margin = 4
        bake_settings.use_cage = False
        
        try:
            print(f"Baking combined appearance to {atlas_size}×{atlas_size} texture...")
            
            # Ensure object is selected and active
            bpy.ops.object.select_all(action='DESELECT')
            atlas_object.select_set(True)
            bpy.context.view_layer.objects.active = atlas_object
            
            # Enter Edit mode and select all faces to ensure complete baking
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            
            # Check that we have faces selected
            selected_faces = sum(1 for face in atlas_object.data.polygons if face.select)
            total_faces = len(atlas_object.data.polygons)
            print(f"Selected {selected_faces}/{total_faces} faces for baking")
            
            # Return to Object mode for baking
            bpy.ops.object.mode_set(mode='OBJECT')
            
            # Set up render engine for baking
            original_engine = bpy.context.scene.render.engine
            bpy.context.scene.render.engine = 'CYCLES'
            
            # Bake COMBINED to get the full visual appearance
            bpy.ops.object.bake(
                type='COMBINED',
                margin=16,  # Even larger margin to avoid black edges
                use_selected_to_active=False,
                use_clear=True  # Clear the image before baking
            )
            
            # Restore original render engine
            bpy.context.scene.render.engine = original_engine
            
            print("✓ Successfully baked combined atlas texture")
            
            # Check if the image has meaningful content
            if atlas_image:
                # Get some pixel data to check if texture is mostly empty
                pixels = atlas_image.pixels[:]
                non_black_pixels = sum(1 for i in range(0, len(pixels), 4) 
                                     if pixels[i] > 0.1 or pixels[i+1] > 0.1 or pixels[i+2] > 0.1)
                total_pixels = len(pixels) // 4
                coverage = non_black_pixels / total_pixels * 100
                print(f"Atlas texture coverage: {coverage:.1f}% non-black pixels")
                
                # If coverage is very low, there might be an issue
                if coverage < 10.0:
                    print("WARNING: Very low texture coverage - most of atlas is black!")
                    print("This suggests UV mapping or baking issues")
            
            # Save if requested
            if atlas_settings.save_atlas_textures:
                save_atlas_texture(atlas_image, "combined", atlas_settings)
            
            # Clean up bake nodes
            for material, bake_node in bake_nodes:
                try:
                    material.node_tree.nodes.remove(bake_node)
                except:
                    pass
            
            # Restore original settings
            bpy.context.scene.render.engine = original_engine
            if hasattr(bpy.context.scene, 'cycles'):
                bpy.context.scene.cycles.samples = original_samples
            
            # Restore original selection
            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selection:
                if obj.name in bpy.data.objects:  # Check if object still exists
                    obj.select_set(True)
            if original_active and original_active.name in bpy.data.objects:
                bpy.context.view_layer.objects.active = original_active
            
            return {'diffuse': atlas_image}
            
        except Exception as e:
            print(f"✗ Baking failed: {str(e)}")
            # Clean up on failure
            for material, bake_node in bake_nodes:
                try:
                    material.node_tree.nodes.remove(bake_node)
                except:
                    pass
            
            # Restore original selection even on error
            try:
                bpy.ops.object.select_all(action='DESELECT')
                for obj in original_selection:
                    if obj.name in bpy.data.objects:  # Check if object still exists
                        obj.select_set(True)
                if original_active and original_active.name in bpy.data.objects:
                    bpy.context.view_layer.objects.active = original_active
            except:
                pass
            
            return {}
        
    except Exception as e:
        print(f"Error in atlas baking: {str(e)}")
        
        # Restore original selection even on outer exception
        try:
            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selection:
                if obj.name in bpy.data.objects:  # Check if object still exists
                    obj.select_set(True)
            if original_active and original_active.name in bpy.data.objects:
                bpy.context.view_layer.objects.active = original_active
        except:
            pass
        
        return {}


def save_atlas_texture(atlas_image, texture_type, atlas_settings):
    """Save atlas texture to disk"""
    try:
        # Ensure output directory exists
        output_dir = bpy.path.abspath(atlas_settings.atlas_output_directory)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Generate filename
        if texture_type in ['diffuse', 'combined']:
            filename = f"{atlas_settings.atlas_name}_BR.png"
        else:
            filename = f"{atlas_settings.atlas_name}_{texture_type}_BR.png"
        filepath = os.path.join(output_dir, filename)
        
        # Set image format
        atlas_image.file_format = 'PNG'
        
        # Save image
        atlas_image.filepath_raw = filepath
        atlas_image.save()
        
        print(f"💾 Saved atlas texture: {filepath}")
        
    except Exception as e:
        print(f"✗ Error saving atlas texture: {str(e)}")


class META_HORIZON_OT_create_material_for_slot(Operator):
    """Create a new material for an empty material slot"""
    bl_idname = "meta_horizon.create_material_for_slot"
    bl_label = "Create Material"
    bl_description = "Create a new material for this empty slot"
    bl_options = {'REGISTER', 'UNDO'}

    object_name: StringProperty(
        name="Object Name",
        description="Name of the object with empty slots"
    )
    
    slot_indices: StringProperty(
        name="Slot Indices",
        description="Comma-separated slot indices to fill"
    )
    
    material_name: StringProperty(
        name="Material Name",
        description="Name for the new material",
        default="NewMaterial"
    )
    
    setup_type: EnumProperty(
        name="Setup Type",
        description="Type of material to create",
        items=[
            ('BASE_PBR', "Base PBR", "Standard Principled BSDF material"),
            ('UNLIT', "Unlit", "Emission-based unlit material"),
            ('BLEND', "Blend", "Unlit material with alpha blending"),
            ('TRANSPARENT', "Transparent", "Transparent material"),
            ('VERTEX_COLOR', "Vertex Color", "Material using vertex colors"),
        ],
        default='BASE_PBR'
    )

    def execute(self, context):
        if not self.object_name:
            self.report({'WARNING'}, "No object name provided")
            return {'CANCELLED'}
        
        # Find the object
        obj = bpy.data.objects.get(self.object_name)
        if not obj:
            self.report({'WARNING'}, f"Object '{self.object_name}' not found")
            return {'CANCELLED'}
        
        if not obj.data or not hasattr(obj.data, 'materials'):
            self.report({'WARNING'}, f"Object '{self.object_name}' doesn't support materials")
            return {'CANCELLED'}
        
        # Parse slot indices
        try:
            slot_indices = [int(x.strip()) for x in self.slot_indices.split(',')]
        except ValueError:
            self.report({'WARNING'}, "Invalid slot indices format")
            return {'CANCELLED'}
        
        # Create the material
        material_name = self.material_name
        if self.setup_type == 'UNLIT' and not material_name.endswith('_Unlit'):
            material_name += '_Unlit'
        elif self.setup_type == 'BLEND' and not material_name.endswith('_Blend'):
            material_name += '_Blend'
        elif self.setup_type == 'TRANSPARENT' and not material_name.endswith('_Transparent'):
            material_name += '_Transparent'
        elif self.setup_type == 'VERTEX_COLOR' and not material_name.endswith('_VXC'):
            material_name += '_VXC'
        
        # Ensure unique name
        base_name = material_name
        counter = 1
        while bpy.data.materials.get(material_name):
            material_name = f"{base_name}.{counter:03d}"
            counter += 1
        
        material = bpy.data.materials.new(name=material_name)
        material.use_nodes = True
        material.node_tree.nodes.clear()
        
        # Create material output node
        output_node = material.node_tree.nodes.new(type='ShaderNodeOutputMaterial')
        output_node.location = (300, 0)
        
        if self.setup_type == 'BASE_PBR':
            # Create Principled BSDF
            principled_node = material.node_tree.nodes.new(type='ShaderNodeBsdfPrincipled')
            principled_node.location = (0, 0)
            material.node_tree.links.new(principled_node.outputs['BSDF'], output_node.inputs['Surface'])
            principled_node.inputs['Base Color'].default_value = (0.8, 0.8, 0.8, 1.0)
            principled_node.inputs['Metallic'].default_value = 0.0
            principled_node.inputs['Roughness'].default_value = 0.5
            
        elif self.setup_type == 'UNLIT':
            # Create Emission shader
            emission_node = material.node_tree.nodes.new(type='ShaderNodeEmission')
            emission_node.location = (0, 0)
            material.node_tree.links.new(emission_node.outputs['Emission'], output_node.inputs['Surface'])
            emission_node.inputs['Color'].default_value = (0.8, 0.8, 0.8, 1.0)
            emission_node.inputs['Strength'].default_value = 1.0
                
        elif self.setup_type == 'BLEND':
            # Create Emission shader for unlit blend material (no transparency in viewport)
            emission_node = material.node_tree.nodes.new(type='ShaderNodeEmission')
            emission_node.location = (0, 0)
            material.node_tree.links.new(emission_node.outputs['Emission'], output_node.inputs['Surface'])
            emission_node.inputs['Color'].default_value = (0.8, 0.8, 0.8, 1.0)
            emission_node.inputs['Strength'].default_value = 1.0
            
            # Keep as opaque in viewport - alpha is handled during export to BA texture
                
        elif self.setup_type == 'TRANSPARENT':
            # Create Principled BSDF with transparency
            principled_node = material.node_tree.nodes.new(type='ShaderNodeBsdfPrincipled')
            principled_node.location = (0, 0)
            material.node_tree.links.new(principled_node.outputs['BSDF'], output_node.inputs['Surface'])
            principled_node.inputs['Base Color'].default_value = (0.8, 0.8, 0.8, 1.0)
            principled_node.inputs['Alpha'].default_value = 0.5
            principled_node.inputs['Metallic'].default_value = 0.0
            principled_node.inputs['Roughness'].default_value = 0.1
            material.blend_method = 'BLEND'
                
        elif self.setup_type == 'VERTEX_COLOR':
            # Create Principled BSDF with vertex color input
            principled_node = material.node_tree.nodes.new(type='ShaderNodeBsdfPrincipled')
            principled_node.location = (0, 0)
            vertex_color_node = material.node_tree.nodes.new(type='ShaderNodeAttribute')
            vertex_color_node.location = (-300, 0)
            vertex_color_node.attribute_name = "Col"
            material.node_tree.links.new(vertex_color_node.outputs['Color'], principled_node.inputs['Base Color'])
            material.node_tree.links.new(principled_node.outputs['BSDF'], output_node.inputs['Surface'])
            principled_node.inputs['Metallic'].default_value = 0.0
            principled_node.inputs['Roughness'].default_value = 0.5
        
        # Assign material to the specified slots
        assigned_slots = []
        for slot_index in slot_indices:
            if slot_index < len(obj.data.materials):
                obj.data.materials[slot_index] = material
                assigned_slots.append(slot_index)
        
        if assigned_slots:
            self.report({'INFO'}, f"Created material '{material_name}' and assigned to slots {assigned_slots} on '{self.object_name}'")
        else:
            self.report({'WARNING'}, f"Created material '{material_name}' but couldn't assign to any slots")
        
        # Refresh the material analysis
        if context.scene.horizon_export_settings.analyze_all_materials:
            bpy.ops.meta_horizon.analyze_all_materials()
        else:
            bpy.ops.meta_horizon.analyze_materials()
        
        return {'FINISHED'}

    def invoke(self, context, event):
        # Set a default material name based on object
        if self.object_name and not self.material_name:
            self.material_name = f"{self.object_name}Material"
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "material_name")
        layout.prop(self, "setup_type")


class META_HORIZON_OT_setup_empty_material(Operator):
    """Setup empty material with basic Meta Horizon compatible nodes"""
    bl_idname = "meta_horizon.setup_empty_material"
    bl_label = "Setup Empty Material"
    bl_description = "Setup empty material with basic Principled BSDF for Meta Horizon Worlds compatibility"
    bl_options = {'REGISTER', 'UNDO'}

    material_name: StringProperty(
        name="Material Name",
        description="Name of the material to setup"
    )
    
    setup_type: EnumProperty(
        name="Setup Type",
        description="Type of material to create",
        items=[
            ('BASE_PBR', "Base PBR", "Standard Principled BSDF material"),
            ('UNLIT', "Unlit", "Emission-based unlit material"),
            ('BLEND', "Blend", "Unlit material with alpha blending"),
            ('TRANSPARENT', "Transparent", "Transparent material"),
            ('VERTEX_COLOR', "Vertex Color", "Material using vertex colors"),
        ],
        default='BASE_PBR'
    )

    def execute(self, context):
        if not self.material_name:
            self.report({'WARNING'}, "No material name provided")
            return {'CANCELLED'}
        
        # Find the material
        material = bpy.data.materials.get(self.material_name)
        if not material:
            self.report({'WARNING'}, f"Material '{self.material_name}' not found")
            return {'CANCELLED'}
        
        # Enable nodes if not already enabled
        if not material.use_nodes:
            material.use_nodes = True
        
        # Clear existing nodes if any
        material.node_tree.nodes.clear()
        
        # Create material output node
        output_node = material.node_tree.nodes.new(type='ShaderNodeOutputMaterial')
        output_node.location = (300, 0)
        
        if self.setup_type == 'BASE_PBR':
            # Create Principled BSDF
            principled_node = material.node_tree.nodes.new(type='ShaderNodeBsdfPrincipled')
            principled_node.location = (0, 0)
            material.node_tree.links.new(principled_node.outputs['BSDF'], output_node.inputs['Surface'])
            
            # Set default PBR values
            principled_node.inputs['Base Color'].default_value = (0.8, 0.8, 0.8, 1.0)
            principled_node.inputs['Metallic'].default_value = 0.0
            principled_node.inputs['Roughness'].default_value = 0.5
            
        elif self.setup_type == 'UNLIT':
            # Create Emission shader
            emission_node = material.node_tree.nodes.new(type='ShaderNodeEmission')
            emission_node.location = (0, 0)
            material.node_tree.links.new(emission_node.outputs['Emission'], output_node.inputs['Surface'])
            
            # Set default emission values
            emission_node.inputs['Color'].default_value = (0.8, 0.8, 0.8, 1.0)
            emission_node.inputs['Strength'].default_value = 1.0
            
            # Update material name to include _Unlit suffix if not present
            if not material.name.endswith('_Unlit'):
                material.name = material.name + '_Unlit'
                
        elif self.setup_type == 'BLEND':
            # Create Emission shader for unlit blend material (no transparency in viewport)
            emission_node = material.node_tree.nodes.new(type='ShaderNodeEmission')
            emission_node.location = (0, 0)
            material.node_tree.links.new(emission_node.outputs['Emission'], output_node.inputs['Surface'])
            
            # Set default emission values for unlit blend material
            emission_node.inputs['Color'].default_value = (0.8, 0.8, 0.8, 1.0)
            emission_node.inputs['Strength'].default_value = 1.0
            
            # Keep as opaque in viewport - alpha is handled during export to BA texture
            
            # Update material name to include _Blend suffix if not present
            if not material.name.endswith('_Blend'):
                material.name = material.name + '_Blend'
                
        elif self.setup_type == 'TRANSPARENT':
            # Create Principled BSDF with transparency
            principled_node = material.node_tree.nodes.new(type='ShaderNodeBsdfPrincipled')
            principled_node.location = (0, 0)
            material.node_tree.links.new(principled_node.outputs['BSDF'], output_node.inputs['Surface'])
            
            # Set transparent properties
            principled_node.inputs['Base Color'].default_value = (0.8, 0.8, 0.8, 1.0)
            principled_node.inputs['Alpha'].default_value = 0.5
            principled_node.inputs['Metallic'].default_value = 0.0
            principled_node.inputs['Roughness'].default_value = 0.1
            
            # Set material blend mode
            material.blend_method = 'BLEND'
            
            # Update material name to include _Transparent suffix if not present
            if not material.name.endswith('_Transparent'):
                material.name = material.name + '_Transparent'
                
        elif self.setup_type == 'VERTEX_COLOR':
            # Create Principled BSDF with vertex color input
            principled_node = material.node_tree.nodes.new(type='ShaderNodeBsdfPrincipled')
            principled_node.location = (0, 0)
            
            # Create Vertex Color attribute node
            vertex_color_node = material.node_tree.nodes.new(type='ShaderNodeAttribute')
            vertex_color_node.location = (-300, 0)
            vertex_color_node.attribute_name = "Col"  # Default vertex color attribute
            
            # Connect vertex color to base color
            material.node_tree.links.new(vertex_color_node.outputs['Color'], principled_node.inputs['Base Color'])
            material.node_tree.links.new(principled_node.outputs['BSDF'], output_node.inputs['Surface'])
            
            # Set default PBR values
            principled_node.inputs['Metallic'].default_value = 0.0
            principled_node.inputs['Roughness'].default_value = 0.5
            
            # Update material name to include _VXC suffix if not present
            if not material.name.endswith('_VXC'):
                material.name = material.name + '_VXC'
        
        self.report({'INFO'}, f"Successfully setup '{self.material_name}' as {self.setup_type.replace('_', ' ').title()} material")
        
        # Refresh the material analysis
        bpy.ops.meta_horizon.analyze_materials()
        
        return {'FINISHED'}

    def invoke(self, context, event):
        # Show a popup to choose setup type
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "setup_type")


class META_HORIZON_OT_convert_glass_to_principled(Operator):
    """Convert Glass BSDF material to Principled BSDF with transparency for Meta Horizon compatibility"""
    bl_idname = "meta_horizon.convert_glass_to_principled"
    bl_label = "Convert to Principled BSDF"
    bl_description = "Convert Glass BSDF to Principled BSDF with transparency for Meta Horizon Worlds compatibility"
    bl_options = {'REGISTER', 'UNDO'}

    material_name: StringProperty(
        name="Material Name",
        description="Name of the material to convert"
    )

    def execute(self, context):
        if not self.material_name:
            self.report({'WARNING'}, "No material name provided")
            return {'CANCELLED'}
        
        # Find the material
        material = bpy.data.materials.get(self.material_name)
        if not material:
            self.report({'WARNING'}, f"Material '{self.material_name}' not found")
            return {'CANCELLED'}
        
        if not material.use_nodes or not material.node_tree:
            self.report({'WARNING'}, f"Material '{self.material_name}' does not use nodes")
            return {'CANCELLED'}
        
        # Find Glass BSDF node
        glass_node = None
        for node in material.node_tree.nodes:
            if node.type == 'BSDF_GLASS':
                glass_node = node
                break
        
        if not glass_node:
            self.report({'WARNING'}, f"No Glass BSDF node found in material '{self.material_name}'")
            return {'CANCELLED'}
        
        # Find material output node
        output_node = None
        for node in material.node_tree.nodes:
            if node.type == 'OUTPUT_MATERIAL':
                output_node = node
                break
        
        if not output_node:
            self.report({'WARNING'}, f"No Material Output node found in material '{self.material_name}'")
            return {'CANCELLED'}
        
        # Create Principled BSDF node
        principled_node = material.node_tree.nodes.new(type='ShaderNodeBsdfPrincipled')
        principled_node.location = glass_node.location
        
        # Transfer properties from Glass BSDF to Principled BSDF
        # Glass BSDF typically has: Color, Roughness, IOR
        
        # Transfer Color if connected or set
        if glass_node.inputs['Color'].is_linked:
            # Get the linked node and connect it to Base Color
            color_link = glass_node.inputs['Color'].links[0]
            material.node_tree.links.new(color_link.from_socket, principled_node.inputs['Base Color'])
        else:
            # Copy the default value
            principled_node.inputs['Base Color'].default_value = glass_node.inputs['Color'].default_value
        
        # Transfer Roughness if connected or set
        if glass_node.inputs['Roughness'].is_linked:
            roughness_link = glass_node.inputs['Roughness'].links[0]
            material.node_tree.links.new(roughness_link.from_socket, principled_node.inputs['Roughness'])
        else:
            principled_node.inputs['Roughness'].default_value = glass_node.inputs['Roughness'].default_value
        
        # Transfer IOR if connected or set
        if glass_node.inputs['IOR'].is_linked:
            ior_link = glass_node.inputs['IOR'].links[0]
            material.node_tree.links.new(ior_link.from_socket, principled_node.inputs['IOR'])
        else:
            principled_node.inputs['IOR'].default_value = glass_node.inputs['IOR'].default_value
        
        # Set up transparency for Meta Horizon Worlds compatibility
        # Meta Horizon doesn't support transmission/refraction, so we use alpha transparency instead
        
        # Set alpha for transparency (Meta Horizon uses alpha channel for transparency)
        principled_node.inputs['Alpha'].default_value = 0.15
        
        # Set up basic PBR properties for transparent material
        # Keep metallic at 0 for glass-like materials
        principled_node.inputs['Metallic'].default_value = 0.0
        
        # Set a low roughness for glass-like reflection
        if not principled_node.inputs['Roughness'].is_linked:
            principled_node.inputs['Roughness'].default_value = 0.1
        
        # Connect Principled BSDF to Material Output
        material.node_tree.links.new(principled_node.outputs['BSDF'], output_node.inputs['Surface'])
        
        # Set material blend mode for transparency
        material.blend_method = 'BLEND'
        material.show_transparent_back = False  # Usually better for glass materials
        
        # Remove the Glass BSDF node
        material.node_tree.nodes.remove(glass_node)
        
        # Update the material name to include _Transparent suffix if not already present
        if not material.name.endswith('_Transparent'):
            # Check if material name ends with any valid suffix first
            valid_suffixes = ['_Metal', '_Unlit', '_Blend', '_Transparent', '_Masked', '_VXC', '_VXM', '_UIO']
            has_suffix = any(material.name.endswith(suffix) for suffix in valid_suffixes)
            
            if not has_suffix:
                material.name = material.name + '_Transparent'
        
        self.report({'INFO'}, f"Successfully converted '{self.material_name}' from Glass BSDF to Principled BSDF with transparency")
        
        # Refresh the material analysis
        bpy.ops.meta_horizon.analyze_materials()
        
        return {'FINISHED'}


class META_HORIZON_OT_select_objects_by_material(Operator):
    """Select all objects using a specific material"""
    bl_idname = "meta_horizon.select_objects_by_material"
    bl_label = "Select Objects"
    bl_description = "Select all objects using this material"
    bl_options = {'REGISTER', 'UNDO'}

    material_name: StringProperty(
        name="Material Name",
        description="Name of the material to select objects for"
    )

    def execute(self, context):
        if not self.material_name:
            self.report({'WARNING'}, "No material name provided")
            return {'CANCELLED'}
        
        # Find the material
        material = bpy.data.materials.get(self.material_name)
        if not material:
            self.report({'WARNING'}, f"Material '{self.material_name}' not found")
            return {'CANCELLED'}
        
        # Clear current selection
        bpy.ops.object.select_all(action='DESELECT')
        
        # Find and select all objects using this material
        selected_objects = []
        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH' and obj.data and obj.data.materials:
                for slot in obj.material_slots:
                    if slot.material and slot.material.name == self.material_name:
                        obj.select_set(True)
                        selected_objects.append(obj.name)
                        break
        
        if selected_objects:
            # Set the first selected object as active
            if selected_objects:
                first_obj = bpy.context.scene.objects.get(selected_objects[0])
                if first_obj:
                    bpy.context.view_layer.objects.active = first_obj
            
            self.report({'INFO'}, f"Selected {len(selected_objects)} objects using material '{self.material_name}'")
        else:
            self.report({'WARNING'}, f"No objects found using material '{self.material_name}'")
        
        return {'FINISHED'}


class META_HORIZON_OT_test_vxm_double_texture(Operator):
    """Test VXM double-texture PBR functionality"""
    bl_idname = "meta_horizon.test_vxm_double_texture"
    bl_label = "Test VXM Double-Texture"
    bl_description = "Test the VXM double-texture PBR functionality"
    bl_options = {'REGISTER'}

    material_name: StringProperty(
        name="Material Name",
        description="Name of the VXM material to test (leave empty to test all VXM materials)",
        default=""
    )

    def execute(self, context):
        try:
            if self.material_name:
                # Test specific material
                material = bpy.data.materials.get(self.material_name)
                if not material:
                    self.report({'ERROR'}, f"Material '{self.material_name}' not found")
                    return {'CANCELLED'}
                
                print(f"\n=== Testing specific VXM material: '{self.material_name}' ===")
                base_name, material_type, texture_info = get_meta_horizon_texture_info(material.name, material)
                print(f"Material type: {material_type}")
                print(f"Textures: {[suffix for suffix, _, _ in texture_info]}")
                
                if material_type == "VXM":
                    texture_count = len(texture_info)
                    has_meo = any(suffix == "_MEO" for suffix, _, _ in texture_info)
                    self.report({'INFO'}, f"VXM material '{self.material_name}': {texture_count} textures {'(with _MEO)' if has_meo else '(_BR only)'}")
                else:
                    self.report({'WARNING'}, f"Material '{self.material_name}' is not a VXM material (type: {material_type})")
            else:
                # Test all VXM materials
                vxm_materials = [mat for mat in bpy.data.materials if mat.name.endswith('_VXM')]
                if not vxm_materials:
                    self.report({'WARNING'}, "No VXM materials found in scene")
                    return {'FINISHED'}
                
                print(f"\n=== Testing all {len(vxm_materials)} VXM materials ===")
                for material in vxm_materials:
                    print(f"\n--- Testing material: '{material.name}' ---")
                    base_name, material_type, texture_info = get_meta_horizon_texture_info(material.name, material)
                    texture_count = len(texture_info)
                    has_meo = any(suffix == "_MEO" for suffix, _, _ in texture_info)
                    print(f"Result: {texture_count} textures {'(with _MEO)' if has_meo else '(_BR only)'}")
                
                self.report({'INFO'}, f"Tested {len(vxm_materials)} VXM materials. Check console for details.")
                
            
        except Exception as e:
            self.report({'ERROR'}, f"VXM double-texture test failed: {str(e)}")
            return {'CANCELLED'}
        
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


class META_HORIZON_OT_apply_recommended_name(Operator):
    """Apply recommended name to material following Meta Horizon naming conventions"""
    bl_idname = "meta_horizon.apply_recommended_name"
    bl_label = "Apply Recommended Name"
    bl_description = "Rename material to follow Meta Horizon Worlds naming conventions"
    bl_options = {'REGISTER', 'UNDO'}

    material_name: StringProperty(
        name="Current Material Name",
        description="Current name of the material to rename"
    )
    
    recommended_name: StringProperty(
        name="Recommended Name",
        description="Recommended name following Meta Horizon conventions"
    )

    def execute(self, context):
        if not self.material_name:
            self.report({'WARNING'}, "No material name provided")
            return {'CANCELLED'}
        
        if not self.recommended_name:
            self.report({'WARNING'}, "No recommended name provided")
            return {'CANCELLED'}
        
        # Find the material
        material = bpy.data.materials.get(self.material_name)
        if not material:
            self.report({'WARNING'}, f"Material '{self.material_name}' not found")
            return {'CANCELLED'}
        
        # Store the old name for the report
        old_name = material.name
        
        # Generate a unique name based on the recommendation
        unique_name = generate_unique_material_name(self.recommended_name, exclude_material=material)
        
        # Apply the unique name
        material.name = unique_name
        
        # Report success
        if old_name != unique_name:
            if unique_name != self.recommended_name:
                self.report({'INFO'}, f"Renamed material from '{old_name}' to '{unique_name}' (resolved name conflict)")
            else:
                self.report({'INFO'}, f"Renamed material from '{old_name}' to '{unique_name}'")
            
            # Refresh the material analysis to show the updated state
            if context.scene.horizon_export_settings.analyze_all_materials:
                bpy.ops.meta_horizon.analyze_all_materials()
            else:
                bpy.ops.meta_horizon.analyze_materials()
        else:
            self.report({'INFO'}, f"Material '{self.material_name}' already has the recommended name")
        
        return {'FINISHED'}


class META_HORIZON_OT_choose_material_suffix(Operator):
    """Choose material suffix with explanations for naming conventions"""
    bl_idname = "meta_horizon.choose_material_suffix"
    bl_label = "Edit Material Type"
    bl_description = "Edit the base material name and choose the appropriate suffix type with detailed explanations"
    bl_options = {'REGISTER', 'UNDO'}

    material_name: StringProperty(
        name="Material Name",
        description="Name of the material to edit"
    )
    
    base_material_name: StringProperty(
        name="Base Material Name",
        description="Custom base name for the material (leave empty to use auto-generated base name)",
        default=""
    )
    
    chosen_suffix: EnumProperty(
        name="Choose Suffix",
        description="Select the appropriate suffix for your material",
        items=[
            ('NONE', "No Suffix (Base PBR)", "Standard PBR material with BaseColor + Roughness"),
            ('METAL', "_Metal", "Metallic PBR material (metalness = 1.0)"),
            ('TRANSPARENT', "_Transparent", "Transparent material with alpha blending"),
            ('UNLIT', "_Unlit", "Unlit material (no lighting calculations)"),
            ('BLEND', "_Blend", "Unlit material with alpha support (not transparent in viewport)"),
            ('MASKED', "_Masked", "Alpha-masked material (alpha cutoff at 0.5)"),
            ('VXC', "_VXC", "Vertex Color PBR (uses mesh vertex colors only)"),
            ('VXM', "_VXM", "Vertex Color Double-Texture PBR (vertex colors multiplied with textures)"),
            ('UIO', "_UIO", "UI Optimized material (for text and UI elements)"),
        ],
        default='NONE'
    )

    def execute(self, context):
        if not self.material_name:
            self.report({'WARNING'}, "No material name provided")
            return {'CANCELLED'}
        
        # Find the material
        material = bpy.data.materials.get(self.material_name)
        if not material:
            self.report({'WARNING'}, f"Material '{self.material_name}' not found")
            return {'CANCELLED'}
        
        # Use custom base name if provided, otherwise generate one
        if self.base_material_name.strip():
            # Use custom base name
            base_name = self.base_material_name.strip()
            
            # Clean the custom base name - remove invalid characters but preserve camelCase
            invalid_chars = ['-', '.', ',', '/', '*', '$', '&']
            for char in invalid_chars:
                base_name = base_name.replace(char, '')
        else:
            # Generate base name automatically
            clean_name = self.material_name
            
            # Remove invalid characters
            invalid_chars = ['-', '.', ',', '/', '*', '$', '&']
            for char in invalid_chars:
                clean_name = clean_name.replace(char, '')
            
            # Remove existing valid suffixes
            valid_suffixes = ['_Metal', '_Unlit', '_Blend', '_Transparent', '_Masked', '_VXC', '_VXM', '_UIO']
            base_name = clean_name
            for suffix in valid_suffixes:
                if clean_name.endswith(suffix):
                    base_name = clean_name[:-len(suffix)]
                    break
            
            # Convert to camelCase
            if '_' in base_name or ' ' in base_name:
                base_name = base_name.replace(' ', '_')
                parts = base_name.split('_')
                base_name = ''.join(part.capitalize() for part in parts if part)
                if base_name:
                    base_name = base_name[0].lower() + base_name[1:]
        
        # Apply the chosen suffix
        if self.chosen_suffix == 'NONE':
            new_name = base_name
        elif self.chosen_suffix == 'METAL':
            new_name = base_name + '_Metal'
        elif self.chosen_suffix == 'TRANSPARENT':
            new_name = base_name + '_Transparent'
        elif self.chosen_suffix == 'UNLIT':
            new_name = base_name + '_Unlit'
        elif self.chosen_suffix == 'BLEND':
            new_name = base_name + '_Blend'
        elif self.chosen_suffix == 'MASKED':
            new_name = base_name + '_Masked'
        elif self.chosen_suffix == 'VXC':
            new_name = base_name + '_VXC'
        elif self.chosen_suffix == 'VXM':
            new_name = base_name + '_VXM'
        elif self.chosen_suffix == 'UIO':
            new_name = base_name + '_UIO'
        else:
            new_name = base_name
        
        # Generate unique name
        unique_name = generate_unique_material_name(new_name, exclude_material=material)
        
        # Store the old name for the report
        old_name = material.name
        
        # Apply the new name
        material.name = unique_name
        
        # Report success
        suffix_display = self.chosen_suffix.replace('_', '') if self.chosen_suffix != 'NONE' else 'Base PBR'
        self.report({'INFO'}, f"Applied {suffix_display} suffix: '{old_name}' → '{unique_name}'")
        
        # Refresh the material analysis to show the updated state
        if context.scene.horizon_export_settings.analyze_all_materials:
            bpy.ops.meta_horizon.analyze_all_materials()
        else:
            bpy.ops.meta_horizon.analyze_materials()
        
        return {'FINISHED'}

    def invoke(self, context, event):
        if not self.material_name:
            self.report({'WARNING'}, "No material name provided")
            return {'CANCELLED'}
        
        # Find the material
        material = bpy.data.materials.get(self.material_name)
        if not material:
            self.report({'WARNING'}, f"Material '{self.material_name}' not found")
            return {'CANCELLED'}
        
        # Analyze the material to set default suggestion
        # Properly detect the main shader node instead of just using nodes[0]
        shader_type = "Unknown"
        if material.use_nodes and material.node_tree and material.node_tree.nodes:
            # Look for the main shader node (Principled BSDF, Emission, etc.)
            for node in material.node_tree.nodes:
                if node.type in ['BSDF_PRINCIPLED', 'EMISSION', 'BSDF_DIFFUSE', 'BSDF_GLOSSY', 'BSDF_TRANSPARENT', 'BSDF_GLASS']:
                    shader_type = node.type
                    break
            # If no shader node found, check if it's a legacy material setup
            if shader_type == "Unknown":
                shader_type = "Legacy Material"
        else:
            shader_type = "Legacy Material"
            
        issues, recommended_name, recommended_suffix = get_material_naming_recommendation(
            self.material_name, 
            shader_type,
            material
        )
        
        # Set the default based on the recommended suffix
        if recommended_suffix == "_Metal":
            self.chosen_suffix = 'METAL'
        elif recommended_suffix == "_Transparent":
            self.chosen_suffix = 'TRANSPARENT'
        elif recommended_suffix == "_Unlit":
            self.chosen_suffix = 'UNLIT'
        elif recommended_suffix == "_Blend":
            self.chosen_suffix = 'BLEND'
        elif recommended_suffix == "_Masked":
            self.chosen_suffix = 'MASKED'
        elif recommended_suffix == "_VXC":
            self.chosen_suffix = 'VXC'
        elif recommended_suffix == "_VXM":
            self.chosen_suffix = 'VXM'
        elif recommended_suffix == "_UIO":
            self.chosen_suffix = 'UIO'
        else:
            self.chosen_suffix = 'NONE'
        
        # Always initialize base material name from the current material
        # Get the cleaned original base name and apply naming convention
        clean_name = self.material_name
        invalid_chars = ['-', '.', ',', '/', '*', '$', '&']
        for char in invalid_chars:
            clean_name = clean_name.replace(char, '')
        
        # Remove protected suffixes to get the original base name
        valid_suffixes = ['_Metal', '_Unlit', '_Blend', '_Transparent', '_Masked', '_VXC', '_VXM', '_UIO']
        base_name = clean_name
        for suffix in valid_suffixes:
            if clean_name.endswith(suffix):
                base_name = clean_name[:-len(suffix)]
                break
        
        # Apply camelCase naming convention to the base name
        if '_' in base_name or ' ' in base_name:
            base_name = base_name.replace(' ', '_')
            parts = base_name.split('_')
            base_name = ''.join(part.capitalize() for part in parts if part)
            if base_name:
                base_name = base_name[0].lower() + base_name[1:]
        
        # Set the base name with proper naming convention
        self.base_material_name = base_name
        
        return context.window_manager.invoke_props_dialog(self, width=500)

    def get_suffix_reasoning(self, material, recommended_suffix):
        """Analyze material properties and provide reasoning for suffix recommendation"""
        reasoning = []
        
        try:
            if not material:
                return reasoning
            
            # Analyze material properties
            if material.use_nodes and material.node_tree:
                # Check for various material properties
                is_transparent = False
                is_emission = False
                has_vertex_colors = False
                is_metallic = False
                alpha_cutoff = False
                metalness_value = 0.0
                
                # Check material blend method
                try:
                    if hasattr(material, 'blend_method'):
                        if material.blend_method in ['BLEND', 'ALPHA']:
                            is_transparent = True
                            reasoning.append(f"Material blend method is '{material.blend_method}' (transparent)")
                        elif material.blend_method == 'CLIP':
                            alpha_cutoff = True
                            reasoning.append(f"Material blend method is 'CLIP' (alpha cutoff)")
                except:
                    pass
                
                # Analyze the node tree for detailed information
                principled_node = None
                has_emission_node = False
                has_transparent_shader = False
                emission_strength = 0.0
                
                try:
                    for node in material.node_tree.nodes:
                        if node.type == 'BSDF_PRINCIPLED':
                            principled_node = node
                            
                            # Check metalness - only suggest _Metal if explicitly > 0
                            try:
                                if 'Metallic' in node.inputs and hasattr(node.inputs['Metallic'], 'default_value'):
                                    metalness_value = node.inputs['Metallic'].default_value
                                    if metalness_value > 0.0:
                                        is_metallic = True
                                        reasoning.append(f"Metallic value is {metalness_value:.2f} (> 0.0)")
                                
                                # Check if metalness input is connected - but don't automatically assume it's metallic
                                if 'Metallic' in node.inputs and node.inputs['Metallic'].is_linked:
                                    # Only mention the connection, don't automatically set as metallic
                                    reasoning.append("Metallic input is connected to a node (but value not determined)")
                            except:
                                pass
                            
                            # Check alpha
                            try:
                                if 'Alpha' in node.inputs and hasattr(node.inputs['Alpha'], 'default_value'):
                                    alpha_value = node.inputs['Alpha'].default_value
                                    if alpha_value < 1.0:
                                        is_transparent = True
                                        reasoning.append(f"Alpha value is {alpha_value:.2f} (< 1.0)")
                                
                                # Check if alpha input is connected
                                if 'Alpha' in node.inputs and node.inputs['Alpha'].is_linked:
                                    is_transparent = True
                                    reasoning.append("Alpha input is connected to a node")
                            except:
                                pass
                            
                            # Check emission
                            try:
                                if 'Emission Strength' in node.inputs and hasattr(node.inputs['Emission Strength'], 'default_value'):
                                    emission_strength = node.inputs['Emission Strength'].default_value
                                    if emission_strength > 0.0:
                                        reasoning.append(f"Emission strength is {emission_strength:.2f} (> 0.0)")
                                
                                # Check if emission input is connected
                                if 'Emission Color' in node.inputs and node.inputs['Emission Color'].is_linked:
                                    reasoning.append("Emission Color input is connected to a node")
                            except:
                                pass
                        
                        elif node.type == 'EMISSION':
                            has_emission_node = True
                            reasoning.append("Material contains Emission shader node")
                            
                            # Check emission strength
                            try:
                                if 'Strength' in node.inputs and hasattr(node.inputs['Strength'], 'default_value'):
                                    emission_strength = node.inputs['Strength'].default_value
                                    if emission_strength > 0.0:
                                        reasoning.append(f"Emission strength is {emission_strength:.2f}")
                            except:
                                pass
                        
                        elif node.type in ['BSDF_TRANSPARENT', 'BSDF_GLASS']:
                            has_transparent_shader = True
                            reasoning.append(f"Material contains {node.type.replace('BSDF_', '')} shader node")
                        
                        elif node.type == 'ATTRIBUTE' and hasattr(node, 'attribute_name'):
                            if 'Col' in node.attribute_name or 'Color' in node.attribute_name:
                                has_vertex_colors = True
                                reasoning.append(f"Material uses vertex colors (attribute: {node.attribute_name})")
                except:
                    pass
                
                # Explain suffix recommendation based on analysis
                if recommended_suffix == "_Metal":
                    if not any("Metallic" in reason for reason in reasoning):
                        reasoning.append("Material appears to be metallic based on shader setup")
                
                elif recommended_suffix == "_Transparent":
                    if not is_transparent and not has_transparent_shader:
                        reasoning.append("Material setup suggests transparency is needed")
                
                elif recommended_suffix == "_Unlit":
                    if has_emission_node and not principled_node:
                        reasoning.append("Pure emission shader detected (no lighting needed)")
                    elif emission_strength > 0.0 and not is_transparent:
                        reasoning.append("Material has emission properties (unlit recommended)")
                    else:
                        reasoning.append("Material setup suggests unlit rendering")
                
                elif recommended_suffix == "_VXC":
                    if not has_vertex_colors:
                        reasoning.append("Material setup suggests vertex color only usage")
                
                elif recommended_suffix == "_VXM":
                    if not has_vertex_colors:
                        reasoning.append("Material setup suggests vertex color + texture usage")
                
                elif recommended_suffix == "_Masked":
                    if not alpha_cutoff:
                        reasoning.append("Material setup suggests alpha masking is needed")
                
                elif recommended_suffix == "None (Base PBR)" or not recommended_suffix:
                    reasoning.append("Standard PBR material detected")
                    if principled_node and not is_metallic and not is_transparent:
                        reasoning.append("Uses Principled BSDF with standard settings")
            
            else:
                # No nodes or legacy material
                reasoning.append("Material has no node setup (legacy material)")
                reasoning.append("Unlit suffix recommended for compatibility")
        
        except Exception as e:
            # If anything goes wrong, provide basic reasoning
            reasoning.append(f"Based on material analysis and naming conventions")
            print(f"Error in get_suffix_reasoning: {e}")
        
        return reasoning

    def draw(self, context):
        layout = self.layout
        
        # Title
        layout.label(text=f"Edit Material Type: {self.material_name}", icon='MATERIAL')
        layout.separator()
        
        # Base material name input
        base_name_box = layout.box()
        base_name_box.label(text="Base Material Name:", icon='TEXT')
        base_name_box.prop(self, "base_material_name", text="")
        
        # Show preview of final name that will be generated
        if self.base_material_name.strip():
            # Use the base name from the field (already properly formatted)
            preview_base = self.base_material_name.strip()
            
            # Clean any invalid characters that might have been typed
            invalid_chars = ['-', '.', ',', '/', '*', '$', '&']
            for char in invalid_chars:
                preview_base = preview_base.replace(char, '')
            
            # Apply camelCase convention if the user typed underscores or spaces
            if '_' in preview_base or ' ' in preview_base:
                preview_base = preview_base.replace(' ', '_')
                parts = preview_base.split('_')
                preview_base = ''.join(part.capitalize() for part in parts if part)
                if preview_base:
                    preview_base = preview_base[0].lower() + preview_base[1:]
            
            # Show preview with chosen suffix
            suffix_text = ""
            if self.chosen_suffix == 'METAL':
                suffix_text = "_Metal"
            elif self.chosen_suffix == 'TRANSPARENT':
                suffix_text = "_Transparent"
            elif self.chosen_suffix == 'UNLIT':
                suffix_text = "_Unlit"
            elif self.chosen_suffix == 'BLEND':
                suffix_text = "_Blend"
            elif self.chosen_suffix == 'MASKED':
                suffix_text = "_Masked"
            elif self.chosen_suffix == 'VXC':
                suffix_text = "_VXC"
            elif self.chosen_suffix == 'VXM':
                suffix_text = "_VXM"
            elif self.chosen_suffix == 'UIO':
                suffix_text = "_UIO"
            
            preview_name = preview_base + suffix_text
            base_name_box.label(text=f"Preview: {preview_name}", icon='INFO')
        
        layout.separator()
        
        # Show current issues and recommendation reasoning
        material = bpy.data.materials.get(self.material_name)
        if material:
            try:
                # Get shader type safely
                shader_type = "Unknown"
                if material.use_nodes and material.node_tree and material.node_tree.nodes:
                    for node in material.node_tree.nodes:
                        if node.type in ['BSDF_PRINCIPLED', 'EMISSION', 'BSDF_TRANSPARENT', 'BSDF_GLASS']:
                            shader_type = node.type
                            break
                
                issues, recommended_name, recommended_suffix = get_material_naming_recommendation(
                    self.material_name, 
                    shader_type,
                    material
                )
                
                if issues:
                    issues_box = layout.box()
                    issues_box.label(text="Current Issues:", icon='ERROR')
                    for issue in issues:
                        issues_box.label(text=f"• {issue}")
                    layout.separator()
                
                # Show recommendation with reasoning
                rec_box = layout.box()
                rec_box.label(text="Recommended Suffix:", icon='INFO')
                
                # Get material analysis for reasoning
                reasoning = self.get_suffix_reasoning(material, recommended_suffix)
                
                if recommended_suffix and recommended_suffix != "None (Base PBR)":
                    rec_box.label(text=f"✓ {recommended_suffix}", icon='CHECKMARK')
                else:
                    rec_box.label(text="✓ No Suffix (Base PBR)", icon='CHECKMARK')
                
                # Show reasoning
                if reasoning:
                    reason_box = rec_box.box()
                    reason_box.label(text="Reasoning:", icon='INFO')
                    for reason in reasoning:
                        reason_box.label(text=f"• {reason}")
                
                layout.separator()
                
            except Exception as e:
                # If material analysis fails, show basic info
                error_box = layout.box()
                error_box.label(text="Material Analysis Error", icon='ERROR')
                error_box.label(text="Using basic naming recommendations")
                layout.separator()
                print(f"Error in material analysis: {e}")
        
        # Suffix selection
        layout.label(text="Choose the appropriate suffix for your material:")
        layout.prop(self, "chosen_suffix", expand=False)
        
        # Show detailed explanations
        layout.separator()
        explanation_box = layout.box()
        explanation_box.label(text="Suffix Explanations:", icon='INFO')
        
        if self.chosen_suffix == 'NONE':
            explanation_box.label(text="• Standard PBR material")
            explanation_box.label(text="• Exports as: MaterialName_BR.png")
            explanation_box.label(text="• Channels: BaseColor (RGB) + Roughness (Alpha)")
            explanation_box.label(text="• May also export: MaterialName_MEO.png if metalness/emissive/AO detected")
        elif self.chosen_suffix == 'METAL':
            explanation_box.label(text="• Metallic PBR material")
            explanation_box.label(text="• Exports as: MaterialName_BR.png")
            explanation_box.label(text="• Channels: BaseColor (RGB) + Roughness (Alpha)")
            explanation_box.label(text="• Properties: Metalness = 1.0")
        elif self.chosen_suffix == 'TRANSPARENT':
            explanation_box.label(text="• Transparent material with alpha blending")
            explanation_box.label(text="• Exports as: MaterialName_BR.png + MaterialName_MESA.png")
            explanation_box.label(text="• Used for: Glass, water, transparent objects")
        elif self.chosen_suffix == 'UNLIT':
            explanation_box.label(text="• Unlit material (no lighting)")
            explanation_box.label(text="• Exports as: MaterialName_B.png")
            explanation_box.label(text="• Used for: Emissive surfaces, screens, glowing objects")
        elif self.chosen_suffix == 'BLEND':
            explanation_box.label(text="• Unlit material with alpha support")
            explanation_box.label(text="• Exports as: MaterialName_BA.png")
            explanation_box.label(text="• Used for: Unlit materials with alpha (not transparent in viewport)")
        elif self.chosen_suffix == 'MASKED':
            explanation_box.label(text="• Alpha-masked material (hard alpha cutoff)")
            explanation_box.label(text="• Exports as: MaterialName_BA.png")
            explanation_box.label(text="• Used for: Leaves, fabric, chain-link fences")
        elif self.chosen_suffix == 'VXC':
            explanation_box.label(text="• Vertex Color PBR (no textures)")
            explanation_box.label(text="• Uses mesh vertex colors only")
            explanation_box.label(text="• Used for: Simple colored objects")
        elif self.chosen_suffix == 'VXM':
            explanation_box.label(text="• Vertex Color Double-Texture PBR")
            explanation_box.label(text="• Texture A: MaterialName_BR.png (BaseColor + Roughness)")
            explanation_box.label(text="• Texture B: MaterialName_MEO.png (Metalness + Emissive + AO)")
            explanation_box.label(text="• Vertex colors multiplied with textures")
            explanation_box.label(text="• _MEO texture only created if material has metal/emissive/AO")
        elif self.chosen_suffix == 'UIO':
            explanation_box.label(text="• UI Optimized material")
            explanation_box.label(text="• Exports as: MaterialName_BA.png")
            explanation_box.label(text="• Used for: Text, icons, UI elements")


class META_HORIZON_OT_toggle_materials_list(Operator):
    """Toggle materials list expanded/collapsed state"""
    bl_idname = "meta_horizon.toggle_materials_list"
    bl_label = "Toggle Materials List"
    bl_description = "Expand or collapse the detailed materials list"
    bl_options = {'REGISTER'}

    def execute(self, context):
        settings = context.scene.horizon_export_settings
        settings.materials_list_expanded = not settings.materials_list_expanded
        # Reset to first page when toggling
        settings.materials_current_page = 0
        return {'FINISHED'}


class META_HORIZON_OT_toggle_meshes_list(Operator):
    """Toggle meshes list expanded/collapsed state"""
    bl_idname = "meta_horizon.toggle_meshes_list"
    bl_label = "Toggle Meshes List"
    bl_description = "Expand or collapse the detailed meshes list"
    bl_options = {'REGISTER'}

    def execute(self, context):
        settings = context.scene.horizon_export_settings
        settings.meshes_list_expanded = not settings.meshes_list_expanded
        # Reset to first page when toggling
        settings.meshes_current_page = 0
        return {'FINISHED'}


class META_HORIZON_OT_materials_page_nav(Operator):
    """Navigate materials list pages"""
    bl_idname = "meta_horizon.materials_page_nav"
    bl_label = "Navigate Materials Page"
    bl_description = "Navigate to next or previous page of materials"
    bl_options = {'REGISTER'}

    direction: StringProperty(
        name="Direction",
        description="Navigation direction: 'next' or 'prev'",
        default="next"
    )

    def execute(self, context):
        settings = context.scene.horizon_export_settings
        total_materials = len(context.scene.material_analysis_results)
        max_page = max(0, (total_materials - 1) // settings.materials_page_size)
        
        if self.direction == "next" and settings.materials_current_page < max_page:
            settings.materials_current_page += 1
        elif self.direction == "prev" and settings.materials_current_page > 0:
            settings.materials_current_page -= 1
        
        return {'FINISHED'}


class META_HORIZON_OT_meshes_page_nav(Operator):
    """Navigate meshes list pages"""
    bl_idname = "meta_horizon.meshes_page_nav"
    bl_label = "Navigate Meshes Page"
    bl_description = "Navigate to next or previous page of meshes"
    bl_options = {'REGISTER'}

    direction: StringProperty(
        name="Direction",
        description="Navigation direction: 'next' or 'prev'",
        default="next"
    )

    def execute(self, context):
        settings = context.scene.horizon_export_settings
        total_meshes = len(context.scene.mesh_analysis_results)
        max_page = max(0, (total_meshes - 1) // settings.meshes_page_size)
        
        if self.direction == "next" and settings.meshes_current_page < max_page:
            settings.meshes_current_page += 1
        elif self.direction == "prev" and settings.meshes_current_page > 0:
            settings.meshes_current_page -= 1
        
        return {'FINISHED'}


class META_HORIZON_OT_apply_all_recommended_names(Operator):
    """Apply recommended names to all materials that need renaming"""
    bl_idname = "meta_horizon.apply_all_recommended_names"
    bl_label = "Apply All Recommended Names"
    bl_description = "Rename all materials to follow Meta Horizon Worlds naming conventions"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not context.scene.material_analysis_results:
            self.report({'WARNING'}, "No material analysis found. Run material analysis first.")
            return {'CANCELLED'}
        
        # Collect materials that need renaming
        materials_to_rename = []
        for item in context.scene.material_analysis_results:
            # Skip empty slots
            if item.material_name.startswith('[Empty Slot'):
                continue
            
            # Only rename if there are naming issues and a different recommended name
            if (item.has_naming_issues and 
                item.recommended_name and 
                item.recommended_name != item.material_name):
                
                # Check if the material still exists
                material = bpy.data.materials.get(item.material_name)
                if material:
                    materials_to_rename.append({
                        'current_name': item.material_name,
                        'recommended_name': item.recommended_name,
                        'material': material
                    })
        
        if not materials_to_rename:
            self.report({'INFO'}, "No materials need renaming - all materials already follow naming conventions!")
            return {'FINISHED'}
        
        # Apply all the renames with intelligent conflict resolution
        successful_renames = 0
        failed_renames = 0
        rename_log = []
        conflict_resolutions = 0
        
        for item in materials_to_rename:
            try:
                old_name = item['material'].name
                
                # Generate a unique name based on the recommendation
                unique_name = generate_unique_material_name(item['recommended_name'], exclude_material=item['material'])
                
                # Apply the unique name
                item['material'].name = unique_name
                
                # Track the rename
                successful_renames += 1
                if unique_name != item['recommended_name']:
                    conflict_resolutions += 1
                    rename_log.append(f"'{old_name}' → '{unique_name}' (resolved conflict)")
                else:
                    rename_log.append(f"'{old_name}' → '{unique_name}'")
                    
            except Exception as e:
                failed_renames += 1
                print(f"Error renaming material '{item['current_name']}': {str(e)}")
        
        # Create comprehensive report
        if successful_renames > 0:
            print(f"\nSuccessfully renamed {successful_renames} materials:")
            for log_entry in rename_log:
                print(f"  • {log_entry}")
            
            if failed_renames > 0:
                self.report({'WARNING'}, f"Renamed {successful_renames} materials successfully, {failed_renames} failed. Check console for details.")
            else:
                if conflict_resolutions > 0:
                    self.report({'INFO'}, f"Successfully renamed {successful_renames} materials to follow Meta Horizon naming conventions! ({conflict_resolutions} name conflicts resolved)")
                else:
                    self.report({'INFO'}, f"Successfully renamed {successful_renames} materials to follow Meta Horizon naming conventions!")
            
            # Refresh the material analysis to show the updated state
            if context.scene.horizon_export_settings.analyze_all_materials:
                bpy.ops.meta_horizon.analyze_all_materials()
            else:
                bpy.ops.meta_horizon.analyze_materials()
        else:
            self.report({'ERROR'}, f"Failed to rename any materials ({failed_renames} failed)")
            return {'CANCELLED'}
        
        return {'FINISHED'}

    def invoke(self, context, event):
        # Show confirmation dialog with the list of materials to be renamed
        if not context.scene.material_analysis_results:
            self.report({'WARNING'}, "No material analysis found. Run material analysis first.")
            return {'CANCELLED'}
        
        # Count materials that need renaming
        materials_to_rename = []
        for item in context.scene.material_analysis_results:
            if (not item.material_name.startswith('[Empty Slot') and
                item.has_naming_issues and 
                item.recommended_name and 
                item.recommended_name != item.material_name):
                materials_to_rename.append(f"'{item.material_name}' → '{item.recommended_name}'")
        
        if not materials_to_rename:
            self.report({'INFO'}, "No materials need renaming - all materials already follow naming conventions!")
            return {'CANCELLED'}
        
        # Store the list for the draw method
        self.materials_to_rename = materials_to_rename
        
        return context.window_manager.invoke_props_dialog(self, width=600)

    def draw(self, context):
        layout = self.layout
        layout.label(text=f"Rename {len(self.materials_to_rename)} materials?", icon='FILE_REFRESH')
        layout.separator()
        
        # Show the list of renames
        box = layout.box()
        box.label(text="Materials to be renamed:", icon='MATERIAL')
        
        # Limit the display to prevent UI overflow
        display_limit = 10
        for i, rename_info in enumerate(self.materials_to_rename[:display_limit]):
            row = box.row()
            row.label(text=f"  {i+1}. {rename_info}", icon='FORWARD')
        
        if len(self.materials_to_rename) > display_limit:
            more_row = box.row()
            more_row.label(text=f"  ... and {len(self.materials_to_rename) - display_limit} more", icon='THREE_DOTS')
        
        layout.separator()
        layout.label(text="This will rename materials to follow Meta Horizon naming conventions.", icon='INFO')


class META_HORIZON_OT_resolve_uv_conflicts(Operator):
    """Resolve UV conflicts by creating separate material copies for each conflicting object"""
    bl_idname = "meta_horizon.resolve_uv_conflicts"
    bl_label = "Resolve UV Conflicts"
    bl_description = "Create separate material copies for each conflicting object to prevent UV mapping conflicts during texture baking"
    bl_options = {'REGISTER', 'UNDO'}

    material_name: StringProperty(
        name="Material Name",
        description="Name of the material with UV conflicts"
    )

    def execute(self, context):
        if not self.material_name:
            self.report({'WARNING'}, "No material name provided")
            return {'CANCELLED'}
        
        # Find the material
        original_material = bpy.data.materials.get(self.material_name)
        if not original_material:
            self.report({'WARNING'}, f"Material '{self.material_name}' not found")
            return {'CANCELLED'}
        
        # Find all objects using this material
        objects_using_material = []
        object_material_slots = {}  # Track which slots contain the material for each object
        
        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH' and obj.data and obj.data.materials:
                slots_with_material = []
                for slot_index, slot in enumerate(obj.material_slots):
                    if slot.material and (slot.material == original_material or slot.material.name == self.material_name):
                        slots_with_material.append(slot_index)
                
                if slots_with_material:
                    objects_using_material.append(obj)
                    object_material_slots[obj.name] = slots_with_material
        
        if len(objects_using_material) < 2:
            self.report({'WARNING'}, f"Material '{self.material_name}' is not used by multiple objects")
            return {'CANCELLED'}
        
        # Check if there are actually UV conflicts
        has_conflicts, conflict_details, conflicting_objects = detect_uv_conflicts([obj.name for obj in objects_using_material])
        
        if not has_conflicts:
            self.report({'WARNING'}, f"No UV conflicts detected for material '{self.material_name}'")
            return {'CANCELLED'}
        
        print(f"\n=== Resolving UV Conflicts for '{self.material_name}' ===")
        print(f"Found {len(objects_using_material)} objects using this material:")
        for obj in objects_using_material:
            slots = object_material_slots.get(obj.name, [])
            print(f"  • {obj.name} (slots: {slots})")
        
        # Check for shared mesh data and make unique copies if needed
        print(f"\nChecking for shared mesh data...")
        mesh_data_usage = {}
        for obj in objects_using_material:
            mesh_name = obj.data.name
            if mesh_name not in mesh_data_usage:
                mesh_data_usage[mesh_name] = []
            mesh_data_usage[mesh_name].append(obj.name)
        
        # Make mesh data unique for objects that share it
        for mesh_name, object_names in mesh_data_usage.items():
            if len(object_names) > 1:
                print(f"  Mesh '{mesh_name}' is shared by {len(object_names)} objects: {object_names}")
                for i, obj_name in enumerate(object_names):
                    if i == 0:
                        print(f"    Object '{obj_name}' keeps original mesh data")
                        continue
                    
                    obj = bpy.data.objects.get(obj_name)
                    if obj:
                        # Create a unique copy of the mesh data
                        obj.data = obj.data.copy()
                        print(f"    Object '{obj_name}' now has unique mesh data: '{obj.data.name}'")
            else:
                print(f"  Mesh '{mesh_name}' is used by only one object: {object_names[0]}")
        
        # Create a separate material copy for each object that shares the material
        # This ensures that each object gets its own unique material
        created_materials = []
        assignments_made = []
        
        # Create unique materials for ALL objects (including the first one)
        # This ensures complete separation
        for i, obj in enumerate(objects_using_material):
            if i == 0:
                # First object keeps the original material name but we'll verify assignment
                print(f"Object '{obj.name}' keeps original material '{self.material_name}'")
                assignments_made.append(f"{obj.name} → {self.material_name}")
                continue
            
            # Create a copy of the material for this object
            material_copy = original_material.copy()
            
            # Find a unique name for the material copy
            base_name = original_material.name
            counter = i  # Use the object index to ensure uniqueness
            while bpy.data.materials.get(f"{base_name}.{counter:03d}"):
                counter += 1
            
            material_copy.name = f"{base_name}.{counter:03d}"
            created_materials.append(material_copy.name)
            
            print(f"Created material copy: '{material_copy.name}' for object '{obj.name}'")
            
            # Replace the material in the tracked slots for this object
            slots_to_update = object_material_slots.get(obj.name, [])
            slots_updated = 0
            
            print(f"  Object '{obj.name}' has {len(slots_to_update)} slots to update: {slots_to_update}")
            
            for slot_index in slots_to_update:
                if slot_index < len(obj.material_slots):
                    old_material_name = obj.material_slots[slot_index].material.name if obj.material_slots[slot_index].material else "None"
                    obj.data.materials[slot_index] = material_copy
                    slots_updated += 1
                    print(f"  Updated slot {slot_index} in object '{obj.name}': '{old_material_name}' → '{material_copy.name}'")
                else:
                    print(f"  ERROR: Slot {slot_index} is out of range for object '{obj.name}' (has {len(obj.material_slots)} slots)")
            
            assignments_made.append(f"{obj.name} → {material_copy.name}")
            
            if slots_updated == 0:
                print(f"  ERROR: No slots updated for object '{obj.name}' - this indicates a problem with slot detection")
        
        print(f"\nFinal material assignments:")
        for assignment in assignments_made:
            print(f"  • {assignment}")
        
        if created_materials:
            self.report({'INFO'}, 
                       f"UV conflicts resolved for '{self.material_name}': "
                       f"Created {len(created_materials)} unique material copies: {', '.join(created_materials)}")
            
            # Refresh analyses if they exist
            if hasattr(context.scene, 'material_analysis_results') and context.scene.material_analysis_results:
                if context.scene.horizon_export_settings.analyze_all_materials:
                    bpy.ops.meta_horizon.analyze_all_materials()
                else:
                    bpy.ops.meta_horizon.analyze_materials()
            
            if hasattr(context.scene, 'mesh_analysis_results') and context.scene.mesh_analysis_results:
                bpy.ops.meta_horizon.analyze_meshes()
        else:
            self.report({'WARNING'}, f"No material copies were created for '{self.material_name}'")
        
        return {'FINISHED'}


class META_HORIZON_OT_resolve_all_uv_conflicts(Operator):
    """Resolve UV conflicts for all materials that have them by creating separate material copies"""
    bl_idname = "meta_horizon.resolve_all_uv_conflicts"
    bl_label = "Resolve All UV Conflicts"
    bl_description = "Automatically resolve UV conflicts for all materials that have them by creating separate material copies for each conflicting object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Check if material analysis results exist
        if not hasattr(context.scene, 'material_analysis_results') or not context.scene.material_analysis_results:
            self.report({'WARNING'}, "No material analysis results found. Please run material analysis first.")
            return {'CANCELLED'}
        
        # Find all materials with UV conflicts
        materials_with_conflicts = []
        for material_data in context.scene.material_analysis_results:
            if material_data.has_uv_conflicts:
                materials_with_conflicts.append(material_data.material_name)
        
        if not materials_with_conflicts:
            self.report({'INFO'}, "No materials with UV conflicts found.")
            return {'FINISHED'}
        
        print(f"\n=== Resolving UV Conflicts for All Materials ===")
        print(f"Found {len(materials_with_conflicts)} materials with UV conflicts:")
        for material_name in materials_with_conflicts:
            print(f"  • {material_name}")
        
        # Resolve UV conflicts for each material
        successfully_resolved = []
        failed_to_resolve = []
        
        for material_name in materials_with_conflicts:
            try:
                print(f"\nResolving UV conflicts for material: '{material_name}'")
                
                # Call the individual resolve operator
                result = bpy.ops.meta_horizon.resolve_uv_conflicts(material_name=material_name)
                
                if 'FINISHED' in result:
                    successfully_resolved.append(material_name)
                    print(f"  ✓ Successfully resolved UV conflicts for '{material_name}'")
                else:
                    failed_to_resolve.append(material_name)
                    print(f"  ✗ Failed to resolve UV conflicts for '{material_name}'")
                    
            except Exception as e:
                failed_to_resolve.append(material_name)
                print(f"  ✗ Error resolving UV conflicts for '{material_name}': {e}")
        
        # Generate summary report
        print(f"\n=== Summary ===")
        print(f"Successfully resolved: {len(successfully_resolved)} materials")
        print(f"Failed to resolve: {len(failed_to_resolve)} materials")
        
        if successfully_resolved:
            print(f"Successfully resolved materials:")
            for material_name in successfully_resolved:
                print(f"  ✓ {material_name}")
        
        if failed_to_resolve:
            print(f"Failed to resolve materials:")
            for material_name in failed_to_resolve:
                print(f"  ✗ {material_name}")
        
        # Report results to user
        if successfully_resolved and not failed_to_resolve:
            self.report({'INFO'}, f"Successfully resolved UV conflicts for all {len(successfully_resolved)} materials!")
        elif successfully_resolved and failed_to_resolve:
            self.report({'WARNING'}, f"Resolved UV conflicts for {len(successfully_resolved)} materials, but {len(failed_to_resolve)} failed. Check console for details.")
        else:
            self.report({'ERROR'}, f"Failed to resolve UV conflicts for all {len(failed_to_resolve)} materials. Check console for details.")
        
        return {'FINISHED'}

    def invoke(self, context, event):
        # Check if material analysis results exist
        if not hasattr(context.scene, 'material_analysis_results') or not context.scene.material_analysis_results:
            self.report({'WARNING'}, "No material analysis results found. Please run material analysis first.")
            return {'CANCELLED'}
        
        # Count materials with UV conflicts
        materials_with_conflicts = []
        for material_data in context.scene.material_analysis_results:
            if material_data.has_uv_conflicts:
                materials_with_conflicts.append(material_data.material_name)
        
        if not materials_with_conflicts:
            self.report({'INFO'}, "No materials with UV conflicts found.")
            return {'FINISHED'}
        
        # Show confirmation dialog
        return context.window_manager.invoke_confirm(self, event)
    
    def draw(self, context):
        layout = self.layout
        
        # Count materials with UV conflicts
        materials_with_conflicts = []
        if hasattr(context.scene, 'material_analysis_results') and context.scene.material_analysis_results:
            for material_data in context.scene.material_analysis_results:
                if material_data.has_uv_conflicts:
                    materials_with_conflicts.append(material_data.material_name)
        
        layout.label(text="Resolve UV Conflicts for All Materials", icon='UV_DATA')
        layout.separator()
        
        if materials_with_conflicts:
            layout.label(text=f"Found {len(materials_with_conflicts)} materials with UV conflicts:")
            layout.separator()
            
            # Show first few materials
            max_display = 10
            for i, material_name in enumerate(materials_with_conflicts[:max_display]):
                layout.label(text=f"• {material_name}", icon='MATERIAL')
            
            if len(materials_with_conflicts) > max_display:
                layout.label(text=f"... and {len(materials_with_conflicts) - max_display} more")
            
            layout.separator()
            layout.label(text="This will create separate material copies for each")
            layout.label(text="conflicting object to prevent UV mapping conflicts.")
        else:
            layout.label(text="No materials with UV conflicts found.")


class META_HORIZON_OT_simplify_material(Operator):
    """Simplify problematic material by creating a basic Meta Horizon compatible material"""
    bl_idname = "meta_horizon.simplify_material"
    bl_label = "Simplify Material"
    bl_description = "Create a simplified Meta Horizon compatible material to replace problematic material"
    bl_options = {'REGISTER', 'UNDO'}

    material_name: StringProperty(
        name="Material Name",
        description="Name of the material to simplify"
    )

    def execute(self, context):
        if not self.material_name:
            self.report({'WARNING'}, "No material name provided")
            return {'CANCELLED'}
        
        # Find the material
        material = bpy.data.materials.get(self.material_name)
        if not material:
            self.report({'WARNING'}, f"Material '{self.material_name}' not found")
            return {'CANCELLED'}
        
        # Find objects using this material
        objects_using_material = []
        for obj in bpy.data.objects:
            if obj.type == 'MESH' and obj.data and obj.data.materials:
                for mat in obj.data.materials:
                    if mat == material:
                        objects_using_material.append(obj)
                        break
        
        if not objects_using_material:
            self.report({'WARNING'}, f"No objects found using material '{self.material_name}'")
            return {'CANCELLED'}
        
        # Create a simplified material name
        simplified_material_name = f"{material.name}_Simplified"
        
        # Remove existing simplified material if it exists
        if bpy.data.materials.get(simplified_material_name):
            bpy.data.materials.remove(bpy.data.materials[simplified_material_name])
        
        # Create a new simplified material
        simplified_material = bpy.data.materials.new(name=simplified_material_name)
        
        # Enable use_nodes to create a node tree
        simplified_material.use_nodes = True
        
        # Clear default nodes
        simplified_material.node_tree.nodes.clear()
        
        # Create a simple Principled BSDF setup
        # Add Material Output node
        output_node = simplified_material.node_tree.nodes.new(type='ShaderNodeOutputMaterial')
        output_node.location = (400, 0)
        output_node.name = "Material_Output"
        
        # Add Principled BSDF node
        principled_node = simplified_material.node_tree.nodes.new(type='ShaderNodeBsdfPrincipled')
        principled_node.location = (0, 0)
        principled_node.name = "Principled_BSDF"
        
        # Connect Principled BSDF to Material Output
        simplified_material.node_tree.links.new(principled_node.outputs['BSDF'], output_node.inputs['Surface'])
        
        # Try to preserve basic color information from the original material
        try:
            if material.node_tree:
                # Look for existing Principled BSDF nodes
                principled_nodes = [node for node in material.node_tree.nodes if node.type == 'BSDF_PRINCIPLED']
                if principled_nodes:
                    original_principled = principled_nodes[0]
                    # Copy basic color settings
                    principled_node.inputs['Base Color'].default_value = original_principled.inputs['Base Color'].default_value
                    principled_node.inputs['Metallic'].default_value = original_principled.inputs['Metallic'].default_value
                    principled_node.inputs['Roughness'].default_value = original_principled.inputs['Roughness'].default_value
                    print(f"Preserved basic color settings from original material")
                else:
                    # Set default Meta Horizon friendly values
                    principled_node.inputs['Base Color'].default_value = (0.8, 0.8, 0.8, 1.0)  # Light gray
                    principled_node.inputs['Metallic'].default_value = 0.0
                    principled_node.inputs['Roughness'].default_value = 0.5
                    print(f"Applied default Meta Horizon compatible values")
            else:
                # Set default Meta Horizon friendly values
                principled_node.inputs['Base Color'].default_value = (0.8, 0.8, 0.8, 1.0)  # Light gray
                principled_node.inputs['Metallic'].default_value = 0.0
                principled_node.inputs['Roughness'].default_value = 0.5
                print(f"Applied default Meta Horizon compatible values")
                
        except Exception as e:
            print(f"Warning: Could not preserve original color settings: {e}")
            # Apply safe defaults
            principled_node.inputs['Base Color'].default_value = (0.8, 0.8, 0.8, 1.0)
            principled_node.inputs['Metallic'].default_value = 0.0
            principled_node.inputs['Roughness'].default_value = 0.5
        
        # Apply Meta Horizon naming convention
        clean_name = material.name
        # Remove invalid characters
        invalid_chars = ['-', '.', ',', '/', '*', '$', '&', ' ']
        for char in invalid_chars:
            clean_name = clean_name.replace(char, '_')
        
        # Add appropriate suffix for PBR material
        if not clean_name.endswith('_PBR'):
            clean_name += '_PBR'
        
        # Ensure unique name
        counter = 1
        final_name = clean_name
        while bpy.data.materials.get(final_name):
            final_name = f"{clean_name}_{counter:02d}"
            counter += 1
        
        simplified_material.name = final_name
        
        # Store the original material name
        original_name = material.name
        
        # Rename the original material to backup
        backup_name = f"{original_name}_Original"
        if bpy.data.materials.get(backup_name):
            bpy.data.materials.remove(bpy.data.materials[backup_name])
        material.name = backup_name
        
        # Replace material on all objects
        objects_updated = 0
        for obj in bpy.data.objects:
            if obj.type == 'MESH' and obj.data and obj.data.materials:
                for i, mat in enumerate(obj.data.materials):
                    if mat and mat.name == backup_name:
                        obj.data.materials[i] = simplified_material
                        objects_updated += 1
        
        self.report({'INFO'}, f"Successfully simplified material! Created '{final_name}' and updated {objects_updated} objects. Original saved as '{backup_name}'")
        
        # Refresh material analysis to update the UI
        if hasattr(context.scene, 'material_analysis_results') and context.scene.material_analysis_results:
            try:
                # Re-analyze materials based on user setting
                if context.scene.horizon_export_settings.analyze_all_materials:
                    bpy.ops.meta_horizon.analyze_all_materials()
                else:
                    bpy.ops.meta_horizon.analyze_materials()
                print("Material analysis refreshed after material simplification")
            except Exception as e:
                print(f"Warning: Could not refresh material analysis: {e}")
            
        return {'FINISHED'}


class META_HORIZON_OT_apply_geometry_modifiers(Operator):
    """Apply geometry-adding modifiers to prepare mesh for UV unwrapping"""
    bl_idname = "meta_horizon.apply_geometry_modifiers"
    bl_label = "Apply Geometry Modifiers"
    bl_description = "Apply geometry-adding modifiers to finalize mesh geometry before UV unwrapping"
    bl_options = {'REGISTER', 'UNDO'}

    object_name: StringProperty(
        name="Object Name",
        description="Name of the object to apply modifiers to"
    )

    def execute(self, context):
        if not self.object_name:
            self.report({'WARNING'}, "No object name provided")
            return {'CANCELLED'}
        
        # Find the object
        obj = bpy.data.objects.get(self.object_name)
        if not obj:
            self.report({'WARNING'}, f"Object '{self.object_name}' not found")
            return {'CANCELLED'}
        
        if obj.type != 'MESH':
            self.report({'WARNING'}, f"Object '{self.object_name}' is not a mesh")
            return {'CANCELLED'}
        
        # Geometry-adding modifier types
        geometry_adding_types = {
            'ARRAY', 'MIRROR', 'SOLIDIFY', 'BEVEL', 'SUBSURF',
            'MULTIRES', 'SCREW', 'SKIN', 'BOOLEAN', 'BUILD', 
            'WIREFRAME', 'NODES'
        }
        
        # Find geometry-adding modifiers
        modifiers_to_apply = []
        for modifier in obj.modifiers:
            if modifier.type in geometry_adding_types:
                modifiers_to_apply.append(modifier.name)
        
        if not modifiers_to_apply:
            self.report({'WARNING'}, f"No geometry-adding modifiers found on '{self.object_name}'")
            return {'CANCELLED'}
        
        # Make sure the object is selected and active
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        
        # Apply modifiers in order
        applied_count = 0
        for modifier_name in modifiers_to_apply:
            modifier = obj.modifiers.get(modifier_name)
            if modifier and modifier.type in geometry_adding_types:
                try:
                    bpy.ops.object.modifier_apply(modifier=modifier_name)
                    applied_count += 1
                except RuntimeError as e:
                    self.report({'WARNING'}, f"Failed to apply modifier '{modifier_name}': {str(e)}")
        
        if applied_count > 0:
            self.report({'INFO'}, f"Applied {applied_count} geometry-adding modifiers to '{self.object_name}'")
            
            # Refresh the mesh analysis
            bpy.ops.meta_horizon.analyze_meshes()
        else:
            self.report({'WARNING'}, f"No modifiers were successfully applied to '{self.object_name}'")
        
        return {'FINISHED'}


class META_HORIZON_OT_apply_all_modifiers(Operator):
    """Apply all modifiers to selected objects"""
    bl_idname = "meta_horizon.apply_all_modifiers"
    bl_label = "Apply All Modifiers"
    bl_description = "Apply all modifiers to all selected mesh objects and their children"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Get all selected objects and their children
        all_objects = set()
        for obj in context.selected_objects:
            collect_children_objects(obj, all_objects)
        
        # Filter to mesh objects only
        mesh_objects = [obj for obj in all_objects if obj.type == 'MESH' and obj.data]
        
        if not mesh_objects:
            self.report({'WARNING'}, "No mesh objects found in selection or their children")
            return {'CANCELLED'}
        
        applied_count = 0
        total_modifiers_applied = 0
        objects_with_modifiers = 0
        
        # Store original active object and mode
        original_active = context.view_layer.objects.active
        original_mode = context.mode
        
        try:
            # Ensure we're in object mode
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            
            for obj in mesh_objects:
                if len(obj.modifiers) == 0:
                    continue
                
                objects_with_modifiers += 1
                
                # Set object as active and select it
                bpy.context.view_layer.objects.active = obj
                obj.select_set(True)
                
                # Get list of modifiers to apply (copy names since we'll be removing them)
                modifiers_to_apply = [mod.name for mod in obj.modifiers]
                object_applied_count = 0
                
                # Apply all modifiers in order
                for modifier_name in modifiers_to_apply:
                    modifier = obj.modifiers.get(modifier_name)
                    if modifier:
                        try:
                            bpy.ops.object.modifier_apply(modifier=modifier_name)
                            object_applied_count += 1
                            total_modifiers_applied += 1
                        except RuntimeError as e:
                            self.report({'WARNING'}, f"Failed to apply modifier '{modifier_name}' on '{obj.name}': {str(e)}")
                
                if object_applied_count > 0:
                    applied_count += 1
                    print(f"Applied {object_applied_count} modifiers to '{obj.name}'")
                
                # Deselect the object
                obj.select_set(False)
        
        finally:
            # Restore original active object and mode
            if original_active:
                bpy.context.view_layer.objects.active = original_active
            if original_mode != 'OBJECT':
                try:
                    bpy.ops.object.mode_set(mode=original_mode)
                except:
                    pass  # Mode change might fail, that's okay
        
        # Report results
        if total_modifiers_applied > 0:
            if objects_with_modifiers == 1:
                self.report({'INFO'}, f"Applied {total_modifiers_applied} modifiers to 1 object")
            else:
                self.report({'INFO'}, f"Applied {total_modifiers_applied} modifiers to {applied_count} objects (out of {objects_with_modifiers} objects with modifiers)")
            
            # Refresh the mesh analysis if it exists
            if hasattr(context.scene, 'mesh_analysis_results') and context.scene.mesh_analysis_results:
                bpy.ops.meta_horizon.analyze_meshes()
        else:
            self.report({'WARNING'}, f"No modifiers were applied. Found {objects_with_modifiers} objects with modifiers")
        
        return {'FINISHED'}


class META_HORIZON_OT_decimate_meshes(Operator):
    """Apply decimation modifier to selected mesh objects and their children to reduce polygon count"""
    bl_idname = "meta_horizon.decimate_meshes"
    bl_label = "Decimate Meshes"
    bl_description = "Apply decimation modifier to reduce polygon count on selected mesh objects and their children"
    bl_options = {'REGISTER', 'UNDO'}

    ratio: FloatProperty(
        name="Decimation Ratio",
        description="Ratio of faces to keep (0.1 = 10% of original faces)",
        default=0.5,
        min=0.01,
        max=1.0
    )
    
    type: EnumProperty(
        name="Decimation Type",
        description="Type of decimation to apply",
        items=[
            ('COLLAPSE', "Collapse", "Merge vertices together (good general purpose)"),
            ('UNSUBDIV', "Un-Subdivide", "Remove edge loops (good for over-subdivided meshes)"),
            ('PLANAR', "Planar", "Dissolve geometry in planar areas"),
        ],
        default='COLLAPSE'
    )
    
    preserve_boundaries: BoolProperty(
        name="Preserve Boundaries",
        description="Keep boundary edges unchanged during decimation",
        default=True
    )
    
    symmetry: BoolProperty(
        name="Symmetry",
        description="Maintain symmetry on meshes with mirror modifier",
        default=False
    )


    
    def execute(self, context):
        # Get all selected objects and their children
        all_objects = set()
        for obj in context.selected_objects:
            collect_children_objects(obj, all_objects)
        
        # Filter to mesh objects only
        mesh_objects = [obj for obj in all_objects if obj.type == 'MESH' and obj.data]
        
        if not mesh_objects:
            self.report({'WARNING'}, "No mesh objects found in selection or their children")
            return {'CANCELLED'}
        
        decimated_count = 0
        total_faces_before = 0
        total_faces_after = 0
        total_verts_before = 0
        total_verts_after = 0
        
        # Store original active object and mode
        original_active = context.view_layer.objects.active
        original_mode = context.mode
        
        try:
            # Ensure we're in object mode
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            
            for obj in mesh_objects:
                # Set object as active and select it
                bpy.context.view_layer.objects.active = obj
                obj.select_set(True)
                
                # Get counts before decimation
                faces_before = len(obj.data.polygons)
                verts_before = len(obj.data.vertices)
                
                total_faces_before += faces_before
                total_verts_before += verts_before
                
                # Add decimation modifier
                decimate_modifier = obj.modifiers.new(name="Decimation", type='DECIMATE')
                decimate_modifier.decimate_type = self.type
                decimate_modifier.ratio = self.ratio
                
                # Set type-specific properties
                if self.type == 'COLLAPSE':
                    decimate_modifier.use_collapse_triangulate = True
                    if hasattr(decimate_modifier, 'use_symmetry'):
                        decimate_modifier.use_symmetry = self.symmetry
                elif self.type == 'UNSUBDIV':
                    pass  # Un-subdivide doesn't have additional properties
                elif self.type == 'PLANAR':
                    decimate_modifier.angle_limit = 0.0873  # 5 degrees default

                # Apply the modifier
                try:
                    bpy.ops.object.modifier_apply(modifier=decimate_modifier.name)
                    
                    # Get counts after decimation
                    faces_after = len(obj.data.polygons)
                    verts_after = len(obj.data.vertices)
                    
                    total_faces_after += faces_after
                    total_verts_after += verts_after
                    

                    
                    decimated_count += 1
                    
                    print(f"Decimated {obj.name}: {faces_before} → {faces_after} faces ({face_reduction:.1f}%), {verts_before} → {verts_after} vertices ({vert_reduction:.1f}%)")
                    
                except Exception as e:
                    self.report({'WARNING'}, f"Failed to decimate {obj.name}: {str(e)}")
                    # Remove the modifier if application failed
                    if decimate_modifier.name in obj.modifiers:
                        obj.modifiers.remove(decimate_modifier)
                
                # Deselect the object
                obj.select_set(False)
        
        except Exception as e:
            self.report({'ERROR'}, f"Error during decimation: {str(e)}")
            return {'CANCELLED'}
        
        finally:
            # Restore original active object
            if original_active:
                bpy.context.view_layer.objects.active = original_active
            
            # Restore original selection
            for obj in context.selected_objects:
                obj.select_set(True)
        
        if decimated_count > 0:
            face_reduction_percent = ((total_faces_before - total_faces_after) / total_faces_before * 100) if total_faces_before > 0 else 0
            vert_reduction_percent = ((total_verts_before - total_verts_after) / total_verts_before * 100) if total_verts_before > 0 else 0
            
            # Report success with detailed summary
            self.report({'INFO'}, 
                       f"Decimated {decimated_count} objects: {total_faces_before:,} → {total_faces_after:,} faces ({face_reduction_percent:.1f}% reduction)")
            
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "No objects were decimated")
            return {'CANCELLED'}

    def invoke(self, context, event):
        # Use settings from the export settings
        export_settings = context.scene.horizon_export_settings
        self.ratio = export_settings.decimate_ratio
        self.type = export_settings.decimate_type
        self.preserve_boundaries = export_settings.decimate_preserve_boundaries
        self.symmetry = export_settings.decimate_symmetry
        
        # Show popup with decimation settings
        return context.window_manager.invoke_props_dialog(self, width=350)

    def draw(self, context):
        layout = self.layout
        
        # Show settings dialog (before decimation)
        selected_objects = context.selected_objects
        all_objects = set()
        for obj in selected_objects:
            collect_children_objects(obj, all_objects)
        
        mesh_count = len([obj for obj in all_objects if obj.type == 'MESH' and obj.data])
        
        layout.label(text=f"Decimate {mesh_count} mesh objects", icon='MOD_DECIM')
        layout.separator()
        
        # Decimation settings
        layout.prop(self, "type")
        layout.prop(self, "ratio", slider=True)
        
        if self.type == 'COLLAPSE':
            layout.prop(self, "preserve_boundaries")
            layout.prop(self, "symmetry")
        
        layout.separator()
        layout.label(text="⚠️ This operation cannot be undone after closing the dialog", icon='INFO')


class META_HORIZON_OT_decimate_single_mesh(Operator):
    """Apply decimation modifier to a single mesh object to reduce polygon count"""
    bl_idname = "meta_horizon.decimate_single_mesh"
    bl_label = "Decimate Mesh"
    bl_description = "Apply decimation modifier to reduce polygon count on this specific mesh object"
    bl_options = {'REGISTER', 'UNDO'}

    object_name: StringProperty(
        name="Object Name",
        description="Name of the object to decimate"
    )
    
    ratio: FloatProperty(
        name="Decimation Ratio",
        description="Ratio of faces to keep (0.1 = 10% of original faces)",
        default=0.5,
        min=0.01,
        max=1.0
    )
    
    type: EnumProperty(
        name="Decimation Type",
        description="Type of decimation to apply",
        items=[
            ('COLLAPSE', "Collapse", "Merge vertices together (good general purpose)"),
            ('UNSUBDIV', "Un-Subdivide", "Remove edge loops (good for over-subdivided meshes)"),
            ('PLANAR', "Planar", "Dissolve geometry in planar areas"),
        ],
        default='COLLAPSE'
    )
    
    preserve_boundaries: BoolProperty(
        name="Preserve Boundaries",
        description="Keep boundary edges unchanged during decimation",
        default=True
    )
    
    symmetry: BoolProperty(
        name="Symmetry",
        description="Maintain symmetry on meshes with mirror modifier",
        default=False
    )



    def execute(self, context):
        if not self.object_name:
            self.report({'ERROR'}, "No object name specified")
            return {'CANCELLED'}
        
        # Find the object
        obj = bpy.data.objects.get(self.object_name)
        if not obj:
            self.report({'ERROR'}, f"Object '{self.object_name}' not found")
            return {'CANCELLED'}
        
        if obj.type != 'MESH' or not obj.data:
            self.report({'ERROR'}, f"Object '{self.object_name}' is not a mesh")
            return {'CANCELLED'}
        
        # Store original counts
        original_polygons = len(obj.data.polygons)
        original_vertices = len(obj.data.vertices)
        
        # Apply decimation modifier
        try:
            # Set the object as active
            bpy.context.view_layer.objects.active = obj
            
            # Add decimation modifier
            decimate_mod = obj.modifiers.new(name="Decimate", type='DECIMATE')
            decimate_mod.decimate_type = self.type
            decimate_mod.ratio = self.ratio
            
            if self.type == 'COLLAPSE':
                decimate_mod.use_collapse_triangulate = True
                if self.preserve_boundaries:
                    decimate_mod.vertex_group_factor = 0.0
                if self.symmetry:
                    decimate_mod.use_symmetry = True
            
            # Apply the modifier
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.modifier_apply(modifier=decimate_mod.name)
            
            # Get new counts
            new_polygons = len(obj.data.polygons)
            new_vertices = len(obj.data.vertices)
            

            
            # Update mesh analysis if it exists
            if hasattr(context.scene, 'mesh_analysis_results'):
                for item in context.scene.mesh_analysis_results:
                    if item.object_name == self.object_name:
                        item.polygon_count = new_polygons
                        item.vertex_count = new_vertices
                        item.polygon_count_final = new_polygons
                        item.vertex_count_final = new_vertices
                        # Update high-poly status
                        item.is_high_poly = new_polygons > 10000
                        break
            
            # Report success
            reduction_percent = ((original_polygons - new_polygons) / original_polygons * 100) if original_polygons > 0 else 0
            self.report({'INFO'}, 
                       f"Decimated '{self.object_name}': {original_polygons} → {new_polygons} polygons ({reduction_percent:.1f}% reduction)")
            
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Failed to decimate '{self.object_name}': {str(e)}")
            return {'CANCELLED'}

    def invoke(self, context, event):
        # Use settings from the export settings
        export_settings = context.scene.horizon_export_settings
        self.ratio = export_settings.decimate_ratio
        self.type = export_settings.decimate_type
        self.preserve_boundaries = export_settings.decimate_preserve_boundaries
        self.symmetry = export_settings.decimate_symmetry
        
        # Show settings dialog
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        layout = self.layout
        
        # Object info
        obj = bpy.data.objects.get(self.object_name)
        if obj and obj.data:
            info_box = layout.box()
            info_box.label(text=f"Decimating: {self.object_name}", icon='MESH_DATA')
            
            # Current mesh info
            current_polygons = len(obj.data.polygons)
            current_vertices = len(obj.data.vertices)
            
            info_col = info_box.column()
            info_col.label(text=f"Current: {current_polygons:,} polygons, {current_vertices:,} vertices")
            
            # Predicted result
            predicted_polygons = int(current_polygons * self.ratio)
            predicted_vertices = int(current_vertices * self.ratio)
            info_col.label(text=f"After decimation: ~{predicted_polygons:,} polygons, ~{predicted_vertices:,} vertices")
            
            # Reduction percentage
            reduction_percent = (1 - self.ratio) * 100
            info_col.label(text=f"Reduction: ~{reduction_percent:.1f}%")
        
        # Decimation settings
        layout.separator()
        settings_box = layout.box()
        settings_box.label(text="Decimation Settings", icon='SETTINGS')
        
        settings_col = settings_box.column()
        settings_col.prop(self, "type", text="Type")
        settings_col.prop(self, "ratio", text="Ratio", slider=True)
        
        if self.type == 'COLLAPSE':
            settings_col.prop(self, "preserve_boundaries", text="Preserve Boundaries")
            settings_col.prop(self, "symmetry", text="Maintain Symmetry")


class META_HORIZON_OT_smart_uv_project_selected(Operator):
    """Unwrap UVs for all selected objects using Smart UV Project with Meta Horizon Worlds UV Channel 0 management"""
    bl_idname = "meta_horizon.smart_uv_project_selected"
    bl_label = "Re-unwrap UVs (All Selected)"
    bl_description = "Create new UV Channel 0 for Meta Horizon Worlds export and unwrap UVs for all selected mesh objects"
    bl_options = {'REGISTER', 'UNDO'}
    
    angle_limit: bpy.props.FloatProperty(
        name="Angle Limit",
        description="Lower angle values result in more seams",
        default=66.0,
        min=1.0,
        max=89.0,
        subtype='ANGLE'
    )
    
    island_margin: bpy.props.FloatProperty(
        name="Island Margin",
        description="Space between UV islands",
        default=0.02,
        min=0.0,
        max=1.0
    )
    
    area_weight: bpy.props.FloatProperty(
        name="Area Weight",
        description="Weight projections vector by faces with larger areas",
        default=0.0,
        min=0.0,
        max=1.0
    )
    
    preserve_existing_uvs: bpy.props.BoolProperty(
        name="Preserve Existing UVs",
        description="Keep existing UV maps and create a new one for Horizon Worlds export",
        default=True
    )
    
    uv_map_name: bpy.props.StringProperty(
        name="UV Map Name",
        description="Name for the new UV map (will be set as UV Channel 0)",
        default="HorizonUVs"
    )

    def execute(self, context):
        selected_objects = context.selected_objects
        if not selected_objects:
            self.report({'WARNING'}, "No objects selected")
            return {'CANCELLED'}
        
        # Filter to mesh objects only
        mesh_objects = [obj for obj in selected_objects if obj.type == 'MESH' and obj.data]
        
        if not mesh_objects:
            self.report({'WARNING'}, "No mesh objects found in selection")
            return {'CANCELLED'}
        
        unwrapped_count = 0
        failed_count = 0
        uv_channels_created = 0
        
        # Store original active object and selection
        original_active = context.view_layer.objects.active
        original_selection = context.selected_objects.copy()
        
        for obj in mesh_objects:
            try:
                # Clear selection and select only current object
                bpy.ops.object.select_all(action='DESELECT')
                obj.select_set(True)
                context.view_layer.objects.active = obj
                
                # Check existing UV layers
                existing_uv_count = len(obj.data.uv_layers)
                existing_uv_names = [uv.name for uv in obj.data.uv_layers]
                
                # Create or manage UV Channel 0 for Meta Horizon Worlds
                horizon_uv_name = self.uv_map_name
                
                # Ensure unique name if preserve_existing_uvs is True
                if self.preserve_existing_uvs and horizon_uv_name in existing_uv_names:
                    counter = 1
                    base_name = horizon_uv_name
                    while horizon_uv_name in existing_uv_names:
                        horizon_uv_name = f"{base_name}_{counter:02d}"
                        counter += 1
                
                # Create new UV map for Horizon Worlds export
                if self.preserve_existing_uvs or not obj.data.uv_layers:
                    # Create new UV layer
                    new_uv_layer = obj.data.uv_layers.new(name=horizon_uv_name)
                    print(f"Created new UV layer '{horizon_uv_name}' for '{obj.name}'")
                    uv_channels_created += 1
                else:
                    # Use existing first UV layer but rename it
                    if obj.data.uv_layers:
                        obj.data.uv_layers[0].name = horizon_uv_name
                        new_uv_layer = obj.data.uv_layers[0]
                        print(f"Renamed existing UV layer to '{horizon_uv_name}' for '{obj.name}'")
                    else:
                        # Create new if none exist
                        new_uv_layer = obj.data.uv_layers.new(name=horizon_uv_name)
                        print(f"Created new UV layer '{horizon_uv_name}' for '{obj.name}'")
                        uv_channels_created += 1
                
                # Ensure the new UV layer is at UV Channel 0 (index 0)
                # We need to reorder UV layers to make the new one first
                if len(obj.data.uv_layers) > 1 and obj.data.uv_layers[0] != new_uv_layer:
                    # Store existing UV layer data that we want to preserve
                    existing_uv_data = []
                    if self.preserve_existing_uvs:
                        for uv_layer in obj.data.uv_layers:
                            if uv_layer != new_uv_layer:
                                # Store UV coordinates
                                uv_coords = []
                                for loop_idx, uv_loop in enumerate(uv_layer.data):
                                    uv_coords.append((uv_loop.uv[0], uv_loop.uv[1]))
                                existing_uv_data.append((uv_layer.name, uv_coords))
                    
                    # Clear all UV layers
                    while obj.data.uv_layers:
                        obj.data.uv_layers.remove(obj.data.uv_layers[0])
                    
                    # Create the Horizon UV map first (becomes Channel 0)
                    new_uv_layer = obj.data.uv_layers.new(name=horizon_uv_name)
                    
                    # Restore other UV layers if preserving
                    if self.preserve_existing_uvs:
                        for uv_name, uv_coords in existing_uv_data:
                            restored_layer = obj.data.uv_layers.new(name=uv_name)
                            # Restore UV coordinates
                            for loop_idx, (u, v) in enumerate(uv_coords):
                                if loop_idx < len(restored_layer.data):
                                    restored_layer.data[loop_idx].uv = (u, v)

                # Set the new UV layer as active (Channel 0)
                obj.data.uv_layers.active = new_uv_layer
                obj.data.uv_layers.active_index = 0
                
                print(f"Set '{horizon_uv_name}' as UV Channel 0 (active) for '{obj.name}'")
                
                # Enter Edit mode
                bpy.ops.object.mode_set(mode='EDIT')
                
                # Select all faces
                bpy.ops.mesh.select_all(action='SELECT')
                
                # Apply Smart UV Project to the new UV Channel 0
                bpy.ops.uv.smart_project(
                    angle_limit=self.angle_limit,
                    island_margin=self.island_margin,
                    area_weight=self.area_weight,
                    correct_aspect=True,
                    scale_to_bounds=False
                )
                
                # Return to Object mode
                bpy.ops.object.mode_set(mode='OBJECT')
                
                unwrapped_count += 1
                print(f"Successfully unwrapped UVs for '{obj.name}' in UV Channel 0")
                
            except RuntimeError as e:
                # Return to Object mode if there was an error
                try:
                    bpy.ops.object.mode_set(mode='OBJECT')
                except:
                    pass
                
                print(f"Failed to unwrap UVs for '{obj.name}': {str(e)}")
                failed_count += 1
                continue
        
        # Restore original selection and active object
        bpy.ops.object.select_all(action='DESELECT')
        for obj in original_selection:
            obj.select_set(True)
        
        if original_active:
            context.view_layer.objects.active = original_active
        
        # Report results
        if unwrapped_count > 0:
            if failed_count > 0:
                self.report({'INFO'}, f"UV unwrapping complete: {unwrapped_count} objects successful, {failed_count} failed. Created {uv_channels_created} new UV Channel 0 maps for Meta Horizon Worlds.")
            else:
                self.report({'INFO'}, f"Successfully unwrapped UVs for {unwrapped_count} objects in UV Channel 0 for Meta Horizon Worlds export. Created {uv_channels_created} new UV maps.")
            
            # Refresh the mesh analysis
            bpy.ops.meta_horizon.analyze_meshes()
        else:
            self.report({'ERROR'}, f"Failed to unwrap UVs for any objects ({failed_count} failed)")
            return {'CANCELLED'}
        
        return {'FINISHED'}

    def invoke(self, context, event):
        # Show a popup to adjust UV unwrapping settings
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        layout = self.layout
        
        # Count mesh objects
        selected_objects = context.selected_objects
        mesh_objects = [obj for obj in selected_objects if obj.type == 'MESH' and obj.data]
        
        # Information section
        info_box = layout.box()
        info_box.label(text="Meta Horizon Worlds UV Channel 0 Setup", icon='INFO')
        info_box.label(text=f"Will process {len(mesh_objects)} mesh objects")
        info_box.label(text="• Only UV Channel 0 is used in Meta Horizon Worlds")
        info_box.label(text="• Creates dedicated UV map for export compatibility")
        
        layout.separator()
        
        # UV management options
        uv_box = layout.box()
        uv_box.label(text="UV Map Management:")
        uv_box.prop(self, "preserve_existing_uvs")
        uv_box.prop(self, "uv_map_name")
        
        if self.preserve_existing_uvs:
            uv_box.label(text="✓ Existing UV maps will be preserved", icon='CHECKMARK')
        else:
            uv_box.label(text="⚠ Existing UV maps may be replaced", icon='ERROR')
        
        layout.separator()
        
        # UV unwrapping settings
        settings_box = layout.box()
        settings_box.label(text="UV Unwrapping Settings:")
        settings_box.prop(self, "angle_limit")
        settings_box.prop(self, "island_margin")
        settings_box.prop(self, "area_weight")


class META_HORIZON_OT_smart_uv_project(Operator):
    """Unwrap mesh UVs using Smart UV Project with Meta Horizon Worlds UV Channel 0 management"""
    bl_idname = "meta_horizon.smart_uv_project"
    bl_label = "Smart UV Unwrap"
    bl_description = "Create new UV Channel 0 for Meta Horizon Worlds export and unwrap mesh UVs"
    bl_options = {'REGISTER', 'UNDO'}

    object_name: StringProperty(
        name="Object Name",
        description="Name of the object to unwrap UVs for"
    )
    
    angle_limit: bpy.props.FloatProperty(
        name="Angle Limit",
        description="Lower angle values result in more seams",
        default=66.0,
        min=1.0,
        max=89.0,
        subtype='ANGLE'
    )
    
    island_margin: bpy.props.FloatProperty(
        name="Island Margin",
        description="Space between UV islands",
        default=0.02,
        min=0.0,
        max=1.0
    )
    
    area_weight: bpy.props.FloatProperty(
        name="Area Weight",
        description="Weight projections vector by faces with larger areas",
        default=0.0,
        min=0.0,
        max=1.0
    )
    
    preserve_existing_uvs: bpy.props.BoolProperty(
        name="Preserve Existing UVs",
        description="Keep existing UV maps and create a new one for Horizon Worlds export",
        default=True
    )
    
    uv_map_name: bpy.props.StringProperty(
        name="UV Map Name",
        description="Name for the new UV map (will be set as UV Channel 0)",
        default="HorizonUVs"
    )

    def execute(self, context):
        if not self.object_name:
            self.report({'WARNING'}, "No object name provided")
            return {'CANCELLED'}
        
        # Find the object
        obj = bpy.data.objects.get(self.object_name)
        if not obj:
            self.report({'WARNING'}, f"Object '{self.object_name}' not found")
            return {'CANCELLED'}
        
        if obj.type != 'MESH' or not obj.data:
            self.report({'WARNING'}, f"Object '{self.object_name}' is not a mesh or has no mesh data")
            return {'CANCELLED'}
        
        # Make sure the object is selected and active
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        
        try:
            # Check existing UV layers
            existing_uv_count = len(obj.data.uv_layers)
            existing_uv_names = [uv.name for uv in obj.data.uv_layers]
            
            print(f"Processing '{obj.name}': Found {existing_uv_count} existing UV layers")
            
            # Create or manage UV Channel 0 for Meta Horizon Worlds
            horizon_uv_name = self.uv_map_name
            
            # Ensure unique name if preserve_existing_uvs is True
            if self.preserve_existing_uvs and horizon_uv_name in existing_uv_names:
                counter = 1
                base_name = horizon_uv_name
                while horizon_uv_name in existing_uv_names:
                    horizon_uv_name = f"{base_name}_{counter:02d}"
                    counter += 1
            
            # Create new UV map for Horizon Worlds export
            if self.preserve_existing_uvs or not obj.data.uv_layers:
                # Create new UV layer
                new_uv_layer = obj.data.uv_layers.new(name=horizon_uv_name)
                print(f"Created new UV layer '{horizon_uv_name}' for Meta Horizon Worlds export")
                uv_action = "created"
            else:
                # Use existing first UV layer but rename it
                if obj.data.uv_layers:
                    obj.data.uv_layers[0].name = horizon_uv_name
                    new_uv_layer = obj.data.uv_layers[0]
                    print(f"Renamed existing UV layer to '{horizon_uv_name}' for Meta Horizon Worlds export")
                    uv_action = "renamed"
                else:
                    # Create new if none exist
                    new_uv_layer = obj.data.uv_layers.new(name=horizon_uv_name)
                    print(f"Created new UV layer '{horizon_uv_name}' for Meta Horizon Worlds export")
                    uv_action = "created"
            
            # Ensure the new UV layer is at UV Channel 0 (index 0)
            # We need to reorder UV layers to make the new one first
            if len(obj.data.uv_layers) > 1 and obj.data.uv_layers[0] != new_uv_layer:
                # Store existing UV layer data that we want to preserve
                existing_uv_data = []
                if self.preserve_existing_uvs:
                    for uv_layer in obj.data.uv_layers:
                        if uv_layer != new_uv_layer:
                            # Store UV coordinates
                            uv_coords = []
                            for loop_idx, uv_loop in enumerate(uv_layer.data):
                                uv_coords.append((uv_loop.uv[0], uv_loop.uv[1]))
                            existing_uv_data.append((uv_layer.name, uv_coords))
                
                # Clear all UV layers
                while obj.data.uv_layers:
                    obj.data.uv_layers.remove(obj.data.uv_layers[0])
                
                # Create the Horizon UV map first (becomes Channel 0)
                new_uv_layer = obj.data.uv_layers.new(name=horizon_uv_name)
                
                # Restore other UV layers if preserving
                if self.preserve_existing_uvs:
                    for uv_name, uv_coords in existing_uv_data:
                        restored_layer = obj.data.uv_layers.new(name=uv_name)
                        # Restore UV coordinates
                        for loop_idx, (u, v) in enumerate(uv_coords):
                            if loop_idx < len(restored_layer.data):
                                restored_layer.data[loop_idx].uv = (u, v)
            
            # Set the new UV layer as active (Channel 0)
            obj.data.uv_layers.active = new_uv_layer
            obj.data.uv_layers.active_index = 0
            
            print(f"Set '{horizon_uv_name}' as UV Channel 0 (active) for Meta Horizon Worlds compatibility")
            
            # Enter Edit mode
            bpy.ops.object.mode_set(mode='EDIT')
            
            # Select all faces
            bpy.ops.mesh.select_all(action='SELECT')
            
            # Apply Smart UV Project to the new UV Channel 0
            bpy.ops.uv.smart_project(
                angle_limit=self.angle_limit,
                island_margin=self.island_margin,
                area_weight=self.area_weight,
                correct_aspect=True,
                scale_to_bounds=False
            )
            
            # Return to Object mode
            bpy.ops.object.mode_set(mode='OBJECT')
            
            self.report({'INFO'}, f"Successfully {uv_action} UV Channel 0 '{horizon_uv_name}' and unwrapped UVs for '{self.object_name}' - Ready for Meta Horizon Worlds export!")
            
            # Refresh the mesh analysis
            bpy.ops.meta_horizon.analyze_meshes()
        
        except RuntimeError as e:
            # Return to Object mode if there was an error
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except:
                pass
            self.report({'ERROR'}, f"Failed to unwrap UVs: {str(e)}")
            return {'CANCELLED'}
        
        return {'FINISHED'}

    def invoke(self, context, event):
        # Show a popup to adjust UV unwrapping settings
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        layout = self.layout
        
        # Information section
        info_box = layout.box()
        info_box.label(text="Meta Horizon Worlds UV Channel 0 Setup", icon='INFO')
        info_box.label(text=f"Processing: {self.object_name}")
        info_box.label(text="• Only UV Channel 0 is used in Meta Horizon Worlds")
        info_box.label(text="• Creates dedicated UV map for export compatibility")
        
        layout.separator()
        
        # UV management options
        uv_box = layout.box()
        uv_box.label(text="UV Map Management:")
        uv_box.prop(self, "preserve_existing_uvs")
        uv_box.prop(self, "uv_map_name")
        
        if self.preserve_existing_uvs:
            uv_box.label(text="✓ Existing UV maps will be preserved", icon='CHECKMARK')
        else:
            uv_box.label(text="⚠ Existing UV maps may be replaced", icon='ERROR')
        
        layout.separator()
        
        # UV unwrapping settings
        settings_box = layout.box()
        settings_box.label(text="UV Unwrapping Settings:")
        settings_box.prop(self, "angle_limit")
        settings_box.prop(self, "island_margin")
        settings_box.prop(self, "area_weight")


class META_HORIZON_OT_analyze_meshes(Operator):
    """Analyze meshes in selected objects and their children"""
    bl_idname = "meta_horizon.analyze_meshes"
    bl_label = "Analyze Meshes"
    bl_description = "Analyze all meshes in selected objects and their children with polygon counts, modifiers, and UV channels"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Clear previous analysis results
        context.scene.mesh_analysis_results.clear()
        
        selected_objects = context.selected_objects
        if not selected_objects:
            self.report({'WARNING'}, "No objects selected")
            return {'CANCELLED'}
        
        def analyze_object(obj):
            """Recursively analyze object and its children"""
            if obj.type == 'MESH' and obj.data:
                mesh_data = obj.data
                
                # Create analysis item
                item = context.scene.mesh_analysis_results.add()
                item.object_name = obj.name
                item.mesh_name = mesh_data.name
                
                # Basic geometry counts (original mesh data)
                item.polygon_count = len(mesh_data.polygons)
                item.vertex_count = len(mesh_data.vertices)
                
                # Get evaluated mesh data (with modifiers applied)
                depsgraph = context.evaluated_depsgraph_get()
                eval_obj = obj.evaluated_get(depsgraph)
                if eval_obj and eval_obj.data:
                    eval_mesh = eval_obj.data
                    item.polygon_count_final = len(eval_mesh.polygons)
                    item.vertex_count_final = len(eval_mesh.vertices)
                else:
                    # Fallback to original counts
                    item.polygon_count_final = item.polygon_count
                    item.vertex_count_final = item.vertex_count
                
                # Analyze modifiers
                item.modifier_count = len(obj.modifiers)
                modifier_names = []
                destructive_modifiers = []
                geometry_adding_modifiers = []
                
                # Categories of modifiers that might affect performance or workflow
                destructive_types = {
                    'BOOLEAN', 'SOLIDIFY', 'BEVEL', 'SUBDIVISION_SURFACE', 
                    'MULTIRESOLUTION', 'DECIMATE', 'REMESH', 'TRIANGULATE'
                }
                
                # Categories of modifiers that add geometry and should be applied before UV unwrapping
                geometry_adding_types = {
                    'ARRAY', 'MIRROR', 'SOLIDIFY', 'BEVEL', 'SUBSURF',
                    'MULTIRES', 'SCREW', 'SKIN', 'BOOLEAN', 'BUILD', 
                    'WIREFRAME', 'NODES'  # Geometry Nodes can add geometry
                }
                
                for modifier in obj.modifiers:
                    modifier_names.append(f"{modifier.name} ({modifier.type})")
                    if modifier.type in destructive_types:
                        destructive_modifiers.append(modifier.name)
                    if modifier.type in geometry_adding_types:
                        geometry_adding_modifiers.append(modifier.name)
                
                item.modifier_list = ", ".join(modifier_names) if modifier_names else "None"
                item.has_destructive_modifiers = len(destructive_modifiers) > 0
                item.has_geometry_adding_modifiers = len(geometry_adding_modifiers) > 0
                item.geometry_adding_modifiers = ", ".join(geometry_adding_modifiers) if geometry_adding_modifiers else ""
                
                # Analyze UV channels
                uv_layers = mesh_data.uv_layers
                item.uv_channel_count = len(uv_layers)
                item.has_multiple_uv_channels = len(uv_layers) > 1
                
                uv_names = []
                for uv_layer in uv_layers:
                    status = " (active)" if uv_layer == uv_layers.active else ""
                    uv_names.append(f"{uv_layer.name}{status}")
                
                item.uv_channel_list = ", ".join(uv_names) if uv_names else "None"
                
                # Performance analysis
                warnings = []
                
                # High polygon count thresholds
                high_poly_threshold = 10000  # Adjust based on Meta Horizon requirements
                very_high_poly_threshold = 50000
                
                if item.polygon_count_final > very_high_poly_threshold:
                    item.is_high_poly = True
                    warnings.append(f"Very high polygon count ({item.polygon_count_final:,})")
                elif item.polygon_count_final > high_poly_threshold:
                    item.is_high_poly = True
                    warnings.append(f"High polygon count ({item.polygon_count_final:,})")
                
                # Check for performance-affecting modifiers
                if 'SUBDIVISION_SURFACE' in [m.type for m in obj.modifiers]:
                    subdiv_mods = [m for m in obj.modifiers if m.type == 'SUBDIVISION_SURFACE']
                    for mod in subdiv_mods:
                        if hasattr(mod, 'levels') and mod.levels > 2:
                            warnings.append(f"High subdivision levels ({mod.levels})")
                
                if 'MULTIRESOLUTION' in [m.type for m in obj.modifiers]:
                    warnings.append("Multiresolution modifier (high memory usage)")
                
                # Check UV channel issues
                if item.uv_channel_count == 0:
                    warnings.append("No UV channels (required for texturing)")
                elif item.uv_channel_count > 2:
                    warnings.append(f"Many UV channels ({item.uv_channel_count}) may impact performance")
                
                # Check for mesh data issues
                if item.polygon_count != item.polygon_count_final:
                    poly_change = item.polygon_count_final - item.polygon_count
                    if poly_change > 0:
                        warnings.append(f"Modifiers add {poly_change:,} polygons")
                    else:
                        warnings.append(f"Modifiers remove {abs(poly_change):,} polygons")
                
                item.performance_warnings = "; ".join(warnings) if warnings else "None"
            
            # Recursively analyze children
            for child in obj.children:
                analyze_object(child)
        
        # Analyze all selected objects and their children
        for obj in selected_objects:
            analyze_object(obj)
        
        total_meshes = len(context.scene.mesh_analysis_results)
        if total_meshes == 0:
            self.report({'WARNING'}, "No mesh objects found in selection")
            return {'CANCELLED'}
        
        # Calculate totals for summary
        total_polygons = sum(item.polygon_count_final for item in context.scene.mesh_analysis_results)
        total_vertices = sum(item.vertex_count_final for item in context.scene.mesh_analysis_results)
        high_poly_count = sum(1 for item in context.scene.mesh_analysis_results if item.is_high_poly)
        no_uv_count = sum(1 for item in context.scene.mesh_analysis_results if item.uv_channel_count == 0)
        multiple_uv_count = sum(1 for item in context.scene.mesh_analysis_results if item.has_multiple_uv_channels)
        modifier_count = sum(item.modifier_count for item in context.scene.mesh_analysis_results)
        
        # Create comprehensive report message
        report_parts = [f"Mesh analysis complete: {total_meshes} meshes found"]
        report_parts.append(f"Total polygons: {total_polygons:,}")
        report_parts.append(f"Total vertices: {total_vertices:,}")
        
        if high_poly_count > 0:
            report_parts.append(f"{high_poly_count} high-poly meshes")
        
        if no_uv_count > 0:
            report_parts.append(f"{no_uv_count} meshes without UV channels")
        
        if multiple_uv_count > 0:
            report_parts.append(f"{multiple_uv_count} meshes with multiple UV channels")
        
        if modifier_count > 0:
            report_parts.append(f"{modifier_count} total modifiers")
        
        self.report({'INFO'}, ". ".join(report_parts) + ".")
        
        return {'FINISHED'}


class META_HORIZON_OT_analyze_all_materials(Operator):
    """Analyze ALL materials in the scene, including unassigned ones"""
    bl_idname = "meta_horizon.analyze_all_materials"
    bl_label = "Analyze All Materials"
    bl_description = "Analyze all materials in the scene, including empty and unassigned materials"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Clear previous analysis results
        context.scene.material_analysis_results.clear()
        
        # Dictionary to store material usage data
        material_data = defaultdict(lambda: {'objects': set(), 'shader_type': 'Unknown', 'material_ref': None, 'is_empty': False})
        
        # First, get all materials in the scene
        all_materials = list(bpy.data.materials)
        
        if not all_materials:
            self.report({'WARNING'}, "No materials found in the scene")
            return {'CANCELLED'}
        
        # Analyze material usage across all objects
        empty_slots_data = defaultdict(lambda: {'objects': set(), 'slot_indices': set()})
        
        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH' and obj.data and obj.data.materials:
                for slot_index, slot in enumerate(obj.material_slots):
                    if slot.material:
                        material_data[slot.material.name]['objects'].add(obj.name)
                    else:
                        # Track empty material slots
                        empty_slots_data[obj.name]['objects'].add(obj.name)
                        empty_slots_data[obj.name]['slot_indices'].add(slot_index)
        
        # Now analyze all materials, whether they're used or not
        for material in all_materials:
            if material.name not in material_data:
                # Material exists but isn't assigned to any object
                material_data[material.name] = {'objects': set(), 'shader_type': 'Unknown', 'material_ref': material, 'is_empty': False}
            
            # Set material reference
            material_data[material.name]['material_ref'] = material
            
            # Determine shader type and check if material is empty
            shader_type = "Unknown"
            is_empty = False
            
            if material.use_nodes and material.node_tree:
                # Check if the node tree is effectively empty
                shader_nodes = [node for node in material.node_tree.nodes 
                              if node.type not in ['OUTPUT_MATERIAL']]
                
                if not shader_nodes:
                    # Only has output node or no nodes at all
                    shader_type = "Empty Material"
                    is_empty = True
                elif len(shader_nodes) == 1 and shader_nodes[0].type == 'OUTPUT_MATERIAL':
                    # Only has output node
                    shader_type = "Empty Material"
                    is_empty = True
                else:
                    # Has actual shader nodes
                    for node in material.node_tree.nodes:
                        if node.type == 'BSDF_PRINCIPLED':
                            shader_type = "Principled BSDF"
                            break
                        elif node.type == 'BSDF_DIFFUSE':
                            shader_type = "Diffuse BSDF"
                            break
                        elif node.type == 'EMISSION':
                            shader_type = "Emission"
                            break
                        elif node.type == 'BSDF_GLOSSY':
                            shader_type = "Glossy BSDF"
                            break
                        elif node.type == 'BSDF_TRANSPARENT':
                            shader_type = "Transparent BSDF"
                            break
                        elif node.type == 'BSDF_GLASS':
                            shader_type = "Glass BSDF"
                            break
            elif not material.use_nodes:
                # Legacy material system (no nodes enabled)
                shader_type = "Empty Material (No Nodes)"
                is_empty = True
            else:
                # Nodes enabled but no node tree
                shader_type = "Empty Material"
                is_empty = True
            
            material_data[material.name]['shader_type'] = shader_type
            material_data[material.name]['is_empty'] = is_empty
        
        # Store results in scene property with naming analysis
        total_issues = 0
        empty_materials = 0
        unassigned_materials = 0
        empty_slots_count = 0
        uv_conflict_materials = 0
        
        for material_name, data in material_data.items():
            item = context.scene.material_analysis_results.add()
            item.material_name = material_name
            item.shader_type = data['shader_type']
            
            
            # Check if material is unassigned
            if not data['objects']:
                item.using_objects = "(Unassigned)"
                unassigned_materials += 1
            else:
                item.using_objects = ", ".join(sorted(data['objects']))
            
            # Handle empty materials
            item.is_empty_material = data.get('is_empty', False)
            if item.is_empty_material:
                empty_materials += 1
                # Try to guess the purpose of empty materials
                if any(keyword in material_name.lower() for keyword in ['placeholder', 'temp', 'wip']):
                    item.empty_material_purpose = 'PLACEHOLDER'
                elif any(keyword in material_name.lower() for keyword in ['group', 'selection', 'org']):
                    item.empty_material_purpose = 'ORGANIZATIONAL'
                elif any(keyword in material_name.lower() for keyword in ['vertex', 'color', 'vx']):
                    item.empty_material_purpose = 'VERTEX_COLOR'
                elif any(keyword in material_name.lower() for keyword in ['external', 'system']):
                    item.empty_material_purpose = 'EXTERNAL'
                else:
                    item.empty_material_purpose = 'UNKNOWN'
            
            # Analyze naming and get recommendations
            issues, recommended_name, recommended_suffix = get_material_naming_recommendation(
                material_name, data['shader_type'], data['material_ref']
            )
            
            item.has_naming_issues = len(issues) > 0
            item.naming_issues = "; ".join(issues) if issues else ""
            item.recommended_name = recommended_name
            item.recommended_suffix = recommended_suffix
            
            # Check for UV conflicts
            has_uv_conflicts, uv_conflict_details, conflicting_objects = detect_uv_conflicts(data['objects'])
            item.has_uv_conflicts = has_uv_conflicts
            item.uv_conflict_details = uv_conflict_details
            item.conflicting_objects = conflicting_objects
            
            # Check for UV mapping nodes
            has_uv_mapping_nodes, uv_mapping_node_details = detect_uv_mapping_nodes(data['material_ref'])
            item.has_uv_mapping_nodes = has_uv_mapping_nodes
            item.uv_mapping_node_details = uv_mapping_node_details
            item.needs_uv_correction = has_uv_mapping_nodes
            
            if item.has_naming_issues:
                total_issues += 1
            
            if item.has_uv_conflicts:
                uv_conflict_materials += 1
        
        # Add empty material slots to the analysis
        for obj_name, slot_data in empty_slots_data.items():
            if slot_data['slot_indices']:  # Only if there are actually empty slots
                empty_slots_count += 1
                item = context.scene.material_analysis_results.add()
                slot_indices_list = sorted(list(slot_data['slot_indices']))
                if len(slot_indices_list) == 1:
                    item.material_name = f"[Empty Slot {slot_indices_list[0]}]"
                else:
                    item.material_name = f"[Empty Slots {', '.join(map(str, slot_indices_list))}]"
                item.shader_type = "Empty Material Slot"
                item.using_objects = obj_name
                item.is_empty_material = True
                item.empty_material_purpose = 'PLACEHOLDER'  # Assume placeholder by default
                item.can_be_setup = True
                item.has_naming_issues = False  # Empty slots don't have naming issues
                item.naming_issues = ""
                item.recommended_name = ""
                item.recommended_suffix = ""
        
        total_materials = len(material_data)
        assigned_materials = total_materials - unassigned_materials
        
        # Create comprehensive report message
        report_parts = [f"Analysis complete: {total_materials} materials found"]
        
        if unassigned_materials > 0:
            report_parts.append(f"{unassigned_materials} unassigned")
        
        if assigned_materials > 0:
            total_objects = len(set().union(*[data['objects'] for data in material_data.values() if data['objects']]))
            report_parts.append(f"{assigned_materials} assigned to {total_objects} objects")
        
        if empty_materials > 0:
            report_parts.append(f"{empty_materials} empty materials found")
        
        if empty_slots_count > 0:
            report_parts.append(f"{empty_slots_count} objects with empty material slots")
        
        if total_issues > 0:
            report_parts.append(f"{total_issues} materials have naming recommendations")
        else:
            report_parts.append("All materials follow naming conventions!")
        
        if uv_conflict_materials > 0:
            report_parts.append(f"{uv_conflict_materials} materials have UV mapping conflicts")
        
        self.report({'INFO'}, ". ".join(report_parts) + ".")
        
        return {'FINISHED'}


class META_HORIZON_OT_analyze_materials(Operator):
    """Analyze materials in selected objects and their children"""
    bl_idname = "meta_horizon.analyze_materials"
    bl_label = "Analyze Materials"
    bl_description = "Analyze all materials in selected objects and their children with Meta Horizon naming recommendations"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Clear previous analysis results
        context.scene.material_analysis_results.clear()
        
        selected_objects = context.selected_objects
        if not selected_objects:
            self.report({'WARNING'}, "No objects selected")
            return {'CANCELLED'}
        
        # Dictionary to store material usage data
        material_data = defaultdict(lambda: {'objects': set(), 'shader_type': 'Unknown', 'material_ref': None})
        empty_slots_data = defaultdict(lambda: {'objects': set(), 'slot_indices': set()})
        
        def analyze_object(obj):
            """Recursively analyze object and its children"""
            if obj.type == 'MESH' and obj.data and obj.data.materials:
                for slot_index, slot in enumerate(obj.material_slots):
                    if slot.material:
                        material = slot.material
                        material_data[material.name]['objects'].add(obj.name)
                        material_data[material.name]['material_ref'] = material
                        
                        # Determine shader type and check if material is empty
                        shader_type = "Unknown"
                        is_empty = False
                        
                        if material.use_nodes and material.node_tree:
                            # Check if the node tree is effectively empty
                            shader_nodes = [node for node in material.node_tree.nodes 
                                          if node.type not in ['OUTPUT_MATERIAL']]
                            
                            if not shader_nodes:
                                # Only has output node or no nodes at all
                                shader_type = "Empty Material"
                                is_empty = True
                            elif len(shader_nodes) == 1 and shader_nodes[0].type == 'OUTPUT_MATERIAL':
                                # Only has output node
                                shader_type = "Empty Material"
                                is_empty = True
                            else:
                                # Has actual shader nodes
                                for node in material.node_tree.nodes:
                                    if node.type == 'BSDF_PRINCIPLED':
                                        shader_type = "Principled BSDF"
                                        break
                                    elif node.type == 'BSDF_DIFFUSE':
                                        shader_type = "Diffuse BSDF"
                                        break
                                    elif node.type == 'EMISSION':
                                        shader_type = "Emission"
                                        break
                                    elif node.type == 'BSDF_GLOSSY':
                                        shader_type = "Glossy BSDF"
                                        break
                                    elif node.type == 'BSDF_TRANSPARENT':
                                        shader_type = "Transparent BSDF"
                                        break
                                    elif node.type == 'BSDF_GLASS':
                                        shader_type = "Glass BSDF"
                                        break
                        elif not material.use_nodes:
                            # Legacy material system (no nodes enabled)
                            shader_type = "Empty Material (No Nodes)"
                            is_empty = True
                        else:
                            # Nodes enabled but no node tree
                            shader_type = "Empty Material"
                            is_empty = True
                        
                        material_data[material.name]['shader_type'] = shader_type
                        material_data[material.name]['is_empty'] = is_empty
                    else:
                        # Track empty material slots
                        empty_slots_data[obj.name]['objects'].add(obj.name)
                        empty_slots_data[obj.name]['slot_indices'].add(slot_index)
            
            # Recursively analyze children
            for child in obj.children:
                analyze_object(child)
        
        # Analyze all selected objects and their children
        for obj in selected_objects:
            analyze_object(obj)
        
        # Store results in scene property with naming analysis
        total_issues = 0
        empty_materials = 0
        empty_slots_count = 0
        uv_conflict_materials = 0
        for material_name, data in material_data.items():
            item = context.scene.material_analysis_results.add()
            item.material_name = material_name
            item.shader_type = data['shader_type']
            item.using_objects = ", ".join(sorted(data['objects']))
            
            # Handle empty materials
            item.is_empty_material = data.get('is_empty', False)
            if item.is_empty_material:
                empty_materials += 1
                # Try to guess the purpose of empty materials
                if any(keyword in material_name.lower() for keyword in ['placeholder', 'temp', 'wip']):
                    item.empty_material_purpose = 'PLACEHOLDER'
                elif any(keyword in material_name.lower() for keyword in ['group', 'selection', 'org']):
                    item.empty_material_purpose = 'ORGANIZATIONAL'
                elif any(keyword in material_name.lower() for keyword in ['vertex', 'color', 'vx']):
                    item.empty_material_purpose = 'VERTEX_COLOR'
                elif any(keyword in material_name.lower() for keyword in ['external', 'system']):
                    item.empty_material_purpose = 'EXTERNAL'
                else:
                    item.empty_material_purpose = 'UNKNOWN'
            
            # Analyze naming and get recommendations
            issues, recommended_name, recommended_suffix = get_material_naming_recommendation(
                material_name, data['shader_type'], data['material_ref']
            )
            
            item.has_naming_issues = len(issues) > 0
            item.naming_issues = "; ".join(issues) if issues else ""
            item.recommended_name = recommended_name
            item.recommended_suffix = recommended_suffix
            
            # Check for UV conflicts
            has_uv_conflicts, uv_conflict_details, conflicting_objects = detect_uv_conflicts(data['objects'])
            item.has_uv_conflicts = has_uv_conflicts
            item.uv_conflict_details = uv_conflict_details
            item.conflicting_objects = conflicting_objects
            
            # Check for UV mapping nodes
            has_uv_mapping_nodes, uv_mapping_node_details = detect_uv_mapping_nodes(data['material_ref'])
            item.has_uv_mapping_nodes = has_uv_mapping_nodes
            item.uv_mapping_node_details = uv_mapping_node_details
            item.needs_uv_correction = has_uv_mapping_nodes
            
            if item.has_naming_issues:
                total_issues += 1
            
            if item.has_uv_conflicts:
                uv_conflict_materials += 1
        
        # Add empty material slots to the analysis
        for obj_name, slot_data in empty_slots_data.items():
            if slot_data['slot_indices']:  # Only if there are actually empty slots
                empty_slots_count += 1
                item = context.scene.material_analysis_results.add()
                slot_indices_list = sorted(list(slot_data['slot_indices']))
                if len(slot_indices_list) == 1:
                    item.material_name = f"[Empty Slot {slot_indices_list[0]}]"
                else:
                    item.material_name = f"[Empty Slots {', '.join(map(str, slot_indices_list))}]"
                item.shader_type = "Empty Material Slot"
                item.using_objects = obj_name
                item.is_empty_material = True
                item.empty_material_purpose = 'PLACEHOLDER'  # Assume placeholder by default
                item.can_be_setup = True
                item.has_naming_issues = False  # Empty slots don't have naming issues
                item.naming_issues = ""
                item.recommended_name = ""
                item.recommended_suffix = ""
        
        total_materials = len(material_data)
        total_objects = len(set().union(*[data['objects'] for data in material_data.values()]))
        
        # Create comprehensive report message
        report_parts = [f"Analysis complete: {total_materials} materials found on {total_objects} objects"]
        
        if empty_materials > 0:
            report_parts.append(f"{empty_materials} empty materials found")
        
        if empty_slots_count > 0:
            report_parts.append(f"{empty_slots_count} objects with empty material slots")
        
        if total_issues > 0:
            report_parts.append(f"{total_issues} materials have naming recommendations")
        else:
            report_parts.append("All materials follow naming conventions!")
        
        if uv_conflict_materials > 0:
            report_parts.append(f"{uv_conflict_materials} materials have UV mapping conflicts")
        
        self.report({'INFO'}, ". ".join(report_parts) + ".")
        
        return {'FINISHED'}


class META_HORIZON_OT_bake_material(Operator):
    """Bake texture for a specific material"""
    bl_idname = "meta_horizon.bake_material"
    bl_label = "Bake Material"
    bl_description = "Bake texture for this material using Cycles renderer with advanced settings"
    bl_options = {'REGISTER', 'UNDO'}

    material_name: StringProperty(
        name="Material Name",
        description="Name of the material to bake"
    )
    
    open_console: BoolProperty(
        name="Open Console",
        description="Open console window to show baking progress",
        default=True
    )

    def execute(self, context):
        if not self.material_name:
            self.report({'WARNING'}, "No material name provided")
            return {'CANCELLED'}
        
        # Open console window if requested
        if self.open_console:
            try:
                bpy.ops.wm.console_toggle()
            except:
                pass  # Console toggle might not be available on all platforms
        
        # Find the material
        material = bpy.data.materials.get(self.material_name)
        if not material:
            self.report({'WARNING'}, f"Material '{self.material_name}' not found")
            return {'CANCELLED'}
        
        # Check if this is a VXC material (Vertex Color only - no textures needed)
        base_name, material_type, texture_info = get_meta_horizon_texture_info(material.name, material)
        if material_type == "VXC":
            self.report({'INFO'}, f"Material '{self.material_name}' is a Vertex Color material - no textures need to be baked")
            return {'FINISHED'}
        
        # Find objects using this material
        objects_using_material = []
        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH' and obj.data and obj.data.materials:
                for slot in obj.material_slots:
                    if slot.material and slot.material.name == self.material_name:
                        objects_using_material.append(obj)
                        break
        
        if not objects_using_material:
            self.report({'WARNING'}, f"No objects found using material '{self.material_name}'")
            return {'CANCELLED'}
        
        # Get bake settings
        bake_settings = context.scene.horizon_bake_settings
        
        # Setup for baking
        success, error_msg = setup_and_bake_material(context, material, objects_using_material, bake_settings)
        
        if success:
            self.report({'INFO'}, f"Successfully baked texture for material '{self.material_name}'")
        else:
            self.report({'ERROR'}, f"Failed to bake texture for material '{self.material_name}': {error_msg}")
            return {'CANCELLED'}
        
        return {'FINISHED'}


class META_HORIZON_OT_bake_all_materials(Operator):
    """Batch bake textures for all analyzed materials"""
    bl_idname = "meta_horizon.bake_all_materials"
    bl_label = "Bake All Materials"
    bl_description = "Batch bake textures for all analyzed materials with comprehensive options"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        # Check if file is saved first
        if not bpy.data.is_saved:
            self.report({'ERROR'}, "Please save your Blender file before baking materials. Baking creates texture files that need to be saved relative to your .blend file location.")
            return {'CANCELLED'}
        
        # Open console window to show progress
        try:
            bpy.ops.wm.console_toggle()
        except:
            pass  # Console toggle might not be available on all platforms
        
        # Get materials from analysis
        if not context.scene.material_analysis_results:
            self.report({'WARNING'}, "No material analysis found. Run material analysis first.")
            return {'CANCELLED'}
        
        # Filter materials that can be baked (exclude empty slots and VXC materials)
        bakeable_materials = []
        for item in context.scene.material_analysis_results:
            if not item.material_name.startswith('[Empty Slot'):
                material = bpy.data.materials.get(item.material_name)
                if material:
                    # Check if this is a VXC material (Vertex Color only - no textures needed)
                    base_name, material_type, texture_info = get_meta_horizon_texture_info(material.name, material)
                    if material_type != "VXC":  # Exclude VXC materials from baking
                        bakeable_materials.append(material)
        
        if not bakeable_materials:
            self.report({'WARNING'}, "No bakeable materials found in analysis")
            return {'CANCELLED'}
        
        # Get bake settings
        bake_settings = context.scene.horizon_bake_settings
        
        print(f"Starting batch bake for {len(bakeable_materials)} materials...")
        print(f"Bake settings: {bake_settings.bake_type}, {bake_settings.samples} samples, {bake_settings.image_width}x{bake_settings.image_height}")
        
        successful_bakes = 0
        failed_bakes = 0
        total_start_time = time.time()
        
        for i, material in enumerate(bakeable_materials):
            if bake_settings.show_progress:
                print(f"\n--- Baking material {i+1}/{len(bakeable_materials)}: '{material.name}' ---")
            
            # Find objects using this material
            objects_using_material = []
            for obj in bpy.context.scene.objects:
                if obj.type == 'MESH' and obj.data and obj.data.materials:
                    for slot in obj.material_slots:
                        if slot.material and slot.material.name == material.name:
                            objects_using_material.append(obj)
                            break
            
            if not objects_using_material:
                if bake_settings.show_progress:
                    print(f"Skipping '{material.name}': No objects using this material")
                continue
            
            # Check if objects have UV maps
            valid_objects = []
            for obj in objects_using_material:
                if obj.data and obj.data.uv_layers:
                    valid_objects.append(obj)
                else:
                    if bake_settings.show_progress:
                        print(f"Warning: Object '{obj.name}' has no UV map")
            
            if not valid_objects:
                if bake_settings.show_progress:
                    print(f"Skipping '{material.name}': No objects with UV maps")
                failed_bakes += 1
                continue
            
            # Call the shared baking function
            success, error_msg = setup_and_bake_material(context, material, valid_objects, bake_settings)
            
            if success:
                successful_bakes += 1
                if bake_settings.show_progress:
                    print(f"✓ Successfully baked '{material.name}'")
            else:
                failed_bakes += 1
                if bake_settings.show_progress:
                    print(f"✗ Failed to bake '{material.name}'")
        
        total_end_time = time.time()
        total_duration = total_end_time - total_start_time
        
        # Final report
        print(f"\n=== Batch Bake Complete ===")
        print(f"Total time: {total_duration:.2f} seconds")
        print(f"Successful: {successful_bakes}")
        print(f"Failed: {failed_bakes}")
        print(f"Total materials processed: {successful_bakes + failed_bakes}")
        
        if bake_settings.auto_save and successful_bakes > 0:
            output_dir = bpy.path.abspath(bake_settings.output_directory)
            print(f"Baked textures saved to: {output_dir}")
        
        if successful_bakes > 0:
            self.report({'INFO'}, f"Batch bake complete: {successful_bakes} successful, {failed_bakes} failed")
        else:
            self.report({'WARNING'}, f"Batch bake failed: No materials were successfully baked")
        
        return {'FINISHED'}

    def invoke(self, context, event):
        # Check if file is saved first
        if not bpy.data.is_saved:
            # Show save file dialog
            bpy.ops.wm.save_as_mainfile('INVOKE_DEFAULT')
            self.report({'INFO'}, "Please save your file to continue with baking. After saving, run Bake All Materials again.")
            return {'CANCELLED'}
        
        # Show settings dialog before batch baking
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        layout = self.layout
        bake_settings = context.scene.horizon_bake_settings
        
        # Header
        layout.label(text="Batch Bake Settings", icon='RENDER_RESULT')
        layout.separator()
        
        # Output settings
        output_box = layout.box()
        output_box.label(text="Output Settings", icon='FILE_FOLDER')
        output_box.prop(bake_settings, "output_directory")
        
        row = output_box.row()
        row.prop(bake_settings, "image_width")
        row.prop(bake_settings, "image_height")
        
        row = output_box.row()
        row.prop(bake_settings, "file_format")
        row.prop(bake_settings, "color_depth")
        
        # Bake settings
        bake_box = layout.box()
        bake_box.label(text="Bake Settings", icon='RENDER_STILL')
        bake_box.prop(bake_settings, "bake_type")
        bake_box.prop(bake_settings, "samples")
        
        # Lighting passes
        passes_row = bake_box.row()
        passes_row.prop(bake_settings, "use_pass_direct")
        passes_row.prop(bake_settings, "use_pass_indirect")
        passes_row.prop(bake_settings, "use_pass_color")
        
        # Advanced settings
        advanced_box = layout.box()
        advanced_box.label(text="Advanced Settings", icon='PREFERENCES')
        advanced_box.prop(bake_settings, "margin")
        
        cage_row = advanced_box.row()
        cage_row.prop(bake_settings, "use_cage")
        cage_row.prop(bake_settings, "cage_extrusion")
        
        # Denoising
        denoise_box = layout.box()
        denoise_box.label(text="Denoising", icon='RENDER_ANIMATION')
        denoise_box.prop(bake_settings, "use_denoising")
        if bake_settings.use_denoising:
            denoise_box.prop(bake_settings, "denoising_input_passes")
        
        # GPU acceleration settings
        gpu_box = layout.box()
        gpu_box.label(text="GPU Acceleration", icon='ONIONSKIN_ON')
        gpu_box.prop(bake_settings, "use_gpu")
        if bake_settings.use_gpu:
            gpu_box.prop(bake_settings, "device")
        
        # Batch options
        batch_box = layout.box()
        batch_box.label(text="Batch Options", icon='OPTIONS')
        batch_box.prop(bake_settings, "clear_existing")
        batch_box.prop(bake_settings, "auto_save")
        batch_box.prop(bake_settings, "show_progress")
        
        # Material count info
        if context.scene.material_analysis_results:
            bakeable_count = 0
            for item in context.scene.material_analysis_results:
                if not item.material_name.startswith('[Empty Slot'):
                    material = bpy.data.materials.get(item.material_name)
                    if material:
                        # Check if this is a VXC material (Vertex Color only - no textures needed)
                        base_name, material_type, texture_info = get_meta_horizon_texture_info(material.name, material)
                        if material_type != "VXC":  # Exclude VXC materials from baking
                            bakeable_count += 1
            
            layout.separator()
            info_box = layout.box()
            info_box.label(text=f"Will bake {bakeable_count} materials", icon='INFO')








class META_HORIZON_PT_quick_start(bpy.types.Panel):
    """Quick Start Panel for beginners"""
    bl_label = "Quick Start"
    bl_idname = "META_HORIZON_PT_quick_start"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Horizon Worlds"
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        
        # Welcome header
        header_box = layout.box()
        header_row = header_box.row()
        header_row.label(text="Welcome to Blender to Meta Horizon Exporter!", icon='WORLD')
        
        # Quick start info
        info_box = header_box.box()
        info_box.label(text="First time using this tool? Start here:", icon='HELP')
        info_col = info_box.column(align=True)
        info_col.label(text="1. Select your objects")
        info_col.label(text="2. Launch the Export Wizard")
        info_col.label(text="3. Follow the step-by-step guide")
        
        # Launch wizard button - most prominent with persistent blue
        layout.separator()
        
        wizard_col = layout.column()
        wizard_col.scale_y = 2.0
        
        # Create button with persistent pressed/blue appearance
        button_row = wizard_col.row()
        button_row.operator("meta_horizon.wizard_reset", text="🚀 Launch Export Wizard", icon='SCRIPT', depress=True)


class META_HORIZON_PT_analysis(bpy.types.Panel):
    """Analysis Panel - Step 1 in logical workflow"""
    bl_label = "1. Scene Analysis"
    bl_idname = "META_HORIZON_PT_analysis"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Horizon Worlds"
    bl_order = 1

    def draw(self, context):
        layout = self.layout
        
        # Analysis controls
        analysis_box = layout.box()
        analysis_box.label(text="Analyze Your Scene", icon='VIEWZOOM')
        
        settings = context.scene.horizon_export_settings
        
        # Mode selection
        mode_row = analysis_box.row()
        mode_row.prop(settings, "analyze_all_materials", text="Include ALL scene materials")
        
        # Analysis buttons
        button_col = analysis_box.column()
        button_col.scale_y = 1.3
        
        # Materials analysis
        mat_row = button_col.row()
        if settings.analyze_all_materials:
            mat_row.operator("meta_horizon.analyze_all_materials", text="🎨 Analyze All Materials", icon='MATERIAL_DATA')
        else:
            # Check if any objects are selected
            has_selected_objects = len(context.selected_objects) > 0
            mat_row.enabled = has_selected_objects
            mat_row.operator("meta_horizon.analyze_materials", text="🎨 Analyze Materials (Selected)", icon='MATERIAL')
            if not has_selected_objects:
                # Add a label below to explain why it's disabled
                disabled_row = button_col.row()
                disabled_row.label(text="Select objects to analyze materials", icon='INFO')
        
        # Mesh analysis
        mesh_row = button_col.row()
        # Check if any objects are selected
        has_selected_objects = len(context.selected_objects) > 0
        mesh_row.enabled = has_selected_objects
        mesh_row.operator("meta_horizon.analyze_meshes", text="🔧 Analyze Meshes (Selected)", icon='MESH_DATA')
        if not has_selected_objects:
            # Add a label below to explain why it's disabled
            disabled_row = button_col.row()
            disabled_row.label(text="Select objects to analyze meshes", icon='INFO')
        
        # Show analysis summary if available
        if context.scene.material_analysis_results or context.scene.mesh_analysis_results:
            layout.separator()
            summary_box = layout.box()
            summary_box.label(text="Analysis Results", icon='INFO')
            
            # Material summary
            if context.scene.material_analysis_results:
                total_materials = len(context.scene.material_analysis_results)
                issues = sum(1 for item in context.scene.material_analysis_results if item.has_naming_issues)
                
                mat_summary_row = summary_box.row()
                if issues > 0:
                    mat_summary_row.label(text=f"Materials: {total_materials} total, {issues} need fixes", icon='ERROR')
                else:
                    mat_summary_row.label(text=f"Materials: {total_materials} total, all compliant", icon='CHECKMARK')
            
            # Mesh summary
            if context.scene.mesh_analysis_results:
                total_meshes = len(context.scene.mesh_analysis_results)
                total_polygons = sum(item.polygon_count_final for item in context.scene.mesh_analysis_results)
                total_vertices = sum(item.vertex_count_final for item in context.scene.mesh_analysis_results)
                high_poly = sum(1 for item in context.scene.mesh_analysis_results if item.is_high_poly)
                no_uvs = sum(1 for item in context.scene.mesh_analysis_results if item.uv_channel_count == 0)
                
                mesh_summary_row = summary_box.row()
                if high_poly > 0 or no_uvs > 0:
                    warnings = []
                    if high_poly > 0:
                        warnings.append(f"{high_poly} high-poly")
                    if no_uvs > 0:
                        warnings.append(f"{no_uvs} missing UVs")
                    mesh_summary_row.label(text=f"Meshes: {total_meshes} total, {', '.join(warnings)}", icon='ERROR')
                else:
                    mesh_summary_row.label(text=f"Meshes: {total_meshes} total, ready for export", icon='CHECKMARK')
                
                # Show total polygon and vertex counts
                totals_row = summary_box.row()
                totals_row.label(text=f"Total: {total_polygons:,} polygons, {total_vertices:,} vertices", icon='MESH_DATA')
            
            # Detailed Material List
            if context.scene.material_analysis_results:
                layout.separator()
                materials_box = layout.box()
                
                # Header with expand/collapse button
                header_row = materials_box.row()
                toggle_op = header_row.operator("meta_horizon.toggle_materials_list", 
                                              text="", 
                                              icon='TRIA_DOWN' if settings.materials_list_expanded else 'TRIA_RIGHT')
                header_row.label(text=f"📋 Material Analysis Details ({len(context.scene.material_analysis_results)} total)", 
                               icon='MATERIAL_DATA')
                
                # Status Legend inside Material Analysis Details
                if settings.materials_list_expanded:
                    legend_box = materials_box.box()
                    legend_box.label(text="Status Legend", icon='INFO')
                    legend_col = legend_box.column()
                    legend_col.scale_y = 0.8
                    
                    legend_row1 = legend_col.row()
                    legend_row1.label(text="✓ Ready for export", icon='CHECKMARK')
                    legend_row1.label(text="⚠️ Needs attention", icon='CANCEL')
                    
                    legend_row2 = legend_col.row()
                    legend_row2.label(text="❌ Critical issues", icon='ERROR')
                    legend_row2.label(text="", icon='BLANK1')  # Empty space for alignment
                
                # Show expandable list if expanded
                if settings.materials_list_expanded:
                    # Filter out empty slots for cleaner display
                    filtered_materials = [item for item in context.scene.material_analysis_results 
                                        if not item.material_name.startswith('[Empty Slot')]
                    
                    if filtered_materials:
                        # Pagination controls
                        total_filtered = len(filtered_materials)
                        page_size = settings.materials_page_size
                        current_page = settings.materials_current_page
                        max_page = max(0, (total_filtered - 1) // page_size)
                        
                        # Ensure current page is valid
                        if current_page > max_page:
                            settings.materials_current_page = max_page
                            current_page = max_page
                        
                        start_idx = current_page * page_size
                        end_idx = min(start_idx + page_size, total_filtered)
                        
                        # Pagination header
                        if total_filtered > page_size:
                            nav_row = materials_box.row()
                            nav_row.label(text=f"Page {current_page + 1} of {max_page + 1} ({start_idx + 1}-{end_idx} of {total_filtered})")
                            
                            nav_buttons = nav_row.row()
                            nav_buttons.scale_x = 0.8
                            
                            # Previous button
                            prev_button = nav_buttons.row()
                            prev_button.enabled = current_page > 0
                            prev_op = prev_button.operator("meta_horizon.materials_page_nav", text="◀ Prev", icon='TRIA_LEFT')
                            prev_op.direction = "prev"
                            
                            # Next button
                            next_button = nav_buttons.row()
                            next_button.enabled = current_page < max_page
                            next_op = next_button.operator("meta_horizon.materials_page_nav", text="Next ▶", icon='TRIA_RIGHT')
                            next_op.direction = "next"
                        
                        # Material list for current page
                        materials_col = materials_box.column()
                        
                        for i, item in enumerate(filtered_materials[start_idx:end_idx]):
                            # Create a box for each material for better organization
                            mat_box = materials_col.box()
                            
                            # Main material info row
                            mat_row = mat_box.row()
                            
                            # Status icon and material name
                            if item.has_naming_issues or item.is_empty_material or item.has_uv_conflicts or item.has_uv_mapping_nodes:
                                if item.is_empty_material:
                                    mat_row.label(text="", icon='ERROR')  # Red X for empty materials
                                    status_text = "❌"
                                elif item.has_uv_conflicts:
                                    mat_row.label(text="", icon='ERROR')  # Red X for UV conflicts
                                    status_text = "❌"
                                elif item.has_uv_mapping_nodes:
                                    mat_row.label(text="", icon='ERROR')  # Red X for UV mapping nodes
                                    status_text = "❌"
                                else:
                                    mat_row.label(text="", icon='CANCEL')  # Warning for naming issues
                                    status_text = "⚠️"
                            else:
                                mat_row.label(text="", icon='CHECKMARK')  # Green check for compliant
                                status_text = "✓"
                            
                            # Material name with truncation for long names
                            mat_name = item.material_name
                            if len(mat_name) > 20:
                                mat_name = mat_name[:17] + "..."
                            
                            # Show material name and type (take up full width)
                            name_col = mat_row.column()
                            name_col.scale_x = 3.0
                            name_col.label(text=f"{status_text} {mat_name}")
                            
                            # Show shader type
                            type_col = mat_row.column()
                            type_col.scale_x = 1.5
                            shader_display = item.shader_type.replace("ShaderNodeBsdf", "").replace("Principled", "PBR")
                            type_col.label(text=shader_display)
                            
                            # Action buttons section - in a separate row for better readability
                            buttons_added = False
                            
                            # Critical issues first
                            if item.has_uv_mapping_nodes or item.has_uv_conflicts or (item.is_empty_material and item.can_be_setup):
                                actions_row = mat_box.row()
                                actions_row.scale_y = 1.1
                                
                                if item.has_uv_mapping_nodes:
                                    simplify_op = actions_row.operator("meta_horizon.simplify_material", text="Simplify", icon='MATERIAL')
                                    simplify_op.material_name = item.material_name
                                    buttons_added = True
                                
                                if item.has_uv_conflicts:
                                    resolve_op = actions_row.operator("meta_horizon.resolve_uv_conflicts", text="Fix UVs", icon='UV_DATA')
                                    resolve_op.material_name = item.material_name
                                    buttons_added = True
                                
                                if item.is_empty_material and item.can_be_setup:
                                    setup_op = actions_row.operator("meta_horizon.setup_empty_material", text="Setup", icon='ADD')
                                    setup_op.material_name = item.material_name
                                    buttons_added = True
                            
                            # Always show Edit Type button
                            if buttons_added:
                                # Add to existing row if there's space, otherwise new row
                                edit_type_op = actions_row.operator("meta_horizon.choose_material_suffix", text="Edit Type", icon='MATERIAL')
                            else:
                                # Create new row for edit type
                                edit_type_row = mat_box.row()
                                edit_type_row.scale_y = 1.1
                                edit_type_op = edit_type_row.operator("meta_horizon.choose_material_suffix", text="Edit Type", icon='MATERIAL')
                            edit_type_op.material_name = item.material_name
                            buttons_added = True
                            
                            # If no buttons were added, show ready status
                            if not buttons_added:
                                status_row = mat_box.row()
                                status_row.scale_y = 0.8
                                status_row.label(text="✅ Material ready for export", icon='CHECKMARK')
                            
                            # Objects using this material row
                            if item.using_objects:
                                objects_row = mat_box.row()
                                objects_row.scale_y = 0.8
                                
                                # Objects label
                                objects_label_col = objects_row.column()
                                objects_label_col.scale_x = 0.3
                                objects_label_col.label(text="Objects:", icon='OBJECT_DATA')
                                
                                # Objects list (truncated if too long)
                                objects_col = objects_row.column()
                                objects_col.scale_x = 2.0
                                objects_text = item.using_objects
                                if len(objects_text) > 40:
                                    objects_text = objects_text[:37] + "..."
                                objects_col.label(text=objects_text)
                                
                                # Select objects button
                                select_col = objects_row.column()
                                select_col.scale_x = 0.8
                                select_op = select_col.operator("meta_horizon.select_objects_by_material", text="Select", icon='RESTRICT_SELECT_OFF')
                                select_op.material_name = item.material_name
                            else:
                                # No objects using this material
                                objects_row = mat_box.row()
                                objects_row.scale_y = 0.8
                                objects_row.label(text="⚠ No objects using this material", icon='INFO')
                        
                        # Page size settings
                        if total_filtered > 5:
                            page_settings_row = materials_box.row()
                            page_settings_row.prop(settings, "materials_page_size", text="Items per page")
                    else:
                        materials_box.label(text="No materials to display (empty slots filtered out)")
                    
                    # Material Fixes section - inside Material Analysis Details
                    materials_box.separator()
                    fixes_box = materials_box.box()
                    fixes_box.label(text="Material Fixes", icon='TOOL_SETTINGS')
                    
                    # Quick fix button
                    fix_col = fixes_box.column()
                    fix_col.scale_y = 1.3
                    
                    # Check if we have materials that need renaming
                    materials_needing_rename = 0
                    if context.scene.material_analysis_results:
                        materials_needing_rename = sum(1 for item in context.scene.material_analysis_results 
                                                     if not item.material_name.startswith('[Empty Slot') and
                                                     item.has_naming_issues and 
                                                     item.recommended_name and 
                                                     item.recommended_name != item.material_name)
                    
                    fix_button_row = fix_col.row()
                    if materials_needing_rename > 0:
                        fix_button_row.operator("meta_horizon.apply_all_recommended_names", 
                                               text=f"🏷️ Fix All Material Names ({materials_needing_rename})", 
                                               icon='FILE_REFRESH')
                    else:
                        fix_button_row.operator("meta_horizon.apply_all_recommended_names", 
                                               text="🏷️ Fix All Material Names (Run Analysis First)", 
                                               icon='FILE_REFRESH')
                        fix_button_row.enabled = False
                    
                    # Create unique materials
                    fix_col.operator("meta_horizon.create_unique_materials", text="🎯 Make Materials Unique", icon='DUPLICATE')
                    # Resolve all UV conflicts
                    fix_col.operator("meta_horizon.resolve_all_uv_conflicts", text="🔄 Resolve All UV Conflicts", icon='UV_DATA')
                else:
                    # Collapsed state - show brief summary
                    materials_box.label(text="Click to expand detailed material list", icon='INFO')
            
            # Detailed Mesh List
            if context.scene.mesh_analysis_results:
                layout.separator()
                meshes_box = layout.box()
                
                # Header with expand/collapse button
                header_row = meshes_box.row()
                toggle_op = header_row.operator("meta_horizon.toggle_meshes_list", 
                                              text="", 
                                              icon='TRIA_DOWN' if settings.meshes_list_expanded else 'TRIA_RIGHT')
                header_row.label(text=f"🔧 Mesh Analysis Details ({len(context.scene.mesh_analysis_results)} total)", 
                               icon='MESH_DATA')
                
                # Status Legend inside Mesh Analysis Details
                if settings.meshes_list_expanded:
                    legend_box = meshes_box.box()
                    legend_box.label(text="Status Legend", icon='INFO')
                    legend_col = legend_box.column()
                    legend_col.scale_y = 0.8
                    
                    legend_row1 = legend_col.row()
                    legend_row1.label(text="✓ Ready for export", icon='CHECKMARK')
                    legend_row1.label(text="⚠️ Needs attention", icon='CANCEL')
                    
                    legend_row2 = legend_col.row()
                    legend_row2.label(text="❌ Critical issues", icon='ERROR')
                    legend_row2.label(text="", icon='BLANK1')  # Empty space for alignment
                
                # Show expandable list if expanded
                if settings.meshes_list_expanded:
                    mesh_results = context.scene.mesh_analysis_results
                    
                    if mesh_results:
                        # Pagination controls
                        total_meshes = len(mesh_results)
                        page_size = settings.meshes_page_size
                        current_page = settings.meshes_current_page
                        max_page = max(0, (total_meshes - 1) // page_size)
                        
                        # Ensure current page is valid
                        if current_page > max_page:
                            settings.meshes_current_page = max_page
                            current_page = max_page
                        
                        start_idx = current_page * page_size
                        end_idx = min(start_idx + page_size, total_meshes)
                        
                        # Pagination header
                        if total_meshes > page_size:
                            nav_row = meshes_box.row()
                            nav_row.label(text=f"Page {current_page + 1} of {max_page + 1} ({start_idx + 1}-{end_idx} of {total_meshes})")
                            
                            nav_buttons = nav_row.row()
                            nav_buttons.scale_x = 0.8
                            
                            # Previous button
                            prev_button = nav_buttons.row()
                            prev_button.enabled = current_page > 0
                            prev_op = prev_button.operator("meta_horizon.meshes_page_nav", text="◀ Prev", icon='TRIA_LEFT')
                            prev_op.direction = "prev"
                            
                            # Next button
                            next_button = nav_buttons.row()
                            next_button.enabled = current_page < max_page
                            next_op = next_button.operator("meta_horizon.meshes_page_nav", text="Next ▶", icon='TRIA_RIGHT')
                            next_op.direction = "next"
                        
                        # Mesh list for current page
                        meshes_col = meshes_box.column()
                        
                        for i, item in enumerate(mesh_results[start_idx:end_idx]):
                            # Create a box for each mesh for better organization
                            mesh_box = meshes_col.box()
                            
                            # Main mesh info row
                            mesh_row = mesh_box.row()
                            
                            # Status icon and object name
                            has_issues = (item.is_high_poly or 
                                        item.uv_channel_count == 0 or 
                                        item.has_geometry_adding_modifiers or
                                        item.has_destructive_modifiers)
                            
                            if has_issues:
                                if item.is_high_poly or item.uv_channel_count == 0:
                                    mesh_row.label(text="", icon='ERROR')  # Red X for critical issues
                                    status_text = "❌"
                                else:
                                    mesh_row.label(text="", icon='CANCEL')  # Warning for modifier issues
                                    status_text = "⚠️"
                            else:
                                mesh_row.label(text="", icon='CHECKMARK')  # Green check for ready objects
                                status_text = "✓"
                            
                            # Object name with truncation
                            obj_name = item.object_name
                            if len(obj_name) > 18:
                                obj_name = obj_name[:15] + "..."
                            
                            # Show object name and poly count (take up more space)
                            name_col = mesh_row.column()
                            name_col.scale_x = 2.5
                            poly_text = f"({item.polygon_count})" if item.polygon_count > 0 else ""
                            name_col.label(text=f"{status_text} {obj_name} {poly_text}")
                            
                            # Show issues summary
                            issue_col = mesh_row.column()
                            issue_col.scale_x = 2.0
                            issues = []
                            if item.is_high_poly:
                                issues.append("High-poly")
                            if item.uv_channel_count == 0:
                                issues.append("No UVs")
                            if item.has_geometry_adding_modifiers:
                                issues.append("Modifiers")
                            
                            if issues:
                                issue_col.label(text=", ".join(issues))
                            else:
                                issue_col.label(text="Ready")
                            
                            # Action buttons section - in a separate row for better readability
                            actions_added = False
                            
                            # Critical issues first
                            if item.uv_channel_count == 0 or item.has_geometry_adding_modifiers or item.polygon_count > 100:
                                actions_row = mesh_box.row()
                                actions_row.scale_y = 1.1
                                
                                if item.uv_channel_count == 0:
                                    unwrap_op = actions_row.operator("meta_horizon.smart_uv_project", text="Create UVs", icon='UV_DATA')
                                    unwrap_op.object_name = item.object_name
                                    actions_added = True
                                
                                if item.has_geometry_adding_modifiers:
                                    apply_op = actions_row.operator("meta_horizon.apply_geometry_modifiers", text="Apply Mods", icon='MODIFIER')
                                    apply_op.object_name = item.object_name
                                    actions_added = True
                                
                                if item.polygon_count > 100:
                                    decimate_op = actions_row.operator("meta_horizon.decimate_single_mesh", text="Optimize", icon='MOD_DECIM')
                                    decimate_op.object_name = item.object_name
                                    actions_added = True
                            
                            # If no actions are needed, show ready status
                            if not actions_added:
                                status_row = mesh_box.row()
                                status_row.scale_y = 0.8
                                status_row.label(text="✅ Mesh ready for export", icon='CHECKMARK')
                        
                        # Page size settings
                        if total_meshes > 5:
                            page_settings_row = meshes_box.row()
                            page_settings_row.prop(settings, "meshes_page_size", text="Items per page")
                    else:
                        meshes_box.label(text="No mesh analysis results available")
                    
                    # Mesh Preparation section - inside Mesh Analysis Details
                    meshes_box.separator()
                    prep_box = meshes_box.box()
                    prep_box.label(text="Mesh Preparation", icon='TOOL_SETTINGS')
                    
                    prep_col = prep_box.column()
                    prep_col.scale_y = 1.3
                    
                    # UV unwrapping
                    prep_col.operator("meta_horizon.smart_uv_project_selected", text="📐 Unwrap UVs (Selected)", icon='UV_DATA')
                    
                    # Decimation
                    export_settings = context.scene.horizon_export_settings
                    selected_objects = context.selected_objects
                    all_objects = set()
                    for obj in selected_objects:
                        collect_children_objects(obj, all_objects)
                    
                    mesh_objects = [obj for obj in all_objects if obj.type == 'MESH' and obj.data]
                    has_mesh_objects = len(mesh_objects) > 0
                    
                    # Decimation settings row
                    decimate_row = prep_box.row()
                    decimate_row.prop(export_settings, "decimate_type", text="Type")
                    decimate_row.prop(export_settings, "decimate_ratio", text="Ratio", slider=True)
                    
                    # Decimation button
                    decimate_button_row = prep_col.row()
                    decimate_button_row.enabled = has_mesh_objects
                    
                    if has_mesh_objects:
                        decimate_button_row.operator("meta_horizon.decimate_meshes", 
                                                    text=f"🔻 Decimate Meshes ({len(mesh_objects)} objects)", 
                                                    icon='MOD_DECIM')
                    else:
                        decimate_button_row.operator("meta_horizon.decimate_meshes", 
                                                    text="🔻 Decimate Meshes (No Meshes Selected)", 
                                                    icon='MOD_DECIM')
                    
                    # Apply all modifiers button
                    prep_col.operator("meta_horizon.apply_all_modifiers", text="🔧 Apply All Modifiers", icon='MODIFIER')
                else:
                    # Collapsed state - show brief summary
                    meshes_box.label(text="Click to expand detailed mesh list", icon='INFO')
            



class META_HORIZON_PT_preparation(bpy.types.Panel):
    """Preparation Panel - Step 2 in logical workflow"""
    bl_label = "2. Performance"
    bl_idname = "META_HORIZON_PT_preparation"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Horizon Worlds"
    bl_order = 2

    def draw(self, context):
        layout = self.layout
        
        # Performance optimization
        perf_box = layout.box()
        perf_box.label(text="Combine Mesh & Create UV Atlas", icon='SETTINGS')
        
        # UV Atlas
        atlas_settings = context.scene.horizon_atlas_settings
        selected_objects = context.selected_objects
        mesh_objects = [obj for obj in selected_objects if obj.type == 'MESH' and obj.data]
        has_enough_objects = len(mesh_objects) >= 2
        
        # Apply All Modifiers button
        apply_modifiers_row = perf_box.row()
        apply_modifiers_row.scale_y = 1.2
        
        # Count objects with modifiers
        objects_with_modifiers = 0
        total_modifiers = 0
        for obj in mesh_objects:
            if len(obj.modifiers) > 0:
                objects_with_modifiers += 1
                total_modifiers += len(obj.modifiers)
        
        if mesh_objects:
            if objects_with_modifiers > 0:
                apply_modifiers_row.operator("meta_horizon.apply_all_modifiers", 
                                        text=f"🔧 Apply All Modifiers ({total_modifiers} modifiers on {objects_with_modifiers} objects)", 
                                        icon='MODIFIER')
            else:
                apply_modifiers_row.operator("meta_horizon.apply_all_modifiers", 
                                        text="🔧 Apply All Modifiers (No Modifiers Found)", 
                                        icon='MODIFIER')
                apply_modifiers_row.enabled = False
        else:
            apply_modifiers_row.operator("meta_horizon.apply_all_modifiers", 
                                    text="🔧 Apply All Modifiers (Select Objects)", 
                                    icon='MODIFIER')
            apply_modifiers_row.enabled = False
        
        perf_box.separator()
        
        atlas_row = perf_box.row()
        atlas_row.prop(atlas_settings, "atlas_size", text="Atlas Size")
        atlas_row.prop(atlas_settings, "combine_materials", text="Combine Materials")
        
        atlas_button_row = perf_box.row()
        atlas_button_row.scale_y = 1.3
        atlas_button_row.enabled = has_enough_objects
        
        if has_enough_objects:
            atlas_button_row.operator("meta_horizon.create_uv_atlas", text=f"🗂️ Create UV Atlas ({len(mesh_objects)} objects)", icon='UV_DATA')
        else:
            atlas_button_row.operator("meta_horizon.create_uv_atlas", text="🗂️ Create UV Atlas (Select 2+ Objects)", icon='UV_DATA')


class META_HORIZON_PT_export_options(bpy.types.Panel):
    """Export Options and Advanced Tools Panel - Step 3 in logical workflow"""
    bl_label = "3. Export & Advanced Tools"
    bl_idname = "META_HORIZON_PT_export_options"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Horizon Worlds"
    bl_order = 3

    def draw(self, context):
        layout = self.layout
        
        export_settings = context.scene.horizon_export_settings
        
        # Texture Baking Section (moved to top)
        baking_box = layout.box()
        baking_box.label(text="Texture Baking", icon='RENDER_STILL')
        
        bake_settings = context.scene.horizon_bake_settings
        
        # Output directory (moved to first)
        baking_box.prop(bake_settings, "output_directory", text="Output")
        
        # Quick bake settings
        settings_row = baking_box.row()
        settings_row.prop(bake_settings, "bake_type", text="Type")
        settings_row.prop(bake_settings, "samples", text="Quality")
        
        # Bake buttons
        bake_col = baking_box.column()
        bake_col.scale_y = 1.3
        
        # Check if we have materials to bake
        bakeable_count = 0
        if context.scene.material_analysis_results:
            for item in context.scene.material_analysis_results:
                if not item.material_name.startswith('[Empty Slot'):
                    material = bpy.data.materials.get(item.material_name)
                    if material:
                        # Check if this is a VXC material (Vertex Color only - no textures needed)
                        base_name, material_type, texture_info = get_meta_horizon_texture_info(material.name, material)
                        if material_type != "VXC":  # Exclude VXC materials from baking
                            bakeable_count += 1
        
        bake_button_row = bake_col.row()
        
        # Check if file is saved
        file_is_saved = bpy.data.is_saved
        
        if bakeable_count > 0:
            if file_is_saved:
                bake_button_row.operator("meta_horizon.bake_all_materials", text=f"🔥 Bake All Materials ({bakeable_count})", icon='RENDER_ANIMATION')
            else:
                save_first_btn = bake_button_row.operator("meta_horizon.bake_all_materials", text=f"💾 Save File & Bake All Materials ({bakeable_count})", icon='FILE_TICK')
                # Add a warning row
                warning_row = bake_col.row()
                warning_row.alert = True
                warning_row.label(text="⚠️ File must be saved before baking", icon='ERROR')
        else:
            if file_is_saved:
                bake_button_row.operator("meta_horizon.bake_all_materials", text="🔥 Bake All Materials (Run Analysis First)", icon='RENDER_ANIMATION')
            else:
                bake_button_row.operator("meta_horizon.bake_all_materials", text="💾 Save File & Bake All Materials (Run Analysis First)", icon='FILE_TICK')
                # Add a warning row
                warning_row = bake_col.row()
                warning_row.alert = True
                warning_row.label(text="⚠️ File must be saved before baking", icon='ERROR')
            bake_button_row.enabled = False

        layout.separator()
        
        # FBX Export Section (moved below baking)
        export_box = layout.box()
        export_box.label(text="🚀 FBX Export", icon='EXPORT')
        
        # Export directory setting
        export_box.prop(export_settings, "export_location", text="Export Directory")
        
        export_box.separator()
        
        # Check selection and show appropriate text
        selected_count = len([obj for obj in context.selected_objects if obj.type == 'MESH'])
        
        # Export button
        export_col = export_box.column()
        export_col.scale_y = 1.8
        
        # Check if file is saved
        file_is_saved = bpy.data.is_saved
        
        if selected_count > 0:
            if file_is_saved:
                export_button = export_col.operator("meta_horizon.export_with_details", text=f"Export {selected_count} Selected Objects (FBX)", icon='EXPORT')
            else:
                export_button = export_col.operator("meta_horizon.export_with_details", text=f"💾 Save File & Export {selected_count} Selected Objects (FBX)", icon='FILE_TICK')
                # Add a warning row
                warning_row = export_col.row()
                warning_row.alert = True
                warning_row.label(text="⚠️ File must be saved before exporting", icon='ERROR')
        else:
            if file_is_saved:
                export_button = export_col.operator("meta_horizon.export_with_details", text="Export All Objects (FBX)", icon='EXPORT')
            else:
                export_button = export_col.operator("meta_horizon.export_with_details", text="💾 Save File & Export All Objects (FBX)", icon='FILE_TICK')
                # Add a warning row
                warning_row = export_col.row()
                warning_row.alert = True
                warning_row.label(text="⚠️ File must be saved before exporting", icon='ERROR')




class META_HORIZON_OT_create_uv_atlas(Operator):
    """Create UV atlas for selected objects to improve performance"""
    bl_idname = "meta_horizon.create_uv_atlas"
    bl_label = "Create UV Atlas"
    bl_description = "Combine selected objects into a single UV atlas for improved performance (reduces draw calls)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected_objects = context.selected_objects
        if not selected_objects:
            self.report({'WARNING'}, "No objects selected")
            return {'CANCELLED'}
        
        # Filter to mesh objects only
        mesh_objects = [obj for obj in selected_objects if obj.type == 'MESH' and obj.data]
        
        if not mesh_objects:
            self.report({'WARNING'}, "No mesh objects found in selection")
            return {'CANCELLED'}
        
        if len(mesh_objects) < 2:
            self.report({'WARNING'}, "Select at least 2 mesh objects to create an atlas")
            return {'CANCELLED'}
        
        # Get atlas settings
        atlas_settings = context.scene.horizon_atlas_settings
        
        # Open console to show progress
        try:
            bpy.ops.wm.console_toggle()
        except:
            pass  # Console toggle might not be available on all platforms
        
        # Create the UV atlas
        success, atlas_material, error_msg = create_uv_atlas(mesh_objects, atlas_settings)
        
        if success:
            message_parts = [f"Successfully created UV atlas with {len(mesh_objects)} objects"]
            
            if atlas_material:
                message_parts.append(f"Atlas material: '{atlas_material.name}'")
            
            if atlas_settings.combine_materials:
                message_parts.append("Materials combined into single atlas material")
            
            message_parts.append("Performance should be improved due to reduced draw calls")
            
            self.report({'INFO'}, ". ".join(message_parts) + ".")
            
            # Refresh analyses if they exist
            if hasattr(context.scene, 'material_analysis_results') and context.scene.material_analysis_results:
                if context.scene.horizon_export_settings.analyze_all_materials:
                    bpy.ops.meta_horizon.analyze_all_materials()
                else:
                    bpy.ops.meta_horizon.analyze_materials()
            
            if hasattr(context.scene, 'mesh_analysis_results') and context.scene.mesh_analysis_results:
                bpy.ops.meta_horizon.analyze_meshes()
        else:
            self.report({'ERROR'}, f"Failed to create UV atlas: {error_msg}")
            return {'CANCELLED'}
        
        return {'FINISHED'}

    def invoke(self, context, event):
        # Count mesh objects
        selected_objects = context.selected_objects
        mesh_objects = [obj for obj in selected_objects if obj.type == 'MESH' and obj.data]
        
        if not mesh_objects:
            self.report({'WARNING'}, "No mesh objects found in selection")
            return {'CANCELLED'}
        
        if len(mesh_objects) < 2:
            self.report({'WARNING'}, "Select at least 2 mesh objects to create an atlas")
            return {'CANCELLED'}
        
        # Store for the draw method
        self.mesh_objects = mesh_objects
        
        return context.window_manager.invoke_props_dialog(self, width=600)

    def draw(self, context):
        layout = self.layout
        atlas_settings = context.scene.horizon_atlas_settings
        
        layout.label(text=f"Create UV Atlas with {len(self.mesh_objects)} objects?", icon='UV_DATA')
        layout.separator()
        
        # Show object list
        objects_box = layout.box()
        objects_box.label(text="Objects to be atlased:", icon='MESH_DATA')
        
        # Limit display to prevent UI overflow
        display_limit = 8
        for i, obj in enumerate(self.mesh_objects[:display_limit]):
            row = objects_box.row()
            row.label(text=f"  • {obj.name}", icon='OBJECT_DATA')
        
        if len(self.mesh_objects) > display_limit:
            more_row = objects_box.row()
            more_row.label(text=f"  ... and {len(self.mesh_objects) - display_limit} more objects", icon='THREE_DOTS')
        
        layout.separator()
        
        # Atlas settings
        settings_box = layout.box()
        settings_box.label(text="Atlas Settings", icon='SETTINGS')
        
        # Basic settings
        settings_box.prop(atlas_settings, "atlas_name")
        settings_box.prop(atlas_settings, "atlas_size")
        
        # UV settings
        uv_row = settings_box.row()
        uv_row.prop(atlas_settings, "island_margin")
        uv_row.prop(atlas_settings, "rotate_islands")
        
        settings_box.prop(atlas_settings, "auto_unwrap")
        
        # Atlas workflow options
        workflow_box = layout.box()
        workflow_box.label(text="Atlas Workflow", icon='TEXTURE')
        
        workflow_box.prop(atlas_settings, "combine_materials", text="Create single atlas material for Meta Horizon")
        
        if atlas_settings.combine_materials:
            bake_row = workflow_box.row()
            bake_row.label(text="✓ Will bake all materials into one atlas texture", icon='RENDER_STILL')
            result_row = workflow_box.row()
            result_row.label(text="  → Single material + Single texture = Best performance", icon='CHECKMARK')
            
            # Bake settings
            settings_row = workflow_box.row()
            settings_row.prop(atlas_settings, "bake_samples", text="Quality")
            settings_row.prop(atlas_settings, "save_atlas_textures", text="Save Texture")
        else:
            keep_row = workflow_box.row()
            keep_row.label(text="✓ Keep original materials (no baking)", icon='INFO')
            note_row = workflow_box.row()
            note_row.label(text="  → UV atlas only, still multiple materials", icon='BLANK1')
        
        # Material settings
        material_box = layout.box()
        material_box.label(text="Material Options", icon='MATERIAL')
        
        material_box.prop(atlas_settings, "create_atlas_material")
        if atlas_settings.create_atlas_material:
            material_box.prop(atlas_settings, "atlas_material_type")
            material_box.prop(atlas_settings, "combine_materials")
        
        # Warnings
        layout.separator()
        warning_box = layout.box()
        warning_box.label(text="⚠️ Important Notes:", icon='ERROR')
        warning_box.label(text="• This operation will JOIN objects (cannot be undone)", icon='BLANK1')
        warning_box.label(text="• Save your file before proceeding", icon='BLANK1')
        warning_box.label(text="• Textures are preserved automatically", icon='BLANK1')
        warning_box.label(text="• Atlas reduces draw calls = better performance", icon='BLANK1')


class META_HORIZON_OT_create_unique_materials(Operator):
    """Create unique material copies for all objects that share materials"""
    bl_idname = "meta_horizon.create_unique_materials"
    bl_label = "Create Unique Materials"
    bl_description = "Create unique material copies for all objects that share materials with other objects"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Dictionary to track material usage: material_name -> list of objects using it
        material_usage = defaultdict(list)
        
        # Collect all objects and their material usage
        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH' and obj.data and obj.data.materials:
                for slot_index, slot in enumerate(obj.material_slots):
                    if slot.material:
                        material_usage[slot.material.name].append((obj, slot_index))
        
        # Find materials used by multiple objects
        shared_materials = {}
        for material_name, object_slots in material_usage.items():
            if len(object_slots) > 1:
                shared_materials[material_name] = object_slots
        
        if not shared_materials:
            self.report({'INFO'}, "No shared materials found - all materials are already unique to their objects")
            return {'FINISHED'}
        
        # Create unique materials for shared materials
        created_materials = []
        total_new_materials = 0
        
        for material_name, object_slots in shared_materials.items():
            original_material = bpy.data.materials.get(material_name)
            if not original_material:
                continue
            
            # Keep the original material for the first object, create copies for the rest
            objects_to_process = object_slots[1:]  # Skip the first object
            
            for obj, slot_index in objects_to_process:
                # Create a copy of the material for this object
                material_copy = original_material.copy()
                
                # Find a unique name for the material copy
                base_name = original_material.name
                counter = 1
                while bpy.data.materials.get(f"{base_name}.{counter:03d}"):
                    counter += 1
                
                material_copy.name = f"{base_name}.{counter:03d}"
                created_materials.append({
                    'original': material_name,
                    'copy': material_copy.name,
                    'object': obj.name
                })
                total_new_materials += 1
                
                # Replace the material in this object's slot
                obj.data.materials[slot_index] = material_copy
        
        # Create comprehensive report
        if created_materials:
            print(f"\n=== Created Unique Materials ===")
            print(f"Found {len(shared_materials)} materials shared between objects")
            print(f"Created {total_new_materials} unique material copies")
            print(f"\nDetails:")
            
            # Group by original material for cleaner reporting
            by_original = defaultdict(list)
            for item in created_materials:
                by_original[item['original']].append(item)
            
            for original_name, copies in by_original.items():
                print(f"\n  '{original_name}' was shared by {len(copies) + 1} objects:")
                print(f"    • First object keeps original material")
                for copy_info in copies:
                    print(f"    • '{copy_info['object']}' now uses '{copy_info['copy']}'")
            
            self.report({'INFO'}, 
                       f"Created {total_new_materials} unique materials from {len(shared_materials)} shared materials. "
                       f"Check console for details.")
            
            # Refresh the material analysis to show the updated state
            if context.scene.horizon_export_settings.analyze_all_materials:
                bpy.ops.meta_horizon.analyze_all_materials()
            else:
                bpy.ops.meta_horizon.analyze_materials()
        else:
            self.report({'WARNING'}, "No material copies were created")
        
        return {'FINISHED'}

    def invoke(self, context, event):
        # Count materials that would be affected
        material_usage = defaultdict(list)
        
        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH' and obj.data and obj.data.materials:
                for slot_index, slot in enumerate(obj.material_slots):
                    if slot.material:
                        material_usage[slot.material.name].append((obj, slot_index))
        
        # Count shared materials and total new materials that would be created
        shared_materials = {}
        total_new_materials = 0
        for material_name, object_slots in material_usage.items():
            if len(object_slots) > 1:
                shared_materials[material_name] = object_slots
                total_new_materials += len(object_slots) - 1  # -1 because first object keeps original
        
        if not shared_materials:
            self.report({'INFO'}, "No shared materials found - all materials are already unique to their objects")
            return {'CANCELLED'}
        
        # Store for the draw method
        self.shared_materials_info = []
        for material_name, object_slots in shared_materials.items():
            object_names = [obj.name for obj, _ in object_slots]
            self.shared_materials_info.append({
                'material': material_name,
                'objects': object_names,
                'count': len(object_slots)
            })
        
        self.total_new_materials = total_new_materials
        
        return context.window_manager.invoke_props_dialog(self, width=700)

    def draw(self, context):
        layout = self.layout
        layout.label(text=f"Create {self.total_new_materials} unique material copies?", icon='DUPLICATE')
        layout.separator()
        
        # Show the list of shared materials
        box = layout.box()
        box.label(text="Shared Materials Found:", icon='MATERIAL')
        
        # Limit the display to prevent UI overflow
        display_limit = 15
        for i, info in enumerate(self.shared_materials_info[:display_limit]):
            row = box.row()
            row.label(text=f"• '{info['material']}' shared by {info['count']} objects:", icon='MATERIAL_DATA')
            
            # Show object names (limited to prevent overflow)
            objects_text = ", ".join(info['objects'][:5])
            if len(info['objects']) > 5:
                objects_text += f" (and {len(info['objects']) - 5} more)"
            
            obj_row = box.row()
            obj_row.label(text=f"    Objects: {objects_text}", icon='OBJECT_DATA')
        
        if len(self.shared_materials_info) > display_limit:
            more_row = box.row()
            more_row.label(text=f"... and {len(self.shared_materials_info) - display_limit} more shared materials", icon='THREE_DOTS')
        
        layout.separator()
        
        # Explanation
        info_box = layout.box()
        info_box.label(text="What this will do:", icon='INFO')
        info_box.label(text="• First object using each material keeps the original", icon='BLANK1')
        info_box.label(text="• Other objects get unique copies (MaterialName.001, .002, etc.)", icon='BLANK1')
        info_box.label(text="• Enables independent material editing and texture baking", icon='BLANK1')
        info_box.label(text="• Prevents materials from affecting multiple objects simultaneously", icon='BLANK1')


class META_HORIZON_OT_export_wizard(Operator):
    """Ultimate Export Wizard for Meta Horizon Worlds - Step-by-step guided workflow"""
    bl_idname = "meta_horizon.export_wizard"
    bl_label = "Export Wizard"
    bl_description = "Ultimate guided workflow for preparing and exporting assets to Meta Horizon Worlds"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        # Initialize wizard state
        wizard = context.scene.horizon_wizard_state
        
        if wizard.current_step == 0:
            # Step 1: Scene Analysis
            self.perform_scene_analysis(context)
            wizard.current_step = 1
            wizard.step_analysis_complete = True
            wizard.progress_percentage = 15
            
        elif wizard.current_step == 1:
            # Step 2: Material Preparation
            if wizard.auto_fix_materials:
                self.auto_fix_materials(context)
            wizard.current_step = 2
            wizard.step_materials_complete = True
            wizard.progress_percentage = 30
            
        elif wizard.current_step == 2:
            # Step 3: Mesh Preparation
            if wizard.auto_apply_modifiers:
                self.auto_apply_modifiers(context)
            wizard.current_step = 3
            wizard.step_meshes_complete = True
            wizard.progress_percentage = 45
            
        elif wizard.current_step == 3:
            # Step 4: UV Preparation
            if wizard.auto_unwrap_uvs:
                self.auto_unwrap_uvs(context)
            wizard.current_step = 4
            wizard.step_uvs_complete = True
            wizard.progress_percentage = 60
            
        elif wizard.current_step == 4:
            # Step 5: Texture Baking (optional)
            if wizard.bake_textures:
                self.bake_textures(context)
            wizard.current_step = 5
            wizard.step_baking_complete = True
            wizard.progress_percentage = 80
            
        elif wizard.current_step == 5:
            # Step 6: Final Export
            self.perform_export(context)
            wizard.current_step = 6
            wizard.step_export_complete = True
            wizard.progress_percentage = 100
        
        # Force UI update to show the new step
        for area in context.screen.areas:
            area.tag_redraw()
            
        return {'FINISHED'}
    
    def perform_scene_analysis(self, context):
        """Analyze the scene and collect statistics"""
        wizard = context.scene.horizon_wizard_state
        
        # Clear previous analysis - use correct property names
        if hasattr(context.scene, 'mesh_analysis_results'):
            context.scene.mesh_analysis_results.clear()
        if hasattr(context.scene, 'material_analysis_results'):  
            context.scene.material_analysis_results.clear()
        
        # Get selected objects or all objects
        objects_to_analyze = context.selected_objects if context.selected_objects else context.scene.objects
        
        mesh_objects = [obj for obj in objects_to_analyze if obj.type == 'MESH']
        
        wizard.total_objects = len(objects_to_analyze)
        wizard.mesh_objects = len(mesh_objects)
        wizard.current_task = "Analyzing scene..."
        
        try:
            # Analyze meshes
            bpy.ops.meta_horizon.analyze_meshes()
            
            # Analyze materials
            bpy.ops.meta_horizon.analyze_all_materials()
            
            # Count issues - use correct property names
            materials_with_issues = 0
            objects_with_modifiers = 0
            objects_needing_uvs = 0
            
            # Check if the properties exist
            if hasattr(context.scene, 'material_analysis_results'):
                for material_data in context.scene.material_analysis_results:
                    if material_data.has_naming_issues or material_data.is_empty_material or material_data.has_uv_conflicts:
                        materials_with_issues += 1
            
            if hasattr(context.scene, 'mesh_analysis_results'):
                for mesh_data in context.scene.mesh_analysis_results:
                    if mesh_data.has_geometry_adding_modifiers:
                        objects_with_modifiers += 1
                    if mesh_data.uv_channel_count == 0:
                        objects_needing_uvs += 1
            
            wizard.materials_with_issues = materials_with_issues
            wizard.objects_with_modifiers = objects_with_modifiers
            wizard.objects_needing_uvs = objects_needing_uvs
            wizard.materials_for_baking = len([m for m in bpy.data.materials if m.users > 0])
            
            wizard.current_task = "Analysis complete"
            
            self.report({'INFO'}, f"Analysis complete: {wizard.mesh_objects} mesh objects, {materials_with_issues} materials with issues")
        
        except Exception as e:
            wizard.current_task = f"Analysis failed: {str(e)}"
            self.report({'ERROR'}, f"Analysis failed: {str(e)}")
            print(f"Wizard analysis error: {e}")
    
    def auto_fix_materials(self, context):
        """Automatically fix material issues"""
        wizard = context.scene.horizon_wizard_state
        wizard.current_task = "Fixing materials..."
        
        try:
            # Apply recommended names
            bpy.ops.meta_horizon.apply_all_recommended_names()
            
            # Setup empty materials
            if hasattr(context.scene, 'material_analysis_results'):
                for material_data in context.scene.material_analysis_results:
                    if material_data.is_empty_material and material_data.can_be_setup:
                        bpy.ops.meta_horizon.setup_empty_material(material_name=material_data.material_name)
            
            # Resolve UV conflicts
            if hasattr(context.scene, 'material_analysis_results'):
                for material_data in context.scene.material_analysis_results:
                    if material_data.has_uv_conflicts:
                        bpy.ops.meta_horizon.resolve_uv_conflicts(material_name=material_data.material_name)
            
            wizard.current_task = "Materials fixed"
            self.report({'INFO'}, "Material issues automatically resolved")
            
        except Exception as e:
            wizard.current_task = f"Material fix failed: {str(e)}"
            self.report({'ERROR'}, f"Material fix failed: {str(e)}")
            print(f"Wizard material fix error: {e}")
    
    def auto_apply_modifiers(self, context):
        """Automatically apply geometry-adding modifiers"""
        wizard = context.scene.horizon_wizard_state
        wizard.current_task = "Applying modifiers..."
        
        try:
            if hasattr(context.scene, 'mesh_analysis_results'):
                for mesh_data in context.scene.mesh_analysis_results:
                    if mesh_data.has_geometry_adding_modifiers:
                        bpy.ops.meta_horizon.apply_geometry_modifiers(object_name=mesh_data.object_name)
            
            wizard.current_task = "Modifiers applied"
            self.report({'INFO'}, "Geometry modifiers applied")
            
        except Exception as e:
            wizard.current_task = f"Modifier application failed: {str(e)}"
            self.report({'ERROR'}, f"Modifier application failed: {str(e)}")
            print(f"Wizard modifier error: {e}")
    
    def auto_unwrap_uvs(self, context):
        """Automatically unwrap UVs for objects that need it"""
        wizard = context.scene.horizon_wizard_state
        wizard.current_task = "Unwrapping UVs..."
        
        try:
            # Select objects that need UV unwrapping
            objects_to_unwrap = []
            if hasattr(context.scene, 'mesh_analysis_results'):
                for mesh_data in context.scene.mesh_analysis_results:
                    if mesh_data.uv_channel_count == 0:
                        obj = bpy.data.objects.get(mesh_data.object_name)
                        if obj:
                            objects_to_unwrap.append(obj)
            
            if objects_to_unwrap:
                # Clear selection
                bpy.ops.object.select_all(action='DESELECT')
                
                # Select objects that need unwrapping
                for obj in objects_to_unwrap:
                    obj.select_set(True)
                
                if objects_to_unwrap:
                    context.view_layer.objects.active = objects_to_unwrap[0]
                    bpy.ops.meta_horizon.smart_uv_project_selected()
            
            wizard.current_task = "UVs unwrapped"
            self.report({'INFO'}, f"UV unwrapping complete for {len(objects_to_unwrap)} objects")
            
        except Exception as e:
            wizard.current_task = f"UV unwrapping failed: {str(e)}"
            self.report({'ERROR'}, f"UV unwrapping failed: {str(e)}")
            print(f"Wizard UV unwrap error: {e}")
    
    def create_atlas(self, context):
        """Create UV atlas if requested"""
        wizard = context.scene.horizon_wizard_state
        wizard.current_task = "Creating UV atlas..."
        
        # Select mesh objects
        mesh_objects = [obj for obj in context.scene.objects if obj.type == 'MESH']
        if len(mesh_objects) > 1:
            bpy.ops.object.select_all(action='DESELECT')
            for obj in mesh_objects:
                obj.select_set(True)
            
            if mesh_objects:
                context.view_layer.objects.active = mesh_objects[0]
                bpy.ops.meta_horizon.create_uv_atlas()
        
        wizard.current_task = "Atlas created"
        self.report({'INFO'}, "UV atlas creation complete")
    
    def bake_textures(self, context):
        """Bake textures if requested"""
        wizard = context.scene.horizon_wizard_state
        wizard.current_task = "Baking textures..."
        
        bpy.ops.meta_horizon.bake_all_materials()
        
        wizard.current_task = "Textures baked"
        self.report({'INFO'}, "Texture baking complete")
    
    def perform_export(self, context):
        """Perform the final export"""
        wizard = context.scene.horizon_wizard_state
        wizard.current_task = "Exporting assets..."
        
        # Restore original selection for export
        if wizard.export_selected_only and wizard.original_selected_objects:
            # Clear current selection
            bpy.ops.object.select_all(action='DESELECT')
            
            # Restore original selection
            object_names = wizard.original_selected_objects.split(",")
            restored_objects = []
            for obj_name in object_names:
                obj = bpy.data.objects.get(obj_name.strip())
                if obj:
                    obj.select_set(True)
                    restored_objects.append(obj)
            
            # Restore active object
            if wizard.original_active_object:
                active_obj = bpy.data.objects.get(wizard.original_active_object)
                if active_obj:
                    context.view_layer.objects.active = active_obj
            
            wizard.current_task = f"Restored selection of {len(restored_objects)} objects for export..."
        
        export_settings = context.scene.horizon_export_settings
        
        # Ensure export directory exists
        if not export_settings.export_location:
            export_settings.export_location = "//exports/"
        
        export_path = bpy.path.abspath(export_settings.export_location)
        os.makedirs(export_path, exist_ok=True)
        
        # Generate filename
        blend_name = bpy.path.basename(bpy.data.filepath)
        if blend_name.endswith('.blend'):
            base_name = blend_name[:-6]
        else:
            base_name = "HorizonExport"
        
        # Determine if we should use selection based on wizard settings
        use_selection = wizard.export_selected_only
        
        if wizard.export_format == 'FBX':
            export_file = os.path.join(export_path, f"{base_name}.fbx")
            # Use simplified FBX export parameters for Blender 4.4 compatibility
            bpy.ops.export_scene.fbx(
                filepath=export_file,
                use_selection=use_selection
            )
        elif wizard.export_format == 'GLTF':
            export_file = os.path.join(export_path, f"{base_name}.gltf")
            bpy.ops.export_scene.gltf(
                filepath=export_file,
                use_selection=use_selection,
                export_apply=True
            )
        elif wizard.export_format == 'OBJ':
            export_file = os.path.join(export_path, f"{base_name}.obj")
            bpy.ops.export_scene.obj(
                filepath=export_file,
                use_selection=use_selection,
                use_materials=True
            )
        elif wizard.export_format == 'BLEND':
            export_file = os.path.join(export_path, f"{base_name}_prepared.blend")
            bpy.ops.wm.save_as_mainfile(filepath=export_file)
        
        wizard.current_task = f"Export complete: {export_file}"
        self.report({'INFO'}, f"Export complete: {export_file}")
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=600)
    
    def draw(self, context):
        layout = self.layout
        wizard = context.scene.horizon_wizard_state
        
        # Header
        header = layout.box()
        header.label(text="Meta Horizon Worlds Export Wizard", icon='EXPORT')
        
        # Progress bar
        progress_box = header.box()
        progress_row = progress_box.row()
        progress_row.prop(wizard, "progress_percentage", text="Progress", slider=True)
        if wizard.current_step >= wizard.total_steps:
            progress_row.label(text="Complete")
        else:
            progress_row.label(text=f"Step {wizard.current_step + 1} of {wizard.total_steps}")
        
        # Current task
        if wizard.current_task:
            progress_box.label(text=f"Current: {wizard.current_task}", icon='TIME')
        
        layout.separator()
        
        # Step-by-step wizard interface
        if wizard.current_step == 0:
            self.draw_step_analysis(layout, context)
        elif wizard.current_step == 1:
            self.draw_step_materials(layout, context)
        elif wizard.current_step == 2:
            self.draw_step_meshes(layout, context)
        elif wizard.current_step == 3:
            self.draw_step_uvs(layout, context)
        elif wizard.current_step == 4:
            self.draw_step_baking(layout, context)
        elif wizard.current_step == 5:
            self.draw_step_export(layout, context)
        elif wizard.current_step >= 6:
            self.draw_step_complete(layout, context)
        
        # Navigation buttons
        layout.separator()
        nav_box = layout.box()
        nav_row = nav_box.row()
        
        # Previous button
        if wizard.current_step > 0 and wizard.current_step < 6:
            prev_button = nav_row.operator("meta_horizon.wizard_previous", text="◀ Previous")
        
        # Next/Action button
        if wizard.current_step < 6:
            if wizard.current_step == 0:
                # Split into two rows for better layout
                first_row = nav_box.row()
                start_button = first_row.operator("meta_horizon.wizard_start_analysis", text="🔍 Start Analysis")
                second_row = nav_box.row()
                run_all_button = second_row.operator("meta_horizon.wizard_run_all", text="🚀 Run All Steps")
            else:
                next_button = nav_row.operator("meta_horizon.wizard_next", text="Next ▶")
        else:
            close_button = nav_row.operator("meta_horizon.wizard_close", text="✓ Close Wizard")
    
    def draw_step_analysis(self, layout, context):
        wizard = context.scene.horizon_wizard_state
        
        step_box = layout.box()
        header_row = step_box.row()
        header_row.label(text="Step 1: Scene Analysis", icon='ZOOM_ALL')
        
        if wizard.step_analysis_complete:
            # Summary stats
            results_box = step_box.box()
            results_box.label(text="📊 Analysis Results:", icon='INFO')
            
            stats_row = results_box.row()
            stats_col1 = stats_row.column()
            stats_col1.label(text=f"📦 Total Objects: {wizard.total_objects}")
            stats_col1.label(text=f"🔺 Mesh Objects: {wizard.mesh_objects}")
            
            stats_col2 = stats_row.column()
            stats_col2.label(text=f"🎨 Materials w/ Issues: {wizard.materials_with_issues}")
            stats_col2.label(text=f"⚙️ Objects w/ Modifiers: {wizard.objects_with_modifiers}")
            stats_col2.label(text=f"🗺️ Objects Needing UVs: {wizard.objects_needing_uvs}")
            
            # Status indicator
            if wizard.materials_with_issues > 0 or wizard.objects_with_modifiers > 0 or wizard.objects_needing_uvs > 0:
                warning_box = step_box.box()
                warning_box.alert = True
                warning_box.label(text="⚠ Issues found that need attention before export", icon='ERROR')
            else:
                success_box = step_box.box()
                success_box.label(text="✅ Scene is ready for Meta Horizon Worlds", icon='CHECKMARK')
    
    def draw_step_materials(self, layout, context):
        wizard = context.scene.horizon_wizard_state
        
        step_box = layout.box()
        header_row = step_box.row()
        header_row.label(text="Step 2: Material Preparation", icon='MATERIAL')
        
        if wizard.materials_with_issues == 0:
            success_box = step_box.box()
            success_box.label(text="✅ No material issues found!", icon='CHECKMARK')
        else:
            issues_box = step_box.box()
            issues_box.alert = True
            issues_box.label(text=f"⚠ Found {wizard.materials_with_issues} materials that need attention", icon='ERROR')
            
            # Auto-fix settings
            settings_box = step_box.box()
            settings_box.prop(wizard, "auto_fix_materials", text="🔧 Auto-fix material issues")
    
    def draw_step_meshes(self, layout, context):
        wizard = context.scene.horizon_wizard_state
        
        step_box = layout.box()
        header_row = step_box.row()
        header_row.label(text="Step 3: Mesh Preparation", icon='MESH_DATA')
        
        if wizard.objects_with_modifiers == 0:
            success_box = step_box.box()
            success_box.label(text="✅ No geometry modifiers found!", icon='CHECKMARK')
        else:
            issues_box = step_box.box()
            issues_box.alert = True
            issues_box.label(text=f"⚠ Found {wizard.objects_with_modifiers} objects with geometry modifiers", icon='MODIFIER')
            
            # Auto-apply settings
            settings_box = step_box.box()
            settings_box.prop(wizard, "auto_apply_modifiers", text="🔧 Auto-apply geometry modifiers")
    
    def draw_step_uvs(self, layout, context):
        wizard = context.scene.horizon_wizard_state
        
        step_box = layout.box()
        header_row = step_box.row()
        header_row.label(text="Step 4: UV Preparation", icon='UV')
        
        if wizard.objects_needing_uvs == 0:
            success_box = step_box.box()
            success_box.label(text="✅ All objects have UV coordinates!", icon='CHECKMARK')
        else:
            issues_box = step_box.box()
            issues_box.alert = True
            issues_box.label(text=f"⚠ Found {wizard.objects_needing_uvs} objects without UV coordinates", icon='ERROR')
            
            # Auto-unwrap settings
            settings_box = step_box.box()
            settings_box.prop(wizard, "auto_unwrap_uvs", text="🔧 Auto-unwrap UVs")
    
    def draw_step_baking(self, layout, context):
        wizard = context.scene.horizon_wizard_state
        
        step_box = layout.box()
        header_row = step_box.row()
        header_row.label(text="Step 5: Texture Baking (Optional)", icon='RENDER_RESULT')
        
        step_box.prop(wizard, "bake_textures", text="🔥 Bake Textures")
        
        if wizard.bake_textures:
            # Baking settings
            bake_settings = context.scene.horizon_bake_settings
            settings_box = step_box.box()
            settings_box.label(text="🎛️ Baking Settings:", icon='SETTINGS')
            
            settings_row = settings_box.row()
            settings_col1 = settings_row.column()
            settings_col1.prop(bake_settings, "bake_type", text="Bake Type")
            settings_col1.prop(bake_settings, "samples", text="Samples")
            
            settings_col2 = settings_row.column()
            settings_col2.prop(bake_settings, "image_width", text="Width")
            settings_col2.prop(bake_settings, "image_height", text="Height")
            
            # Output settings
            output_box = settings_box.box()
            output_box.label(text="💾 Output Settings:", icon='FILE')
            output_row = output_box.row()
            output_col1 = output_row.column()
            output_col1.prop(bake_settings, "file_format", text="Format")
            output_col1.prop(bake_settings, "color_depth", text="Bit Depth")
            
            output_col2 = output_row.column()
            output_col2.prop(bake_settings, "margin", text="Margin")
            output_col2.prop(bake_settings, "use_denoising", text="Denoising")
    
    def draw_step_export(self, layout, context):
        wizard = context.scene.horizon_wizard_state
        
        step_box = layout.box()
        header_row = step_box.row()
        header_row.label(text="Step 5: Final Export", icon='EXPORT')
        
        # Show what will be exported
        export_info_box = step_box.box()
        if wizard.export_selected_only and wizard.original_selected_objects:
            object_names = wizard.original_selected_objects.split(",")
            valid_objects = [name.strip() for name in object_names if bpy.data.objects.get(name.strip())]
            
            export_info_box.label(text=f"📦 Will Export: {len(valid_objects)} Originally Selected Objects", icon='INFO')
            
            # Show object names in a compact way
            if len(valid_objects) <= 5:
                for obj_name in valid_objects:
                    export_info_box.label(text=f"  • {obj_name}")
            else:
                for obj_name in valid_objects[:3]:
                    export_info_box.label(text=f"  • {obj_name}")
                export_info_box.label(text=f"  • ... and {len(valid_objects) - 3} more objects")
        else:
            all_mesh_objects = [obj for obj in context.scene.objects if obj.type == 'MESH']
            export_info_box.label(text=f"📦 Will Export: All Scene Objects ({len(all_mesh_objects)} mesh objects)", icon='INFO')
        
        # Export location
        export_settings = context.scene.horizon_export_settings
        location_box = step_box.box()
        location_box.label(text="📂 Export Location:", icon='FOLDER_REDIRECT')
        location_box.prop(export_settings, "export_location", text="")
    
    def draw_step_complete(self, layout, context):
        wizard = context.scene.horizon_wizard_state
        
        complete_box = layout.box()
        header_row = complete_box.row()
        header_row.label(text="🎉 Export Wizard Complete!", icon='CHECKMARK')
        
        # Export status
        if wizard.current_task:
            status_box = complete_box.box()
            status_box.label(text=wizard.current_task)


class META_HORIZON_OT_wizard_previous(Operator):
    """Go to previous step in the wizard"""
    bl_idname = "meta_horizon.wizard_previous"
    bl_label = "Previous Step"
    bl_description = "Go to the previous step in the export wizard"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        wizard = context.scene.horizon_wizard_state
        if wizard.current_step > 0:
            wizard.current_step -= 1
            wizard.progress_percentage = max(0, wizard.progress_percentage - 15)
        return {'FINISHED'}


class META_HORIZON_OT_wizard_run_all(Operator):
    """Run all wizard steps automatically"""
    bl_idname = "meta_horizon.wizard_run_all"
    bl_label = "Run All Steps"
    bl_description = "Automatically run all wizard steps with current settings"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        wizard = context.scene.horizon_wizard_state
        
        # Run all steps in sequence
        for step in range(7):
            wizard.current_step = step
            wizard.progress_percentage = int((step + 1) * (100 / 7))
            
            # Execute the main wizard operator for each step
            result = bpy.ops.meta_horizon.export_wizard()
            if 'CANCELLED' in result:
                self.report({'WARNING'}, f"Wizard stopped at step {step + 1}")
                break
        
        return {'FINISHED'}


class META_HORIZON_OT_wizard_reset(Operator):
    """Reset and start the wizard"""
    bl_idname = "meta_horizon.wizard_reset"
    bl_label = "Start Export Wizard"
    bl_description = "Reset wizard state and launch the export wizard"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        # Reset wizard state
        wizard = context.scene.horizon_wizard_state
        wizard.current_step = 0
        wizard.progress_percentage = 0
        wizard.current_task = "Starting export wizard..."
        
        # Reset step completion
        wizard.step_analysis_complete = False
        wizard.step_materials_complete = False
        wizard.step_meshes_complete = False
        wizard.step_uvs_complete = False
        wizard.step_baking_complete = False
        wizard.step_export_complete = False
        
        # Capture original selection for later export
        selected_objects = context.selected_objects
        if selected_objects:
            # Store names of selected objects
            wizard.original_selected_objects = ",".join([obj.name for obj in selected_objects])
            wizard.export_selected_only = True
            
            # Store active object
            if context.active_object:
                wizard.original_active_object = context.active_object.name
        else:
            # No selection, export all objects
            wizard.original_selected_objects = ""
            wizard.original_active_object = ""
            wizard.export_selected_only = False
        
        # Launch the wizard
        bpy.ops.meta_horizon.export_wizard('INVOKE_DEFAULT')
        
        return {'FINISHED'}


class META_HORIZON_OT_wizard_close(Operator):
    """Close the wizard"""
    bl_idname = "meta_horizon.wizard_close"
    bl_label = "Close Wizard"
    bl_description = "Close the export wizard"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        return {'FINISHED'}


class META_HORIZON_OT_wizard_start_analysis(Operator):
    """Start the analysis step in the wizard"""
    bl_idname = "meta_horizon.wizard_start_analysis"
    bl_label = "Start Analysis"
    bl_description = "Start the scene analysis step in the export wizard"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        wizard = context.scene.horizon_wizard_state
        
        # Capture original selection for later export if not already captured
        if not wizard.original_selected_objects and not wizard.export_selected_only:
            selected_objects = context.selected_objects
            if selected_objects:
                # Store names of selected objects
                wizard.original_selected_objects = ",".join([obj.name for obj in selected_objects])
                wizard.export_selected_only = True
                
                # Store active object
                if context.active_object:
                    wizard.original_active_object = context.active_object.name
            else:
                # No selection, export all objects
                wizard.original_selected_objects = ""
                wizard.original_active_object = ""
                wizard.export_selected_only = False
        
        # Reset analysis completion status
        wizard.step_analysis_complete = False
        wizard.current_task = "Starting scene analysis..."
        wizard.progress_percentage = 10
        
        try:
            # Perform scene analysis directly
            self.perform_scene_analysis(context)
            
            # Mark analysis as complete and advance to next step
            wizard.step_analysis_complete = True
            wizard.current_step = 1
            wizard.current_task = "Analysis complete!"
            wizard.progress_percentage = 20
            
            self.report({'INFO'}, "Scene analysis completed successfully!")
            
        except Exception as e:
            self.report({'ERROR'}, f"Analysis failed: {str(e)}")
            wizard.current_task = f"Analysis failed: {str(e)}"
            return {'CANCELLED'}
        
        return {'FINISHED'}
    
    def perform_scene_analysis(self, context):
        """Analyze the scene and collect statistics"""
        wizard = context.scene.horizon_wizard_state
        
        # Clear previous analysis - use correct property names
        if hasattr(context.scene, 'mesh_analysis_results'):
            context.scene.mesh_analysis_results.clear()
        if hasattr(context.scene, 'material_analysis_results'):  
            context.scene.material_analysis_results.clear()
        
        # Get selected objects or all objects
        objects_to_analyze = context.selected_objects if context.selected_objects else context.scene.objects
        
        mesh_objects = [obj for obj in objects_to_analyze if obj.type == 'MESH']
        
        wizard.total_objects = len(objects_to_analyze)
        wizard.mesh_objects = len(mesh_objects)
        wizard.current_task = "Analyzing scene..."
        
        try:
            # Analyze meshes
            bpy.ops.meta_horizon.analyze_meshes()
            
            # Analyze materials
            bpy.ops.meta_horizon.analyze_all_materials()
            
            # Count issues - use correct property names
            materials_with_issues = 0
            objects_with_modifiers = 0
            objects_needing_uvs = 0
            
            # Check if the properties exist
            if hasattr(context.scene, 'material_analysis_results'):
                for material_data in context.scene.material_analysis_results:
                    if material_data.has_naming_issues or material_data.is_empty_material or material_data.has_uv_conflicts:
                        materials_with_issues += 1
            
            if hasattr(context.scene, 'mesh_analysis_results'):
                for mesh_data in context.scene.mesh_analysis_results:
                    if mesh_data.has_geometry_adding_modifiers:
                        objects_with_modifiers += 1
                    if mesh_data.uv_channel_count == 0:
                        objects_needing_uvs += 1
            
            wizard.materials_with_issues = materials_with_issues
            wizard.objects_with_modifiers = objects_with_modifiers
            wizard.objects_needing_uvs = objects_needing_uvs
            wizard.materials_for_baking = len([m for m in bpy.data.materials if m.users > 0])
            
            wizard.current_task = "Analysis complete"
            
            self.report({'INFO'}, f"Analysis complete: {wizard.mesh_objects} mesh objects, {materials_with_issues} materials with issues")
        
        except Exception as e:
            wizard.current_task = f"Analysis failed: {str(e)}"
            self.report({'ERROR'}, f"Analysis failed: {str(e)}")
            print(f"Wizard analysis error: {e}")


class META_HORIZON_OT_wizard_next(Operator):
    """Advance to the next step in the wizard"""
    bl_idname = "meta_horizon.wizard_next"
    bl_label = "Next Step"
    bl_description = "Advance to the next step in the export wizard"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        wizard = context.scene.horizon_wizard_state
        
        # Determine which step we're on and what to do
        current_step = wizard.current_step
        
        try:
            if current_step == 1:  # Materials step
                if wizard.auto_fix_materials:
                    self.auto_fix_materials(context)
                wizard.step_materials_complete = True
                
            elif current_step == 2:  # Meshes step
                if wizard.auto_apply_modifiers:
                    self.auto_apply_modifiers(context)
                wizard.step_meshes_complete = True
                
            elif current_step == 3:  # UVs step
                if wizard.auto_unwrap_uvs:
                    self.auto_unwrap_uvs(context)
                wizard.step_uvs_complete = True
                
            elif current_step == 4:  # Baking step
                if wizard.bake_textures:
                    self.bake_textures(context)
                wizard.step_baking_complete = True
                
            elif current_step == 5:  # Export step
                self.perform_export(context)
                wizard.step_export_complete = True
            
            # Advance to next step
            wizard.current_step = min(wizard.current_step + 1, wizard.total_steps)
            wizard.progress_percentage = min(100, int((wizard.current_step / wizard.total_steps) * 100))
            
            self.report({'INFO'}, f"Step {current_step + 1} completed successfully!")
            
        except Exception as e:
            self.report({'ERROR'}, f"Step failed: {str(e)}")
            wizard.current_task = f"Step failed: {str(e)}"
            return {'CANCELLED'}
        
        return {'FINISHED'}
    
    def auto_fix_materials(self, context):
        """Automatically fix material issues"""
        wizard = context.scene.horizon_wizard_state
        wizard.current_task = "Fixing materials..."
        
        try:
            # Apply recommended names
            bpy.ops.meta_horizon.apply_all_recommended_names()
            
            # Setup empty materials
            if hasattr(context.scene, 'material_analysis_results'):
                for material_data in context.scene.material_analysis_results:
                    if material_data.is_empty_material and material_data.can_be_setup:
                        bpy.ops.meta_horizon.setup_empty_material(material_name=material_data.material_name)
            
            # Resolve UV conflicts
            if hasattr(context.scene, 'material_analysis_results'):
                for material_data in context.scene.material_analysis_results:
                    if material_data.has_uv_conflicts:
                        bpy.ops.meta_horizon.resolve_uv_conflicts(material_name=material_data.material_name)
            
            wizard.current_task = "Materials fixed"
            
        except Exception as e:
            wizard.current_task = f"Material fix failed: {str(e)}"
            raise e
    
    def auto_apply_modifiers(self, context):
        """Automatically apply geometry-adding modifiers"""
        wizard = context.scene.horizon_wizard_state
        wizard.current_task = "Applying modifiers..."
        
        try:
            if hasattr(context.scene, 'mesh_analysis_results'):
                for mesh_data in context.scene.mesh_analysis_results:
                    if mesh_data.has_geometry_adding_modifiers:
                        bpy.ops.meta_horizon.apply_geometry_modifiers(object_name=mesh_data.object_name)
            
            wizard.current_task = "Modifiers applied"
            
        except Exception as e:
            wizard.current_task = f"Modifier application failed: {str(e)}"
            raise e
    
    def auto_unwrap_uvs(self, context):
        """Automatically unwrap UVs for objects that need it"""
        wizard = context.scene.horizon_wizard_state
        wizard.current_task = "Unwrapping UVs..."
        
        try:
            # Select objects that need UV unwrapping
            objects_to_unwrap = []
            if hasattr(context.scene, 'mesh_analysis_results'):
                for mesh_data in context.scene.mesh_analysis_results:
                    if mesh_data.uv_channel_count == 0:
                        obj = bpy.data.objects.get(mesh_data.object_name)
                        if obj:
                            objects_to_unwrap.append(obj)
            
            if objects_to_unwrap:
                # Clear selection
                bpy.ops.object.select_all(action='DESELECT')
                
                # Select objects that need unwrapping
                for obj in objects_to_unwrap:
                    obj.select_set(True)
                
                if objects_to_unwrap:
                    context.view_layer.objects.active = objects_to_unwrap[0]
                    bpy.ops.meta_horizon.smart_uv_project_selected()
            
            wizard.current_task = "UVs unwrapped"
            
        except Exception as e:
            wizard.current_task = f"UV unwrapping failed: {str(e)}"
            raise e
    
    def bake_textures(self, context):
        """Bake textures if requested"""
        wizard = context.scene.horizon_wizard_state
        wizard.current_task = "Baking textures..."
        
        bpy.ops.meta_horizon.bake_all_materials()
        
        wizard.current_task = "Textures baked"
    
    def perform_export(self, context):
        """Perform the final export"""
        wizard = context.scene.horizon_wizard_state
        wizard.current_task = "Exporting assets..."
        
        # Restore original selection for export
        if wizard.export_selected_only and wizard.original_selected_objects:
            # Clear current selection
            bpy.ops.object.select_all(action='DESELECT')
            
            # Restore original selection
            object_names = wizard.original_selected_objects.split(",")
            restored_objects = []
            for obj_name in object_names:
                obj = bpy.data.objects.get(obj_name.strip())
                if obj:
                    obj.select_set(True)
                    restored_objects.append(obj)
            
            # Restore active object
            if wizard.original_active_object:
                active_obj = bpy.data.objects.get(wizard.original_active_object)
                if active_obj:
                    context.view_layer.objects.active = active_obj
            
            wizard.current_task = f"Restored selection of {len(restored_objects)} objects for export..."
        
        export_settings = context.scene.horizon_export_settings
        
        # Ensure export directory exists
        if not export_settings.export_location:
            export_settings.export_location = "//exports/"
        
        export_path = bpy.path.abspath(export_settings.export_location)
        os.makedirs(export_path, exist_ok=True)
        
        # Generate filename
        blend_name = bpy.path.basename(bpy.data.filepath)
        if blend_name.endswith('.blend'):
            base_name = blend_name[:-6]
        else:
            base_name = "HorizonExport"
        
        # Determine if we should use selection based on wizard settings
        use_selection = wizard.export_selected_only
        
        if wizard.export_format == 'FBX':
            export_file = os.path.join(export_path, f"{base_name}.fbx")
            # Use simplified FBX export parameters for Blender 4.4 compatibility
            bpy.ops.export_scene.fbx(
                filepath=export_file,
                use_selection=use_selection
            )
        elif wizard.export_format == 'GLTF':
            export_file = os.path.join(export_path, f"{base_name}.gltf")
            bpy.ops.export_scene.gltf(
                filepath=export_file,
                use_selection=use_selection,
                export_apply=True
            )
        elif wizard.export_format == 'OBJ':
            export_file = os.path.join(export_path, f"{base_name}.obj")
            bpy.ops.export_scene.obj(
                filepath=export_file,
                use_selection=use_selection,
                use_materials=True
            )
        elif wizard.export_format == 'BLEND':
            export_file = os.path.join(export_path, f"{base_name}_prepared.blend")
            bpy.ops.wm.save_as_mainfile(filepath=export_file)
        
        wizard.current_task = f"Export complete: {export_file}"


class META_HORIZON_OT_export_with_details(Operator):
    """Export scene to FBX with detailed information popup"""
    bl_idname = "meta_horizon.export_with_details"
    bl_label = "Export to FBX"
    bl_description = "Export scene to FBX with detailed information about the export"
    bl_options = {'REGISTER', 'UNDO'}
    
    # Export filename property
    filename: StringProperty(
        name="File Name",
        description="Name for the exported FBX file (without extension)",
        default="horizon_export"
    )
    
    # Store export information for display
    export_objects = []
    total_polygons = 0
    total_vertices = 0
    export_path = ""
    
    def execute(self, context):
        # Check if file is saved first
        if not bpy.data.is_saved:
            self.report({'ERROR'}, "Please save your Blender file before exporting. Export uses relative paths that depend on your .blend file location.")
            return {'CANCELLED'}
        
        # Get export settings
        export_settings = context.scene.horizon_export_settings
        export_path = bpy.path.abspath(export_settings.export_location)
        
        # Create export directory if it doesn't exist
        if not os.path.exists(export_path):
            try:
                os.makedirs(export_path)
            except Exception as e:
                self.report({'ERROR'}, f"Failed to create export directory: {e}")
                return {'CANCELLED'}
        
        # Determine which objects to export
        selected_count = len([obj for obj in context.selected_objects if obj.type == 'MESH'])
        
        # Use user-provided filename
        base_filename = self.filename.strip()
        if not base_filename:
            base_filename = "horizon_export"
        
        # Ensure filename ends with .fbx extension
        if not base_filename.lower().endswith('.fbx'):
            filename = f"{base_filename}.fbx"
        else:
            filename = base_filename
        
        if selected_count > 0:
            # Export only selected objects
            export_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        else:
            # Export all mesh objects
            export_objects = [obj for obj in context.scene.objects if obj.type == 'MESH']
        
        full_path = os.path.join(export_path, filename)
        
        # Save current selection
        original_selection = context.selected_objects[:]
        original_active = context.active_object
        
        try:
            # Select objects to export
            bpy.ops.object.select_all(action='DESELECT')
            for obj in export_objects:
                obj.select_set(True)
            
            if export_objects:
                context.view_layer.objects.active = export_objects[0]
            
            # Export to FBX
            bpy.ops.export_scene.fbx(
                filepath=full_path,
                use_selection=True,
                global_scale=1.0,
                apply_unit_scale=True,
                apply_scale_options='FBX_SCALE_NONE',
                bake_space_transform=False,
                object_types={'MESH'},
                use_mesh_modifiers=True,
                use_mesh_modifiers_render=True,
                mesh_smooth_type='OFF',
                use_subsurf=False,
                use_mesh_edges=False,
                use_tspace=False,
                use_custom_props=False,
                add_leaf_bones=True,
                primary_bone_axis='Y',
                secondary_bone_axis='X',
                use_armature_deform_only=False,
                armature_nodetype='NULL',
                bake_anim=True,
                bake_anim_use_all_bones=True,
                bake_anim_use_nla_strips=True,
                bake_anim_use_all_actions=True,
                bake_anim_force_startend_keying=True,
                bake_anim_step=1.0,
                bake_anim_simplify_factor=1.0,
                path_mode='AUTO',
                embed_textures=False,
                batch_mode='OFF',
                use_batch_own_dir=True,
                use_metadata=True
            )
            
            # Restore original selection
            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selection:
                obj.select_set(True)
            context.view_layer.objects.active = original_active
            
            self.report({'INFO'}, f"Successfully exported {len(export_objects)} objects to {filename}")
            
        except Exception as e:
            # Restore original selection even if export fails
            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selection:
                obj.select_set(True)
            context.view_layer.objects.active = original_active
            
            self.report({'ERROR'}, f"Export failed: {e}")
            return {'CANCELLED'}
        
        return {'FINISHED'}
    
    def invoke(self, context, event):
        # Check if file is saved first
        if not bpy.data.is_saved:
            # Show save file dialog
            bpy.ops.wm.save_as_mainfile('INVOKE_DEFAULT')
            self.report({'INFO'}, "Please save your file to continue with export. After saving, try the export again.")
            return {'CANCELLED'}
        
        # Calculate export information
        export_settings = context.scene.horizon_export_settings
        self.export_path = bpy.path.abspath(export_settings.export_location)
        
        # Determine which objects will be exported
        selected_count = len([obj for obj in context.selected_objects if obj.type == 'MESH'])
        
        if selected_count > 0:
            # Export selected objects
            self.export_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
            # Set default filename based on first selected object
            if self.export_objects:
                # Use the first selected mesh object's name
                first_object_name = self.export_objects[0].name
                self.filename = f"{first_object_name}"
            else:
                self.filename = "selected_objects_export"
        else:
            # Export all mesh objects
            self.export_objects = [obj for obj in context.scene.objects if obj.type == 'MESH']
            # Set default filename based on scene name
            scene_name = context.scene.name if context.scene.name != "Scene" else "scene"
            self.filename = f"{scene_name}_export"
        
        # Calculate total polygons and vertices
        self.total_polygons = 0
        self.total_vertices = 0
        
        for obj in self.export_objects:
            if obj.data:
                # Get final mesh data considering modifiers
                depsgraph = context.evaluated_depsgraph_get()
                eval_obj = obj.evaluated_get(depsgraph)
                
                if eval_obj.data:
                    mesh = eval_obj.data
                    self.total_polygons += len(mesh.polygons)
                    self.total_vertices += len(mesh.vertices)
        
        # Show the popup
        return context.window_manager.invoke_props_dialog(self, width=500)
    
    def draw(self, context):
        layout = self.layout
        export_settings = context.scene.horizon_export_settings
        
        # Title
        layout.label(text="Export Details", icon='EXPORT')
        layout.separator()
        
        # Filename input
        filename_box = layout.box()
        filename_box.label(text="📁 Export Settings", icon='FILE_3D')
        filename_box.prop(self, "filename", text="File Name")
        filename_box.label(text="Note: .fbx extension will be added automatically", icon='INFO')
        
        layout.separator()
        
        # Export information box
        info_box = layout.box()
        info_box.label(text="📦 Export Information", icon='INFO')
        
        # Export path
        path_row = info_box.row()
        path_row.label(text="Export Location:")
        path_col = info_box.column()
        path_col.label(text=self.export_path)
        
        # Object count
        count_row = info_box.row()
        count_row.label(text="Objects to Export:")
        count_row.label(text=str(len(self.export_objects)))
        
        # Geometry statistics
        stats_row = info_box.row()
        stats_row.label(text="Total Polygons:")
        stats_row.label(text=f"{self.total_polygons:,}")
        
        verts_row = info_box.row()
        verts_row.label(text="Total Vertices:")
        verts_row.label(text=f"{self.total_vertices:,}")
        
        layout.separator()
        
        # Performance recommendations
        if self.total_polygons > 50000:
            perf_box = layout.box()
            perf_box.label(text="⚠️ Performance Warning", icon='ERROR')
            perf_box.label(text=f"High polygon count ({self.total_polygons:,}) may impact performance")
            perf_box.label(text="Consider using decimation or LOD models for Meta Horizon Worlds")
        elif self.total_polygons > 20000:
            perf_box = layout.box()
            perf_box.label(text="💡 Performance Tip", icon='INFO')
            perf_box.label(text=f"Moderate polygon count ({self.total_polygons:,})")
            perf_box.label(text="Consider optimization for better performance")
        
        layout.separator()
        
        # Object list (limited display)
        if len(self.export_objects) > 0:
            objects_box = layout.box()
            objects_box.label(text="Objects to Export:", icon='OUTLINER_OB_MESH')
            
            # Limit display to prevent UI overflow
            display_limit = 8
            for i, obj in enumerate(self.export_objects[:display_limit]):
                row = objects_box.row()
                
                # Get object stats
                obj_polys = 0
                obj_verts = 0
                if obj.data:
                    depsgraph = context.evaluated_depsgraph_get()
                    eval_obj = obj.evaluated_get(depsgraph)
                    if eval_obj.data:
                        mesh = eval_obj.data
                        obj_polys = len(mesh.polygons)
                        obj_verts = len(mesh.vertices)
                
                row.label(text=f"  • {obj.name} ({obj_polys:,} polys, {obj_verts:,} verts)")
            
            if len(self.export_objects) > display_limit:
                objects_box.label(text=f"  ... and {len(self.export_objects) - display_limit} more objects")
        
        layout.separator()
        
        # Export format info
        format_box = layout.box()
        format_box.label(text="📋 Export Format: FBX", icon='FILE_3D')
        format_box.label(text="✅ Compatible with Meta Horizon Worlds")
        format_box.label(text="✅ Preserves materials and UV coordinates")
        format_box.label(text="✅ Includes mesh modifiers")


def register():
    # Register property groups
    bpy.utils.register_class(HorizonExportWizardState)
    bpy.utils.register_class(HorizonBakeSettings)
    bpy.utils.register_class(HorizonExportSettings)
    bpy.utils.register_class(HorizonAtlasSettings)

    bpy.utils.register_class(MeshAnalysisData)
    bpy.utils.register_class(MaterialAnalysisData)
    
    # Register operators
    bpy.utils.register_class(META_HORIZON_OT_export_wizard)
    bpy.utils.register_class(META_HORIZON_OT_wizard_reset)
    bpy.utils.register_class(META_HORIZON_OT_wizard_previous)
    bpy.utils.register_class(META_HORIZON_OT_wizard_run_all)
    bpy.utils.register_class(META_HORIZON_OT_wizard_close)
    bpy.utils.register_class(META_HORIZON_OT_analyze_materials)
    bpy.utils.register_class(META_HORIZON_OT_analyze_all_materials)
    bpy.utils.register_class(META_HORIZON_OT_analyze_meshes)
    bpy.utils.register_class(META_HORIZON_OT_apply_geometry_modifiers)
    bpy.utils.register_class(META_HORIZON_OT_apply_all_modifiers)
    bpy.utils.register_class(META_HORIZON_OT_decimate_meshes)
    bpy.utils.register_class(META_HORIZON_OT_smart_uv_project_selected)
    bpy.utils.register_class(META_HORIZON_OT_smart_uv_project)
    bpy.utils.register_class(META_HORIZON_OT_select_objects_by_material)
    bpy.utils.register_class(META_HORIZON_OT_apply_recommended_name)
    bpy.utils.register_class(META_HORIZON_OT_toggle_materials_list)
    bpy.utils.register_class(META_HORIZON_OT_toggle_meshes_list)
    bpy.utils.register_class(META_HORIZON_OT_materials_page_nav)
    bpy.utils.register_class(META_HORIZON_OT_meshes_page_nav)
    bpy.utils.register_class(META_HORIZON_OT_apply_all_recommended_names)
    bpy.utils.register_class(META_HORIZON_OT_resolve_uv_conflicts)
    bpy.utils.register_class(META_HORIZON_OT_simplify_material)
    bpy.utils.register_class(META_HORIZON_OT_create_material_for_slot)
    bpy.utils.register_class(META_HORIZON_OT_setup_empty_material)
    bpy.utils.register_class(META_HORIZON_OT_convert_glass_to_principled)
    bpy.utils.register_class(META_HORIZON_OT_create_uv_atlas)
    bpy.utils.register_class(META_HORIZON_OT_create_unique_materials)
    bpy.utils.register_class(META_HORIZON_OT_bake_material)
    bpy.utils.register_class(META_HORIZON_OT_bake_all_materials)
    bpy.utils.register_class(META_HORIZON_OT_wizard_start_analysis)
    bpy.utils.register_class(META_HORIZON_OT_wizard_next)
    bpy.utils.register_class(META_HORIZON_OT_export_with_details)
    bpy.utils.register_class(META_HORIZON_OT_decimate_single_mesh)
    bpy.utils.register_class(META_HORIZON_OT_resolve_all_uv_conflicts)
    bpy.utils.register_class(META_HORIZON_OT_choose_material_suffix)
    
    # Register new panels
    bpy.utils.register_class(META_HORIZON_PT_quick_start)
    bpy.utils.register_class(META_HORIZON_PT_analysis)
    bpy.utils.register_class(META_HORIZON_PT_preparation)
    bpy.utils.register_class(META_HORIZON_PT_export_options)
    
    # Add properties to scene
    bpy.types.Scene.horizon_wizard_state = bpy.props.PointerProperty(type=HorizonExportWizardState)
    bpy.types.Scene.horizon_bake_settings = bpy.props.PointerProperty(type=HorizonBakeSettings)
    bpy.types.Scene.horizon_export_settings = bpy.props.PointerProperty(type=HorizonExportSettings)
    bpy.types.Scene.horizon_atlas_settings = bpy.props.PointerProperty(type=HorizonAtlasSettings)

    bpy.types.Scene.material_analysis_results = bpy.props.CollectionProperty(type=MaterialAnalysisData)
    bpy.types.Scene.mesh_analysis_results = bpy.props.CollectionProperty(type=MeshAnalysisData)


def unregister():
    # Remove properties from scene
    del bpy.types.Scene.horizon_wizard_state
    del bpy.types.Scene.horizon_bake_settings
    del bpy.types.Scene.horizon_export_settings
    del bpy.types.Scene.horizon_atlas_settings

    del bpy.types.Scene.material_analysis_results
    del bpy.types.Scene.mesh_analysis_results
    
    # Unregister panels
    bpy.utils.unregister_class(META_HORIZON_PT_export_options)
    bpy.utils.unregister_class(META_HORIZON_PT_preparation)
    bpy.utils.unregister_class(META_HORIZON_PT_analysis)
    bpy.utils.unregister_class(META_HORIZON_PT_quick_start)
    
    # Unregister operators

    bpy.utils.unregister_class(META_HORIZON_OT_bake_all_materials)
    bpy.utils.unregister_class(META_HORIZON_OT_bake_material)
    bpy.utils.unregister_class(META_HORIZON_OT_create_unique_materials)
    bpy.utils.unregister_class(META_HORIZON_OT_create_uv_atlas)
    bpy.utils.unregister_class(META_HORIZON_OT_convert_glass_to_principled)
    bpy.utils.unregister_class(META_HORIZON_OT_setup_empty_material)
    bpy.utils.unregister_class(META_HORIZON_OT_create_material_for_slot)
    bpy.utils.unregister_class(META_HORIZON_OT_smart_uv_project)
    bpy.utils.unregister_class(META_HORIZON_OT_smart_uv_project_selected)
    bpy.utils.unregister_class(META_HORIZON_OT_decimate_meshes)
    bpy.utils.unregister_class(META_HORIZON_OT_apply_geometry_modifiers)
    bpy.utils.unregister_class(META_HORIZON_OT_apply_all_modifiers)
    bpy.utils.unregister_class(META_HORIZON_OT_analyze_meshes)
    bpy.utils.unregister_class(META_HORIZON_OT_analyze_all_materials)
    bpy.utils.unregister_class(META_HORIZON_OT_analyze_materials)
    bpy.utils.unregister_class(META_HORIZON_OT_select_objects_by_material)
    bpy.utils.unregister_class(META_HORIZON_OT_apply_recommended_name)
    bpy.utils.unregister_class(META_HORIZON_OT_toggle_materials_list)
    bpy.utils.unregister_class(META_HORIZON_OT_toggle_meshes_list)
    bpy.utils.unregister_class(META_HORIZON_OT_materials_page_nav)
    bpy.utils.unregister_class(META_HORIZON_OT_meshes_page_nav)
    bpy.utils.unregister_class(META_HORIZON_OT_apply_all_recommended_names)
    bpy.utils.unregister_class(META_HORIZON_OT_resolve_uv_conflicts)
    bpy.utils.unregister_class(META_HORIZON_OT_simplify_material)
    bpy.utils.unregister_class(META_HORIZON_OT_export_wizard)
    bpy.utils.unregister_class(META_HORIZON_OT_wizard_reset)
    bpy.utils.unregister_class(META_HORIZON_OT_wizard_previous)
    bpy.utils.unregister_class(META_HORIZON_OT_wizard_run_all)
    bpy.utils.unregister_class(META_HORIZON_OT_wizard_close)
    bpy.utils.unregister_class(META_HORIZON_OT_wizard_start_analysis)
    bpy.utils.unregister_class(META_HORIZON_OT_wizard_next)
    bpy.utils.unregister_class(META_HORIZON_OT_export_with_details)
    bpy.utils.unregister_class(META_HORIZON_OT_decimate_single_mesh)
    bpy.utils.unregister_class(META_HORIZON_OT_resolve_all_uv_conflicts)
    bpy.utils.unregister_class(META_HORIZON_OT_choose_material_suffix)
    
    # Unregister property groups
    bpy.utils.unregister_class(MaterialAnalysisData)
    bpy.utils.unregister_class(MeshAnalysisData)

    bpy.utils.unregister_class(HorizonAtlasSettings)
    bpy.utils.unregister_class(HorizonExportSettings)
    bpy.utils.unregister_class(HorizonBakeSettings)
    bpy.utils.unregister_class(HorizonExportWizardState)


if __name__ == "__main__":
    register()
