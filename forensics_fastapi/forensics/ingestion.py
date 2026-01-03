import email
import hashlib
import os
from email.policy import default


class ArtifactRegistry:
    def __init__(self):
        pass

    def register_artifact(self, filepath):
        """Hashes file. Returns SHA256."""
        return self._compute_hash(filepath)

    def compute_string_hash(self, content: str) -> str:
        """Computes hash of string content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _compute_hash(self, filepath):
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()


class MimeExploder:
    def __init__(self):
        pass

    def parse_eml(self, filepath):
        with open(filepath, "rb") as f:
            msg = email.message_from_binary_file(f, policy=default)
        return self._extract_from_msg(msg)

    def parse_eml_bytes(self, raw_bytes):
        msg = email.message_from_bytes(raw_bytes, policy=default)
        return self._extract_from_msg(msg)

    def _extract_from_msg(self, msg):
        # Extract headers
        received_headers = msg.get_all("Received") or []
        headers = {
            "Message-ID": msg.get("Message-ID"),
            "From": msg.get("From"),
            "To": msg.get("To"),
            "Subject": msg.get("Subject"),
            "Date": msg.get("Date"),
            "Received": received_headers,
        }

        ingress_timestamp = received_headers[0] if received_headers else "Unknown"

        return headers, ingress_timestamp, msg


if __name__ == "__main__":
    # Test
    ingester = ArtifactRegistry()
    # Mock file for test
    with open("test_evidence.eml", "w") as f:
        f.write("From: bad@guy.com\nSubject: Lien\n\nPay me.")

    h = ingester.register_artifact("test_evidence.eml")
    print(f"Registered: {h}")
    os.remove("test_evidence.eml")
