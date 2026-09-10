# 🖼️ Image Pipeline

## Purpose & Scope
The `image_pipeline` will handle visual threat artifacts, architecture diagrams, screenshots of terminal sessions, and infographics related to cybersecurity incidents.

## Planned Capabilities (Roadmap)
1. **OCR Extraction:** High-accuracy OCR (e.g., Tesseract or Docling OCR) to extract text, code snippets, and terminal commands embedded in images.
2. **Visual Feature Extraction:** Detection of architecture topologies, network diagrams, and attack graphs.
3. **Vision LLM Grounding:** Captioning and visual reasoning via multimodal models (e.g., Gemini Flash Vision / Qwen-VL) to extract structured context into the canonical grounding bundle.
4. **Output Contract:** Emits an image context bundle compatible with downstream reporting and slide synthesis.
