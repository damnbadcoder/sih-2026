import argparse
import json
from .generator import generate_final_deliverable

def main():
    parser = argparse.ArgumentParser(description="Standalone CLI test for Final Post Pipeline")
    parser.add_argument("--platform", type=str, required=True, help="Target platform key (e.g., linkedin_post)")
    parser.add_argument("--draft", type=str, required=True, help="The approved draft text")
    parser.add_argument("--md", type=str, required=True, help="Path to sample markdown file")
    
    args = parser.parse_args()
    
    with open(args.md, "r") as f:
        content_md = f.read()
        
    result = generate_final_deliverable(
        platform_key=args.platform,
        approved_draft=args.draft,
        content_md=content_md,
        metadata_json={"title": "Test Meta"},
        parameters={"tone": "Urgent"}
    )
    
    print(result.model_dump_json(indent=2))

if __name__ == "__main__":
    main()
