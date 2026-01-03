import hashlib

import diff_match_patch as dmp_module


class VerificationEngine:
    def __init__(self):
        self.dmp = dmp_module.diff_match_patch()

    def normalize_content(self, text):
        """Strict normalization for hashing (lower, strip, collapse whitespace)"""
        if not text:
            return ""
        return " ".join(text.lower().split())

    def compute_hash(self, text):
        norm = self.normalize_content(text)
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()

    def verify_quote(self, quote_text, original_source_text):
        """
        Verifies if quote matches original source.
        Returns: match (bool), diff_html (str)
        """
        quote_hash = self.compute_hash(quote_text)
        original_hash = self.compute_hash(original_source_text)

        if quote_hash == original_hash:
            return True, None

        # If mismatch, compute diff
        # Semantic diff (word based ideally, but DMP is char based. We can use line mode or cleanup)
        diffs = self.dmp.diff_main(original_source_text, quote_text)
        self.dmp.diff_cleanupSemantic(diffs)
        html = self.dmp.diff_prettyHtml(diffs)

        return False, html

    def diff_texts(self, text1, text2):
        """Wrapper for semantic diff"""
        diffs = self.dmp.diff_main(text1, text2)
        self.dmp.diff_cleanupSemantic(diffs)
        return self.dmp.diff_prettyHtml(diffs)


if __name__ == "__main__":
    verifier = VerificationEngine()

    original = "The installation will be completed by Friday per contract."
    altered = "The installation will be completed by next week per conversation."

    print(f"Original: {original}")
    print(f"Quote:    {altered}")

    match, diff = verifier.verify_quote(altered, original)
    print(f"Match: {match}")
    if not match:
        print(f"Diff HTML: {diff}")
