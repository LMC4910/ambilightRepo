"""
ambilight — Production-grade GPU-accelerated Ambilight system.

Quick start
-----------
>>> from ambilight.config import ConfigManager
>>> from ambilight.pipeline import AmbilightPipeline
>>>
>>> config = ConfigManager.load("configuration.yaml")
>>> pipeline = AmbilightPipeline(config)
>>> pipeline.start()
>>> pipeline.run()   # blocks until Ctrl-C or pipeline.stop()

Public API surface
------------------
The stable public symbols are:

* :class:`ambilight.pipeline.AmbilightPipeline`
* :class:`ambilight.config.ConfigManager`, :class:`ambilight.config.AppConfig`
* :class:`ambilight.led_output.MagicHomeController`
* :class:`ambilight.discovery.DeviceDiscovery`, :class:`ambilight.discovery.DeviceScanner`
* :class:`ambilight.color.ColorAnalyzer`, :class:`ambilight.color.ColorMode`
* :class:`ambilight.smoothing.SmoothingEngine`
* :class:`ambilight.zones.ZoneManager`, :class:`ambilight.zones.Zone`
* :class:`ambilight.capture.ScreenCaptureManager`
* :class:`ambilight.gpu.GpuAccelerator`, :func:`ambilight.gpu.detect_backend`
* :func:`ambilight.logging_setup.setup_logging`
"""

__version__ = "1.0.0"
__author__ = "Ambilight Engine"

from .config import AppConfig, ConfigManager
from .pipeline import AmbilightPipeline

__all__ = [
    "AmbilightPipeline",
    "AppConfig",
    "ConfigManager",
    "__version__",
]
