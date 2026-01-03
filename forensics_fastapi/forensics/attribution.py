import json


class AttributionEngine:
    def __init__(self):
        pass

    def attribute_atoms(self, atoms, sender_email, thread_participants=None):
        """
        Refines attribution for a list of atoms from a single message.
        """
        # Determine likely quoted author (naively previous sender in thread or "Other")
        # In a real system, we look up In-Reply-To header -> Sender.
        # For this function, we assume 'quote_author' is passed or resolved.
        # We will use "Quoted_Party" as placeholder if unknown.

        # current_author = sender_email

        for atom in atoms:
            quote_depth = atom.get("quoteDepth", 0)
            visual_style_str = atom.get("visualStyle", "{}")
            visual_style = json.loads(visual_style_str)

            # Heuristic 1: Depth 0 = Sender
            if quote_depth == 0:
                atom["attributedTo"] = sender_email
                atom["attributionMethod"] = "HEADER_DEPTH_0"
                atom["isAlteredQuote"] = False

            else:
                # Depth > 0
                # Heuristic 2: Inline Reply Detection (The "Franken-Thread" Logic)
                # If highly styled (color/bold) inside a quote, it's likely the Sender interrupting

                is_aggressive_style = False
                if visual_style:
                    # Check for Red or Bold
                    if "color" in visual_style and "red" in visual_style["color"]:
                        is_aggressive_style = True
                    if "font_weight" in visual_style and visual_style["font_weight"] == "bold":
                        is_aggressive_style = True
                    if (
                        "text_transform" in visual_style
                        and visual_style["text_transform"] == "uppercase"
                    ):
                        is_aggressive_style = True

                if is_aggressive_style:
                    # Flag as Interjection
                    atom["attributedTo"] = sender_email
                    atom["attributionMethod"] = "STYLE_INFERENCE_INTERJECTION"
                    # It's technically an "Altered Quote" because it breaks the quote block,
                    # but authorship is correctly reassigned to Sender.
                    # We might mark logic flag here.
                else:
                    # Standard Quote
                    atom["attributedTo"] = "Quoted_Party"  # Needs Reference Resolution
                    atom["attributionMethod"] = "QUOTE_DEPTH"

        return atoms


if __name__ == "__main__":
    # Test Data from Atomizer output
    test_atoms = [
        {"quoteDepth": 0, "content": "On Jan 1...:", "visualStyle": "{}"},
        {"quoteDepth": 1, "content": "Did you get the permit?", "visualStyle": "{}"},
        {
            "quoteDepth": 1,
            "content": "YES WE DID",
            "visualStyle": '{"color": "red", "font_weight": "bold"}',
        },
        {"quoteDepth": 1, "content": "Please confirm.", "visualStyle": "{}"},
    ]

    engine = AttributionEngine()
    attributed = engine.attribute_atoms(test_atoms, "mark@roofer.com")

    for a in attributed:
        print(
            f"[{a['quoteDepth']}] {a['content']} -> {a['attributedTo']} ({a.get('attributionMethod')})"
        )
