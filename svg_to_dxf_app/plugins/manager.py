from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Dict, List

from svg_to_dxf_app.plugins.base import BaseConversionPlugin, PluginDescriptor


class PluginManager:
    def __init__(self, manifest_path: Path | None = None) -> None:
        self._manifest_path = manifest_path or Path(__file__).with_name("manifest.json")
        self._descriptors = self._load_manifest()

    def list_plugins(self) -> List[PluginDescriptor]:
        return list(self._descriptors.values())

    def reload(self) -> None:
        self._descriptors = self._load_manifest()

    def get_descriptor(self, plugin_id: str) -> PluginDescriptor:
        if plugin_id not in self._descriptors:
            raise ValueError(f"Unknown plugin id: {plugin_id}")
        return self._descriptors[plugin_id]

    def create_plugin(self, plugin_id: str) -> BaseConversionPlugin:
        descriptor = self.get_descriptor(plugin_id)
        if not descriptor.enabled:
            raise ValueError(f"Plugin '{descriptor.name}' is disabled.")
        if not descriptor.available:
            reason = descriptor.availability_reason or "Module/class could not be loaded."
            raise ValueError(f"Plugin '{descriptor.name}' is unavailable: {reason}")

        module = importlib.import_module(descriptor.module)
        plugin_class = getattr(module, descriptor.class_name)
        plugin = plugin_class()
        if not isinstance(plugin, BaseConversionPlugin):
            raise TypeError(
                f"Plugin '{descriptor.name}' does not implement BaseConversionPlugin."
            )
        return plugin

    def _load_manifest(self) -> Dict[str, PluginDescriptor]:
        data = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        descriptors: Dict[str, PluginDescriptor] = {}

        for item in data.get("plugins", []):
            module_name = str(item["module"])
            class_name = str(item["class"])
            enabled = bool(item.get("enabled", True))
            available = enabled
            reason = ""

            if enabled:
                try:
                    module = importlib.import_module(module_name)
                    if not hasattr(module, class_name):
                        raise AttributeError(f"Class '{class_name}' not found")
                except Exception as exc:  # noqa: BLE001 - report plugin availability
                    available = False
                    reason = str(exc)

            descriptor = PluginDescriptor(
                plugin_id=str(item["id"]),
                name=str(item["name"]),
                description=str(item.get("description", "")),
                module=module_name,
                class_name=class_name,
                input_extensions=list(item.get("input_extensions", [])),
                output_extension=str(item.get("output_extension", "")),
                enabled=enabled,
                available=available,
                availability_reason=reason,
            )
            descriptors[descriptor.plugin_id] = descriptor

        return descriptors
