# SVG Converter (PyQt5, Plugin-Ready)

Desktop app with conversion modes. Current production mode is `SVG -> DXF`, and the app is structured to support additional modes (for example `SVG -> PNG`) without rewriting the codebase.

## Features

- Select mode from plugin-backed mode list
- Select input file from the GUI
- Select save location and output filename (`Save as...` popup)
- 0-100% progress indicator during conversion
- Live feedback panel showing input/output and progress updates
- Conversion history panel and exportable conversion report
- Drag-and-drop input support
- Batch folder conversion
- Preset save/load for conversion settings
- Dedicated SVG and DXF viewer windows for quick geometry checks
- DXF viewer zoom controls (`+`, `-`, `Fit`, mouse wheel)
- Success and error popup messages
- Extensible conversion options architecture for future parameters
- Actionable conversion failure messages with suggested fixes
- Lazy plugin loading for faster startup

## Current conversion options

- `Scale`
- `Target width (mm)` and `Target height (mm)` for exact output sizing
- `Lock aspect ratio` to keep width/height linked
- `Origin reference` for center-of-mass or bounding-box placement
- `Curve detail` (samples used to approximate curves)
- `Layer name`
- `Invert Y-axis`
- `X offset`
- `Y offset`
- `Stitch tolerance` (snaps nearby nodes but keeps each loop as a separate polyline)
- `Stitch mode` (`all-points` or `endpoints-only`)

## Setup

### Option A: Run from source

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Optional plugin dependencies:

```powershell
pip install -r requirements-plugins.txt
```

### Option B: Install as a package

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install .
svg-converter
```

If `svg-converter` is not found on Windows, run:

```powershell
python -m svg_to_dxf_app
```

## Usage

1. Select a mode (`SVG -> DXF` currently enabled).
2. Choose or drag-drop an input SVG file.
3. Choose output path.
4. Configure sizing/origin/stitch parameters.
5. Click `Convert`.
6. Use `Preview SVG` / `Preview DXF` and live geometry preview for verification.

## Development

Install development dependencies:

```powershell
pip install -r requirements-dev.txt
```

## Run tests

```powershell
python -m pytest -q
```

## Packaging an executable (optional)

For distribution outside Python environments, you can build a standalone executable with PyInstaller:

```powershell
pip install pyinstaller
pyinstaller --name svg-converter --onefile --windowed app.py
```

Binary will be created under `dist/`.

## Architecture (for scalability)

- `svg_to_dxf_app/plugins/manifest.json`
  - Mode registry (currently `svg-to-dxf`, plus disabled placeholder `svg-to-png`)
- `svg_to_dxf_app/plugins/base.py`
  - `BaseConversionPlugin` and plugin descriptor model
- `svg_to_dxf_app/plugins/manager.py`
  - Plugin discovery, availability checks, and lazy instantiation
- `svg_to_dxf_app/plugins/svg_to_dxf_plugin.py`
  - Built-in plugin implementation for SVG->DXF
- `svg_to_dxf_app/conversion/base.py`
  - `ConversionOptions` dataclass used by DXF conversion plugin
  - `BaseConverter` abstract interface
- `svg_to_dxf_app/conversion/svg_to_dxf.py`
  - SVG->DXF converter implementation
- `svg_to_dxf_app/workers.py`
  - Background worker for plugin/converter execution and progress signals
- `svg_to_dxf_app/gui/main_window.py`
  - GUI wiring, mode selection, plugin execution, and feedback

Plugin authoring contract: `PLUGIN_REQUIREMENTS.md`.
