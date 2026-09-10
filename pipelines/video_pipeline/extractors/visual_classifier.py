"""
Visual Keyframe Classification and Triage Engine.
Categorizes keyframes into SLIDE, TERMINAL, DIAGRAM, or OTHER based on
computer vision heuristics (brightness, edge/contour geometry) and OCR textual analysis.
"""

import re
import cv2
import numpy as np
from PIL import Image
from typing import Tuple
from pipelines.video_pipeline.schema import VisualType
from pipelines.text_pipeline.extractors.ocr_utils import extract_text_from_image_bytes


# Terminal indicator keywords and regexes
TERMINAL_PATTERNS = [
    re.compile(r"[$#]\s+[a-zA-Z0-9_\-]+"),                # shell prompt $ command
    re.compile(r"root@[a-zA-Z0-9_\-]+", re.I),            # root@host
    re.compile(r"[A-Z]:\\[a-zA-Z0-9_\\]+", re.I),         # C:\path
    re.compile(r"\b(?:sudo|chmod|nmap|curl|wget|python3?|docker|kubectl|ssh|grep|cat|ls|cd|dir)\b", re.I),
    re.compile(r"\b(?:STDIN|STDOUT|STDERR|bash|powershell|cmd\.exe|zsh)\b", re.I),
]

# Diagram indicator keywords
DIAGRAM_KEYWORDS = {
    "architecture", "topology", "firewall", "router", "dmz", "switch", "cloud",
    "vpc", "proxy", "c2", "attacker", "target", "database", "gateway", "flowchart",
    "pipeline", "orchestrator", "ingress", "egress", "mitre"
}

# Slide indicator keywords
SLIDE_KEYWORDS = {
    "agenda", "overview", "summary", "key takeaways", "mitigation", "conclusion",
    "timeline", "recommendations", "impact", "vulnerability details", "objective"
}


class KeyframeVisualClassifier:
    """Classifies video keyframes into SLIDE, TERMINAL, DIAGRAM, or OTHER."""

    def classify(self, image_path: str, raw_ocr_text: str = "") -> VisualType:
        """
        Classifies an extracted keyframe image.

        Args:
            image_path: Path to the keyframe image on disk.
            raw_ocr_text: Pre-extracted OCR text (if already computed), or will be computed.

        Returns:
            VisualType enum value.
        """
        image_cv = cv2.imread(image_path)
        if image_cv is None:
            return VisualType.OTHER

        # Read image bytes for OCR if not provided
        if not raw_ocr_text:
            with open(image_path, "rb") as f:
                raw_ocr_text = extract_text_from_image_bytes(f.read(), min_length=3)

        ocr_lower = raw_ocr_text.lower()
        word_count = len(raw_ocr_text.split())

        # 1. Computer Vision Feature Extraction
        gray = cv2.cvtColor(image_cv, cv2.COLOR_BGR2GRAY)
        mean_brightness = float(np.mean(gray))

        # Detect contours / bounding boxes for diagram box/node detection
        edges = cv2.Canny(gray, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        
        # Count rectangular bounding boxes of substantial size (indicative of diagram blocks/nodes)
        h, w = gray.shape
        node_boxes = 0
        for cnt in contours:
            approx = cv2.approxPolyDP(cnt, 0.04 * cv2.arcLength(cnt, True), True)
            if len(approx) == 4:  # Quadrilateral
                bx, by, bw, bh = cv2.boundingRect(approx)
                if 40 < bw < (w * 0.7) and 30 < bh < (h * 0.7):
                    node_boxes += 1

        # 2. Check for TERMINAL
        # Characteristics: Dark background (mean brightness < 100), prompt syntax, CLI commands
        terminal_matches = sum(1 for pat in TERMINAL_PATTERNS if pat.search(raw_ocr_text))
        if mean_brightness < 110 and (terminal_matches >= 1 or "powershell" in ocr_lower or "root@" in ocr_lower or "$ " in raw_ocr_text):
            return VisualType.TERMINAL
        if terminal_matches >= 2 and word_count > 5:
            return VisualType.TERMINAL

        # 3. Check for DIAGRAM
        # Characteristics: Multiple connected boxes/nodes, moderate text, architecture terminology
        diagram_term_matches = sum(1 for kw in DIAGRAM_KEYWORDS if kw in ocr_lower)
        if (node_boxes >= 4 and word_count < 60) or (node_boxes >= 2 and diagram_term_matches >= 2):
            return VisualType.DIAGRAM

        # 4. Check for SLIDE
        # Characteristics: Clean headings, bullet points, structured text, presentation terminology
        slide_term_matches = sum(1 for kw in SLIDE_KEYWORDS if kw in ocr_lower)
        has_bullets = any(line.strip().startswith(("-", "*", "•", "1.", "2.", "3.")) for line in raw_ocr_text.splitlines())
        if word_count >= 15 or slide_term_matches >= 1 or has_bullets:
            return VisualType.SLIDE

        # 5. Fallback to OTHER (camera feed, logo card, low information)
        return VisualType.OTHER
