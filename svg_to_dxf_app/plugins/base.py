from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

ProgressCallback = Callable[[int], None]


@dataclass(frozen=True)
class PluginDescriptor:
    plugin_id: str
    name: str
    description: str
    module: str
    class_name: str
    input_extensions: List[str]
    output_extension: str
    enabled: bool
    available: bool
    availability_reason: str = ""


class BaseConversionPlugin(ABC):
    @property
    @abstractmethod
    def plugin_id(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def run(
        self,
        input_path: str,
        output_path: str,
        settings: Dict[str, Any],
        progress_callback: ProgressCallback,
    ) -> None:
        """Execute conversion and emit progress values from 0..100."""
