from __future__ import annotations

from svg_to_dxf_app.conversion.base import BaseConverter, ConversionError, ConversionOptions
from svg_to_dxf_app.workers import ConversionWorker


class _SuccessConverter(BaseConverter):
    def convert(self, input_path, output_path, options, progress_callback):
        progress_callback(25)
        progress_callback(75)


class _FailingConverter(BaseConverter):
    def convert(self, input_path, output_path, options, progress_callback):
        raise ConversionError("Synthetic conversion failure")


def test_worker_emits_progress_and_finished() -> None:
    worker = ConversionWorker(
        _SuccessConverter(),
        "input.svg",
        "output.dxf",
        ConversionOptions(),
    )

    progress: list[int] = []
    finished: list[str] = []
    failed: list[str] = []

    worker.progress.connect(progress.append)
    worker.finished.connect(finished.append)
    worker.failed.connect(failed.append)

    worker.run()

    assert progress == [0, 25, 75, 100]
    assert finished == ["output.dxf"]
    assert failed == []


def test_worker_emits_failed_and_resets_progress() -> None:
    worker = ConversionWorker(
        _FailingConverter(),
        "input.svg",
        "output.dxf",
        ConversionOptions(),
    )

    progress: list[int] = []
    finished: list[str] = []
    failed: list[str] = []

    worker.progress.connect(progress.append)
    worker.finished.connect(finished.append)
    worker.failed.connect(failed.append)

    worker.run()

    assert progress == [0, 0]
    assert finished == []
    assert failed == ["Synthetic conversion failure"]
