from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict

ProgressCallback = Callable[[int], None]


class ConversionError(Exception):
    """User-facing conversion error with actionable details."""


@dataclass
class ConversionOptions:
    """Base options for SVG->DXF conversion.

    The extra_params dictionary is intentionally open-ended so new UI options can
    be wired in without changing the converter interface.
    """

    scale: float = 1.0
    target_width_mm: float = 0.0
    target_height_mm: float = 0.0
    lock_uniform_scale: bool = True
    origin_reference: str = "center-of-mass"
    curve_approximation_steps: int = 16
    layer_name: str = "SVG_IMPORT"
    invert_y_axis: bool = False
    stitch_tolerance: float = 0.0
    stitch_mode: str = "all-points"
    extra_params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BaseConverter(ABC):
    @abstractmethod
    def convert(
        self,
        input_path: str,
        output_path: str,
        options: ConversionOptions,
        progress_callback: ProgressCallback,
    ) -> None:
        """Convert input_path file into output_path, reporting progress 0..100."""
