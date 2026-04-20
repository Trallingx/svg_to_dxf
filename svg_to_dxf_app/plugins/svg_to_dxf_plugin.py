from __future__ import annotations

from typing import Any, Dict

from svg_to_dxf_app.plugins.base import BaseConversionPlugin, ProgressCallback


class SvgToDxfPlugin(BaseConversionPlugin):
    @property
    def plugin_id(self) -> str:
        return "svg-to-dxf"

    def run(
        self,
        input_path: str,
        output_path: str,
        settings: Dict[str, Any],
        progress_callback: ProgressCallback,
    ) -> None:
        # Lazy imports keep startup fast when this mode is not used.
        from svg_to_dxf_app.conversion.base import ConversionOptions
        from svg_to_dxf_app.conversion.svg_to_dxf import SvgToDxfConverter

        options = ConversionOptions(
            scale=float(settings.get("scale", 1.0)),
            target_width_mm=float(settings.get("target_width_mm", 0.0)),
            target_height_mm=float(settings.get("target_height_mm", 0.0)),
            lock_uniform_scale=bool(settings.get("lock_uniform_scale", True)),
            origin_reference=str(settings.get("origin_reference", "center-of-mass")),
            curve_approximation_steps=int(settings.get("curve_approximation_steps", 16)),
            layer_name=str(settings.get("layer_name", "SVG_IMPORT")),
            invert_y_axis=bool(settings.get("invert_y_axis", False)),
            stitch_tolerance=float(settings.get("stitch_tolerance", 0.0)),
            stitch_mode=str(settings.get("stitch_mode", "all-points")),
            extra_params={
                "x_offset": float(settings.get("x_offset", 0.0)),
                "y_offset": float(settings.get("y_offset", 0.0)),
            },
        )

        converter = SvgToDxfConverter()
        converter.convert(input_path, output_path, options, progress_callback)
