# Plugin Requirements

This app supports mode plugins loaded from `svg_to_dxf_app/plugins/manifest.json`.

## 1) Manifest Entry

Each plugin must be registered in `svg_to_dxf_app/plugins/manifest.json`:

- `id`: unique mode id, e.g. `svg-to-dxf`
- `name`: user-facing mode name
- `description`: short mode description
- `module`: python import path to plugin module
- `class`: plugin class name in module
- `input_extensions`: list of accepted input extensions
- `output_extension`: output file extension including dot
- `enabled`: `true` or `false`

## 2) Python Contract

Plugin class must implement `BaseConversionPlugin` from `svg_to_dxf_app/plugins/base.py`.

Required API:

```python
class BaseConversionPlugin(ABC):
    @property
    def plugin_id(self) -> str: ...

    def run(
        self,
        input_path: str,
        output_path: str,
        settings: dict[str, Any],
        progress_callback: Callable[[int], None],
    ) -> None: ...
```

## 3) Runtime Rules

- Emit progress values in range `0..100` using `progress_callback`.
- Raise clear exceptions for user-facing errors.
- Keep plugin self-contained: any extra dependencies should be installed separately.

## 4) Settings Payload

UI passes plugin settings as a dictionary. Plugins should read only keys they need and provide defaults for missing keys.

Current shared keys from UI:

- `scale`
- `target_width_mm`
- `target_height_mm`
- `lock_uniform_scale`
- `origin_reference`
- `curve_approximation_steps`
- `layer_name`
- `invert_y_axis`
- `stitch_tolerance`
- `stitch_mode`
- `x_offset`
- `y_offset`

## 5) Optional Dependencies

Use `requirements-plugins.txt` for optional plugin packages, so core app install remains lightweight.
