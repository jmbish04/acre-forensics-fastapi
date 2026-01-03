import asyncio
import base64
import os
import pickle
from functools import partial
from typing import Dict, List, Optional, Tuple

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class GmailCollector:
    """
    Gmail Collector that supports both OAuth (User) and Service Account (Server-to-Server) auth.
    """
    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

    def __init__(self, service_account_json: Optional[str] = None, logger=None):
        self.logger = logger
        self.service = None
        self.creds = None

        # A. Try Service Account (Preferred for Automation)
        if service_account_json:
            try:
                # 1. Load basic credentials
                if service_account_json.startswith('{'):
                    import json
                    info = json.loads(service_account_json)
                    self.creds = service_account.Credentials.from_service_account_info(
                        info, scopes=self.SCOPES
                    )
                else:
                    self.creds = service_account.Credentials.from_service_account_file(
                        service_account_json, scopes=self.SCOPES
                    )
                
                # 2. Apply Domain-Wide Delegation (Impersonation)
                target_user = os.environ.get("GMAIL_IMPERSONATE_USER")
                if target_user:
                    self.creds = self.creds.with_subject(target_user)
                    self._log(f"✅ Enabled Impersonation for: {target_user}")
                else:
                    self._log("⚠️ Using Service Account without impersonation", level="warn")

            except Exception as e:
                self._log(f"Service Account Auth Failed: {e}", level="error")
                return

        # B. Fallback to Local User OAuth
        elif os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                self.creds = pickle.load(token)

        # Build Service
        if self.creds:
            self.service = build('gmail', 'v1', credentials=self.creds)

    def _log(self, msg, level="info"):
        if self.logger:
            getattr(self.logger, level)("GmailCollector", msg)
        else:
            prefix = "[ERROR]" if level == "error" else "[INFO]"
            print(f"{prefix} GmailCollector: {msg}")

    def list_message_ids(self, query: str = "after:2024/01/01") -> List[str]:
        """Returns a list of message IDs matching the query."""
        if not self.service:
            self._log("No service initialized.", level="error")
            return []
            
        try:
            self._log(f"Listing messages for: {query}")
            response = self.service.users().messages().list(userId='me', q=query, maxResults=500).execute()
            messages = []
            if 'messages' in response:
                messages.extend(response['messages'])

            while 'nextPageToken' in response:
                page_token = response['nextPageToken']
                response = self.service.users().messages().list(userId='me', q=query, pageToken=page_token).execute()
                if 'messages' in response:
                    messages.extend(response['messages'])
            
            return [m['id'] for m in messages]
        except Exception as e:
            self._log(f"List execution failed: {e}", level="error")
            return []

    async def fetch_messages(self, message_ids: List[str]):
        """
        Async generator that yields parsed message details.
        Uses run_in_executor to prevent blocking the FastAPI event loop.
        """
        loop = asyncio.get_running_loop()

        for msg_id in message_ids:
            try:
                # partial allows us to pass arguments to the synchronous function
                func = partial(self._fetch_single_message_sync, msg_id)
                # Run blocking API call in thread pool
                email_data = await loop.run_in_executor(None, func)
                
                if email_data:
                    yield email_data
                    
            except Exception as e:
                self._log(f"Error fetching {msg_id}: {e}", level="error")

    def _fetch_single_message_sync(self, message_id: str) -> Optional[Dict]:
        """Synchronous helper to fetch and parse a single message."""
        try:
            if not self.service:
                return None
            # Fetch full format to get snippet and payload headers
            msg = self.service.users().messages().get(userId='me', id=message_id, format='full').execute()
            
            payload = msg.get('payload', {})
            headers_list = payload.get('headers', [])
            
            # Helper to extract header value
            def get_header(name):
                return next((h['value'] for h in headers_list if h['name'].lower() == name.lower()), None)

            # Simple Body Extraction (Best Effort)
            body_plain = ""
            body_html = ""
            
            if 'parts' in payload:
                for part in payload['parts']:
                    if part['mimeType'] == 'text/plain':
                        data = part['body'].get('data')
                        if data:
                            body_plain = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                    elif part['mimeType'] == 'text/html':
                        data = part['body'].get('data')
                        if data:
                            body_html = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
            else:
                # No parts, try body directly
                data = payload.get('body', {}).get('data')
                if data:
                    body_plain = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')

            return {
                "messageId": msg.get("id"),
                "threadId": msg.get("threadId"),
                "headers": {h['name']: h['value'] for h in headers_list},
                "fromAddress": get_header("From"),
                "toAddress": get_header("To"),
                "subject": get_header("Subject"),
                "sentDate": get_header("Date"),
                "bodyPlain": body_plain,
                "bodyHtml": body_html
            }
        except HttpError as error:
            self._log(f"API Error fetching {message_id}: {error}", level="error")
            return None
        except Exception as e:
            self._log(f"Parse Error fetching {message_id}: {e}", level="error")
            return None

    def fetch_raw_message(self, message_id: str) -> Optional[Tuple[bytes, Dict]]:
        """Fetches raw EML bytes."""
        if not self.service:
            return None
        try:
            message = self.service.users().messages().get(userId='me', id=message_id, format='raw').execute()
            msg_str = base64.urlsafe_b64decode(message['raw'].encode('ASCII'))
            return msg_str, message
        except HttpError as error:
            self._log(f"Error fetching raw {message_id}: {error}", level="error")
            return None

    async def sync(self, query: str = "after:2024/01/01", engagement_id: str = "default"):
        """Syncs messages from Gmail to D1."""
        self._log(f"Starting Sync: {query} for {engagement_id}")
        
        # dynamic import to avoid circular dependency
        from .remote_worker_api import RemoteWorkerClient
        client = RemoteWorkerClient()

        ids = self.list_message_ids(query)
        self._log(f"Found {len(ids)} messages.")
        
        async for msg in self.fetch_messages(ids):
            # Transform to DB schema format
            db_msg = {
                "messageId": msg["messageId"],
                "threadId": msg.get("threadId"),
                "engagementId": engagement_id,
                "fromAddress": msg.get("fromAddress"),
                "toAddresses": msg.get("toAddress"),
                "subject": msg.get("subject"),
                "bodyPlain": msg.get("bodyPlain"),
                "bodyHtml": msg.get("bodyHtml"),
                "sentDate": msg.get("sentDate"),
                "status": "PENDING",
                # "headers": msg.get("headers") 
            }
            try:
                client.create_message(db_msg)
                self._log(f"Ingested {msg['messageId']}")
            except Exception as e:
                self._log(f"Failed to ingest {msg['messageId']}: {e}", level="error")