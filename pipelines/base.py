"""
Base pipeline abstraction for the SIH PS 26154 Multimodal Intelligence System.
"""
from abc import ABC, abstractmethod
from typing import Any


class BasePipeline(ABC):
    """
    Abstract base class for all data ingestion and extraction pipelines
    (Image, Text, Video, Audio).
    """

    @abstractmethod
    def process(self, *args, **kwargs) -> Any:
        """
        Execute the ingestion and extraction pipeline.
        """
        pass
