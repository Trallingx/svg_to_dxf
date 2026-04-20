from __future__ import annotations

from dataclasses import dataclass
from math import floor
from pathlib import Path
from typing import Dict, Iterable, List, Tuple
from xml.etree import ElementTree as ET

import ezdxf
from svgpathtools import Arc, CubicBezier, Line, Path as SvgPath, QuadraticBezier, svg2paths2

from svg_to_dxf_app.conversion.base import (
    BaseConverter,
    ConversionError,
    ConversionOptions,
    ProgressCallback,
)

Point = Tuple[float, float]


@dataclass(frozen=True)
class SvgGeometryInfo:
    min_x: float
    min_y: float
    max_x: float
    max_y: float
    centroid_x: float
    centroid_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height if self.height else 0.0

    @property
    def center(self) -> Point:
        return (self.min_x + self.width / 2.0, self.min_y + self.height / 2.0)


def inspect_svg_geometry(input_path: str, curve_approximation_steps: int = 16) -> SvgGeometryInfo:
    paths, _path_attributes, _svg_attributes = svg2paths2(input_path)
    converter = SvgToDxfConverter()
    entities = converter._collect_entities(paths, curve_approximation_steps)
    return converter._build_geometry_info(entities)


class SvgToDxfConverter(BaseConverter):
    """Converter implementation for SVG path geometry into DXF polylines."""

    def convert(
        self,
        input_path: str,
        output_path: str,
        options: ConversionOptions,
        progress_callback: ProgressCallback,
    ) -> None:
        input_file = Path(input_path)
        if not input_file.exists():
            raise ConversionError(f"Input file does not exist: {input_path}")
        if input_file.suffix.lower() != ".svg":
            raise ConversionError("Input file must have .svg extension.")

        try:
            paths, _path_attributes, _svg_attributes = svg2paths2(input_path)
            if not paths:
                hint = self._build_no_path_hint(input_file)
                raise ConversionError(
                    "No SVG path geometry found. " + hint
                )

            progress_callback(5)

            doc = ezdxf.new("R2010")
            msp = doc.modelspace()

            entities = self._collect_entities(paths, options.curve_approximation_steps)
            if not entities:
                raise ConversionError("SVG contains empty paths; nothing to convert.")

            geometry = self._build_geometry_info(entities)
            origin_x, origin_y = self._resolve_origin(geometry, options.origin_reference)
            scale_x, scale_y = self._resolve_scale(geometry, options)
            stitcher = _NodeStitcher(options.stitch_tolerance)

            total_points = sum(len(points) for points, _closed in entities)
            segment_counter = 0

            for points_raw, is_closed in entities:
                points = [
                    self._transform_point_scaled(
                        x,
                        y,
                        origin_x,
                        origin_y,
                        scale_x,
                        scale_y,
                        options,
                    )
                    for x, y in points_raw
                ]
                points = stitcher.snap_points(points, options.stitch_mode, is_closed)
                if len(points) >= 2:
                    msp.add_lwpolyline(
                        points,
                        dxfattribs={"layer": options.layer_name},
                        close=is_closed,
                    )

                segment_counter += len(points_raw)
                progress = 10 + int((segment_counter / total_points) * 85)
                progress_callback(min(progress, 95))

            doc.saveas(output_path)
            progress_callback(100)
        except ConversionError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalize for UI feedback
            raise ConversionError(self._build_failure_message(exc)) from exc

    def _build_failure_message(self, exc: Exception) -> str:
        detail = str(exc).strip() or exc.__class__.__name__
        return (
            "Conversion failed.\n"
            f"Details: {detail}\n\n"
            "Try:\n"
            "- Ensure the SVG contains vector paths\n"
            "- Convert text and special effects to paths in your design tool\n"
            "- Lower curve detail if file is very complex"
        )

    def _build_no_path_hint(self, input_file: Path) -> str:
        try:
            root = ET.parse(str(input_file)).getroot()
        except ET.ParseError:
            return "Ensure the SVG is valid XML and contains path elements."

        tag_names = [element.tag.split("}")[-1].lower() for element in root.iter()]
        shape_tags = {"rect", "circle", "ellipse", "line", "polyline", "polygon", "text"}
        found_shapes = sorted(tag for tag in shape_tags if tag in tag_names)

        if found_shapes:
            shape_list = ", ".join(found_shapes)
            return f"Found non-path elements: {shape_list}. Convert them to paths first."

        return "Ensure your file contains <path ...> elements."

    def _collect_entities(
        self,
        paths: List[SvgPath],
        samples: int,
    ) -> List[Tuple[List[Point], bool]]:
        entities: List[Tuple[List[Point], bool]] = []
        for path in paths:
            for subpath in self._iter_continuous_subpaths(path):
                points = self._path_to_raw_points(subpath, samples)
                if points:
                    entities.append((points, self._is_closed_subpath(subpath)))
        return entities

    def _build_geometry_info(self, entities: List[Tuple[List[Point], bool]]) -> SvgGeometryInfo:
        all_points = [point for points, _closed in entities for point in points]
        if not all_points:
            raise ConversionError("SVG contains no drawable points.")

        min_x = min(x for x, _y in all_points)
        max_x = max(x for x, _y in all_points)
        min_y = min(y for _x, y in all_points)
        max_y = max(y for _x, y in all_points)
        centroid_x, centroid_y = self._estimate_centroid(entities, min_x, min_y, max_x, max_y)
        return SvgGeometryInfo(min_x, min_y, max_x, max_y, centroid_x, centroid_y)

    def _estimate_centroid(
        self,
        entities: List[Tuple[List[Point], bool]],
        min_x: float,
        min_y: float,
        max_x: float,
        max_y: float,
    ) -> Point:
        weighted_area = 0.0
        weighted_cx = 0.0
        weighted_cy = 0.0

        for points, is_closed in entities:
            if not is_closed or len(points) < 3:
                continue
            area, cx, cy = self._polygon_centroid(points)
            if area == 0.0:
                continue
            weighted_area += area
            weighted_cx += cx * area
            weighted_cy += cy * area

        if weighted_area != 0.0:
            return weighted_cx / weighted_area, weighted_cy / weighted_area

        return (min_x + (max_x - min_x) / 2.0, min_y + (max_y - min_y) / 2.0)

    def _polygon_centroid(self, points: List[Point]) -> Tuple[float, float, float]:
        if len(points) < 3:
            return 0.0, 0.0, 0.0

        area_sum = 0.0
        cx_sum = 0.0
        cy_sum = 0.0
        for index, (x0, y0) in enumerate(points):
            x1, y1 = points[(index + 1) % len(points)]
            cross = x0 * y1 - x1 * y0
            area_sum += cross
            cx_sum += (x0 + x1) * cross
            cy_sum += (y0 + y1) * cross

        area = area_sum / 2.0
        if area == 0.0:
            return 0.0, 0.0, 0.0

        centroid_x = cx_sum / (6.0 * area)
        centroid_y = cy_sum / (6.0 * area)
        return area, centroid_x, centroid_y

    def _resolve_origin(self, geometry: SvgGeometryInfo, origin_reference: str) -> Point:
        reference = origin_reference.strip().lower()
        if reference == "center-of-mass":
            return geometry.centroid_x, geometry.centroid_y

        mapping = {
            "bbox-top-left": (geometry.min_x, geometry.max_y),
            "bbox-top-center": (geometry.min_x + geometry.width / 2.0, geometry.max_y),
            "bbox-top-right": (geometry.max_x, geometry.max_y),
            "bbox-middle-left": (geometry.min_x, geometry.min_y + geometry.height / 2.0),
            "bbox-center": geometry.center,
            "bbox-middle-right": (geometry.max_x, geometry.min_y + geometry.height / 2.0),
            "bbox-bottom-left": (geometry.min_x, geometry.min_y),
            "bbox-bottom-center": (geometry.min_x + geometry.width / 2.0, geometry.min_y),
            "bbox-bottom-right": (geometry.max_x, geometry.min_y),
        }
        return mapping.get(reference, geometry.center)

    def _resolve_scale(self, geometry: SvgGeometryInfo, options: ConversionOptions) -> Tuple[float, float]:
        manual_scale = float(options.scale)
        target_width = float(options.target_width_mm)
        target_height = float(options.target_height_mm)

        scale_x = manual_scale
        scale_y = manual_scale

        has_width = target_width > 0.0 and geometry.width > 0.0
        has_height = target_height > 0.0 and geometry.height > 0.0

        if has_width or has_height:
            if options.lock_uniform_scale:
                if has_width and has_height:
                    width_scale = target_width / geometry.width
                    height_scale = target_height / geometry.height
                    locked_scale = min(width_scale, height_scale)
                elif has_width:
                    locked_scale = target_width / geometry.width
                else:
                    locked_scale = target_height / geometry.height
                scale_x = scale_y = locked_scale
            else:
                scale_x = target_width / geometry.width if has_width else 1.0
                scale_y = target_height / geometry.height if has_height else 1.0

        return scale_x * manual_scale, scale_y * manual_scale

    def _path_to_raw_points(self, path: SvgPath, samples: int) -> List[Point]:
        points: List[Point] = []
        sample_count = max(samples, 2)

        for segment in path:
            segment_points = self._segment_to_points(segment, sample_count)
            for x, y in segment_points:
                if not points or points[-1] != (x, y):
                    points.append((x, y))

        return points

    def _transform_point_scaled(
        self,
        x: float,
        y: float,
        origin_x: float,
        origin_y: float,
        scale_x: float,
        scale_y: float,
        options: ConversionOptions,
    ) -> Point:
        tx = (x - origin_x) * scale_x
        ty = (y - origin_y) * scale_y

        if options.invert_y_axis:
            ty = -ty

        x_offset = float(options.extra_params.get("x_offset", 0.0))
        y_offset = float(options.extra_params.get("y_offset", 0.0))

        return tx + x_offset, ty + y_offset

    def _path_to_points(self, path: SvgPath, options: ConversionOptions) -> List[Point]:
        points: List[Point] = []
        samples = max(options.curve_approximation_steps, 2)

        for segment in path:
            segment_points = self._segment_to_points(segment, samples)
            for x, y in segment_points:
                tx, ty = self._transform_point(x, y, options)
                if not points or points[-1] != (tx, ty):
                    points.append((tx, ty))

        return points

    def _iter_continuous_subpaths(self, path: SvgPath) -> Iterable[SvgPath]:
        if path.iscontinuous():
            return [path]
        subpaths = path.continuous_subpaths()
        return subpaths or [path]

    def _is_closed_subpath(self, path: SvgPath) -> bool:
        # Avoid svgpathtools assertion by only calling isclosed() on continuous paths.
        if path.iscontinuous():
            return bool(path.isclosed())
        return False

    def _segment_to_points(self, segment: object, samples: int) -> List[Point]:
        if isinstance(segment, Line):
            return [
                (segment.start.real, segment.start.imag),
                (segment.end.real, segment.end.imag),
            ]

        if isinstance(segment, (Arc, CubicBezier, QuadraticBezier)):
            result: List[Point] = []
            for i in range(samples + 1):
                t = i / samples
                p = segment.point(t)
                result.append((p.real, p.imag))
            return result

        raise TypeError(f"Unsupported SVG segment type: {type(segment).__name__}")

    def _transform_point(self, x: float, y: float, options: ConversionOptions) -> Point:
        sx = x * options.scale
        sy = y * options.scale

        if options.invert_y_axis:
            sy = -sy

        x_offset = float(options.extra_params.get("x_offset", 0.0))
        y_offset = float(options.extra_params.get("y_offset", 0.0))

        return sx + x_offset, sy + y_offset


class _NodeStitcher:
    """Snaps nearby points to a shared node using the provided tolerance."""

    def __init__(self, tolerance: float) -> None:
        self._tolerance = max(float(tolerance), 0.0)
        self._nodes: List[Point] = []
        self._grid: Dict[Tuple[int, int], List[int]] = {}

    def snap_points(self, points: List[Point], stitch_mode: str, is_closed: bool) -> List[Point]:
        if self._tolerance <= 0.0:
            return points
        normalized_mode = stitch_mode.strip().lower()

        if normalized_mode == "endpoints-only":
            if len(points) < 2:
                return points
            result = points[:]
            result[0] = self._snap_point(result[0])
            result[-1] = self._snap_point(result[-1])
            if is_closed:
                result[-1] = result[0]
            return result

        return [self._snap_point(point) for point in points]

    def _snap_point(self, point: Point) -> Point:
        key = self._cell(point)
        best_index: int | None = None
        best_distance_sq = self._tolerance * self._tolerance

        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                cell = (key[0] + dx, key[1] + dy)
                for index in self._grid.get(cell, []):
                    node = self._nodes[index]
                    distance_sq = (point[0] - node[0]) ** 2 + (point[1] - node[1]) ** 2
                    if distance_sq <= best_distance_sq:
                        best_distance_sq = distance_sq
                        best_index = index

        if best_index is not None:
            return self._nodes[best_index]

        node_index = len(self._nodes)
        self._nodes.append(point)
        self._grid.setdefault(key, []).append(node_index)
        return point

    def _cell(self, point: Point) -> Tuple[int, int]:
        if self._tolerance <= 0.0:
            return (0, 0)
        return (
            floor(point[0] / self._tolerance),
            floor(point[1] / self._tolerance),
        )
