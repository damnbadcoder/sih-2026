import argparse
import json
from .generator import generate_previews
from .types import OutputType

def main():
    parser = argparse.ArgumentParser(description="Standalone CLI test for Preview Pipeline")
    parser.add_argument("--md", type=str, required=True, help="Path to sample markdown file")
    parser.add_argument("--json", type=str, required=True, help="Path to sample JSON metadata file")
    parser.add_argument("--outputs", type=str, required=True, help="Comma separated list of output platforms")
    parser.add_argument("--org", action="store_true", help="Enable organization mode (sensitive data flag/redact)")
    parser.add_argument("--tone", type=str, default="Professional", help="Tone for generation")
    parser.add_argument("--audience", type=str, default="SOC Analysts", help="Target audience")
    parser.add_argument("--detail", type=str, default="High", help="Detail level")
    parser.add_argument("--language", type=str, default="English", help="Output language")
    parser.add_argument("--objective", type=str, default="Generate actionable threat intelligence deliverable", help="Generation objective")
    
    args = parser.parse_args()
    
    with open(args.md, "r") as f:
        content_md = f.read()
        
    with open(args.json, "r") as f:
        metadata_json = json.load(f)
        
    selected_outputs = [x.strip() for x in args.outputs.split(",")]
    
    # Validate outputs
    valid_outputs = [o.value for o in OutputType]
    invalid = [o for o in selected_outputs if o not in valid_outputs]
    if invalid:
        print(f"Warning: Invalid output types: {invalid}. Valid: {valid_outputs}")
    
    parameters = {
        "tone": args.tone,
        "targetAudience": args.audience,
        "detail": args.detail,
        "language": args.language,
        "objective": args.objective,
    }
    
    result = generate_previews(
        content_md=content_md,
        metadata_json=metadata_json,
        selected_outputs=selected_outputs,
        parameters=parameters,
        is_organization=args.org
    )
    
    print(result.model_dump_json(indent=2))

if __name__ == "__main__":
    main()