from __future__ import annotations

from typing import Any

from PyQt5.QtCore import QObject, pyqtSignal

from svg_to_dxf_app.conversion.base import ConversionError


class ConversionWorker(QObject):
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        converter: Any,
        input_path: str,
        output_path: str,
        options: Any,
    ) -> None:
        super().__init__()
        self._converter = converter
        self._input_path = input_path
        self._output_path = output_path
        self._options = options

    def run(self) -> None:
        try:
            self.progress.emit(0)
            if hasattr(self._converter, "run"):
                self._converter.run(
                    self._input_path,
                    self._output_path,
                    self._options,
                    self.progress.emit,
                )
            else:
                self._converter.convert(
                    self._input_path,
                    self._output_path,
                    self._options,
                    self.progress.emit,
                )
            self.progress.emit(100)
            self.finished.emit(self._output_path)
        except ConversionError as exc:
            self.progress.emit(0)
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - bubble readable message to UI
            self.progress.emit(0)
            self.failed.emit(str(exc))
