from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtSvg import QSvgWidget
from PyQt5.QtWidgets import (
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class SvgViewerWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SVG Viewer")
        self.resize(900, 700)

        self._svg_widget = QSvgWidget()
        self._svg_widget.renderer().setAspectRatioMode(Qt.KeepAspectRatio)

        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.addWidget(self._svg_widget)
        self.setCentralWidget(container)

    def load_file(self, file_path: str) -> None:
        path = Path(file_path)
        if not path.exists():
            raise ValueError(f"SVG file does not exist: {file_path}")
        if path.suffix.lower() != ".svg":
            raise ValueError("Viewer expects an SVG file.")

        self._svg_widget.load(str(path))
        self.setWindowTitle(f"SVG Viewer - {path.name}")


class DxfViewerWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DXF Viewer")
        self.resize(900, 700)

        self._scene = QGraphicsScene(self)
        self._view = QGraphicsView(self._scene)
        self._view.setRenderHint(QPainter.Antialiasing, True)
        self._view.setDragMode(QGraphicsView.ScrollHandDrag)
        self._view.wheelEvent = self._on_wheel_zoom  # type: ignore[assignment]

        self._empty_label = QLabel("No drawable entities found in DXF file.")
        self._empty_label.setAlignment(Qt.AlignCenter)

        controls = QHBoxLayout()
        zoom_in = QPushButton("+")
        zoom_out = QPushButton("-")
        fit_btn = QPushButton("Fit")
        zoom_in.clicked.connect(lambda: self._zoom(1.2))
        zoom_out.clicked.connect(lambda: self._zoom(1 / 1.2))
        fit_btn.clicked.connect(self._fit_scene)
        controls.addWidget(zoom_in)
        controls.addWidget(zoom_out)
        controls.addWidget(fit_btn)
        controls.addStretch(1)

        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.addLayout(controls)
        layout.addWidget(self._view)
        layout.addWidget(self._empty_label)
        self.setCentralWidget(container)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._fit_scene()

    def load_file(self, file_path: str) -> None:
        import ezdxf

        path = Path(file_path)
        if not path.exists():
            raise ValueError(f"DXF file does not exist: {file_path}")
        if path.suffix.lower() != ".dxf":
            raise ValueError("Viewer expects a DXF file.")

        self._scene.clear()

        doc = ezdxf.readfile(str(path))
        modelspace = doc.modelspace()

        pen = QPen(QColor(30, 30, 30))
        pen.setCosmetic(True)

        for entity in modelspace:
            entity_type = entity.dxftype()
            if entity_type == "LINE":
                start = entity.dxf.start
                end = entity.dxf.end
                self._scene.addLine(start.x, -start.y, end.x, -end.y, pen)
            elif entity_type == "LWPOLYLINE":
                points = [(p[0], p[1]) for p in entity.get_points()]
                self._add_polyline(points, bool(entity.closed), pen)
            elif entity_type == "POLYLINE":
                points = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
                self._add_polyline(points, bool(entity.is_closed), pen)
            elif entity_type == "CIRCLE":
                center = entity.dxf.center
                radius = entity.dxf.radius
                self._scene.addEllipse(
                    center.x - radius,
                    -(center.y + radius),
                    radius * 2,
                    radius * 2,
                    pen,
                )
            elif entity_type == "ARC":
                arc_points = []
                for point in entity.flattening(0.5):
                    arc_points.append((point.x, point.y))
                self._add_polyline(arc_points, False, pen)

        has_content = bool(self._scene.items())
        self._empty_label.setVisible(not has_content)
        self.setWindowTitle(f"DXF Viewer - {path.name}")
        self._fit_scene()

    def _add_polyline(self, points: list[tuple[float, float]], closed: bool, pen: QPen) -> None:
        if len(points) < 2:
            return

        for i in range(1, len(points)):
            x0, y0 = points[i - 1]
            x1, y1 = points[i]
            self._scene.addLine(x0, -y0, x1, -y1, pen)

        if closed:
            x0, y0 = points[-1]
            x1, y1 = points[0]
            self._scene.addLine(x0, -y0, x1, -y1, pen)

    def _fit_scene(self) -> None:
        rect = self._scene.itemsBoundingRect()
        if rect.isValid():
            self._view.fitInView(rect, Qt.KeepAspectRatio)

    def _zoom(self, factor: float) -> None:
        self._view.scale(factor, factor)

    def _on_wheel_zoom(self, event) -> None:
        delta = event.angleDelta().y()
        if delta > 0:
            self._zoom(1.15)
        elif delta < 0:
            self._zoom(1 / 1.15)
        event.accept()
