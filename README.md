# Blender to Meta Horizon Exporter

A comprehensive Blender add-on designed specifically for Meta Horizon Worlds asset creation. This tool provides material analysis, export tools, and a guided workflow wizard to help your assets meet Meta Horizon Worlds requirements.

## Features

### 🎨 Material Analysis & Management
- **Shader Type Detection**: Automatically identifies and analyzes material shader types
- **Naming Convention Validation**: Removes invalid characters (`- . , / * $ &`) and ensures compliance
- **Intelligent Suffix Recommendations**: Suggests appropriate suffixes based on material properties
- **Complete Material Type Support**:
  - Base PBR, Metal PBR, Transparent, Unlit, Blend, Masked
  - Vertex Color materials (`_VXC`, `_VXM`)
  - UI Optimized materials (`_UIO`)

### 🔧 Material Tools
- **Glass BSDF Conversion**: Automatically converts Glass BSDF to Principled BSDF for Meta Horizon compatibility
- **Empty Material Handling**: Setup assistance for materials without proper shader configurations
- **Batch Material Operations**: Apply recommended names and fixes to multiple materials at once

### 📐 Mesh Analysis & Optimization
- **Geometry Analysis**: Polygon/vertex counts, modifier detection, UV channel information
- **Modifier Management**: Apply geometry-adding modifiers with guided workflow
- **Smart UV Project**: Automated UV unwrapping workflow for optimal asset preparation
- **Mesh Decimation**: Reduce polygon counts while maintaining visual quality

### 🧙‍♂️ Export Wizard
- **Guided Workflow**: Step-by-step process for preparing and exporting assets
- **FBX Export**: Configured specifically for Meta Horizon Worlds requirements
- **Batch Processing**: Handle multiple objects and materials efficiently
- **Quality Assurance**: Built-in checks to ensure assets meet platform standards

## Installation

1. Download the `__init__.py` file
2. Open Blender and go to `Edit > Preferences > Add-ons`
3. Click `Install...` and select the `__init__.py` file
4. Enable the "Blender to Meta Horizon Exporter" add-on
5. The add-on panel will appear in the 3D Viewport's N-Panel under "Horizon Worlds"

## Usage

### Quick Start
1. Open the **N-Panel** in the 3D Viewport (`N` key)
2. Navigate to the **"Horizon Worlds"** tab

### Workflow Sections

#### 1. Analysis
- Review material and mesh analysis
- Identify potential issues before export
- Get recommendations for optimization

#### 2. Preparation  
- Apply recommended material names
- Convert incompatible materials
- Resolve UV conflicts
- Apply geometry modifiers

#### 3. Export Options
- Configure FBX export settings
- Select objects for export
- Choose export location
- Execute final export

## Requirements

- **Blender Version**: 4.4.0 or higher
- **Graphics Card**: NVIDIA RTX 3070/4060 Ti or AMD RX 6700 XT or higher recommended (8GB+ VRAM)
- **Platform**: Compatible with Meta Horizon Worlds asset requirements

## Supported Material Types

The add-on recognizes and properly handles all Meta Horizon Worlds material types:

- **Base PBR**: Standard physically-based rendering materials
- **Metal PBR**: Metallic materials with proper workflow
- **Transparent**: Materials with alpha transparency
- **Unlit**: Non-lit materials for UI and special effects
- **Blend**: Alpha blended materials
- **Masked**: Alpha masked/cutout materials
- **Vertex Color (_VXC, _VXM)**: Materials using vertex color data
- **UI Optimized (_UIO)**: Performance-optimized materials for UI elements


## Troubleshooting

- **Materials not recognized**: Ensure materials use Principled BSDF or supported shader types
- **Export issues**: Check that all objects have proper UV coordinates
- **Performance**: Use decimation tools for high-poly models
- **Naming conflicts**: Run the naming validation tools before export

## Author

**SimLabs101** - Version 1.0.0

## License

This add-on is designed specifically for Meta Horizon Worlds asset creation and follows their platform requirements and guidelines.

---

*For more information about Meta Horizon Worlds asset requirements, please refer to the [official Meta Horizon Worlds documentation](https://developers.meta.com/horizon-worlds/learn/documentation/custom-model-import/creating-custom-models-for-horizon-worlds/materials-guidance-and-reference-for-custom-models).*
