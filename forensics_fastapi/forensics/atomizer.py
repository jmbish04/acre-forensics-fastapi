import hashlib
import json
import os
import re

import nltk
from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString

# Load NLTK model
# Ensure NLTK_DATA path is respected/added if explicitly set
# Ensure NLTK_DATA path is respected/added if explicitly set (though NLTK does checking, strict appending helps)
NLTK_DATA_ENV = os.environ.get("NLTK_DATA")
if NLTK_DATA_ENV and NLTK_DATA_ENV not in nltk.data.path:
    nltk.data.path.append(NLTK_DATA_ENV)

try:
    nltk.data.find("tokenizers/punkt")
    nltk.data.find("tokenizers/punkt_tab")
except LookupError:
    print("NLTK tokenizer not found (atomizer). Attempting fallback download...")
    # Use env var for download location if available to ensure persistence
    dl_dir = NLTK_DATA_ENV if NLTK_DATA_ENV else None
    nltk.download("punkt", download_dir=dl_dir)
    nltk.download("punkt_tab", download_dir=dl_dir)


class Atomizer:
    def __init__(self):
        pass

    def atomize(self, message_id, html_content, plain_content=None, sender_email=None):
        """
        Parses HTML, extracting atomic transcripts with depth and style.
        Returns list of MessageTranscript dicts.
        """
        if not html_content and plain_content:
            # Fallback to plain text if no HTML (treat as depth 0, style none)
            return self._atomize_plain(message_id, plain_content, sender_email)

        soup = BeautifulSoup(html_content, "lxml")  # Strict lxml usage per spec

        atoms = []
        sequence_index = 0

        # Recursive traversal
        def traverse(node, current_depth=0, current_style_stack=None):
            nonlocal sequence_index
            if current_style_stack is None:
                current_style_stack = {}

            # Update Style from Tag
            node_style = current_style_stack.copy()
            new_depth = current_depth

            if isinstance(node, Tag):
                # 1. Depth Logic (Blockquotes)
                if node.name == "blockquote":
                    new_depth += 1

                # 2. Visual Fingerprinting (Style extraction)
                # Parse 'style' attribute
                style_attr = str(node.get("style", "")).lower()
                if style_attr:
                    # Simple parser for color/font-weight
                    if "color" in style_attr:
                        # Extract color value (simplified)
                        match = re.search(r'color\s*:\s*([^;"]+)', style_attr)
                        if match:
                            node_style["color"] = match.group(1).strip()
                    if "font-weight" in style_attr or node.name in ["b", "strong"]:
                        if "bold" in style_attr or node.name in ["b", "strong"]:
                            node_style["font_weight"] = "bold"
                    if "text-transform" in style_attr and "uppercase" in style_attr:
                        node_style["text_transform"] = "uppercase"

                # Tag-based style
                if node.name in ["b", "strong"]:
                    node_style["font_weight"] = "bold"
                if node.name == "font":
                    color_attr = node.get("color")
                    if isinstance(color_attr, list) and color_attr:
                        color_attr = color_attr[0]
                    if isinstance(color_attr, str):
                        node_style["color"] = color_attr.lower()

                # Recurse
                for child in node.children:
                    traverse(child, new_depth, node_style)

            elif isinstance(node, NavigableString):
                text = str(node).strip()
                if not text:
                    return

                # 3. Sentence Segmentation
                sentences = nltk.sent_tokenize(text)
                for sent_text in sentences:
                    sent_text = sent_text.strip()
                    if not sent_text:
                        continue

                    # Create Transcript Atom
                    atom_hash = hashlib.sha256(sent_text.lower().encode("utf-8")).hexdigest()

                    # Serialize Style for Fingerprint
                    # Clean up default styles to reduce noise
                    clean_style = {k: v for k, v in node_style.items() if v}
                    visual_json = json.dumps(clean_style, sort_keys=True)

                    atom = {
                        "id": hashlib.sha256(
                            f"{message_id}_{sequence_index}".encode()
                        ).hexdigest(),  # Deterministic ID
                        "messageId": message_id,
                        "content": sent_text,
                        "normalizedHash": atom_hash,
                        "sequenceIndex": sequence_index,
                        "quoteDepth": new_depth,
                        "visualStyle": visual_json,
                        "attributedTo": None,  # Filled by Attribution Engine
                        "attributionMethod": None,
                    }
                    atoms.append(atom)
                    sequence_index += 1

        body = soup.find("body") or soup
        traverse(body)
        return atoms

    def _atomize_plain(self, message_id, text, sender_email):
        # Plain text processor (fallback)
        atoms = []
        sentences = nltk.sent_tokenize(text)
        for i, sent_text in enumerate(sentences):
            sent_text = sent_text.strip()
            if not sent_text:
                continue

            # Simple quote detection for plain text (lines starting with >)
            # This is sentence level, so might be lossy if spaCy grouped > with text.
            # Ideally split by newline first then spacy. But for now simplified:
            depth = 0
            if sent_text.startswith(">"):
                depth = sent_text.count(">")  # Rough heuristic
                sent_text = sent_text.lstrip("> ").strip()

            atom = {
                "id": hashlib.sha256(f"{message_id}_{i}".encode()).hexdigest(),
                "messageId": message_id,
                "content": sent_text,
                "normalizedHash": hashlib.sha256(sent_text.lower().encode()).hexdigest(),
                "sequenceIndex": i,
                "quoteDepth": depth,
                "visualStyle": "{}",
                "attributedTo": sender_email if depth == 0 else None,
            }
            atoms.append(atom)
        return atoms


if __name__ == "__main__":
    # Test "Franken-Thread"
    html_f = """
    <html><body>
        On Jan 1, Victim wrote:
        <blockquote>
            Did you get the permit?
            <span style="color: red; font-weight: bold;">YES WE DID (C39 #12345)</span>
            Please confirm installation date.
        </blockquote>
    </body></html>
    """

    atomizer = Atomizer()
    results = atomizer.atomize("msg_001", html_f)
    print(f"Extracted {len(results)} atoms.")
    for r in results:
        print(f"[{r['quoteDepth']}] {r['content']} (Style: {r['visualStyle']})")
