from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import QSignalBlocker, QThread, Qt
from PyQt5.QtGui import QPainter, QPen
from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSplitter,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from svg_to_dxf_app.gui.viewers import DxfViewerWindow, SvgViewerWindow
from svg_to_dxf_app.plugins.base import PluginDescriptor
from svg_to_dxf_app.plugins.manager import PluginManager
from svg_to_dxf_app.workers import ConversionWorker


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SVG to DXF Converter")
        self.resize(980, 720)
        self.setAcceptDrops(True)

        self._thread: QThread | None = None
        self._worker: ConversionWorker | None = None
        self._svg_viewer_window: SvgViewerWindow | None = None
        self._dxf_viewer_window: DxfViewerWindow | None = None
        self._plugin_manager = PluginManager()
        self._plugin_descriptors = self._plugin_manager.list_plugins()
        self._history: list[str] = []
        self._last_report: dict[str, object] = {}
        self._source_aspect_ratio: float | None = None

        self.mode_combo = QComboBox()
        self.mode_description_label = QLabel()
        self.input_path_edit = QLineEdit()
        self.output_path_edit = QLineEdit()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        self.status_label = QLabel("Select an SVG file and start conversion.")
        self.feedback_box = QTextEdit()
        self.feedback_box.setReadOnly(True)
        self.feedback_box.setPlaceholderText("Conversion feedback will appear here.")

        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(0.001, 10000.0)
        self.scale_spin.setValue(1.0)
        self.scale_spin.setSingleStep(0.1)

        self.target_width_spin = QDoubleSpinBox()
        self.target_width_spin.setRange(0.0, 100000.0)
        self.target_width_spin.setDecimals(3)
        self.target_width_spin.setSingleStep(1.0)

        self.target_height_spin = QDoubleSpinBox()
        self.target_height_spin.setRange(0.0, 100000.0)
        self.target_height_spin.setDecimals(3)
        self.target_height_spin.setSingleStep(1.0)

        self.lock_uniform_checkbox = QCheckBox("Lock aspect ratio")
        self.lock_uniform_checkbox.setChecked(True)

        self.origin_reference_combo = QComboBox()
        self._populate_origin_reference_combo()

        self.steps_spin = QSpinBox()
        self.steps_spin.setRange(2, 200)
        self.steps_spin.setValue(16)

        self.layer_edit = QLineEdit("SVG_IMPORT")
        self.invert_y_checkbox = QCheckBox("Invert Y-axis (SVG down -> DXF up)")

        self.x_offset_spin = QDoubleSpinBox()
        self.x_offset_spin.setRange(-100000.0, 100000.0)
        self.x_offset_spin.setValue(0.0)
        self.x_offset_spin.setSingleStep(1.0)

        self.y_offset_spin = QDoubleSpinBox()
        self.y_offset_spin.setRange(-100000.0, 100000.0)
        self.y_offset_spin.setValue(0.0)
        self.y_offset_spin.setSingleStep(1.0)

        self.stitch_tolerance_spin = QDoubleSpinBox()
        self.stitch_tolerance_spin.setRange(0.0, 1000.0)
        self.stitch_tolerance_spin.setDecimals(4)
        self.stitch_tolerance_spin.setValue(0.0)
        self.stitch_tolerance_spin.setSingleStep(0.01)

        self.stitch_mode_combo = QComboBox()
        self.stitch_mode_combo.addItem("All points", "all-points")
        self.stitch_mode_combo.addItem("Endpoints only", "endpoints-only")

        self.convert_button = QPushButton("Convert")
        self.batch_convert_button = QPushButton("Batch Convert Folder")
        self.reload_plugins_button = QPushButton("Reload Plugins")
        self.save_preset_button = QPushButton("Save Preset")
        self.load_preset_button = QPushButton("Load Preset")
        self.export_report_button = QPushButton("Export Report")
        self.preview_svg_button = QPushButton("Preview SVG")
        self.preview_dxf_button = QPushButton("Preview DXF")

        self.history_box = QTextEdit()
        self.history_box.setReadOnly(True)
        self.history_box.setPlaceholderText("Conversion history will appear here.")

        self.preview_scene = QGraphicsScene(self)
        self.preview_view = QGraphicsView(self.preview_scene)
        self.preview_view.setMinimumHeight(260)
        self.preview_view.setRenderHint(QPainter.Antialiasing, True)
        self.preview_view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.preview_summary_label = QLabel("Preview will appear after an SVG is selected.")

        self._build_ui()
        self._populate_mode_combo()
        self._connect_scale_sync()

    def _build_ui(self) -> None:
        central = QWidget(self)
        root_layout = QVBoxLayout(central)

        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Mode:"))
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addWidget(self.reload_plugins_button)
        self.reload_plugins_button.clicked.connect(self._reload_plugins)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("SVG file:"))
        input_layout.addWidget(self.input_path_edit)
        browse_input = QPushButton("Select file")
        browse_input.clicked.connect(self._select_input_file)
        input_layout.addWidget(browse_input)
        self.preview_svg_button.clicked.connect(self._open_svg_viewer)
        input_layout.addWidget(self.preview_svg_button)

        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("DXF output:"))
        output_layout.addWidget(self.output_path_edit)
        browse_output = QPushButton("Save as...")
        browse_output.clicked.connect(self._select_output_file)
        output_layout.addWidget(browse_output)
        self.preview_dxf_button.clicked.connect(self._open_dxf_viewer)
        output_layout.addWidget(self.preview_dxf_button)

        options_box = QGroupBox("Conversion Parameters (Scalable)")
        options_form = QFormLayout(options_box)
        options_form.addRow("Target width (mm)", self.target_width_spin)
        options_form.addRow("Target height (mm)", self.target_height_spin)
        options_form.addRow("", self.lock_uniform_checkbox)
        options_form.addRow("Origin reference", self.origin_reference_combo)
        options_form.addRow("Scale multiplier", self.scale_spin)
        options_form.addRow("Curve detail", self.steps_spin)
        options_form.addRow("Layer name", self.layer_edit)
        options_form.addRow("", self.invert_y_checkbox)
        options_form.addRow("X offset", self.x_offset_spin)
        options_form.addRow("Y offset", self.y_offset_spin)
        options_form.addRow("Stitch tolerance", self.stitch_tolerance_spin)
        options_form.addRow("Stitch mode", self.stitch_mode_combo)

        tools_layout = QHBoxLayout()
        self.save_preset_button.clicked.connect(self._save_preset)
        self.load_preset_button.clicked.connect(self._load_preset)
        self.batch_convert_button.clicked.connect(self._batch_convert_folder)
        self.export_report_button.clicked.connect(self._export_report)
        tools_layout.addWidget(self.save_preset_button)
        tools_layout.addWidget(self.load_preset_button)
        tools_layout.addWidget(self.batch_convert_button)
        tools_layout.addWidget(self.export_report_button)
        tools_layout.addStretch(1)

        action_layout = QHBoxLayout()
        self.convert_button.clicked.connect(self._start_conversion)
        action_layout.addStretch(1)
        action_layout.addWidget(self.convert_button)

        left_panel = QWidget(self)
        left_layout = QVBoxLayout(left_panel)
        left_layout.addLayout(mode_layout)
        left_layout.addWidget(self.mode_description_label)
        left_layout.addLayout(input_layout)
        left_layout.addLayout(output_layout)
        left_layout.addWidget(options_box)
        left_layout.addLayout(tools_layout)
        left_layout.addWidget(self.progress_bar)
        left_layout.addWidget(self.status_label)
        left_layout.addLayout(action_layout)

        right_panel = QWidget(self)
        right_layout = QVBoxLayout(right_panel)
        right_layout.addWidget(QLabel("Geometry Preview"))
        right_layout.addWidget(self.preview_summary_label)
        right_layout.addWidget(self.preview_view)
        right_layout.addWidget(QLabel("Live Feedback"))
        right_layout.addWidget(self.feedback_box)
        right_layout.addWidget(QLabel("History"))
        right_layout.addWidget(self.history_box)

        splitter = QSplitter(self)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([560, 380])

        root_layout.addWidget(splitter)

        self.setCentralWidget(central)

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        descriptor = self._selected_plugin_descriptor()
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                local_file = url.toLocalFile()
                if local_file and Path(local_file).suffix.lower() in descriptor.input_extensions:
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event) -> None:  # type: ignore[override]
        descriptor = self._selected_plugin_descriptor()
        for url in event.mimeData().urls():
            local_file = url.toLocalFile()
            if local_file and Path(local_file).suffix.lower() in descriptor.input_extensions:
                self.input_path_edit.setText(local_file)
                self._refresh_source_geometry()
                self._sync_locked_dimensions(changed="width")
                self._apply_default_output_for_mode()
                self.status_label.setText(f"Input dropped: {Path(local_file).name}")
                event.acceptProposedAction()
                return
        event.ignore()

    def _populate_mode_combo(self) -> None:
        self.mode_combo.clear()
        for descriptor in self._plugin_descriptors:
            suffix = "" if descriptor.available and descriptor.enabled else " (unavailable)"
            self.mode_combo.addItem(f"{descriptor.name}{suffix}", descriptor.plugin_id)
        self._on_mode_changed()

    def _populate_origin_reference_combo(self) -> None:
        self.origin_reference_combo.addItem("Center of mass", "center-of-mass")
        self.origin_reference_combo.addItem("Bounding box: top-left", "bbox-top-left")
        self.origin_reference_combo.addItem("Bounding box: top-center", "bbox-top-center")
        self.origin_reference_combo.addItem("Bounding box: top-right", "bbox-top-right")
        self.origin_reference_combo.addItem("Bounding box: middle-left", "bbox-middle-left")
        self.origin_reference_combo.addItem("Bounding box: center", "bbox-center")
        self.origin_reference_combo.addItem("Bounding box: middle-right", "bbox-middle-right")
        self.origin_reference_combo.addItem("Bounding box: bottom-left", "bbox-bottom-left")
        self.origin_reference_combo.addItem("Bounding box: bottom-center", "bbox-bottom-center")
        self.origin_reference_combo.addItem("Bounding box: bottom-right", "bbox-bottom-right")

    def _connect_scale_sync(self) -> None:
        self.target_width_spin.valueChanged.connect(self._on_target_width_changed)
        self.target_height_spin.valueChanged.connect(self._on_target_height_changed)
        self.lock_uniform_checkbox.toggled.connect(self._sync_locked_dimensions)
        self.scale_spin.valueChanged.connect(self._update_preview)
        self.target_width_spin.valueChanged.connect(self._update_preview)
        self.target_height_spin.valueChanged.connect(self._update_preview)
        self.lock_uniform_checkbox.toggled.connect(self._update_preview)
        self.origin_reference_combo.currentIndexChanged.connect(self._update_preview)
        self.steps_spin.valueChanged.connect(self._on_detail_changed)

    def _refresh_source_geometry(self) -> None:
        input_path = self.input_path_edit.text().strip()
        if not input_path or not Path(input_path).exists() or Path(input_path).suffix.lower() != ".svg":
            self._source_aspect_ratio = None
            return

        try:
            from svg_to_dxf_app.conversion.svg_to_dxf import inspect_svg_geometry

            info = inspect_svg_geometry(input_path, int(self.steps_spin.value()))
            self._source_aspect_ratio = info.aspect_ratio if info.aspect_ratio > 0 else None
            self._update_preview()
        except Exception:
            self._source_aspect_ratio = None
            self.preview_summary_label.setText("Preview unavailable for the current input.")
            self.preview_scene.clear()

    def _on_target_width_changed(self, _value: float) -> None:
        self._sync_locked_dimensions(changed="width")

    def _on_target_height_changed(self, _value: float) -> None:
        self._sync_locked_dimensions(changed="height")

    def _sync_locked_dimensions(self, checked: bool | None = None, changed: str | None = None) -> None:
        if not self.lock_uniform_checkbox.isChecked() or not self._source_aspect_ratio:
            return

        if changed is None:
            changed = "width" if self.target_width_spin.value() > 0 else "height"

        aspect = self._source_aspect_ratio
        if aspect <= 0:
            return

        if changed == "width" and self.target_width_spin.value() > 0:
            with QSignalBlocker(self.target_height_spin):
                self.target_height_spin.setValue(self.target_width_spin.value() / aspect)
        elif changed == "height" and self.target_height_spin.value() > 0:
            with QSignalBlocker(self.target_width_spin):
                self.target_width_spin.setValue(self.target_height_spin.value() * aspect)

    def _on_detail_changed(self, _value: int) -> None:
        self._refresh_source_geometry()

    def _update_preview(self) -> None:
        input_path = self.input_path_edit.text().strip()
        if not input_path or not Path(input_path).exists() or Path(input_path).suffix.lower() != ".svg":
            self.preview_scene.clear()
            self.preview_summary_label.setText("Select an SVG to preview bounding box and origin.")
            return

        try:
            from svg_to_dxf_app.conversion.base import ConversionOptions
            from svg_to_dxf_app.conversion.svg_to_dxf import SvgToDxfConverter, inspect_svg_geometry
            from svgpathtools import svg2paths2

            info = inspect_svg_geometry(input_path, int(self.steps_spin.value()))
            options = ConversionOptions(
                scale=self.scale_spin.value(),
                target_width_mm=self.target_width_spin.value(),
                target_height_mm=self.target_height_spin.value(),
                lock_uniform_scale=self.lock_uniform_checkbox.isChecked(),
                origin_reference=str(self.origin_reference_combo.currentData()),
            )
            converter = SvgToDxfConverter()
            origin_x, origin_y = converter._resolve_origin(info, options.origin_reference)
            scale_x, scale_y = converter._resolve_scale(info, options)

            min_x = (info.min_x - origin_x) * scale_x
            max_x = (info.max_x - origin_x) * scale_x
            min_y = (info.min_y - origin_y) * scale_y
            max_y = (info.max_y - origin_y) * scale_y

            if options.invert_y_axis:
                min_y, max_y = -max_y, -min_y

            x_offset = options.extra_params.get("x_offset", 0.0)
            y_offset = options.extra_params.get("y_offset", 0.0)
            min_x += float(x_offset)
            max_x += float(x_offset)
            min_y += float(y_offset)
            max_y += float(y_offset)

            paths, _path_attributes, _svg_attributes = svg2paths2(input_path)
            entities = converter._collect_entities(paths, int(self.steps_spin.value()))

            self.preview_scene.clear()
            bbox_pen = QPen()
            bbox_pen.setWidthF(0.0)
            bbox_pen.setColor(Qt.blue)
            source_pen = QPen()
            source_pen.setWidthF(0.0)
            source_pen.setColor(Qt.darkGray)
            outline_pen = QPen()
            outline_pen.setWidthF(0.0)
            outline_pen.setColor(Qt.darkGreen)
            origin_pen = QPen()
            origin_pen.setWidthF(0.0)
            origin_pen.setColor(Qt.red)

            self.preview_scene.addRect(info.min_x, -info.max_y, info.width, info.height, source_pen)
            self.preview_scene.addRect(min_x, -max_y, max_x - min_x, max_y - min_y, bbox_pen)

            for points_raw, is_closed in entities:
                transformed_points = [
                    converter._transform_point_scaled(
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
                if len(transformed_points) < 2:
                    continue

                for index in range(1, len(transformed_points)):
                    x0, y0 = transformed_points[index - 1]
                    x1, y1 = transformed_points[index]
                    self.preview_scene.addLine(x0, -y0, x1, -y1, outline_pen)

                if is_closed:
                    x0, y0 = transformed_points[-1]
                    x1, y1 = transformed_points[0]
                    self.preview_scene.addLine(x0, -y0, x1, -y1, outline_pen)

            self.preview_scene.addLine(-5, 0, 5, 0, origin_pen)
            self.preview_scene.addLine(0, -5, 0, 5, origin_pen)
            self.preview_scene.addEllipse(-1.5, -1.5, 3, 3, origin_pen)

            self.preview_summary_label.setText(
                f"Source: {info.width:.3f} × {info.height:.3f} | "
                f"Target: {abs(max_x - min_x):.3f} × {abs(max_y - min_y):.3f} mm | "
                f"Origin: {options.origin_reference} | "
                f"Paths: {len(entities)}"
            )
            rect = self.preview_scene.itemsBoundingRect()
            if rect.isValid():
                self.preview_view.fitInView(rect, Qt.KeepAspectRatio)
        except Exception:
            self.preview_summary_label.setText("Preview unavailable for the current input/settings.")

    def _reload_plugins(self) -> None:
        self._plugin_manager.reload()
        self._plugin_descriptors = self._plugin_manager.list_plugins()
        self._populate_mode_combo()
        self.status_label.setText("Plugin manifest reloaded.")

    def _selected_plugin_descriptor(self) -> PluginDescriptor:
        plugin_id = str(self.mode_combo.currentData())
        return self._plugin_manager.get_descriptor(plugin_id)

    def _on_mode_changed(self) -> None:
        descriptor = self._selected_plugin_descriptor()
        self.status_label.setText(f"Mode selected: {descriptor.name}")
        self.mode_description_label.setText(descriptor.description or "No mode description provided.")
        self.preview_svg_button.setEnabled(".svg" in descriptor.input_extensions)
        self.preview_dxf_button.setEnabled(descriptor.output_extension == ".dxf")
        if not self.output_path_edit.text().strip() and self.input_path_edit.text().strip():
            self._apply_default_output_for_mode()

    def _select_input_file(self) -> None:
        descriptor = self._selected_plugin_descriptor()
        ext_patterns = " ".join(f"*{ext}" for ext in descriptor.input_extensions) or "*.*"
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Input File",
            "",
            f"Supported Files ({ext_patterns});;All Files (*.*)",
        )
        if path:
            self.input_path_edit.setText(path)
            self._refresh_source_geometry()
            self._sync_locked_dimensions(changed="width")
            self._apply_default_output_for_mode()

    def _select_output_file(self) -> None:
        descriptor = self._selected_plugin_descriptor()
        default_name = self.output_path_edit.text().strip() or f"output{descriptor.output_extension}"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Output As",
            default_name,
            f"Output Files (*{descriptor.output_extension});;All Files (*.*)",
        )
        if path:
            self.output_path_edit.setText(path)

    def _apply_default_output_for_mode(self) -> None:
        descriptor = self._selected_plugin_descriptor()
        input_path = self.input_path_edit.text().strip()
        if not input_path:
            return
        suggested = str(Path(input_path).with_suffix(descriptor.output_extension))
        self.output_path_edit.setText(suggested)

    def _current_settings(self) -> dict[str, object]:
        return {
            "scale": self.scale_spin.value(),
            "target_width_mm": self.target_width_spin.value(),
            "target_height_mm": self.target_height_spin.value(),
            "lock_uniform_scale": self.lock_uniform_checkbox.isChecked(),
            "origin_reference": str(self.origin_reference_combo.currentData()),
            "curve_approximation_steps": self.steps_spin.value(),
            "layer_name": self.layer_edit.text().strip() or "SVG_IMPORT",
            "invert_y_axis": self.invert_y_checkbox.isChecked(),
            "stitch_tolerance": self.stitch_tolerance_spin.value(),
            "stitch_mode": str(self.stitch_mode_combo.currentData()),
            "x_offset": self.x_offset_spin.value(),
            "y_offset": self.y_offset_spin.value(),
        }

    def _save_preset(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Preset",
            "preset.json",
            "JSON Files (*.json)",
        )
        if not path:
            return

        payload = {
            "plugin_id": str(self.mode_combo.currentData()),
            "settings": self._current_settings(),
        }
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.status_label.setText(f"Preset saved: {Path(path).name}")

    def _load_preset(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Preset",
            "",
            "JSON Files (*.json)",
        )
        if not path:
            return

        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        plugin_id = str(payload.get("plugin_id", ""))
        settings = payload.get("settings", {})
        for index in range(self.mode_combo.count()):
            if str(self.mode_combo.itemData(index)) == plugin_id:
                self.mode_combo.setCurrentIndex(index)
                break

        self.scale_spin.setValue(float(settings.get("scale", self.scale_spin.value())))
        self.target_width_spin.setValue(float(settings.get("target_width_mm", self.target_width_spin.value())))
        self.target_height_spin.setValue(float(settings.get("target_height_mm", self.target_height_spin.value())))
        self.lock_uniform_checkbox.setChecked(bool(settings.get("lock_uniform_scale", self.lock_uniform_checkbox.isChecked())))
        origin_reference = str(settings.get("origin_reference", self.origin_reference_combo.currentData()))
        origin_index = self.origin_reference_combo.findData(origin_reference)
        if origin_index >= 0:
            self.origin_reference_combo.setCurrentIndex(origin_index)
        self.steps_spin.setValue(int(settings.get("curve_approximation_steps", self.steps_spin.value())))
        self.layer_edit.setText(str(settings.get("layer_name", self.layer_edit.text())))
        self.invert_y_checkbox.setChecked(bool(settings.get("invert_y_axis", self.invert_y_checkbox.isChecked())))
        self.stitch_tolerance_spin.setValue(float(settings.get("stitch_tolerance", self.stitch_tolerance_spin.value())))
        self.x_offset_spin.setValue(float(settings.get("x_offset", self.x_offset_spin.value())))
        self.y_offset_spin.setValue(float(settings.get("y_offset", self.y_offset_spin.value())))
        stitch_mode = str(settings.get("stitch_mode", "all-points"))
        mode_index = self.stitch_mode_combo.findData(stitch_mode)
        if mode_index >= 0:
            self.stitch_mode_combo.setCurrentIndex(mode_index)
        self._refresh_source_geometry()
        self._sync_locked_dimensions(changed="width")
        self.status_label.setText(f"Preset loaded: {Path(path).name}")

    def _append_history(self, message: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {message}"
        self._history.append(line)
        self._history = self._history[-50:]
        self.history_box.setPlainText("\n".join(self._history))
        self.history_box.verticalScrollBar().setValue(self.history_box.verticalScrollBar().maximum())

    def _export_report(self) -> None:
        if not self._last_report:
            QMessageBox.information(self, "No Report", "No conversion report available yet.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Report",
            "conversion-report.json",
            "JSON Files (*.json);;Text Files (*.txt)",
        )
        if not path:
            return

        output = Path(path)
        if output.suffix.lower() == ".txt":
            lines = [f"{k}: {v}" for k, v in self._last_report.items()]
            output.write_text("\n".join(lines), encoding="utf-8")
        else:
            output.write_text(json.dumps(self._last_report, indent=2), encoding="utf-8")
        self.status_label.setText(f"Report exported: {output.name}")

    def _batch_convert_folder(self) -> None:
        descriptor = self._selected_plugin_descriptor()
        if not descriptor.enabled or not descriptor.available:
            QMessageBox.warning(self, "Plugin Unavailable", f"Mode '{descriptor.name}' is unavailable.")
            return

        input_dir = QFileDialog.getExistingDirectory(self, "Select Input Folder")
        if not input_dir:
            return
        output_dir = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if not output_dir:
            return

        input_root = Path(input_dir)
        output_root = Path(output_dir)
        candidates = [
            file
            for file in sorted(input_root.iterdir())
            if file.is_file() and file.suffix.lower() in descriptor.input_extensions
        ]
        if not candidates:
            QMessageBox.information(self, "No Files", "No matching input files found in folder.")
            return

        settings = self._current_settings()
        plugin = self._plugin_manager.create_plugin(descriptor.plugin_id)
        success = 0
        failures = 0
        for index, src in enumerate(candidates, start=1):
            dst = output_root / src.with_suffix(descriptor.output_extension).name
            self.status_label.setText(f"Batch converting {index}/{len(candidates)}: {src.name}")
            QApplication.processEvents()
            try:
                plugin.run(str(src), str(dst), settings, lambda _p: None)
                success += 1
                self._append_history(f"Batch OK: {src.name} -> {dst.name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                self._append_history(f"Batch FAIL: {src.name} ({exc})")

        summary = f"Batch complete. Success: {success}, Failed: {failures}"
        self.status_label.setText(summary)
        self.feedback_box.append(summary)
        self._last_report = {
            "type": "batch",
            "mode": descriptor.name,
            "input_dir": str(input_root),
            "output_dir": str(output_root),
            "total": len(candidates),
            "success": success,
            "failed": failures,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }

    def _open_svg_viewer(self) -> None:
        input_path = self.input_path_edit.text().strip()
        if not input_path:
            QMessageBox.warning(self, "Missing Input", "Please select an SVG file first.")
            return

        try:
            if self._svg_viewer_window is None:
                self._svg_viewer_window = SvgViewerWindow()
            self._svg_viewer_window.load_file(input_path)
            self._svg_viewer_window.show()
            self._svg_viewer_window.raise_()
            self._svg_viewer_window.activateWindow()
        except Exception as exc:  # noqa: BLE001 - show dialog-friendly error
            QMessageBox.critical(self, "SVG Viewer Error", str(exc))

    def _open_dxf_viewer(self) -> None:
        output_path = self.output_path_edit.text().strip()
        if not output_path:
            QMessageBox.warning(self, "Missing Output", "Please select or create a DXF file first.")
            return

        try:
            if self._dxf_viewer_window is None:
                self._dxf_viewer_window = DxfViewerWindow()
            self._dxf_viewer_window.load_file(output_path)
            self._dxf_viewer_window.show()
            self._dxf_viewer_window.raise_()
            self._dxf_viewer_window.activateWindow()
        except Exception as exc:  # noqa: BLE001 - show dialog-friendly error
            QMessageBox.critical(self, "DXF Viewer Error", str(exc))

    def _start_conversion(self) -> None:
        descriptor = self._selected_plugin_descriptor()
        if not descriptor.enabled or not descriptor.available:
            reason = descriptor.availability_reason or "Plugin not installed."
            QMessageBox.warning(
                self,
                "Plugin Unavailable",
                f"Mode '{descriptor.name}' is unavailable.\nReason: {reason}",
            )
            return

        input_path = self.input_path_edit.text().strip()
        if not input_path:
            QMessageBox.warning(self, "Missing Input", "Please select an input file first.")
            return
        if not Path(input_path).exists():
            QMessageBox.warning(self, "Invalid Input", "Selected input file does not exist.")
            return
        if descriptor.input_extensions and Path(input_path).suffix.lower() not in descriptor.input_extensions:
            allowed = ", ".join(descriptor.input_extensions)
            QMessageBox.warning(self, "Invalid Input", f"Input file must use: {allowed}")
            return

        output_path = self.output_path_edit.text().strip()
        if not output_path:
            self._select_output_file()
            output_path = self.output_path_edit.text().strip()
            if not output_path:
                return
        if Path(output_path).suffix.lower() != descriptor.output_extension:
            output_path = f"{output_path}{descriptor.output_extension}"
            self.output_path_edit.setText(output_path)

        options = {
            **self._current_settings(),
        }

        self.progress_bar.setValue(0)
        self.status_label.setText("Converting...")
        self.feedback_box.setPlainText(
            "Starting conversion...\n"
            f"Mode: {descriptor.name}\n"
            f"Input: {input_path}\n"
            f"Output: {output_path}\n"
            f"Target width: {options['target_width_mm']} mm\n"
            f"Target height: {options['target_height_mm']} mm\n"
            f"Lock aspect ratio: {options['lock_uniform_scale']}\n"
            f"Origin reference: {options['origin_reference']}\n"
            f"Stitch tolerance: {options['stitch_tolerance']}\n"
            f"Stitch mode: {options['stitch_mode']}\n"
            "Progress: 0%"
        )
        self._set_controls_enabled(False)

        converter = self._plugin_manager.create_plugin(descriptor.plugin_id)
        self._thread = QThread(self)
        self._worker = ConversionWorker(converter, input_path, output_path, options)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_conversion_success)
        self._worker.failed.connect(self._on_conversion_failure)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)

        self._thread.start()

    def _on_conversion_success(self, output_path: str) -> None:
        self.status_label.setText("Conversion complete.")
        self.feedback_box.append("Progress: 100%")
        self.feedback_box.append("Conversion completed successfully.")
        self._append_history(f"OK: {Path(self.input_path_edit.text().strip()).name} -> {Path(output_path).name}")
        self._last_report = {
            "type": "single",
            "mode": self._selected_plugin_descriptor().name,
            "input": self.input_path_edit.text().strip(),
            "output": output_path,
            "settings": self._current_settings(),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        QMessageBox.information(
            self,
            "Success",
            f"DXF created successfully:\n{output_path}",
        )

        if self._dxf_viewer_window is not None and self._dxf_viewer_window.isVisible():
            try:
                self._dxf_viewer_window.load_file(output_path)
            except Exception:
                # Ignore viewer refresh issues after successful conversion.
                pass

    def _on_conversion_failure(self, error_message: str) -> None:
        self.status_label.setText("Conversion failed.")
        self.feedback_box.append("Conversion failed. See details below.")
        self._append_history(f"FAIL: {Path(self.input_path_edit.text().strip()).name} ({error_message})")
        QMessageBox.critical(self, "Conversion Error", error_message)

    def _on_progress(self, value: int) -> None:
        self.progress_bar.setValue(value)
        self.status_label.setText(f"Converting... {value}%")
        lines = self.feedback_box.toPlainText().splitlines()
        if lines and lines[-1].startswith("Progress:"):
            lines[-1] = f"Progress: {value}%"
            self.feedback_box.setPlainText("\n".join(lines))
        else:
            self.feedback_box.append(f"Progress: {value}%")

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.input_path_edit.setEnabled(enabled)
        self.output_path_edit.setEnabled(enabled)
        self.scale_spin.setEnabled(enabled)
        self.target_width_spin.setEnabled(enabled)
        self.target_height_spin.setEnabled(enabled)
        self.lock_uniform_checkbox.setEnabled(enabled)
        self.origin_reference_combo.setEnabled(enabled)
        self.steps_spin.setEnabled(enabled)
        self.layer_edit.setEnabled(enabled)
        self.invert_y_checkbox.setEnabled(enabled)
        self.x_offset_spin.setEnabled(enabled)
        self.y_offset_spin.setEnabled(enabled)
        self.stitch_tolerance_spin.setEnabled(enabled)
        self.stitch_mode_combo.setEnabled(enabled)
        self.convert_button.setEnabled(enabled)
        self.batch_convert_button.setEnabled(enabled)
        self.reload_plugins_button.setEnabled(enabled)
        self.save_preset_button.setEnabled(enabled)
        self.load_preset_button.setEnabled(enabled)
        self.export_report_button.setEnabled(enabled)
        self.mode_combo.setEnabled(enabled)
        if enabled:
            descriptor = self._selected_plugin_descriptor()
            self.preview_svg_button.setEnabled(".svg" in descriptor.input_extensions)
            self.preview_dxf_button.setEnabled(descriptor.output_extension == ".dxf")
        else:
            self.preview_svg_button.setEnabled(False)
            self.preview_dxf_button.setEnabled(False)

    def _cleanup_thread(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None
        self._set_controls_enabled(True)
