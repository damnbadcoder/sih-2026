"""
Command Line Interface (CLI) runner for the Audio Pipeline.
Usage:
    python -m pipelines.audio_pipeline.cli --audio sample.wav --out ingestion_outputs/
"""
import argparse
import json
import sys
from pathlib import Path

from .extractor import process_audio_pipeline


def main():
    parser = argparse.ArgumentParser(
        description="Transcribe, ground, and extract threat intelligence from voice and audio communications."
    )
    parser.add_argument(
        "--audio",
        "--input",
        "-i",
        dest="audio",
        type=str,
        default="sample.wav",
        help="Path to the input audio file (WAV, MP3, M4A, OGG, FLAC)",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="ingestion_outputs",
        help="Directory to save output files (default: ingestion_outputs/)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gemini-2.5-flash-lite",
        help="Gemini model to use (default: gemini-2.5-flash-lite)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Force offline mock simulation mode",
    )

    args = parser.parse_args()

    audio_path = Path(args.audio)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # If file doesn't exist and in mock mode or sample mode, run mock pipeline gracefully
    if not audio_path.exists():
        if args.mock:
            print(f"ℹ️  Audio file '{args.audio}' not found on disk. Running offline mock simulation.")
            from .mock import get_mock_audio_pipeline_result
            result = get_mock_audio_pipeline_result(audio_name=audio_path.name)
        else:
            print(f"❌ Error: Audio file '{args.audio}' not found.", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"\n🎧 Processing audio recording: {audio_path.resolve()} ...")
        result = process_audio_pipeline(
            audio_input=audio_path,
            audio_name=audio_path.name,
            model=args.model,
            force_mock=args.mock,
        )

    # 1. Save extracted_audio_data.json
    json_path = out_dir / "extracted_audio_data.json"
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(result.model_dump(), indent=2))

    # 2. Save audio_advisory.md
    md_path = out_dir / "audio_advisory.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(result.markdown_output)

    # 3. Print concise summary
    node_count = len(result.grounding_sources)
    duration_info = f"{result.metadata.duration_seconds:.1f}s" if result.metadata.duration_seconds else "N/A"

    print("\n" + "=" * 60)
    print("🛡️  NTRO PS 26154 | Audio Extraction & Grounding Pipeline")
    print("=" * 60)
    print(f"Source Audio     : {result.metadata.source_audio_name} ({result.metadata.source_file_size_kb:.2f} KB)")
    print(f"Format / Length  : {result.metadata.audio_format} | {duration_info}")
    print(f"Execution Mode   : {result.mode.upper()} (Model: {result.model})")
    print(f"Temporal Anchors : {node_count} speaker / timecode citations")
    print(f"Grounding Score  : {result.metadata.grounding_score_percent:.1f}%")
    print(f"Execution Time   : {result.execution_time_ms} ms")
    print("-" * 60)
    print("📁 Generated Artifacts:")
    print(f"  • Extracted JSON : {json_path}")
    print(f"  • Advisory MD    : {md_path}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
