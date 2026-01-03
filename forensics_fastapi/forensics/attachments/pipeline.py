
import logging
from pathlib import Path
from typing import Optional

from .extractor import ForensicAttachmentProcessor

logger = logging.getLogger(__name__)

class AttachmentPipeline:
    def __init__(self):
        self.processor = ForensicAttachmentProcessor()

    async def process_file(self, file_path: str, attachment_id: str, session_id: str, engagement_id: Optional[str] = None) -> dict:
        """
        Main entry point for processing a single attachment file.
        
        Args:
            file_path: Absolute path to the file on disk (or temp path).
            attachment_id: Unique ID for the attachment.
            session_id: The session ID this attachment belongs to.
            engagement_id: Optional engagement ID context.
        
        Returns:
            Dict containing the result of the processing (status, runId).
        """
        logger.info(f"Starting attachment pipeline for {attachment_id} (File: {file_path})")
        
        try:
            # 1. Validation
            path = Path(file_path)
            if not path.exists():
                raise FileNotFoundError(f"File not found at {file_path}")

            # 2. Run Processor (Uploads, Extract, Trigger Worker)
            result = await self.processor.process_attachment(
                file_path=path,
                attachment_id=attachment_id,
                session_id=session_id
            )
            
            logger.info(f"Attachment pipeline completed for {attachment_id}. Result: {result}")
            return result

        except Exception as e:
            logger.error(f"Attachment pipeline failed for {attachment_id}: {e}", exc_info=True)
            raise e
