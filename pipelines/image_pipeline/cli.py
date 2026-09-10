"""
Command Line Interface (CLI) runner for the Image Pipeline.
Usage:
    python -m pipelines.image_pipeline.cli --image test.jpg --out ingestion_outputs/
"""
import argparse
import json
import sys
from pathlib import Path

from .extractor import process_image_pipeline


def main():
    parser = argparse.ArgumentParser(
        description="Extract verbatim text and visual anchor citations from cybersecurity threat diagrams."
    )
    parser.add_argument(
        "--image",
        "--input",
        "-i",
        dest="image",
        type=str,
        default="test.jpg",
        help="Path to the input image / diagram file (default: test.jpg)",
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

    image_path = Path(args.image)
    if not image_path.exists():
        print(f"❌ Error: Image file '{args.image}' not found.", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n🔍 Processing image: {image_path.resolve()} ...")
    result = process_image_pipeline(
        image_input=image_path,
        image_name=image_path.name,
        model=args.model,
        force_mock=args.mock,
    )

    # 1. Save extracted_data.json
    json_path = out_dir / "extracted_data.json"
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(result.model_dump(), indent=2))

    # 2. Save advisory.md
    md_path = out_dir / "advisory.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(result.markdown_output)

    # 3. Print concise terminal summary
    node_count = len(result.grounding_sources)
    print("\n" + "=" * 60)
    print("🛡️  NTRO PS 26154 | Image Extraction & Grounding Pipeline")
    print("=" * 60)
    print(f"Source Image     : {result.metadata.source_image_name} ({result.metadata.source_file_size_kb:.2f} KB)")
    print(f"Execution Mode   : {result.mode.upper()} (Model: {result.model})")
    print(f"Nodes Extracted  : {node_count} visual semantic anchors")
    print(f"Grounding Score  : {result.metadata.grounding_score_percent:.1f}%")
    print(f"Execution Time   : {result.execution_time_ms} ms")
    print("-" * 60)
    print("📁 Generated Artifacts:")
    print(f"  • Extracted JSON : {json_path}")
    print(f"  • Advisory MD    : {md_path}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
