"""
Synthesis & Preview Server — Handles multimodal file ingestion,
preview generation, sensitive data proofchecking, and final post generation.
"""

import os
import sys
import json
import re
import tempfile
import traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Dict, Any, List

from preview_pipeline import generate_previews, scan_and_redact
from final_post_pipeline import generate_final_deliverable

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".ogg", ".flac"}
VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"}

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "*",
}


def _detect_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in VIDEO_EXTS:
        return "video"
    return "text"


def parse_multipart(body: bytes, boundary: str) -> dict:
    result = {}
    boundary_bytes = boundary.encode("utf-8")
    parts = body.split(b"--" + boundary_bytes)

    for part in parts:
        part = part.strip()
        if not part or part == b"--":
            continue

        if b"\r\n\r\n" in part:
            header_section, part_body = part.split(b"\r\n\r\n", 1)
        elif b"\n\n" in part:
            header_section, part_body = part.split(b"\n\n", 1)
        else:
            continue

        if part_body.endswith(b"\r\n"):
            part_body = part_body[:-2]
        if part_body.endswith(b"--"):
            part_body = part_body[:-2]
        if part_body.endswith(b"\r\n"):
            part_body = part_body[:-2]

        headers_str = header_section.decode("utf-8", errors="replace")
        name_match = re.search(r'name="([^"]*)"', headers_str)
        if not name_match:
            continue
        field_name = name_match.group(1)

        filename_match = re.search(r'filename="([^"]*)"', headers_str)
        if filename_match and filename_match.group(1):
            value = {"filename": filename_match.group(1), "data": part_body}
        else:
            value = part_body.decode("utf-8", errors="replace")

        if field_name in result:
            if not isinstance(result[field_name], list):
                result[field_name] = [result[field_name]]
            result[field_name].append(value)
        else:
            result[field_name] = value

    return result


def _run_pipeline_extract(file_path: str, filename: str, file_type: str) -> dict:
    citations = []
    markdown = ""
    try:
        if file_type == "image":
            from pipelines import ingest_image
            r = ingest_image(file_path)
            markdown = r.markdown_output or ""
            for anchor in getattr(r, "grounding_sources", []):
                citations.append({
                    "id": getattr(anchor, "id", f"img-{len(citations)+1}"),
                    "kind": "file",
                    "label": f"[{getattr(anchor, 'visual_anchor', filename)}] {getattr(anchor, 'extracted_verbatim', '')[:100]}",
                })
        elif file_type == "audio":
            from pipelines import ingest_audio
            r = ingest_audio(file_path)
            markdown = r.markdown_output or ""
            for anchor in getattr(r, "grounding_sources", []):
                citations.append({
                    "id": getattr(anchor, "id", f"aud-{len(citations)+1}"),
                    "kind": "file",
                    "label": f"[{getattr(anchor, 'temporal_anchor', filename)}] {getattr(anchor, 'extracted_verbatim', '')[:100]}",
                })
        elif file_type == "video":
            from pipelines import ingest_video
            r = ingest_video(file_path, save_outputs=False, enrich=False)
            markdown = r.clean_markdown or ""
            for scene in getattr(r, "scenes", [])[:5]:
                citations.append({
                    "id": f"vid-{getattr(scene, 'scene_id', 1)}",
                    "kind": "file",
                    "label": f"[{getattr(scene, 'timestamp_display', '00:00')}] {getattr(scene, 'spoken_transcript', '')[:80]}",
                })
        else:
            from pipelines import ingest_text
            r = ingest_text(file_path, save_outputs=False, enrich=False)
            markdown = r.clean_markdown or ""
            iocs = getattr(r, "iocs", None)
            if iocs:
                for cve in getattr(iocs, "cves", []):
                    citations.append({"id": f"cve-{cve}", "kind": "file", "label": cve})
                for ip in getattr(iocs, "ipv4_addresses", []):
                    citations.append({"id": f"ip-{ip}", "kind": "file", "label": ip})
    except Exception as e:
        print(f"Error extracting {filename}: {e}")
        markdown = f"Extracted facts from file `{filename}` ({file_type})."
        citations.append({"id": f"src-{filename}", "kind": "file", "label": filename})

    return {"markdown": markdown, "citations": citations}


class SynthesisRequestHandler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(204)
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()

    def do_GET(self):
        if self.path in ("/api/health", "/health", "/"):
            self._send_json(200, {"status": "healthy", "service": "transmute-synthesis-server"})
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        try:
            content_type = self.headers.get("Content-Type", "")
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)

            if self.path == "/api/health":
                self._send_json(200, {"status": "ok"})
                return

            if self.path == "/api/proofcheck":
                payload = json.loads(body.decode("utf-8"))
                text = payload.get("previewText", "")
                audited_text, flags = scan_and_redact(text)
                self._send_json(200, {
                    "proofcheckedText": audited_text,
                    "sensitiveCount": len(flags),
                    "flags": [f.model_dump() for f in flags] if hasattr(flags[0], "model_dump") else flags if flags else []
                })
                return

            if self.path in ("/api/generate-deliverable", "/api/finalize"):
                payload = json.loads(body.decode("utf-8"))
                # Supports both frontend shape and standalone app shape
                platform_key = payload.get("platform_key") or payload.get("outputType") or "linkedin_post"
                approved_draft = payload.get("approved_draft") or payload.get("previewDraft") or ""
                content_md = payload.get("content_md") or payload.get("groundingMd") or payload.get("sourceText") or ""
                metadata_json = payload.get("metadata_json") or payload.get("groundingJson") or {}
                parameters = payload.get("parameters") or payload.get("params") or {}

                result = generate_final_deliverable(
                    platform_key=platform_key,
                    approved_draft=approved_draft,
                    content_md=content_md,
                    metadata_json=metadata_json if isinstance(metadata_json, dict) else {},
                    parameters=parameters if isinstance(parameters, dict) else {}
                )
                self._send_json(200, {
                    "content": result.final_content,
                    "final_content": result.final_content,
                    "provenance": [p.model_dump() for p in result.provenance]
                })
                return

            if self.path in ("/api/generate-plan", "/api/preview"):
                source_text = ""
                source_links = []
                outputs = []
                file_entries = []
                is_organization = False

                if "multipart/form-data" in content_type:
                    boundary_match = re.search(r'boundary=(.+)', content_type)
                    if not boundary_match:
                        self._send_text(400, "Missing boundary in multipart request")
                        return
                    boundary = boundary_match.group(1).strip()
                    form = parse_multipart(body, boundary)

                    source_text = form.get("sourceText", "")
                    if isinstance(source_text, list):
                        source_text = source_text[0]
                    links_raw = form.get("sourceLinks", "[]")
                    if isinstance(links_raw, list):
                        links_raw = links_raw[0]
                    outputs_raw = form.get("outputs", "[]")
                    if isinstance(outputs_raw, list):
                        outputs_raw = outputs_raw[0]

                    is_org_raw = form.get("isOrganisation", "false")
                    if isinstance(is_org_raw, list):
                        is_org_raw = is_org_raw[0]
                    is_organization = str(is_org_raw).lower() in ("true", "1", "yes")

                    try:
                        source_links = json.loads(links_raw)
                    except:
                        source_links = []
                    try:
                        outputs = json.loads(outputs_raw)
                    except:
                        outputs = []

                    f_list = form.get("files", [])
                    if not isinstance(f_list, list):
                        f_list = [f_list]
                    file_entries = [f for f in f_list if isinstance(f, dict) and "filename" in f]
                else:
                    payload = json.loads(body.decode("utf-8"))
                    source_text = payload.get("sourceText", "") or payload.get("content_md", "")
                    source_links = payload.get("sourceLinks", [])
                    outputs = payload.get("outputs", [])
                    selected_outputs_raw = payload.get("selected_outputs", [])
                    is_organization = bool(payload.get("isOrganisation", False) or payload.get("is_organization", False))
                    parameters = payload.get("parameters", {})

                    if not outputs and selected_outputs_raw:
                        outputs = [{"id": k, "params": parameters} for k in selected_outputs_raw]

                # Run file extraction
                extracted_mds = []
                citations = []
                for entry in file_entries:
                    fname = entry["filename"]
                    fdata = entry["data"]
                    ftype = _detect_type(fname)
                    suffix = Path(fname).suffix
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                        tmp.write(fdata)
                        tmp_path = tmp.name
                    try:
                        res = _run_pipeline_extract(tmp_path, fname, ftype)
                        if res["markdown"]:
                            extracted_mds.append(f"## Data from {fname} ({ftype}):\n\n{res['markdown']}")
                        citations.extend(res["citations"])
                    finally:
                        if os.path.exists(tmp_path):
                            os.unlink(tmp_path)

                combined_md = source_text
                if extracted_mds:
                    combined_md = f"{source_text}\n\n---\n\n" + "\n\n".join(extracted_mds)

                # Collect output types
                selected_keys = []
                merged_params = {}
                key_mapping = {
                    "advisory": "advisory",
                    "executive_summary": "exec_summary",
                    "exec_summary": "exec_summary",
                    "linkedin": "linkedin_post",
                    "linkedin_post": "linkedin_post",
                    "twitter": "social_thread",
                    "social_thread": "social_thread",
                    "presentation": "slide_deck",
                    "slide_deck": "slide_deck",
                    "video_package": "video_script",
                    "video_script": "video_script",
                    "infographic": "playbook",
                    "playbook": "playbook",
                    "incident_report": "incident_report",
                    "press_release": "press_release",
                }

                for out in outputs:
                    oid = out.get("id", "")
                    pkey = key_mapping.get(oid, oid)
                    if pkey not in selected_keys:
                        selected_keys.append(pkey)
                    if "params" in out and isinstance(out["params"], dict):
                        merged_params.update(out["params"])

                if not selected_keys:
                    selected_keys = ["linkedin_post", "advisory"]

                preview_result = generate_previews(
                    content_md=combined_md,
                    metadata_json={"source_links": source_links},
                    selected_outputs=selected_keys,
                    parameters=merged_params,
                    is_organization=is_organization
                )

                # Format response for frontend
                previews_by_type = {}
                previews_dict = {}

                for k, p_obj in preview_result.previews.items():
                    previews_by_type[k] = p_obj.draft_content
                    # also map reverse if needed
                    previews_dict[p_obj.display_name] = {
                        "platform_key": k,
                        "output_type_id": k,
                        "draft_title": p_obj.draft_title,
                        "draft_content": p_obj.draft_content,
                        "citations_used": p_obj.citations_used,
                        "sensitive_items_flagged": len(p_obj.sensitive_flags)
                    }

                default_plan = preview_result.source_summary
                if selected_keys and selected_keys[0] in previews_by_type:
                    default_plan = previews_by_type[selected_keys[0]]

                # Merge extracted citations
                for c in preview_result.extracted_facts:
                    citations.append({
                        "id": f"fact-{len(citations)+1}",
                        "kind": "text",
                        "label": c
                    })

                self._send_json(200, {
                    "plan": default_plan,
                    "previewsByType": previews_by_type,
                    "previews": previews_dict,
                    "citations": citations,
                    "grounding_md": combined_md,
                    "grounding_json": preview_result.metadata_anchors,
                    "extracted_facts": preview_result.extracted_facts
                })
                return

            self.send_response(404)
            self.end_headers()

        except Exception as e:
            traceback.print_exc()
            self._send_text(500, f"Server Error: {str(e)}")

    def _send_json(self, code, data):
        self.send_response(code)
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _send_text(self, code, text):
        self.send_response(code)
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(text.encode("utf-8"))


def run_server(port=8000):
    server_address = ("", port)
    httpd = HTTPServer(server_address, SynthesisRequestHandler)
    print(f"[+] Transmute Synthesis Server running on http://localhost:{port}")
    print(f"    Available routes: /api/generate-plan, /api/proofcheck, /api/generate-deliverable, /api/health")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    httpd.server_close()
    print("Server stopped.")


if __name__ == "__main__":
    run_server(int(os.environ.get("PORT", 8000)))
