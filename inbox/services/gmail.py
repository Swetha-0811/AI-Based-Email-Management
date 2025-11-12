import base64
import logging
import json
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from googleapiclient.errors import HttpError
from django.core.cache import cache

logger = logging.getLogger(__name__)

def build_flow(redirect_uri):
    """Build OAuth flow"""
    from google_auth_oauthlib.flow import Flow
    from django.conf import settings

    # Load client secrets
    client_config = {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": [redirect_uri]
        }
    }

    flow = Flow.from_client_config(
        client_config,
        scopes=[
            'openid',
            'https://www.googleapis.com/auth/userinfo.profile',
            'https://www.googleapis.com/auth/userinfo.email',
            'https://www.googleapis.com/auth/gmail.readonly',
            'https://www.googleapis.com/auth/gmail.send',
            'https://www.googleapis.com/auth/gmail.compose',
            'https://www.googleapis.com/auth/gmail.modify',
            'https://www.googleapis.com/auth/calendar.events'
        ],
        redirect_uri=redirect_uri
    )

    return flow

def get_gmail_service(user=None):
    """Get Gmail service with credentials and improved error handling"""
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from inbox.models import GmailCredentials

    try:
        # Get credentials from database
        if user and user.is_authenticated:
            creds_obj = GmailCredentials.objects.filter(user=user).first()
        else:
            # For anonymous users, get most recent credentials
            creds_obj = GmailCredentials.objects.filter(user=None).order_by('-updated_at').first()

        if not creds_obj:
            logger.warning("No Gmail credentials found in database")
            return None

        logger.info(f"Found Gmail credentials for user: {user.username if user else 'Anonymous'}")
        
        # Parse scopes properly
        scopes = creds_obj.scopes
        if isinstance(scopes, str):
            try:
                scopes = json.loads(scopes)
            except json.JSONDecodeError:
                scopes = scopes.split()
        
        # Log scopes for debugging
        logger.info(f"Using scopes: {scopes}")
        
        # Create credentials object
        creds = Credentials(
            token=creds_obj.token,
            refresh_token=creds_obj.refresh_token,
            token_uri=creds_obj.token_uri,
            client_id=creds_obj.client_id,
            client_secret=creds_obj.client_secret,
            scopes=scopes
        )

        # Check if token is expired and refresh if needed
        if creds.expired and creds.refresh_token:
            logger.info("Gmail token expired, refreshing...")
            creds.refresh(Request())
            
            # Update credentials in database
            creds_obj.token = creds.token
            creds_obj.save()
            logger.info("Gmail token refreshed successfully")

        # Build service
        service = build('gmail', 'v1', credentials=creds)
        
        # Test service by fetching user's profile
        try:
            profile = service.users().getProfile(userId='me').execute()
            logger.info(f"Successfully connected to Gmail API for user: {profile.get('emailAddress')}")
            
            # If we have an anonymous user with credentials, but user is now authenticated,
            # update credentials to link to the authenticated user
            if user and user.is_authenticated and not creds_obj.user:
                logger.info(f"Linking Gmail credentials to authenticated user: {user.username}")
                creds_obj.user = user
                creds_obj.save()
            
        except Exception as e:
            logger.error(f"Error testing Gmail service: {str(e)}")
            return None
        
        return service
    except Exception as e:
        logger.error(f"Error getting Gmail service: {str(e)}", exc_info=True)
        return None

def _save_creds_to_db(credentials, user=None):
    """Save credentials to database with proper scope handling"""
    from inbox.models import GmailCredentials

    try:
        if credentials:
            # Convert scopes list to a JSON string for proper storage
            scopes = credentials.scopes
            if isinstance(scopes, list):
                scopes_str = json.dumps(scopes)
            else:
                scopes_str = scopes

            # If user is authenticated, save with user
            if user and user.is_authenticated:
                GmailCredentials.objects.update_or_create(
                    user=user,
                    defaults={
                        'token': credentials.token,
                        'refresh_token': credentials.refresh_token,
                        'token_uri': credentials.token_uri,
                        'client_id': credentials.client_id,
                        'client_secret': credentials.client_secret,
                        'scopes': scopes_str,  # Save as JSON string
                    }
                )
                logger.info(f"Saved credentials for authenticated user: {user.username}")
            else:
                # For anonymous users
                GmailCredentials.objects.update_or_create(
                    user=None,
                    defaults={
                        'token': credentials.token,
                        'refresh_token': credentials.refresh_token,
                        'token_uri': credentials.token_uri,
                        'client_id': credentials.client_id,
                        'client_secret': credentials.client_secret,
                        'scopes': scopes_str,
                    }
                )
                logger.info("Saved credentials for anonymous user")
        else:
            # Remove credentials
            if user and user.is_authenticated:
                GmailCredentials.objects.filter(user=user).delete()
                logger.info(f"Removed credentials for authenticated user: {user.username}")
            else:
                GmailCredentials.objects.filter(user=None).delete()
                logger.info("Removed credentials for anonymous user")
    except Exception as e:
        logger.error(f"Error saving credentials to database: {str(e)}", exc_info=True)
        raise

def _load_creds_from_db(user=None):
    """Load credentials from database with proper scope parsing"""
    from google.oauth2.credentials import Credentials
    from inbox.models import GmailCredentials

    try:
        creds_obj = None
        
        if user and user.is_authenticated:
            creds_obj = GmailCredentials.objects.filter(user=user).first()
            logger.info(f"Loading credentials for authenticated user: {user.username}")
        else:
            # For anonymous users, get most recent anonymous credential
            creds_obj = GmailCredentials.objects.filter(user=None).order_by('-updated_at').first()
            logger.info("Loading credentials for anonymous user")
        
        if not creds_obj:
            logger.warning("No credentials found in database")
            return None

        # Parse scopes properly
        scopes = creds_obj.scopes
        if isinstance(scopes, str):
            try:
                scopes = json.loads(scopes)
            except json.JSONDecodeError:
                scopes = scopes.split()
        
        # Log scopes for debugging
        logger.info(f"Loaded scopes: {scopes}")

        return Credentials(
            token=creds_obj.token,
            refresh_token=creds_obj.refresh_token,
            token_uri=creds_obj.token_uri,
            client_id=creds_obj.client_id,
            client_secret=creds_obj.client_secret,
            scopes=scopes
        )
    except Exception as e:
        logger.error(f"Error loading credentials from database: {str(e)}", exc_info=True)
        return None

def create_message(to, subject, message_text):
    """Create a message for an email."""
    message = MIMEText(message_text)
    message['to'] = to
    message['subject'] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return {'raw': raw}

def create_gmail_draft(service, to, subject, body):
    """Create a draft email in Gmail"""
    try:
        # Create a simple text message
        from email.mime.text import MIMEText
        
        message = MIMEText(body)
        message['to'] = to
        message['subject'] = subject
        
        # Convert to base64 URL-safe string
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        
        # Log the raw message for debugging
        logger.info(f"Creating draft with raw message length: {len(raw)}")
        
        # Create draft request body
        draft_request = {
            'message': {
                'raw': raw
            }
        }
        
        # Create the draft
        draft = service.users().drafts().create(userId='me', body=draft_request).execute()
        logger.info(f"Draft created successfully with ID: {draft['id']}")
        return draft['id']
    except HttpError as e:
        logger.error(f"HTTP error creating draft: {str(e)}", exc_info=True)
        # Return more detailed error information
        error_details = {
            'code': e.resp.status,
            'reason': e.reason,
            'details': str(e)
        }
        raise Exception(f"Gmail API error: {json.dumps(error_details)}")
    except Exception as e:
        logger.error(f"Error creating draft: {str(e)}", exc_info=True)
        raise

def fetch_unread(service, max_results=10):
    """Fetch unread emails from Gmail"""
    try:
        cache_key = f"gmail_unread_{max_results}"
        cached_emails = cache.get(cache_key)
        if cached_emails:
            logger.info(f"Returning cached unread emails: {len(cached_emails)} emails")
            return cached_emails

        logger.info(f"Fetching unread emails from Gmail API with max_results={max_results}")
        
        # Use only UNREAD label instead of multiple labels
        response = service.users().messages().list(
            userId='me',
            labelIds=['UNREAD'],
            maxResults=max_results
        ).execute()
        
        messages = response.get('messages', [])
        logger.info(f"Found {len(messages)} unread messages")
        
        emails = []

        for message in messages:
            try:
                # Get full message
                msg = service.users().messages().get(userId='me', id=message['id']).execute()
                headers = msg['payload']['headers']
                
                # Extract headers with proper processing
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '(no subject)')
                from_raw = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
                to_raw = next((h['value'] for h in headers if h['name'] == 'To'), '')
                date = next((h['value'] for h in headers if h['name'] == 'Date'), '')
                snippet = msg.get('snippet', '')
                
                # Extract body text
                body_text = ''
                if 'parts' in msg['payload']:
                    for part in msg['payload']['parts']:
                        if part['mimeType'] == 'text/plain':
                            body_data = part['body'].get('data', '')
                            if body_data:
                                body_text = base64.urlsafe_b64decode(body_data).decode('utf-8')
                            break
                else:
                    if 'body' in msg['payload'] and 'data' in msg['payload']['body']:
                        body_data = msg['payload']['body'].get('data', '')
                        if body_data:
                            body_text = base64.urlsafe_b64decode(body_data).decode('utf-8')

                emails.append({
                    'id': message['id'],
                    'threadId': msg.get('threadId', ''),
                    'subject': subject,
                    'from': from_raw,  # Keep raw format for serializer processing
                    'to': to_raw,      # Keep raw format for serializer processing
                    'date': date,
                    'snippet': snippet,
                    'body_text': body_text
                })
            except Exception as e:
                logger.error(f"Error processing message {message['id']}: {str(e)}", exc_info=True)
                continue

        logger.info(f"Successfully processed {len(emails)} unread emails")
        cache.set(cache_key, emails, 300)  # Cache for 5 minutes
        return emails
    except Exception as e:
        logger.error(f"Error fetching unread emails: {str(e)}", exc_info=True)
        return []

def fetch_drafts(service, max_results=10):
    """Fetch draft emails from Gmail with improved error handling"""
    try:
        cache_key = f"gmail_drafts_{max_results}"
        cached_drafts = cache.get(cache_key)
        if cached_drafts:
            logger.info(f"Returning cached drafts: {len(cached_drafts)} drafts")
            return cached_drafts

        logger.info(f"Fetching drafts from Gmail API with max_results={max_results}")
        
        # Get draft list with proper error handling
        try:
            drafts_response = service.users().drafts().list(userId='me', maxResults=max_results).execute()
            logger.info(f"Raw drafts response: {drafts_response}")
        except Exception as api_error:
            logger.error(f"Error fetching drafts list: {str(api_error)}")
            return []
        
        draft_ids = [draft['id'] for draft in drafts_response.get('drafts', [])]
        logger.info(f"Found {len(draft_ids)} draft IDs from Gmail API")

        if not draft_ids:
            logger.warning("No draft IDs found in API response")
            return []

        drafts = []
        for i, draft_id in enumerate(draft_ids):
            try:
                logger.debug(f"Fetching draft details for ID: {draft_id}")
                draft = service.users().drafts().get(userId='me', id=draft_id).execute()
                message = draft['message']
                headers = message.get('payload', {}).get('headers', [])
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '(no subject)')
                to_raw = next((h['value'] for h in headers if h['name'] == 'To'), 'Unknown')
                date = next((h['value'] for h in headers if h['name'] == 'Date'), '')
                snippet = message.get('snippet', '')

                drafts.append({
                    'id': draft_id,
                    'subject': subject,
                    'from': to_raw,  # Keep raw format for serializer processing
                    'date': date,
                    'snippet': snippet,
                    'is_draft': True
                })
                logger.debug(f"Successfully processed draft {i+1}/{len(draft_ids)}: {subject[:30]}...")
                
            except Exception as draft_error:
                logger.error(f"Error processing draft {draft_id}: {str(draft_error)}")
                continue

        logger.info(f"Successfully processed {len(drafts)}/{len(draft_ids)} drafts")
        cache.set(cache_key, drafts, 300)  # Cache for 5 minutes
        return drafts
        
    except Exception as e:
        logger.error(f"Critical error in fetch_drafts: {str(e)}", exc_info=True)
        return []

def get_draft_details(service, draft_id):
    """Get full details of a draft"""
    try:
        draft = service.users().drafts().get(userId='me', id=draft_id).execute()
        message = draft['message']
        headers = message.get('payload', {}).get('headers', [])
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '(no subject)')
        to_raw = next((h['value'] for h in headers if h['name'] == 'To'), 'Unknown')
        from_raw = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
        date = next((h['value'] for h in headers if h['name'] == 'Date'), '')

        body = ''
        if 'parts' in message['payload']:
            for part in message['payload']['parts']:
                if part['mimeType'] == 'text/plain':
                    body_data = part['body'].get('data', '')
                    if body_data:
                        body = base64.urlsafe_b64decode(body_data).decode('utf-8')
                    break
        else:
            if 'body' in message['payload'] and 'data' in message['payload']['body']:
                body_data = message['payload']['body'].get('data', '')
                if body_data:
                    body = base64.urlsafe_b64decode(body_data).decode('utf-8')

        return {
            'id': draft_id,
            'subject': subject,
            'to': to_raw,  # Keep raw format for serializer processing
            'from': from_raw,  # Keep raw format for serializer processing
            'date': date,
            'body': body,
            'snippet': message.get('snippet', '')
        }
    except Exception as e:
        logger.error(f"Error getting draft details: {str(e)}", exc_info=True)
        return None
    
def delete_draft(service, draft_id):
    """Delete a draft"""
    try:
        service.users().drafts().delete(userId='me', id=draft_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error deleting draft: {str(e)}", exc_info=True)
        return False

def update_draft(service, draft_id, to, subject, body):
    """Update an existing draft"""
    try:
        # Create new message with updated fields
        message = create_message(to, subject, body)
        
        # Update the draft
        updated_draft = service.users().drafts().update(
            userId='me',
            id=draft_id,
            body=message
        ).execute()
        
        return updated_draft.get('id')
    except HttpError as e:
        logger.error(f"HTTP error updating draft: {str(e)}", exc_info=True)
        # Return more detailed error information
        error_details = {
            'code': e.resp.status,
            'reason': e.reason,
            'details': str(e)
        }
        raise Exception(f"Gmail API error: {json.dumps(error_details)}")
    except Exception as e:
        logger.error(f"Error updating draft: {str(e)}", exc_info=True)
        return None

def mark_as_read(service, message_id):
    """Mark an email as read"""
    try:
        service.users().messages().modify(
            userId='me',
            id=message_id,
            body={'removeLabelIds': ['UNREAD']}
        ).execute()
        return True
    except HttpError as e:
        if e.resp.status == 404:
            logger.warning(f"Email not found: {message_id}")
        else:
            logger.error(f"Error marking email as read: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Error marking email as read: {str(e)}", exc_info=True)
        return False

def is_email_available(service, message_id):
    """Check if an email is available (not deleted)"""
    try:
        service.users().messages().get(userId='me', id=message_id).execute()
        return True
    except HttpError as e:
        if e.resp.status == 404:
            return False
        raise

def get_email_details(service, message_id):
    """Get full details of an email"""
    try:
        message = service.users().messages().get(userId='me', id=message_id).execute()
        headers = message['payload']['headers']
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '(no subject)')
        from_raw = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
        to_raw = next((h['value'] for h in headers if h['name'] == 'To'), '')
        cc_raw = next((h['value'] for h in headers if h['name'] == 'Cc'), '')
        date = next((h['value'] for h in headers if h['name'] == 'Date'), '')

        body_text = ''
        body_html = ''

        if 'parts' in message['payload']:
            for part in message['payload']['parts']:
                if part['mimeType'] == 'text/plain':
                    body_data = part['body'].get('data', '')
                    if body_data:
                        body_text = base64.urlsafe_b64decode(body_data).decode('utf-8')
                elif part['mimeType'] == 'text/html':
                    body_data = part['body'].get('data', '')
                    if body_data:
                        body_html = base64.urlsafe_b64decode(body_data).decode('utf-8')
        else:
            if 'body' in message['payload']:
                if message['payload']['mimeType'] == 'text/plain':
                    body_data = message['payload']['body'].get('data', '')
                    if body_data:
                        body_text = base64.urlsafe_b64decode(body_data).decode('utf-8')
                elif message['payload']['mimeType'] == 'text/html':
                    body_data = message['payload']['body'].get('data', '')
                    if body_data:
                        body_html = base64.urlsafe_b64decode(body_data).decode('utf-8')

        return {
            'id': message_id,
            'subject': subject,
            'from': from_raw,  # Keep raw format for serializer processing
            'to': to_raw,      # Keep raw format for serializer processing
            'cc': cc_raw,      # Keep raw format for serializer processing
            'date': date,
            'body_text': body_text,
            'body_html': body_html,
            'snippet': message.get('snippet', '')
        }
    except Exception as e:
        logger.error(f"Error getting email details: {str(e)}", exc_info=True)
        return None

# Helper function to extract email address from a string
def extract_email_address(email_str):
    """Extract email address from a string that might contain 'Name <email>' format"""
    if not email_str:
        return ''
    
    # If it's already just an email address, return it
    if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email_str):
        return email_str
    
    # Extract email from 'Name <email>' format
    email_match = re.search(r'<([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})>', email_str)
    if email_match:
        return email_match.group(1)
    
    # If no angle brackets, try to find email address in string
    email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', email_str)
    if email_match:
        return email_match.group(1)
    
    # Return original string if no email found
    return email_str

# Helper function to format email address
def format_email_address(name, email):
    """Format email address as 'Name <email>' or just email if name is not available"""
    if name and email:
        return f"{name} <{email}>"
    elif email:
        return email
    elif name:
        return name
    else:
        return 'Unknown'
    
def delete_email(service, message_id):
    """Delete an email by moving it to trash"""
    try:
        service.users().messages().trash(
            userId='me',
            id=message_id
        ).execute()
        return True
    except Exception as e:
        logger.error(f"Error deleting email {message_id}: {str(e)}")
        return False