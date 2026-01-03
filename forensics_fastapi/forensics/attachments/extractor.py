import json
import logging
import shutil
import tempfile
from pathlib import Path

import boto3
import httpx

# Import Config for Credentials
from ...config import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    HOST_API_URL,
    INTERNAL_SERVICE_KEY,
    R2_DOC_PAGES_BUCKET_NAME,
    R2_ENDPOINT_URL,
    R2_EVIDENCE_BUCKET_NAME,
)

logger = logging.getLogger(__name__)

class ForensicAttachmentProcessor:
    def __init__(self):
        # Initialize S3/R2 Client
        self.s3 = boto3.client(
            's3',
            endpoint_url=R2_ENDPOINT_URL,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name='auto'  # R2 requires region, usually 'auto' or 'us-east-1'
        )
        self.evidence_bucket = R2_EVIDENCE_BUCKET_NAME
        self.doc_pages_bucket = R2_DOC_PAGES_BUCKET_NAME

    async def process_attachment(self, file_path: Path, attachment_id: str, session_id: str):
        """
        Full Chain of Custody Processing:
        1. Upload Original (Evidence Bucket)
        2. Extract Metadata (ExifTool)
        3. OCR & Rasterize (Doc Pages Bucket)
           - Converted PDF
           - TIFF Page Images
           - Per-Page Extracted Text
           - Per-Page OCR Text
        4. Trigger Worker Workflow
        """
        logger.info(f"Processing attachment {attachment_id} from {file_path}")
        
        artifacts = []
        extracted_metadata = {}
        pages_data = [] # List of { pageNumber, r2Key, extractedTextKey, ocrTextKey, tiffKey }
        
        # We'll use a local temp dir for all processing artifacts
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            try:
                # 1. Upload ORIGINAL to Evidence Bucket
                # Key: evidence/{session_id}/{attachment_id}/original/{filename}
                original_key = f"evidence/{session_id}/{attachment_id}/original/{Path(file_path).name}"
                self._upload_file(file_path, self.evidence_bucket, original_key)
                artifacts.append({
                    "type": "ORIGINAL",
                    "key": original_key,
                    "bucket": self.evidence_bucket,
                    "size": Path(file_path).stat().st_size,
                    "contentType": self._guess_mime(file_path)
                })

                # 2. Extract Metadata
                extracted_metadata = self._extract_exif_metadata(file_path)

                # 3. Content Processing (PDF/Image Pipeline)
                mime_type = self._guess_mime(file_path)
                
                # Check if it's a PDF or convertible image
                if "pdf" in mime_type or "image" in mime_type:
                    # Rename input to safe name in temp
                    safe_input = temp_path / f"input_{Path(file_path).name}"
                    shutil.copy(file_path, safe_input)

                    if "image" in mime_type and "pdf" not in mime_type:
                        # Convert image to PDF first for consistent pipeline
                        import img2pdf
                        pdf_input = temp_path / f"{attachment_id}_converted.pdf"
                        pdf_bytes = img2pdf.convert(str(safe_input))
                        if pdf_bytes:
                            with open(pdf_input, "wb") as f:
                                f.write(pdf_bytes)
                        safe_input = pdf_input

                    # Run strict forensic pipeline
                    pipeline_results = self._process_forensic_pipeline(
                        safe_input, 
                        temp_path, 
                        attachment_id, 
                        Path(file_path).name
                    )
                    
                    artifacts.extend(pipeline_results['artifacts'])
                    pages_data = pipeline_results['pages']
                
                # 4. Trigger Worker Workflow
                payload = {
                    "attachmentId": attachment_id,
                    "sessionId": session_id,
                    "artifacts": artifacts,
                    "metadata": extracted_metadata,
                    "pages": pages_data 
                }
                
                await self._trigger_workflow(payload)

                return {"success": True, "artifacts": artifacts}

            except Exception as e:
                logger.error(f"Failed to process attachment {attachment_id}: {e}", exc_info=True)
                return {"success": False, "error": str(e)}

    def _process_forensic_pipeline(self, pdf_path: Path, work_dir: Path, attachment_id: str, original_filename: str):
        """
        Executes the Standard Forensic Pipeline:
        - OCRmyPDF (Force OCR for clean text layer)
        - PDF2Image (TIFF extraction)
        - PyPDF (Text Extraction)
        """
        import ocrmypdf
        from pdf2image import convert_from_path
        from pypdf import PdfReader

        results = {
            "artifacts": [],
            "pages": []
        }

        # A. OCR Processing
        # Output: R2_DOC_PAGES/[converted_pdfs]/{id}/{name}.pdf
        searchable_pdf = work_dir / f"{attachment_id}_searchable.pdf"
        
        try:
            logger.info("Running OCRmyPDF...")
            ocrmypdf.ocr(
                str(pdf_path),
                str(searchable_pdf),
                force_ocr=True,      # Force rasterization + OCR to ensure consistency
                output_type='pdf',
                sidecar=None,        # We'll extract text manually per page
                # deskew=True,       # Optional: deskew
                msg=False
            )
            
            # Upload Converted PDF
            pdf_key = f"converted_pdfs/{attachment_id}/{original_filename}.pdf" # Ensure extension?
             # If original didn't have .pdf, we add it. 
            if not pdf_key.lower().endswith('.pdf'):
                pdf_key += ".pdf"

            self._upload_file(searchable_pdf, self.doc_pages_bucket, pdf_key)
            results['artifacts'].append({ 
                "type": "SEARCHABLE_PDF", 
                "key": pdf_key,
                "bucket": self.doc_pages_bucket 
            })

        except Exception as e:
            logger.error(f"OCR failed: {e}")
            # Fallback? If OCR fails, we might abort or try to continue with original
            return results 

        # B. Page Processing Loop
        try:
            reader = PdfReader(str(searchable_pdf))
            num_pages = len(reader.pages)
            
            # Render TIFFs
            logger.info("Rendering TIFFs...")
            # pdf2image returns PIL images
            images = convert_from_path(str(searchable_pdf), dpi=300, fmt='tiff')

            from typing import Any, Dict
            for i in range(num_pages):
                page_num = i + 1
                page_data: Dict[str, Any] = {
                   "pageNumber": page_num
                }

                # 1. Extracted Text (Python)
                # Key: {id}/extracted_txt/pg_{num}.txt
                # Note: pdf_reader.pages[i].extract_text() gives us the text layer from OCRmyPDF
                text_content = reader.pages[i].extract_text() or ""
                
                txt_filename = f"pg_{page_num}.txt"
                txt_path = work_dir / f"extracted_{txt_filename}"
                with open(txt_path, "w") as f:
                    f.write(text_content)
                
                extract_key = f"{attachment_id}/extracted_txt/{txt_filename}"
                self._upload_file(txt_path, self.doc_pages_bucket, extract_key)
                page_data["extractedTextKey"] = extract_key

                # 2. OCR Text 
                # Key: {id}/ocr_txt/pg_{num}.txt
                # Since we forced OCR, the 'extracted text' IS the OCR text effectively.
                # However, the requirements distinguish them.
                # 'extracted_txt' = Standard python pipeline extraction from native file (before OCR?)
                # 'ocr_txt' = From Tesseract/EasyOCR (or the OCR layer we just made)
                # To be strictly compliant:
                # We could run tesseract on the TIFF image separately to get 'ocr_txt'.
                # Let's do that to have distinct 'vision' vs 'pdf' layers if needed.
                # OR, we treat the OCRmyPDF output as the 'ocr_txt'.
                # Let's use Tesseract on the image for 'ocr_txt' to be robust.
                
                import pytesseract
                # image is the PIL image from pdf2image
                ocr_text_content = pytesseract.image_to_string(images[i])
                
                ocr_filename = f"pg_{page_num}.txt"
                ocr_path = work_dir / f"ocr_{ocr_filename}"
                with open(ocr_path, "w") as f:
                    f.write(ocr_text_content)

                ocr_key = f"{attachment_id}/ocr_txt/{ocr_filename}"
                self._upload_file(ocr_path, self.doc_pages_bucket, ocr_key)
                page_data["ocrTextKey"] = ocr_key

                # 3. TIFF Image
                # Key: {id}/tiff_imgs/pg_{num}.tiff
                tiff_filename = f"pg_{page_num}.tiff"
                tiff_path = work_dir / tiff_filename
                
                # Save as TIFF
                images[i].save(tiff_path, compression="tiff_deflate") # or uncompressed
                
                tiff_key = f"{attachment_id}/tiff_imgs/{tiff_filename}"
                self._upload_file(tiff_path, self.doc_pages_bucket, tiff_key)
                page_data["tiffKey"] = tiff_key
                page_data["r2Key"] = tiff_key # Standard key for vision agent

                results['pages'].append(page_data)

        except Exception as e:
            logger.error(f"Page processing failed: {e}", exc_info=True)

        return results

    def _guess_mime(self, path: Path):
        import mimetypes
        type, _ = mimetypes.guess_type(path)
        return type or "application/octet-stream"

    def _extract_exif_metadata(self, path: Path):
        try:
            import subprocess
            # Use -json for proper parsing, -g for group names if needed (but -j handles flat fine usually)
            # -n for numerical values where appropriate
            result = subprocess.run(
                ["exiftool", "-j", "-n", str(path)],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return data[0] if data else {}
        except Exception:
            logger.warning("Exiftool not found or failed")
        return {}

    def _upload_file(self, path: Path, bucket: str, key: str):
        self.s3.upload_file(str(path), bucket, key)
        logger.info(f"Uploaded {key} to {bucket}")

    async def _trigger_workflow(self, payload: dict):
        """
        Trigger the Cloudflare Worker Workflow via REST API.
        """
        url = f"{HOST_API_URL}/api/workflow/trigger-forensic"
        headers = {
            "X-Worker-Api-Key": INTERNAL_SERVICE_KEY,
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient() as client:
            # Increase timeout for large payloads if necessary, though payload is mostly keys now
            response = await client.post(url, json=payload, headers=headers, timeout=30.0)
            try:
                response.raise_for_status()
                logger.info(f"Triggered workflow: {response.json()}")
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Workflow trigger failed: {e.response.text}")
                raise e

