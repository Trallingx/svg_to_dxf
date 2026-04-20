from __future__ import annotations

from pathlib import Path

import ezdxf
import pytest

from svg_to_dxf_app.conversion.base import ConversionError, ConversionOptions
from svg_to_dxf_app.conversion.svg_to_dxf import SvgToDxfConverter


def _write_svg(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _dxf_bbox(path: Path) -> tuple[float, float, float, float]:
    doc = ezdxf.readfile(str(path))
    points: list[tuple[float, float]] = []
    for entity in doc.modelspace().query("LWPOLYLINE"):
        points.extend((float(x), float(y)) for x, y, *_ in entity.get_points())
    xs = [x for x, _y in points]
    ys = [y for _x, y in points]
    return min(xs), min(ys), max(xs), max(ys)


def test_convert_simple_path_creates_dxf_and_reports_progress(tmp_path: Path) -> None:
    input_svg = tmp_path / "shape.svg"
    output_dxf = tmp_path / "shape.dxf"

    _write_svg(
        input_svg,
        """
        <svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 10 10\">
            <path d=\"M 1 1 L 9 1 L 9 9 Z\" />
        </svg>
        """.strip(),
    )

    converter = SvgToDxfConverter()
    options = ConversionOptions()
    progress_values: list[int] = []

    converter.convert(str(input_svg), str(output_dxf), options, progress_values.append)

    assert output_dxf.exists()
    assert progress_values[0] == 5
    assert progress_values[-1] == 100

    doc = ezdxf.readfile(str(output_dxf))
    entities = list(doc.modelspace())
    assert len(entities) >= 1


def test_convert_empty_svg_raises_conversion_error(tmp_path: Path) -> None:
    input_svg = tmp_path / "empty.svg"
    output_dxf = tmp_path / "empty.dxf"

    _write_svg(
        input_svg,
        """
        <svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 10 10\"></svg>
        """.strip(),
    )

    converter = SvgToDxfConverter()

    with pytest.raises(ConversionError, match="No SVG path geometry found"):
        converter.convert(
            str(input_svg),
            str(output_dxf),
            ConversionOptions(),
            lambda _v: None,
        )


def test_convert_text_only_svg_reports_shape_hint(tmp_path: Path) -> None:
    input_svg = tmp_path / "text_only.svg"
    output_dxf = tmp_path / "text_only.dxf"

    _write_svg(
        input_svg,
        """
        <svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 10 10\">
            <text x=\"1\" y=\"6\">A</text>
        </svg>
        """.strip(),
    )

    converter = SvgToDxfConverter()

    with pytest.raises(ConversionError, match="non-path elements: text"):
        converter.convert(
            str(input_svg),
            str(output_dxf),
            ConversionOptions(),
            lambda _v: None,
        )


def test_transform_point_applies_scale_invert_and_offsets() -> None:
    converter = SvgToDxfConverter()
    options = ConversionOptions(
        scale=2.0,
        invert_y_axis=True,
        extra_params={"x_offset": 3.0, "y_offset": -1.0},
    )

    x, y = converter._transform_point(4.0, 5.0, options)

    assert x == 11.0
    assert y == -11.0


def test_convert_discontinuous_path_data_without_assertion(tmp_path: Path) -> None:
    input_svg = tmp_path / "discontinuous.svg"
    output_dxf = tmp_path / "discontinuous.dxf"

    _write_svg(
        input_svg,
        """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
            <path d="M 1 1 L 5 1 L 5 5 Z M 10 10 L 14 10 L 14 14 Z" />
        </svg>
        """.strip(),
    )

    converter = SvgToDxfConverter()
    progress_values: list[int] = []
    converter.convert(
        str(input_svg),
        str(output_dxf),
        ConversionOptions(),
        progress_values.append,
    )

    assert output_dxf.exists()
    assert progress_values[-1] == 100


def test_stitch_tolerance_shares_nodes_without_merging_loops(tmp_path: Path) -> None:
    input_svg = tmp_path / "two_squares_near.svg"
    output_dxf = tmp_path / "two_squares_near.dxf"

    _write_svg(
        input_svg,
        """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 30 30">
            <path d="M 0 0 L 10 0 L 10 10 L 0 10 Z" />
            <path d="M 10.05 10.05 L 20.05 10.05 L 20.05 20.05 L 10.05 20.05 Z" />
        </svg>
        """.strip(),
    )

    converter = SvgToDxfConverter()
    options = ConversionOptions(stitch_tolerance=0.1, origin_reference="bbox-bottom-left")
    converter.convert(str(input_svg), str(output_dxf), options, lambda _v: None)

    doc = ezdxf.readfile(str(output_dxf))
    polylines = list(doc.modelspace().query("LWPOLYLINE"))
    assert len(polylines) == 2
    assert polylines[0].closed is True
    assert polylines[1].closed is True

    def xy_set(entity: ezdxf.entities.LWPolyline) -> set[tuple[float, float]]:
        return {(round(x, 4), round(y, 4)) for x, y, *_ in entity.get_points()}

    shared_nodes = xy_set(polylines[0]).intersection(xy_set(polylines[1]))
    assert (10.0, 10.0) in shared_nodes


def test_stitch_tolerance_does_not_force_open_path_closed(tmp_path: Path) -> None:
    input_svg = tmp_path / "open_near_close.svg"
    output_dxf = tmp_path / "open_near_close.dxf"

    _write_svg(
        input_svg,
        """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">
            <path d="M 0 0 L 5 0 L 0.04 0" />
        </svg>
        """.strip(),
    )

    converter = SvgToDxfConverter()
    options = ConversionOptions(stitch_tolerance=0.1)
    converter.convert(str(input_svg), str(output_dxf), options, lambda _v: None)

    doc = ezdxf.readfile(str(output_dxf))
    polyline = list(doc.modelspace().query("LWPOLYLINE"))[0]
    assert polyline.closed is False


def test_endpoints_only_stitch_mode_keeps_midpoint_unsnapped(tmp_path: Path) -> None:
    input_svg = tmp_path / "endpoint_mode.svg"
    output_dxf = tmp_path / "endpoint_mode.dxf"

    _write_svg(
        input_svg,
        """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
            <path d="M 0 0 L 10 10 L 20 0" />
            <path d="M 10.05 10.05 L 14 14" />
        </svg>
        """.strip(),
    )

    converter = SvgToDxfConverter()
    options = ConversionOptions(
        stitch_tolerance=0.1,
        stitch_mode="endpoints-only",
        origin_reference="bbox-bottom-left",
    )
    converter.convert(str(input_svg), str(output_dxf), options, lambda _v: None)

    doc = ezdxf.readfile(str(output_dxf))
    polylines = list(doc.modelspace().query("LWPOLYLINE"))
    assert len(polylines) == 2

    points = [
        (round(x, 2), round(y, 2))
        for x, y, *_ in polylines[0].get_points()
    ]
    assert (10.0, 10.0) in points


def test_target_width_scales_exactly_and_uniform_lock_preserves_aspect(tmp_path: Path) -> None:
    input_svg = tmp_path / "exact_width.svg"
    output_dxf = tmp_path / "exact_width.dxf"

    _write_svg(
        input_svg,
        """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 5">
            <path d="M 0 0 L 10 0 L 10 5 L 0 5 Z" />
        </svg>
        """.strip(),
    )

    converter = SvgToDxfConverter()
    options = ConversionOptions(
        target_width_mm=70.0,
        lock_uniform_scale=True,
        origin_reference="bbox-bottom-left",
    )
    converter.convert(str(input_svg), str(output_dxf), options, lambda _v: None)

    min_x, min_y, max_x, max_y = _dxf_bbox(output_dxf)
    assert round(max_x - min_x, 3) == 70.0
    assert round(max_y - min_y, 3) == 35.0
    assert round(min_x, 3) == 0.0
    assert round(min_y, 3) == 0.0


def test_independent_width_height_scaling(tmp_path: Path) -> None:
    input_svg = tmp_path / "independent.svg"
    output_dxf = tmp_path / "independent.dxf"

    _write_svg(
        input_svg,
        """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 5">
            <path d="M 0 0 L 10 0 L 10 5 L 0 5 Z" />
        </svg>
        """.strip(),
    )

    converter = SvgToDxfConverter()
    options = ConversionOptions(
        target_width_mm=70.0,
        target_height_mm=20.0,
        lock_uniform_scale=False,
        origin_reference="bbox-bottom-left",
    )
    converter.convert(str(input_svg), str(output_dxf), options, lambda _v: None)

    min_x, min_y, max_x, max_y = _dxf_bbox(output_dxf)
    assert round(max_x - min_x, 3) == 70.0
    assert round(max_y - min_y, 3) == 20.0


def test_center_of_mass_origin_places_shape_around_zero(tmp_path: Path) -> None:
    input_svg = tmp_path / "centroid.svg"
    output_dxf = tmp_path / "centroid.dxf"

    _write_svg(
        input_svg,
        """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
            <path d="M 5 5 L 15 5 L 15 15 L 5 15 Z" />
        </svg>
        """.strip(),
    )

    converter = SvgToDxfConverter()
    options = ConversionOptions(origin_reference="center-of-mass")
    converter.convert(str(input_svg), str(output_dxf), options, lambda _v: None)

    min_x, min_y, max_x, max_y = _dxf_bbox(output_dxf)
    assert round(min_x, 3) == -5.0
    assert round(min_y, 3) == -5.0
    assert round(max_x, 3) == 5.0
    assert round(max_y, 3) == 5.0
