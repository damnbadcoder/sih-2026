"""
Video Ingestion Pipeline Entry Point.
Aliases VideoIngestionPipeline from pipelines.video_pipeline.ingest.
"""

from pipelines.video_pipeline.ingest import VideoIngestionPipeline, main

__all__ = ["VideoIngestionPipeline", "main"]

if __name__ == "__main__":
    main()
