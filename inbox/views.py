# inbox/views.py

import os
import json
import logging
import base64
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth import login
from django.urls import resolve, reverse
from django.contrib import messages
from django.core.cache import cache
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.core.paginator import Paginator, EmptyPage
from .serializers import EmailSerializer, EmailTemplateSerializer, ReminderSerializer, ScheduledEmailSerializer
from .services import gemini
from .services.gmail import (
    build_flow, get_gmail_service, create_gmail_draft,
    _save_creds_to_db, _load_creds_from_db, fetch_unread, mark_as_read,
    fetch_drafts, get_draft_details, delete_draft, update_draft, get_email_details
)
from .services.workflow import (
    ReminderService, SchedulingService, 
    CategorizationService, PriorityScoringService
)
from .models import GeneratedDraft, ImportantEmail, UserSettings, EmailTemplate, Reminder, ScheduledEmail, EmailCategory, EmailPriority

# Logging
logger = logging.getLogger(__name__)

########################################
# Helper Functions
########################################
def credentials_to_dict(credentials):
    """Convert credentials object to dictionary"""
    return {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes,
    }

def is_authenticated(user=None):
    """Check if user has valid Gmail credentials"""
    try:
        # Try to get service - if it works, we're authenticated
        service = get_gmail_service(user=user)
        return service is not None
    except:
        return False

########################################
# Test View
########################################
def test_view(request):
    """Simple test view to check if the basic setup works"""
    return HttpResponse("Test view works!")

########################################
# Debug URLs
########################################
def debug_urls(request):
    path_info = request.path_info
    try:
        resolver_match = resolve(path_info)
        return JsonResponse({
            "status": "matched",
            "view_name": resolver_match.view_name,
            "app_name": resolver_match.app_name,
            "namespace": resolver_match.namespace,
            "url_name": resolver_match.url_name,
            "function": str(resolver_match.func)
        })
    except Exception as e:
        return JsonResponse({
            "status": "not matched",
            "error": str(e),
            "path": path_info
        })

########################################
# Home page
########################################
def home_view(request):
    try:
        # Check if we have a session variable indicating authentication
        gmail_authenticated = request.session.get('gmail_authenticated', False)
        
        # Try to get the service with better error handling
        service = None
        authed = False
        try:
            service = get_gmail_service(user=request.user if request.user.is_authenticated else None)
            authed = service is not None
        except Exception as e:
            logger.error(f"Error getting Gmail service in home_view: {str(e)}", exc_info=True)
            authed = False
        
        # If we have a session variable but no service, clear the session variable
        if gmail_authenticated and not authed:
            request.session['gmail_authenticated'] = False
        
        return render(request, "inbox/home.html", {
            "authed": authed,
            "gmail_authenticated": gmail_authenticated,
            "user": request.user if request.user.is_authenticated else None
        })
    except Exception as e:
        logger.error(f"Error in home_view: {str(e)}", exc_info=True)
        return HttpResponse(f"Error loading home page: {str(e)}", status=500)

########################################
# OAuth status
########################################
def auth_status(request):
    service = get_gmail_service(user=request.user if request.user.is_authenticated else None)
    
    # Test the service by trying to fetch the user's profile
    profile = None
    if service:
        try:
            profile = service.users().getProfile(userId="me").execute()
            logger.info(f"Successfully fetched Gmail profile: {profile.get('emailAddress')}")
        except Exception as e:
            logger.error(f"Error fetching Gmail profile: {str(e)}", exc_info=True)
            service = None
    
    return JsonResponse({
        "authenticated": service is not None,
        "django_authenticated": request.user.is_authenticated,
        "email": request.user.email if request.user.is_authenticated else None,
        "username": request.user.username if request.user.is_authenticated else None,
        "gmail_profile": profile,
    })
    
########################################
# OAuth start (Updated to force account selection)
########################################

def oauth_start(request):
    try:
        # Clear any existing OAuth state to avoid conflicts
        if 'oauth_state' in request.session:
            del request.session['oauth_state']
        
        redirect_uri = request.build_absolute_uri("/oauth/callback/")
        logger.info(f"OAuth start with redirect_uri: {redirect_uri}")
        
        flow = build_flow(redirect_uri)
        auth_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent select_account",
        )
        request.session["oauth_state"] = state
        logger.info(f"OAuth redirecting to: {auth_url}")
        return redirect(auth_url)
        
    except Exception as e:
        logger.error(f"OAuth start error: {str(e)}", exc_info=True)
        return HttpResponseBadRequest(f"OAuth initialization failed: {str(e)}")

########################################
# OAuth callback (FIXED with Django authentication)
########################################
def oauth_callback(request):
    try:
        expected_state = request.session.get("oauth_state")
        returned_state = request.GET.get("state")
        
        if not expected_state or expected_state != returned_state:
            logger.error(f"State mismatch. Expected: {expected_state}, Got: {returned_state}")
            return HttpResponseBadRequest("Invalid OAuth state. Please try again.")
            
        redirect_uri = request.build_absolute_uri("/oauth/callback/")
        logger.info(f"OAuth callback with redirect_uri: {redirect_uri}")
        
        flow = build_flow(redirect_uri)
        
        # Handle scope changes by updating the flow's scopes with the returned scopes
        returned_scopes = request.GET.get("scope", "").split()
        if returned_scopes:
            flow.scopes = returned_scopes
        
        flow.fetch_token(authorization_response=request.build_absolute_uri())
        creds = flow.credentials
        
        # Get user info from Google
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests
        
        id_info = id_token.verify_oauth2_token(
            creds.id_token,
            request=google_requests.Request(),
            audience=creds.client_id
        )
        
        email = id_info.get("email")
        name = id_info.get("name", "")
        
        # Get or create Django user
        try:
            user = User.objects.get(email=email)
            # Update user info if needed
            if not user.first_name and name:
                name_parts = name.split()
                if len(name_parts) >= 1:
                    user.first_name = name_parts[0]
                if len(name_parts) >= 2:
                    user.last_name = " ".join(name_parts[1:])
                user.save()
            logger.info(f"Existing user logged in: {user.username}")
        except User.DoesNotExist:
            # Create new user
            username = email.split('@')[0]
            # Ensure username is unique
            base_username = username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1
                
            user = User.objects.create_user(
                username=username,
                email=email,
                first_name=name.split()[0] if name else "",
                last_name=" ".join(name.split()[1:]) if name and " " in name else ""
            )
            user.save()
            logger.info(f"New user created: {user.username}")
        
        # FIXED: Specify the authentication backend when logging in
        from django.contrib.auth import login
        from django.contrib.auth.backends import ModelBackend
        
        # Log in the user with explicit backend
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        logger.info(f"User {user.username} logged in successfully")
        
        # Ensure we have a session
        if not request.session.session_key:
            request.session.create()
        
        # Save credentials to database with proper user handling
        _save_creds_to_db(creds, user=user)
        
        # Log successful save
        logger.info(f"OAuth successful. Credentials saved to database for user: {user.username}")
        
        # Clear OAuth state
        request.session.pop("oauth_state", None)
        
        # Set session variable to indicate authentication
        request.session['gmail_authenticated'] = True
        
        return redirect("home")
        
    except Exception as e:
        logger.error(f"OAuth callback error: {str(e)}", exc_info=True)
        error_message = f"OAuth authentication failed: {str(e)}"
        
        # Check for common OAuth errors
        if "invalid_grant" in str(e):
            error_message += ". This may be due to an expired or invalid authorization code. Please try authenticating again."
        elif "redirect_uri_mismatch" in str(e):
            error_message += ". Redirect URI mismatch. Check your Google Cloud Console configuration."
        elif "access_denied" in str(e):
            error_message = "Access denied. This application is in testing mode and your email is not registered as a test user. Please contact the administrator to add your email to the test users list."
        
        return HttpResponseBadRequest(error_message)

########################################
# API: unread emails with pagination
########################################
@api_view(['GET'])
def unread_emails_view(request):
    page_number = request.GET.get('page', 1)
    per_page = request.GET.get('per_page', 10)  # Allow configurable items per page
    
    try:
        page_number = int(page_number)
        if page_number < 1:
            page_number = 1
    except ValueError:
        page_number = 1
        
    try:
        per_page = int(per_page)
        if per_page < 1:
            per_page = 10
        if per_page > 50:  # Limit max items per page
            per_page = 50
    except ValueError:
        per_page = 10
        
    try:
        user = request.user if request.user.is_authenticated else None
        service = get_gmail_service(user=user)
        
        if not service:
            logger.warning("Failed to get Gmail service - user not authenticated or no valid credentials")
            return Response({
                'ok': False, 
                'error': 'Authentication required. Please connect your Gmail account.',
                'auth_required': True
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        logger.info(f"Fetching unread emails for user: {user if user else 'anonymous'}")
        
        # Use the fetch_unread from services.gmail
        emails = fetch_unread(service, max_results=100)  # Fetch more emails for pagination
        
        if not emails:
            logger.warning("No unread emails found")
            return Response({'ok': True, 'emails': [], 'total_pages': 0, 'current_page': 1})
        
        # Add important status to each email
        if user and user.is_authenticated:
            # FIXED: Use email_id instead of message_id
            important_email_ids = ImportantEmail.objects.filter(user=user).values_list('email_id', flat=True)
            for email in emails:
                email['is_important'] = email['id'] in important_email_ids                
                # Add category and priority information
                try:
                    category = CategorizationService.get_email_category(user, email['id'])
                    if category:
                        email['category'] = category.name  # FIXED: Use .name instead of .category
                except Exception as e:
                    logger.warning(f"Error getting category for email {email['id']}: {str(e)}")
                
                try:
                    priority = PriorityScoringService.get_email_priority(user, email['id'])
                    if priority:
                        email['priority'] = priority.priority
                except Exception as e:
                    # Check if the error is due to missing table
                    if "does not exist" in str(e):
                        logger.warning(f"EmailPriority table does not exist. Skipping priority for email {email['id']}")
                    else:
                        logger.warning(f"Error getting priority for email {email['id']}: {str(e)}")
        
        paginator = Paginator(emails, per_page)
        try:
            page_obj = paginator.page(page_number)
        except EmptyPage:
            logger.warning(f"Requested page {page_number} out of range. Returning last page.")
            page_obj = paginator.page(paginator.num_pages)
        
        serializer = EmailSerializer(page_obj.object_list, many=True, context={'user': user})
        return Response({
            'ok': True,
            'emails': serializer.data,
            'total_pages': paginator.num_pages,
            'current_page': page_obj.number,
            'per_page': per_page,
            'total_emails': len(emails),
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
        })
    except Exception as e:
        logger.error(f"Error in unread_emails_view: {str(e)}", exc_info=True)
        error_msg = "Failed to fetch emails"
        
        # Provide more specific error messages
        if "rateLimitExceeded" in str(e):
            error_msg = "Gmail API rate limit exceeded. Please try again later."
        elif "invalid_grant" in str(e):
            error_msg = "Authentication expired. Please reconnect your Gmail account."
        elif "does not exist" in str(e):
            error_msg = "Database tables not created. Please run migrations."
        
        return Response({
            'ok': False, 
            'error': error_msg,
            'auth_required': "invalid_grant" in str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

########################################
# API: drafts with pagination
########################################

@api_view(['GET'])
def drafts_view(request):
    page_number = request.GET.get('page', 1)
    per_page = request.GET.get('per_page', 10)
    refresh = request.GET.get('refresh', 'false').lower() == 'true'  # New refresh parameter
    
    try:
        page_number = int(page_number)
        if page_number < 1:
            page_number = 1
    except ValueError:
        page_number = 1
        
    try:
        per_page = int(per_page)
        if per_page < 1:
            per_page = 10
        if per_page > 50:
            per_page = 50
    except ValueError:
        per_page = 10
        
    try:
        user = request.user if request.user.is_authenticated else None
        service = get_gmail_service(user=user)
        
        if not service:
            return Response({
                'ok': False, 
                'error': 'Authentication required. Please connect your Gmail account.',
                'auth_required': True
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Get authenticated email for verification
        try:
            profile = service.users().getProfile(userId='me').execute()
            authenticated_email = profile.get('emailAddress')
            logger.info(f"Fetching drafts for authenticated Gmail account: {authenticated_email}")
        except Exception as e:
            logger.error(f"Error getting Gmail profile: {str(e)}")
            authenticated_email = "Unknown"
        
        # Clear cache if refresh requested
        if refresh:
            cache_key = f"gmail_drafts_{per_page}"
            cache.delete(cache_key)
            logger.info(f"Cleared drafts cache on refresh request")
        
        # Fetch drafts from Gmail
        drafts = fetch_drafts(service, max_results=100)
        
        if not drafts:
            logger.warning("No drafts returned from fetch_drafts")
            return Response({
                'ok': True, 
                'drafts': [], 
                'total_pages': 0, 
                'current_page': 1,
                'authenticated_email': authenticated_email,
                'debug_info': "No drafts found. Check logs for details."
            })
        
        # Use DraftSerializer for drafts
        from .serializers import DraftSerializer
        paginator = Paginator(drafts, per_page)
        try:
            page_obj = paginator.page(page_number)
        except EmptyPage:
            logger.warning(f"Requested page {page_number} out of range. Returning last page.")
            page_obj = paginator.page(paginator.num_pages)
        
        serializer = DraftSerializer(page_obj.object_list, many=True)
        return Response({
            'ok': True,
            'drafts': serializer.data,
            'total_pages': paginator.num_pages,
            'current_page': page_obj.number,
            'per_page': per_page,
            'total_drafts': len(drafts),
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
            'authenticated_email': authenticated_email
        })
    except Exception as e:
        logger.error(f"Error in drafts_view: {str(e)}", exc_info=True)
        error_msg = "Failed to fetch drafts"
        
        if "rateLimitExceeded" in str(e):
            error_msg = "Gmail API rate limit exceeded. Please try again later."
        elif "invalid_grant" in str(e):
            error_msg = "Authentication expired. Please reconnect your Gmail account."
        
        return Response({
            'ok': False, 
            'error': error_msg,
            'auth_required': "invalid_grant" in str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
             
@api_view(['GET'])
def debug_drafts_view(request):
    """Debug view to test draft fetching"""
    try:
        user = request.user if request.user.is_authenticated else None
        service = get_gmail_service(user=user)
        
        if not service:
            return Response({'error': 'No Gmail service available'}, status=400)
        
        # Test 1: Get profile
        try:
            profile = service.users().getProfile(userId='me').execute()
            profile_info = {
                'emailAddress': profile.get('emailAddress'),
                'historyId': profile.get('historyId'),
                'messagesTotal': profile.get('messagesTotal'),
                'threadsTotal': profile.get('threadsTotal')
            }
        except Exception as e:
            profile_info = {'error': str(e)}
        
        # Test 2: List drafts
        try:
            drafts_list = service.users().drafts().list(userId='me', maxResults=5).execute()
            draft_ids = [draft['id'] for draft in drafts_list.get('drafts', [])]
        except Exception as e:
            drafts_list = {'error': str(e)}
            draft_ids = []
        
        # Test 3: Get first draft details
        draft_details = None
        if draft_ids:
            try:
                draft_details = service.users().drafts().get(userId='me', id=draft_ids[0]).execute()
            except Exception as e:
                draft_details = {'error': str(e)}
        
        return Response({
            'profile': profile_info,
            'drafts_list': drafts_list,
            'draft_ids': draft_ids,
            'draft_details': draft_details
        })
    except Exception as e:
        return Response({'error': str(e)}, status=500)

########################################
# API: generated drafts (FIXED)
########################################
@api_view(['GET'])
def generated_drafts_view(request):
    """Get all generated drafts for the current user"""
    try:
        if not request.user.is_authenticated:
            return Response({'ok': False, 'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
            
        drafts = GeneratedDraft.objects.filter(user=request.user, is_sent=False).order_by('-created_at')
        
        draft_data = []
        for draft in drafts:
            draft_data.append({
                'id': draft.id,
                'subject': draft.subject,
                'recipient': draft.recipient,
                'reply_text': draft.reply_text,
                'created_at': draft.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'original_email_id': draft.original_email_id
            })
            
        logger.info(f"Returning {len(draft_data)} generated drafts for user {request.user.username}")
        return Response({'ok': True, 'drafts': draft_data})
    except Exception as e:
        logger.error(f"Error fetching generated drafts: {str(e)}", exc_info=True)
        return Response({'ok': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

########################################
# API: Debug generated drafts database (NEW)
########################################
@api_view(['GET'])
def debug_drafts_db_view(request):
    """Debug view to check GeneratedDraft database entries"""
    try:
        if not request.user.is_authenticated:
            return Response({'error': 'Authentication required'}, status=401)
            
        # Get all drafts for this user
        drafts = GeneratedDraft.objects.filter(user=request.user)
        
        draft_info = []
        for draft in drafts:
            draft_info.append({
                'id': draft.id,
                'subject': draft.subject,
                'recipient': draft.recipient,
                'reply_text_preview': draft.reply_text[:100] + '...' if len(draft.reply_text) > 100 else draft.reply_text,
                'created_at': draft.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'is_sent': draft.is_sent,
                'original_email_id': draft.original_email_id
            })
        
        return Response({
            'total_drafts': drafts.count(),
            'drafts': draft_info,
            'user': request.user.username,
            'user_email': request.user.email
        })
    except Exception as e:
        return Response({'error': str(e)}, status=500)

########################################
# API: save generated draft (FIXED)
########################################
@api_view(['POST'])
def save_generated_draft_view(request):
    """Save a generated reply as a draft"""
    try:
        if not request.user.is_authenticated:
            return Response({'ok': False, 'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
            
        payload = json.loads(request.body.decode("utf-8"))
        original_email_id = payload.get("original_email_id", "")
        subject = payload.get("subject", "")
        recipient = payload.get("recipient", "")
        reply_text = payload.get("reply_text", "")
        
        logger.info(f"Saving draft for user {request.user.username}:")
        logger.info(f"  - Subject: {subject}")
        logger.info(f"  - Recipient: {recipient}")
        logger.info(f"  - Original Email ID: {original_email_id}")
        logger.info(f"  - Reply Text Length: {len(reply_text)}")
        
        if not all([original_email_id, subject, recipient, reply_text]):
            logger.error("Missing required fields for draft")
            return HttpResponseBadRequest("Missing required fields")
            
        draft = GeneratedDraft.objects.create(
            user=request.user,
            original_email_id=original_email_id,
            subject=subject,
            recipient=recipient,
            reply_text=reply_text
        )
        
        logger.info(f"Draft saved successfully with ID: {draft.id}")
        return JsonResponse({"ok": True, "draft_id": draft.id})
    except Exception as e:
        logger.error(f"Error saving generated draft: {str(e)}", exc_info=True)
        return JsonResponse({"ok": False, "error": str(e)}, status=500)

########################################
# API: send draft
########################################
@api_view(['POST'])
def send_draft_view(request, draft_id):
    """Send a generated draft"""
    try:
        if not request.user.is_authenticated:
            return Response({'ok': False, 'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
            
        draft = GeneratedDraft.objects.get(id=draft_id, user=request.user)
        
        # Get Gmail service
        service = get_gmail_service(user=request.user)
        if not service:
            return Response({'ok': False, 'error': 'Gmail not connected'}, status=status.HTTP_401_UNAUTHORIZED)
        
        # Create and send the message
        from .services.gmail import create_message
        message = create_message(draft.recipient, draft.subject, draft.reply_text)
        sent_message = service.users().messages().send(userId='me', body=message).execute()
        
        # Mark draft as sent
        draft.is_sent = True
        draft.save()
        
        return JsonResponse({"ok": True, "message_id": sent_message['id']})
    except GeneratedDraft.DoesNotExist:
        return Response({'ok': False, 'error': 'Draft not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error sending draft: {str(e)}", exc_info=True)
        return Response({'ok': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

########################################
# API: delete generated draft
########################################
@api_view(['DELETE'])
def delete_generated_draft_view(request, draft_id):
    """Delete a generated draft"""
    try:
        if not request.user.is_authenticated:
            return Response({'ok': False, 'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
            
        draft = GeneratedDraft.objects.get(id=draft_id, user=request.user)
        draft.delete()
        
        return Response({'ok': True})
    except GeneratedDraft.DoesNotExist:
        return Response({'ok': False, 'error': 'Draft not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error deleting generated draft: {str(e)}", exc_info=True)
        return Response({'ok': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

########################################
# API: toggle important
########################################
@api_view(['POST'])
def toggle_important_view(request, message_id):
    """Toggle important status for an email"""
    try:
        if not request.user.is_authenticated:
            return Response({'ok': False, 'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
            
        # FIXED: Use email_id instead of message_id
        important_email, created = ImportantEmail.objects.get_or_create(
            user=request.user,
            email_id=message_id
        )
        
        if not created:
            # If it already exists, remove it (unmark as important)
            important_email.delete()
            is_important = False
        else:
            is_important = True
            
        return Response({'ok': True, 'is_important': is_important})
    except Exception as e:
        logger.error(f"Error toggling important status: {str(e)}", exc_info=True)
        return Response({'ok': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

########################################
# API: important emails
########################################
@api_view(['GET'])
def important_emails_view(request):
    """Get all important emails for the current user"""
    try:
        if not request.user.is_authenticated:
            return Response({'ok': False, 'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
            
        # FIXED: Use email_id instead of message_id
        important_email_ids = ImportantEmail.objects.filter(user=request.user).values_list('email_id', flat=True)
        
        if not important_email_ids:
            return Response({'ok': True, 'emails': []})
            
        # Get Gmail service
        service = get_gmail_service(user=request.user)
        if not service:
            return Response({'ok': False, 'error': 'Gmail not connected'}, status=status.HTTP_401_UNAUTHORIZED)
        
        # Fetch email details for each important message
        emails = []
        for message_id in important_email_ids:
            try:
                email_details = get_email_details(service, message_id)
                if email_details:
                    # Mark as important
                    email_details['is_important'] = True
                    
                    # Add category information with error handling
                    try:
                        category = CategorizationService.get_email_category(request.user, message_id)
                        if category:
                            email_details['category'] = category.name  # FIXED: Use .name instead of .category
                    except Exception as e:
                        # Check if the error is due to missing table
                        if "does not exist" in str(e):
                            logger.warning(f"EmailCategory table does not exist. Skipping category for email {message_id}")
                        else:
                            logger.warning(f"Error getting category for email {message_id}: {str(e)}")
                    
                    # Add priority information with error handling
                    try:
                        priority = PriorityScoringService.get_email_priority(request.user, message_id)
                        if priority:
                            email_details['priority'] = priority.priority
                    except Exception as e:
                        # Check if the error is due to missing table
                        if "does not exist" in str(e):
                            logger.warning(f"EmailPriority table does not exist. Skipping priority for email {message_id}")
                        else:
                            logger.warning(f"Error getting priority for email {message_id}: {str(e)}")
                    
                    emails.append(email_details)
            except Exception as e:
                logger.error(f"Error fetching email {message_id}: {str(e)}")
                continue
        
        # Sort by date
        emails.sort(key=lambda x: x.get('date', ''), reverse=True)
        
        serializer = EmailSerializer(emails, many=True, context={'user': request.user})
        return Response({'ok': True, 'emails': serializer.data})
    except Exception as e:
        logger.error(f"Error fetching important emails: {str(e)}", exc_info=True)
        
        # FIXED: Return proper JSON error response
        error_msg = str(e)
        if "does not exist" in str(e):
            return Response({
                'ok': False, 
                'error': 'Database tables not created. Please run migrations.',
                'table_missing': True
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            return Response({
                'ok': False, 
                'error': error_msg
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

########################################
# API: user settings
########################################
@api_view(['GET', 'POST'])
def user_settings_view(request):
    """Get or update user settings"""
    try:
        if not request.user.is_authenticated:
            return Response({'ok': False, 'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
            
        if request.method == 'GET':
            # Get user settings
            user_settings, created = UserSettings.objects.get_or_create(user=request.user)
            
            return Response({
                'ok': True,
                'settings': {
                    'reply_tone': user_settings.reply_tone,
                    'auto_reply_enabled': user_settings.auto_reply_enabled,
                    'refresh_interval': user_settings.refresh_interval,
                    'theme': user_settings.theme
                }
            })
        else:
            # Update user settings
            payload = json.loads(request.body.decode("utf-8"))
            reply_tone = payload.get("reply_tone", "professional")
            auto_reply_enabled = payload.get("auto_reply_enabled", True)
            refresh_interval = payload.get("refresh_interval", 5)
            theme = payload.get("theme", "light")
            
            # Validate values
            if reply_tone not in ['professional', 'friendly', 'casual']:
                return Response({'ok': False, 'error': 'Invalid reply tone'}, status=status.HTTP_400_BAD_REQUEST)
            
            if not isinstance(refresh_interval, int) or refresh_interval < 1 or refresh_interval > 60:
                return Response({'ok': False, 'error': 'Refresh interval must be between 1 and 60 minutes'}, status=status.HTTP_400_BAD_REQUEST)
            
            if theme not in ['light', 'dark']:
                return Response({'ok': False, 'error': 'Invalid theme'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Update settings
            user_settings, created = UserSettings.objects.get_or_create(user=request.user)
            user_settings.reply_tone = reply_tone
            user_settings.auto_reply_enabled = auto_reply_enabled
            user_settings.refresh_interval = refresh_interval
            user_settings.theme = theme
            user_settings.save()
            
            # Update session for theme
            request.session['theme'] = theme
            
            return Response({
                'ok': True,
                'settings': {
                    'reply_tone': user_settings.reply_tone,
                    'auto_reply_enabled': user_settings.auto_reply_enabled,
                    'refresh_interval': user_settings.refresh_interval,
                    'theme': user_settings.theme
                }
            })
    except Exception as e:
        logger.error(f"Error in user_settings_view: {str(e)}", exc_info=True)
        return Response({'ok': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

########################################
# Settings page
########################################
@login_required
def settings_view(request):
    try:
        # Get or create user settings
        user_settings, created = UserSettings.objects.get_or_create(user=request.user)
        
        if request.method == 'POST':
            # Update settings
            user_settings.reply_tone = request.POST.get('reply_tone', 'professional')
            user_settings.auto_reply_enabled = request.POST.get('auto_reply_enabled', 'off') == 'on'
            user_settings.refresh_interval = int(request.POST.get('refresh_interval', 5))
            user_settings.theme = request.POST.get('theme', 'light')
            user_settings.save()
            
            # Update session for theme
            request.session['theme'] = user_settings.theme
            
            messages.success(request, "Settings saved successfully!")
            return redirect('settings')
        
        # Check if user has Gmail connected
        service = get_gmail_service(user=request.user)
        gmail_connected = service is not None
        
        return render(request, "inbox/settings.html", {
            'gmail_connected': gmail_connected,
            'settings': user_settings
        })
    except Exception as e:
        logger.error(f"Error in settings view: {str(e)}", exc_info=True)
        messages.error(request, f"Error loading settings: {str(e)}")
        return redirect('home')

########################################
# API: generate reply with Gemini (FIXED)
########################################
@csrf_exempt
@require_POST
def generate_reply_view(request):
    try:
        # FIX: Manually parse the JSON body from the request
        payload = json.loads(request.body.decode("utf-8"))
        email_text = payload.get("email_text", "")
        message_id = payload.get("message_id", "")
        subject = payload.get("subject", "")
        from_email = payload.get("from_email", "")
        
        if not email_text:
            return HttpResponseBadRequest("email_text is required")
        
        # Get user settings for reply tone
        reply_tone = 'professional'  # Default
        if request.user.is_authenticated:
            try:
                user_settings = UserSettings.objects.get(user=request.user)
                reply_tone = user_settings.reply_tone
            except UserSettings.DoesNotExist:
                pass
        
        try:
            summary = gemini.summarize_email(email_text)
            
            # Use the existing generate_reply function with tone-specific prompt
            tone_prompt = f"""
            Generate a reply to the following email in a {reply_tone} tone.
            The tone should be {reply_tone} throughout the entire response.
            
            Email Summary: {summary}
            
            Original Email: {email_text}
            
            Reply:
            """
            
            draft = gemini.generate_reply(tone_prompt)
        except Exception as e:
            # Check if this is a quota error
            if "429" in str(e) or "quota" in str(e).lower():
                logger.warning(f"Gemini quota exceeded, using fallback: {str(e)}")
                draft = gemini.generate_reply_fallback(email_text, summary)
            else:
                logger.error(f"Generate reply error: {str(e)}")
                return JsonResponse({"ok": False, "error": str(e)}, status=500)
        
        # Save as draft if user is authenticated
        if request.user.is_authenticated and message_id and subject and from_email:
            GeneratedDraft.objects.create(
                user=request.user,
                original_email_id=message_id,
                subject=f"Re: {subject}",
                recipient=from_email,
                reply_text=draft
            )
        
        return JsonResponse({"ok": True, "summary": summary, "draft_reply": draft})
    except Exception as e:
        logger.error(f"Generate reply error: {str(e)}")
        return JsonResponse({"ok": False, "error": str(e)}, status=500)
    
########################################
# API: generate reply with tone using Gemini (FIXED)
########################################
@csrf_exempt
@require_POST
def generate_tone_reply_view(request):
    try:
        # FIX: Manually parse the JSON body from the request
        payload = json.loads(request.body.decode("utf-8"))
        email_text = payload.get("email_text", "")
        tone = payload.get("tone", "professional")  # Default to professional if not provided
        message_id = payload.get("message_id", "")
        subject = payload.get("subject", "")
        from_email = payload.get("from_email", "")
        
        if not email_text:
            return HttpResponseBadRequest("email_text is required")
        
        # FIXED: Remove the model parameter since the function doesn't accept it
        summary = gemini.summarize_email(email_text)
        
        # Create a tone-specific prompt
        tone_prompt = f"""
        Generate a reply to the following email in a {tone} tone.
        The tone should be {tone} throughout the entire response.
        
        Email Summary: {summary}
        
        Original Email: {email_text}
        
        Reply:
        """
        
        # FIXED: Remove the model parameter since the function doesn't accept it
        draft = gemini.generate_reply(tone_prompt)
        
        # Save as draft if user is authenticated and we have the required information
        if request.user.is_authenticated and message_id and subject and from_email:
            try:
                GeneratedDraft.objects.create(
                    user=request.user,
                    original_email_id=message_id,
                    subject=f"Re: {subject}",
                    recipient=from_email,
                    reply_text=draft
                )
                logger.info(f"Saved generated draft for email {message_id}")
            except Exception as e:
                logger.error(f"Error saving generated draft: {str(e)}")
                # Don't fail the whole request if saving the draft fails
                pass
        
        return JsonResponse({"ok": True, "summary": summary, "draft_reply": draft})
    except Exception as e:
        logger.error(f"Generate tone reply error: {str(e)}")
        
        # Check if this is a quota error and handle it gracefully
        if "429" in str(e) or "quota" in str(e).lower():
            logger.warning(f"Gemini quota exceeded, using fallback: {str(e)}")
            try:
                # Try to use a fallback response
                fallback_draft = gemini.generate_reply_fallback(email_text, summary)
                return JsonResponse({
                    "ok": True, 
                    "summary": summary, 
                    "draft_reply": fallback_draft,
                    "warning": "Using fallback response due to quota limits"
                })
            except Exception as fallback_error:
                logger.error(f"Fallback also failed: {str(fallback_error)}")
                return JsonResponse({
                    "ok": False, 
                    "error": "Service temporarily unavailable due to quota limits. Please try again later.",
                    "quota_error": True
                }, status=503)  # Service Unavailable
        
        return JsonResponse({"ok": False, "error": str(e)}, status=500)
########################################
# API: save draft to Gmail (FIXED)
########################################
@api_view(['POST', 'PUT'])
@csrf_exempt
def save_draft_view(request, draft_id=None):
    """Save or update a draft"""
    try:
        # Get the user and Gmail service
        user = request.user if request.user.is_authenticated else None
        service = get_gmail_service(user=user)
        
        if not service:
            return Response({
                'ok': False,
                'error': 'No Gmail service available'
            }, status=400)
        
        if request.method == 'POST':
            # Create new draft
            to = request.data.get('to')
            subject = request.data.get('subject')
            body = request.data.get('body')
            
            if not all([to, subject, body]):
                return Response({
                    'ok': False,
                    'error': 'Missing required fields: to, subject, body'
                }, status=400)
            
            draft_id = create_gmail_draft(service, to, subject, body)
            
            if draft_id:
                return Response({
                    'ok': True,
                    'draft_id': draft_id,
                    'message': 'Draft saved successfully'
                })
            else:
                return Response({
                    'ok': False,
                    'error': 'Failed to save draft'
                }, status=500)
                
        elif request.method == 'PUT':
            # Update existing draft
            if not draft_id:
                return Response({
                    'ok': False,
                    'error': 'Draft ID is required for updating'
                }, status=400)
                
            to = request.data.get('to')
            subject = request.data.get('subject')
            body = request.data.get('body')
            
            if not all([to, subject, body]):
                return Response({
                    'ok': False,
                    'error': 'Missing required fields: to, subject, body'
                }, status=400)
            
            # Get current draft details
            current_draft = get_draft_details(service, draft_id)
            if not current_draft:
                return Response({
                    'ok': False,
                    'error': 'Draft not found'
                }, status=404)
            
            # Update the draft
            updated_draft_id = update_draft(service, draft_id, to, subject, body)
            
            if updated_draft_id:
                return Response({
                    'ok': True,
                    'draft_id': updated_draft_id,
                    'message': 'Draft updated successfully'
                })
            else:
                return Response({
                    'ok': False,
                    'error': 'Failed to update draft'
                }, status=500)
                
    except Exception as e:
        logger.error(f"Error in save_draft_view: {str(e)}", exc_info=True)
        return Response({
            'ok': False,
            'error': str(e)
        }, status=500)
########################################
# API: email details
########################################
@api_view(['GET'])
def email_detail_view(request, message_id):
    try:
        service = get_gmail_service(user=request.user if request.user.is_authenticated else None)
        if not service:
            return Response({'ok': False, 'error': 'Failed to authenticate'}, status=status.HTTP_401_UNAUTHORIZED)
        
        # First check if the email is available
        from .services.gmail import is_email_available
        
        if not is_email_available(service, message_id):
            return Response({'ok': False, 'error': 'Email not found or may have been deleted'}, status=status.HTTP_404_NOT_FOUND)
        
        email_details = get_email_details(service, message_id)
        if not email_details:
            return Response({'ok': False, 'error': 'Email not found or may have been deleted'}, status=status.HTTP_404_NOT_FOUND)
        
        # Add important status if user is authenticated
        if request.user.is_authenticated:
            # FIXED: Use email_id instead of message_id
            email_details['is_important'] = ImportantEmail.objects.filter(
                user=request.user, 
                email_id=message_id
            ).exists()
            
            # Add category information with error handling
            try:
                category = CategorizationService.get_email_category(request.user, message_id)
                if category:
                    email_details['category'] = category.name  # FIXED: Use .name instead of .category
            except Exception as e:
                # Check if the error is due to missing table
                if "does not exist" in str(e):
                    logger.warning(f"EmailCategory table does not exist. Skipping category for email {message_id}")
                else:
                    logger.warning(f"Error getting category for email {message_id}: {str(e)}")
            
            # Add priority information with error handling
            try:
                priority = PriorityScoringService.get_email_priority(request.user, message_id)
                if priority:
                    email_details['priority'] = priority.priority
            except Exception as e:
                # Check if the error is due to missing table
                if "does not exist" in str(e):
                    logger.warning(f"EmailPriority table does not exist. Skipping priority for email {message_id}")
                else:
                    logger.warning(f"Error getting priority for email {message_id}: {str(e)}")
        
        return Response({'ok': True, 'email': email_details})
    except Exception as e:
        logger.error(f"Error fetching email details: {str(e)}", exc_info=True)
        
        # Provide more specific error messages
        error_msg = str(e)
        if "does not exist" in str(e):
            error_msg = "Database tables not created. Please run migrations."
        
        return Response({'ok': False, 'error': error_msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

########################################
# API: draft details
########################################
@api_view(['GET'])
def draft_detail_view(request, draft_id):
    try:
        service = get_gmail_service(user=request.user if request.user.is_authenticated else None)
        if not service:
            return Response({'ok': False, 'error': 'Failed to authenticate'}, status=status.HTTP_401_UNAUTHORIZED)
        
        draft_details = get_draft_details(service, draft_id)
        if not draft_details:
            return Response({'ok': False, 'error': 'Draft not found'}, status=status.HTTP_404_NOT_FOUND)
        
        return Response({'ok': True, 'draft': draft_details})
    except Exception as e:
        logger.error(f"Error fetching draft details: {str(e)}", exc_info=True)
        return Response({'ok': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

########################################
# API: mark as read
########################################
@api_view(['POST'])
@csrf_exempt
def mark_as_read_view(request, message_id):
    try:
        service = get_gmail_service(user=request.user if request.user.is_authenticated else None)
        if not service:
            return Response({'ok': False, 'error': 'Failed to authenticate. Please reconnect your Gmail account.'}, status=status.HTTP_401_UNAUTHORIZED)
        
        # Log the attempt
        logger.info(f"Attempting to mark email {message_id} as read")
        
        success = mark_as_read(service, message_id)
        if success:
            # Clear the cache for unread emails to ensure fresh data
            try:
                # Try to clear by pattern if supported
                cache.delete_many([key for key in cache.keys('*gmail_unread_*')])
            except (AttributeError, NotImplementedError):
                # Fallback: clear entire cache if pattern deletion not supported
                cache.clear()
            
            logger.info(f"Successfully marked email {message_id} as read")
            return Response({'ok': True})
        else:
            logger.error(f"Failed to mark email {message_id} as read")
            return Response({'ok': False, 'error': 'Failed to mark email as read. The email may have been deleted or already marked as read.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        logger.error(f"Error marking email as read: {str(e)}", exc_info=True)
        return Response({'ok': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

########################################
# API: bulk mark as read
########################################
@api_view(['POST'])
@csrf_exempt
def bulk_mark_as_read_view(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
        email_ids = payload.get("email_ids", [])
        
        if not email_ids:
            return Response({'ok': False, 'error': 'No email IDs provided'}, status=status.HTTP_400_BAD_REQUEST)
        
        service = get_gmail_service(user=request.user if request.user.is_authenticated else None)
        if not service:
            return Response({'ok': False, 'error': 'Failed to authenticate. Please reconnect your Gmail account.'}, status=status.HTTP_401_UNAUTHORIZED)
        
        success_count = 0
        for email_id in email_ids:
            if mark_as_read(service, email_id):
                success_count += 1
        
        # Clear the cache for unread emails to ensure fresh data
        try:
            # Try to clear by pattern if supported
            cache.delete_many([key for key in cache.keys('*gmail_unread_*')])
        except (AttributeError, NotImplementedError):
            # Fallback: clear entire cache if pattern deletion not supported
            cache.clear()
        
        return Response({
            'ok': True, 
            'success_count': success_count,
            'total_count': len(email_ids)
        })
    except Exception as e:
        logger.error(f"Error in bulk_mark_as_read_view: {str(e)}", exc_info=True)
        return Response({'ok': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

########################################
# API: delete draft
########################################
@api_view(['DELETE'])
@csrf_exempt
def delete_draft_view(request, draft_id):
    try:
        service = get_gmail_service(user=request.user if request.user.is_authenticated else None)
        if not service:
            return Response({'ok': False, 'error': 'Failed to authenticate'}, status=status.HTTP_401_UNAUTHORIZED)
        
        success = delete_draft(service, draft_id)
        if success:
            return Response({'ok': True})
        else:
            return Response({'ok': False, 'error': 'Failed to delete draft'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        logger.error(f"Error deleting draft: {str(e)}", exc_info=True)
        return Response({'ok': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

########################################
# API: update draft
########################################
@api_view(['PUT'])
@csrf_exempt
def update_draft_view(request, draft_id):
    try:
        service = get_gmail_service(user=request.user if request.user.is_authenticated else None)
        if not service:
            return JsonResponse({"ok": False, "error": "Not authorized. Connect Gmail first."}, status=401)
        
        payload = json.loads(request.body.decode("utf-8"))
        to_email = payload.get("to")
        subject = payload.get("subject")
        body = payload.get("body")
        
        if not all([to_email, subject, body]):
            return HttpResponseBadRequest("to, subject, body are required")
        
        draft_id = update_draft(service, draft_id, to_email, subject, body)
        return JsonResponse({"ok": True, "draft_id": draft_id})
    except Exception as e:
        logger.error(f"Update draft error: {str(e)}")
        return JsonResponse({"ok": False, "error": str(e)}, status=500)

########################################
# API: Archive email
########################################
@api_view(['POST'])
@csrf_exempt
def archive_email_view(request, message_id):
    """Archive a single email by removing the INBOX label"""
    try:
        service = get_gmail_service(user=request.user if request.user.is_authenticated else None)
        if not service:
            return Response({'ok': False, 'error': 'Failed to authenticate. Please reconnect your Gmail account.'}, 
                          status=status.HTTP_401_UNAUTHORIZED)
        
        # Log the attempt
        logger.info(f"Attempting to archive email {message_id}")
        
        # Archive by removing INBOX label
        success = archive_email(service, message_id)
        if success:
            # Clear the cache for unread emails to ensure fresh data
            try:
                # Try to clear by pattern if supported
                cache.delete_many([key for key in cache.keys('*gmail_unread_*')])
            except (AttributeError, NotImplementedError):
                # Fallback: clear entire cache if pattern deletion not supported
                cache.clear()
            
            logger.info(f"Successfully archived email {message_id}")
            return Response({'ok': True})
        else:
            logger.error(f"Failed to archive email {message_id}")
            return Response({'ok': False, 'error': 'Failed to archive email. The email may have been deleted or already archived.'}, 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        logger.error(f"Error archiving email: {str(e)}", exc_info=True)
        return Response({'ok': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

########################################
# API: Bulk archive emails
########################################
@api_view(['POST'])
@csrf_exempt
def bulk_archive_emails_view(request):
    """Archive multiple emails by removing the INBOX label"""
    try:
        payload = json.loads(request.body.decode("utf-8"))
        email_ids = payload.get("email_ids", [])
        
        if not email_ids:
            return Response({'ok': False, 'error': 'No email IDs provided'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        service = get_gmail_service(user=request.user if request.user.is_authenticated else None)
        if not service:
            return Response({'ok': False, 'error': 'Failed to authenticate. Please reconnect your Gmail account.'}, 
                          status=status.HTTP_401_UNAUTHORIZED)
        
        success_count = 0
        for email_id in email_ids:
            if archive_email(service, email_id):
                success_count += 1
        
        # Clear the cache for unread emails to ensure fresh data
        try:
            # Try to clear by pattern if supported
            cache.delete_many([key for key in cache.keys('*gmail_unread_*')])
        except (AttributeError, NotImplementedError):
            # Fallback: clear entire cache if pattern deletion not supported
            cache.clear()
        
        return Response({
            'ok': True, 
            'success_count': success_count,
            'total_count': len(email_ids)
        })
    except Exception as e:
        logger.error(f"Error in bulk_archive_emails_view: {str(e)}", exc_info=True)
        return Response({'ok': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

########################################
# Helper function: Archive email
########################################
def archive_email(service, message_id):
    """Archive an email by removing the INBOX label"""
    try:
        service.users().messages().modify(
            userId='me',
            id=message_id,
            body={
                'removeLabelIds': ['INBOX']
            }
        ).execute()
        return True
    except Exception as e:
        logger.error(f"Error archiving email {message_id}: {str(e)}")
        return False

########################################
# Logout (Updated to remove credentials)
########################################
def logout_view(request):
    # Remove stored Gmail credentials
    if request.user.is_authenticated:
        _save_creds_to_db(None, user=request.user)
    
    # Clear session data but don't delete the session key yet
    request.session.clear()
    request.session['logout_in_progress'] = True
    
    # Add success message
    messages.success(request, "You have been successfully logged out. You can now sign in with a different account.")
    
    return redirect('oauth_start')

########################################
# Force Re-authentication (Updated)
########################################
def force_reauth_view(request):
    """Force re-authentication with Google"""
    # Remove stored Gmail credentials if user is authenticated
    if request.user.is_authenticated:
        _save_creds_to_db(None, user=request.user)
    
    # Clear all session data
    request.session.flush()
    
    # Add a message to inform the user
    messages.info(request, "All authentication data cleared. Please select your Google account and grant Calendar access permissions.")
    
    # Redirect to OAuth start
    return redirect('oauth_start')

########################################
# API: Schedule Meeting
########################################
@csrf_exempt
@require_POST
def schedule_meeting_view(request):
    """
    Schedules a meeting in Google Calendar.
    Expects a JSON payload with meeting details.
    """
    try:
        # Check if user is authenticated
        if not request.user.is_authenticated:
            return JsonResponse({
                "ok": False, 
                "error": "Authentication required. Please log in.",
                "auth_required": True
            }, status=401)

        # Parse the JSON payload from the request body
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON payload."}, status=400)

        email_id = payload.get("email_id")
        title = payload.get("title")
        description = payload.get("description", "")
        start_datetime = payload.get("start_datetime")
        end_datetime = payload.get("end_datetime")
        attendees = payload.get("attendees", [])  # This should be a list already from JS
        reminders = payload.get("reminders", []) # This should be a list of numbers

        # Validate required fields
        if not all([title, start_datetime, end_datetime]):
            return JsonResponse({
                "ok": False, 
                "error": "Title, start datetime, and end datetime are required."
            }, status=400)

        # Get Gmail service and credentials
        service = get_gmail_service(user=request.user)
        if not service:
            return JsonResponse({
                "ok": False, 
                "error": "Not authorized. Connect Gmail first."
            }, status=401)
        
        creds = _load_creds_from_db(user=request.user)
        if not creds:
            return JsonResponse({
                "ok": False, 
                "error": "Not authorized. Connect Gmail first."
            }, status=401)
        
        # Check if Calendar scope is included
        if 'https://www.googleapis.com/auth/calendar.events' not in creds.scopes:
            return JsonResponse({
                "ok": False, 
                "error": "Calendar access permission not granted. Please re-authenticate with Google and grant Calendar access.",
                "needs_reauth": True
            }, status=403)
        
        # Import the Google Calendar service library
        try:
            from googleapiclient.discovery import build
        except ImportError:
            logger.error("Google API client library not found.")
            return JsonResponse({
                "ok": False, 
                "error": "Server configuration error: Google API library missing."
            }, status=500)

        # Build the Calendar service
        calendar_service = build('calendar', 'v3', credentials=creds)
        
        # Create the event body for the API
        event = {
            'summary': title,
            'description': description,
            'start': {
                'dateTime': start_datetime,
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': end_datetime,
                'timeZone': 'UTC',
            },
        }
        
        # Add attendees if provided and is a list
        if isinstance(attendees, list) and attendees:
            event['attendees'] = [{'email': email} for email in attendees if email]
        
        # Add reminders if provided and is a list
        if isinstance(reminders, list) and reminders:
            event['reminders'] = {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': int(minutes)} for minutes in reminders if minutes
                ]
            }
        else:
            # Use default reminders if none specified
            event['reminders'] = {'useDefault': True}
        
        # Insert the event into the primary calendar
        event_result = calendar_service.events().insert(
            calendarId='primary',
            body=event,
            sendUpdates='all'
        ).execute()
        
        logger.info(f"Successfully scheduled meeting '{title}' for user {request.user.email}")
        return JsonResponse({
            "ok": True,
            "html_link": event_result.get('htmlLink'),
        })

    except Exception as e:
        # Log the full exception for debugging
        logger.error(f"Schedule meeting error: {str(e)}", exc_info=True)
        
        # Check for specific, actionable errors
        error_message = str(e)
        if "insufficient authentication scopes" in error_message or "Insufficient Permission" in error_message:
            return JsonResponse({
                "ok": False, 
                "error": "Calendar access permission not granted. Please re-authenticate with Google and grant Calendar access.",
                "needs_reauth": True
            }, status=403)
        elif "notFound" in error_message or "Resource Not Found" in error_message:
             return JsonResponse({
                "ok": False,
                "error": "Could not find the specified calendar resource."
            }, status=404)
        elif "quotaExceeded" in error_message or "Rate Limit" in error_message:
            return JsonResponse({
                "ok": False,
                "error": "Google Calendar API quota exceeded. Please try again later."
            }, status=429)
        
        # Return a generic server error
        return JsonResponse({
            "ok": False, 
            "error": f"An unexpected server error occurred: {error_message}"
        }, status=500)

########################################
# API: Check Calendar Permissions
########################################
@api_view(['GET'])
def check_calendar_permissions_view(request):
    """Check if the user has granted Calendar permissions"""
    try:
        creds = _load_creds_from_db(user=request.user if request.user.is_authenticated else None)
        if not creds:
            return Response({
                'ok': False,
                'has_calendar_permissions': False,
                'error': 'Not authenticated'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        has_calendar_permissions = 'https://www.googleapis.com/auth/calendar.events' in creds.scopes
        
        return Response({
            'ok': True,
            'has_calendar_permissions': has_calendar_permissions
        })
    except Exception as e:
        logger.error(f"Error checking calendar permissions: {str(e)}")
        return Response({
            'ok': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

########################################
# API: Voice Command Help
########################################
import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)

@csrf_exempt
@require_POST
def voice_command_view(request):
    """Process voice commands and return JSON response"""
    try:
        # Add debug logging
        logger.info(f"Voice command received: {request.method} {request.path}")
        logger.info(f"Request headers: {dict(request.headers)}")
        
        # Check content type first
        content_type = request.content_type
        if content_type != 'application/json':
            logger.error(f"Wrong content type: {content_type}")
            return JsonResponse({"ok": False, "error": "Expected JSON request"}, status=400)
        
        # Parse JSON body with better error handling
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except json.JSONDecodeError:
            logger.error("Invalid JSON in request body")
            return JsonResponse({"ok": False, "error": "Invalid JSON in request body"}, status=400)
        
        command = payload.get("command", "").lower().strip()
        logger.info(f"Received command: '{command}'")
        
        # Validate command
        is_valid, validation_error = validate_voice_command(command)
        if not is_valid:
            logger.error(f"Command validation failed: {validation_error}")
            return JsonResponse({"ok": False, "error": validation_error}, status=400)
        
        logger.info(f"Processing voice command: {command}")
        
        # Process the command and return the action to execute
        action = process_voice_command(command)
        logger.info(f"Processed action: {action}")
        
        # Special handling for help command
        if action.get("type") == "help":
            logger.info("Processing help command")
            commands = get_available_commands()
            voice_text = "Available voice commands are: "
            for cmd in commands:
                voice_text += f"{cmd['command']}. "
            action["voice_output"] = voice_text
            action["commands_list"] = commands
            logger.info(f"Help command processed, returning {len(commands)} commands")
        
        logger.info(f"Returning action: {action}")
        return JsonResponse({
            "ok": True, 
            "action": action,
            "command": command,
            "message": f"Command recognized: {command}"
        })
    except Exception as e:
        logger.error(f"Voice command error: {str(e)}", exc_info=True)
        return JsonResponse({"ok": False, "error": str(e)}, status=500)

def voice_command_help_view(request):
    """Return available voice commands"""
    try:
        commands = get_available_commands()
        return JsonResponse({
            "ok": True,
            "commands": commands,
            "message": "Available voice commands retrieved"
        })
    except Exception as e:
        logger.error(f"Error getting voice commands: {str(e)}")
        return JsonResponse({"ok": False, "error": str(e)}, status=500)

def process_voice_command(command):
    """Process voice command and return the corresponding action"""
    command = command.lower().strip()
    
    # Help - More flexible matching (put first to catch all help variations)
    if "help" in command:
        return {"type": "help"}
    
    # Load emails / refresh
    elif any(keyword in command for keyword in ["load emails", "refresh", "show emails", "get emails"]):
        return {"type": "load_emails"}
    
    # Mark all as read
    elif any(keyword in command for keyword in ["mark all as read", "mark everything as read", "read all"]):
        return {"type": "mark_all_as_read"}
    
    # Mark current email as read
    elif any(keyword in command for keyword in ["mark as read", "mark this as read", "read this"]):
        return {"type": "mark_current_as_read"}
    
    # Archive email
    elif any(keyword in command for keyword in ["archive", "archive this", "archive email"]):
        return {"type": "archive_current"}
    
    # Delete email
    elif any(keyword in command for keyword in ["delete", "delete this", "remove"]):
        return {"type": "delete_current"}
    
    # Reply to email
    elif any(keyword in command for keyword in ["reply", "reply to this", "reply to email"]):
        return {"type": "reply_current"}
    
    # Compose new email
    elif any(keyword in command for keyword in ["compose", "new email", "write email", "create email"]):
        return {"type": "compose_email"}
    
    # Next page
    elif any(keyword in command for keyword in ["next page", "show next", "go to next"]):
        return {"type": "next_page"}
    
    # Previous page
    elif any(keyword in command for keyword in ["previous page", "show previous", "go back"]):
        return {"type": "previous_page"}
    
    # Generate reply
    elif any(keyword in command for keyword in ["generate reply", "create reply", "ai reply"]):
        return {"type": "generate_reply"}
    
    # Save draft
    elif any(keyword in command for keyword in ["save draft", "save as draft"]):
        return {"type": "save_draft"}
    
    # Schedule meeting
    elif any(keyword in command for keyword in ["schedule meeting", "create meeting", "new meeting"]):
        return {"type": "schedule_meeting"}
    
    # Toggle theme
    elif any(keyword in command for keyword in ["toggle theme", "switch theme", "dark mode", "light mode"]):
        return {"type": "toggle_theme"}
    
    # Phase 1: Analyze email thread
    elif any(keyword in command for keyword in ["analyze thread", "thread analysis", "summarize thread"]):
        return {"type": "analyze_thread"}
    
    # Phase 1: Check sentiment
    elif any(keyword in command for keyword in ["check sentiment", "sentiment analysis", "how does this feel"]):
        return {"type": "sentiment_analysis"}
    
    # Phase 1: Use template
    elif any(keyword in command for keyword in ["use template", "apply template", "template"]):
        return {"type": "use_template"}
    
    # Phase 1: Create template
    elif any(keyword in command for keyword in ["create template", "new template", "save template"]):
        return {"type": "create_template"}
    
    # Phase 2: Set reminder
    elif any(keyword in command for keyword in ["remind me", "set reminder", "follow up"]):
        return {"type": "set_reminder"}
    
    # Phase 2: Schedule email
    elif any(keyword in command for keyword in ["schedule email", "send later", "schedule send"]):
        return {"type": "schedule_email"}
    
    # Phase 2: Categorize email
    elif any(keyword in command for keyword in ["categorize", "category", "label"]):
        return {"type": "categorize_email"}
    
    # Phase 2: Set priority
    elif any(keyword in command for keyword in ["priority", "mark as", "set priority"]):
        return {"type": "set_priority"}
    
    # Phase 2: Auto categorize
    elif any(keyword in command for keyword in ["auto categorize", "categorize automatically"]):
        return {"type": "auto_categorize"}
    
    # Phase 2: Auto priority
    elif any(keyword in command for keyword in ["auto priority", "priority automatically"]):
        return {"type": "auto_priority"}
    
    # Unknown command
    else:
        return {"type": "unknown", "message": "Command not recognized"}

def execute_voice_command(action, request):
    """Execute the voice command based on action type"""
    try:
        action_type = action.get("type")
        
        if action_type == "load_emails":
            # Call your existing email loading function
            return {"message": "Loading emails..."}
        
        elif action_type == "mark_all_as_read":
            # Implement mark all as read functionality
            return {"message": "Marking all emails as read..."}
        
        elif action_type == "mark_current_as_read":
            email_id = request.data.get("current_email_id")
            if email_id:
                # Implement mark as read functionality
                return {"message": f"Marking email {email_id} as read..."}
            return {"ok": False, "error": "No email selected"}
        
        elif action_type == "archive_current":
            email_id = request.data.get("current_email_id")
            if email_id:
                # Implement archive functionality
                return {"message": f"Archiving email {email_id}..."}
            return {"ok": False, "error": "No email selected"}
        
        elif action_type == "delete_current":
            email_id = request.data.get("current_email_id")
            if email_id:
                # Implement delete functionality
                return {"message": f"Deleting email {email_id}..."}
            return {"ok": False, "error": "No email selected"}
        
        elif action_type == "reply_current":
            email_id = request.data.get("current_email_id")
            if email_id:
                # Implement reply functionality
                return {"message": f"Replying to email {email_id}..."}
            return {"ok": False, "error": "No email selected"}
        
        elif action_type == "compose_email":
            # Implement compose email functionality
            return {"message": "Opening compose email dialog..."}
        
        elif action_type == "next_page":
            # Implement next page functionality
            return {"message": "Loading next page..."}
        
        elif action_type == "previous_page":
            # Implement previous page functionality
            return {"message": "Loading previous page..."}
        
        elif action_type == "generate_reply":
            email_id = request.data.get("current_email_id")
            if email_id:
                # Implement generate reply functionality
                return {"message": f"Generating reply for email {email_id}..."}
            return {"ok": False, "error": "No email selected"}
        
        elif action_type == "save_draft":
            # Implement save draft functionality
            return {"message": "Saving draft..."}
        
        elif action_type == "schedule_meeting":
            # Implement schedule meeting functionality
            return {"message": "Opening meeting scheduler..."}
        
        elif action_type == "toggle_theme":
            # Implement theme toggle functionality
            return {"message": "Toggling theme..."}
        
        elif action_type == "analyze_thread":
            email_id = request.data.get("current_email_id")
            if email_id:
                # Implement thread analysis functionality
                return {"message": f"Analyzing thread for email {email_id}..."}
            return {"ok": False, "error": "No email selected"}
        
        elif action_type == "sentiment_analysis":
            email_id = request.data.get("current_email_id")
            if email_id:
                # Implement sentiment analysis functionality
                return {"message": f"Analyzing sentiment for email {email_id}..."}
            return {"ok": False, "error": "No email selected"}
        
        elif action_type == "use_template":
            # Implement use template functionality
            return {"message": "Applying template..."}
        
        elif action_type == "create_template":
            # Implement create template functionality
            return {"message": "Creating template..."}
        
        elif action_type == "set_reminder":
            email_id = request.data.get("current_email_id")
            if email_id:
                # Implement set reminder functionality
                return {"message": f"Setting reminder for email {email_id}..."}
            return {"ok": False, "error": "No email selected"}
        
        elif action_type == "schedule_email":
            # Implement schedule email functionality
            return {"message": "Opening email scheduler..."}
        
        elif action_type == "categorize_email":
            email_id = request.data.get("current_email_id")
            if email_id:
                # Implement categorize email functionality
                return {"message": f"Categorizing email {email_id}..."}
            return {"ok": False, "error": "No email selected"}
        
        elif action_type == "set_priority":
            email_id = request.data.get("current_email_id")
            if email_id:
                # Implement set priority functionality
                return {"message": f"Setting priority for email {email_id}..."}
            return {"ok": False, "error": "No email selected"}
        
        elif action_type == "auto_categorize":
            email_id = request.data.get("current_email_id")
            if email_id:
                # Implement auto categorize functionality
                return {"message": f"Auto categorizing email {email_id}..."}
            return {"ok": False, "error": "No email selected"}
        
        elif action_type == "auto_priority":
            email_id = request.data.get("current_email_id")
            if email_id:
                # Implement auto priority functionality
                return {"message": f"Auto setting priority for email {email_id}..."}
            return {"ok": False, "error": "No email selected"}
        
        else:
            return {"ok": False, "error": f"Command not implemented: {action_type}"}
    
    except Exception as e:
        logger.error(f"Error executing voice command: {str(e)}")
        return {"ok": False, "error": str(e)}

def validate_voice_command(command):
    """Validate the voice command"""
    if not command or len(command.strip()) < 2:
        return False, "Command too short"
    return True, ""

def get_available_commands():
    """Get list of available voice commands"""
    return [
        {"command": "load emails", "description": "Load or refresh your emails"},
        {"command": "mark all as read", "description": "Mark all emails as read"},
        {"command": "mark as read", "description": "Mark the current email as read"},
        {"command": "archive", "description": "Archive the current email"},
        {"command": "delete", "description": "Delete the current email"},
        {"command": "reply", "description": "Reply to the current email"},
        {"command": "compose email", "description": "Compose a new email"},
        {"command": "next page", "description": "Go to the next page of emails"},
        {"command": "previous page", "description": "Go to the previous page of emails"},
        {"command": "generate reply", "description": "Generate an AI reply for the current email"},
        {"command": "save draft", "description": "Save the current draft"},
        {"command": "schedule meeting", "description": "Schedule a meeting"},
        {"command": "toggle theme", "description": "Toggle between dark and light theme"},
        {"command": "help", "description": "Show available commands"},
        # Phase 1 commands
        {"command": "analyze thread", "description": "Analyze the entire email thread"},
        {"command": "check sentiment", "description": "Analyze the sentiment of the current email"},
        {"command": "use template", "description": "Apply an email template"},
        {"command": "create template", "description": "Create a new email template"},
        # Phase 2 commands
        {"command": "remind me to follow up", "description": "Set a reminder for an email"},
        {"command": "schedule email", "description": "Schedule an email to be sent later"},
        {"command": "categorize email", "description": "Assign a category to an email"},
        {"command": "set priority", "description": "Set the priority level of an email"},
        {"command": "auto categorize", "description": "Automatically categorize an email using AI"},
        {"command": "auto priority", "description": "Automatically assign a priority score using AI"},
    ]

########################################
# API: Test Gmail drafts (NEW)
########################################
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
import json
import logging
from .services.gmail import get_gmail_service, get_draft_details, create_message

logger = logging.getLogger(__name__)

@api_view(['GET'])
def test_gmail_drafts_view(request):
    """Test endpoint to check Gmail drafts"""
    try:
        user = request.user if request.user.is_authenticated else None
        service = get_gmail_service(user=user)
        
        if not service:
            return Response({'error': 'No Gmail service available'}, status=400)
        
        # Get profile
        try:
            profile = service.users().getProfile(userId='me').execute()
            profile_info = {
                'emailAddress': profile.get('emailAddress'),
                'historyId': profile.get('historyId'),
                'messagesTotal': profile.get('messagesTotal'),
                'threadsTotal': profile.get('threadsTotal')
            }
        except Exception as e:
            profile_info = {'error': str(e)}
        
        # Get all drafts
        try:
            drafts_list = service.users().drafts().list(userId='me', maxResults=5).execute()
            draft_ids = [draft['id'] for draft in drafts_list.get('drafts', [])]
        except Exception as e:
            drafts_list = {'error': str(e)}
            draft_ids = []
        
        # Get first draft details
        draft_details = None
        if draft_ids:
            try:
                draft_details = service.users().drafts().get(userId='me', id=draft_ids[0]).execute()
            except Exception as e:
                draft_details = {'error': str(e)}
        
        return Response({
            'total_drafts': len(draft_ids),
            'draft_details': draft_details,
            'email': profile.get('emailAddress')
        })
    except Exception as e:
        logger.error(f"Error in test_gmail_drafts_view: {str(e)}", exc_info=True)
        return Response({'error': str(e)}, status=500)

########################################
# API: Update Gmail draft
########################################
@api_view(['PUT'])
@csrf_exempt
def update_draft_view(request, draft_id):
    """Update an existing draft"""
    try:
        # Get the draft data from the request
        to = request.data.get('to')
        subject = request.data.get('subject')
        body = request.data.get('body')
        
        # Validate required fields
        if not all([to, subject, body]):
            return Response({
                'ok': False,
                'error': 'Missing required fields: to, subject, body'
            }, status=400)
        
        # Get the user and Gmail service
        user = request.user if request.user.is_authenticated else None
        service = get_gmail_service(user=user)
        
        if not service:
            return Response({
                'ok': False,
                'error': 'No Gmail service available'
            }, status=400)
        
        # Update the draft using the update_draft function from gmail.py
        from .services.gmail import update_draft
        updated_draft_id = update_draft(service, draft_id, to, subject, body)
        
        if updated_draft_id:
            return Response({
                'ok': True,
                'draft_id': updated_draft_id,
                'message': 'Draft updated successfully'
            })
        else:
            return Response({
                'ok': False,
                'error': 'Failed to update draft'
            }, status=500)
            
    except Exception as e:
        logger.error(f"Error in update_draft_view: {str(e)}", exc_info=True)
        return Response({
            'ok': False,
            'error': str(e)
        }, status=500)

########################################
# API: Edit Gmail draft (subject and recipient only)
########################################
@api_view(['PUT'])
@csrf_exempt
def edit_gmail_draft_view(request, draft_id):
    """Edit a Gmail draft (subject and recipient only)"""
    try:
        service = get_gmail_service(user=request.user if request.user.is_authenticated else None)
        if not service:
            return Response({"ok": False, "error": "Not authorized. Connect Gmail first."}, status=401)
        
        # Use request.data instead of manually parsing JSON
        payload = request.data
        new_subject = payload.get("subject")
        new_to = payload.get("to")
        
        if not new_subject or not new_to:
            return Response({"ok": False, "error": "Subject and recipient are required"}, status=400)
        
        logger.info(f"Editing Gmail draft {draft_id}:")
        logger.info(f"  - New subject: {new_subject}")
        logger.info(f"  - New recipient: {new_to}")
        
        # Get current draft details
        current_draft = get_draft_details(service, draft_id)
        if not current_draft:
            return Response({"ok": False, "error": "Draft not found"}, status=404)
        
        # Create updated message with new subject and recipient, keeping original body
        message = create_message(new_to, new_subject, current_draft.get('body', ''))
        
        # Update the draft
        updated_draft = service.users().drafts().update(
            userId='me',
            id=draft_id,
            body=message
        ).execute()
        
        logger.info(f"Draft {draft_id} updated successfully")
        return Response({
            "ok": True,
            "draft_id": updated_draft.get('id'),
            "subject": new_subject,
            "to": new_to
        })
    except Exception as e:
        logger.error(f"Error editing Gmail draft: {str(e)}", exc_info=True)
        return Response({"ok": False, "error": str(e)}, status=500)

########################################
# API: Save generated draft
########################################
@api_view(['POST'])
@csrf_exempt
def save_generated_draft_view(request):
    """Save a generated draft to Gmail"""
    try:
        # Get the draft data from the request
        to = request.data.get('to')
        subject = request.data.get('subject')
        body = request.data.get('body')
        
        # Validate required fields
        if not all([to, subject, body]):
            return Response({
                'ok': False,
                'error': 'Missing required fields: to, subject, body'
            }, status=400)
        
        # Get the user and Gmail service
        user = request.user if request.user.is_authenticated else None
        service = get_gmail_service(user=user)
        
        if not service:
            return Response({
                'ok': False,
                'error': 'No Gmail service available'
            }, status=400)
        
        # Create the draft using the create_gmail_draft function from gmail.py
        from .services.gmail import create_gmail_draft
        draft_id = create_gmail_draft(service, to, subject, body)
        
        if draft_id:
            return Response({
                'ok': True,
                'draft_id': draft_id,
                'message': 'Draft saved successfully'
            })
        else:
            return Response({
                'ok': False,
                'error': 'Failed to save draft'
            }, status=500)
            
    except Exception as e:
        logger.error(f"Error in save_generated_draft_view: {str(e)}", exc_info=True)
        return Response({
            'ok': False,
            'error': str(e)
        }, status=500)

########################################
# API: List Gemini models
########################################
@api_view(['GET'])
def list_gemini_models(request):
    """List available Gemini models"""
    try:
        import google.generativeai as genai
        from django.conf import settings
        
        # Configure with API key
        api_key = getattr(settings, "GEMINI_API_KEY", None)
        if api_key:
            genai.configure(api_key=api_key)
        
        models = genai.list_models()
        model_names = [model.name for model in models]
        
        # Filter for models that support generateContent
        supported_models = []
        for model in models:
            if "generateContent" in model.supported_generation_methods:
                supported_models.append(model.name)
        
        return Response({
            'all_models': model_names,
            'supported_models': supported_models
        })
    except Exception as e:
        return Response({'error': str(e)}, status=500)
    
########################################
# NEW: Email Thread Analysis Views
########################################

@api_view(['GET'])
def email_thread_analysis_view(request, thread_id):
    """Analyze an entire email thread and provide per-message analysis"""
    try:
        service = get_gmail_service(user=request.user if request.user.is_authenticated else None)
        if not service:
            return Response({'ok': False, 'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        
        # Get thread details
        thread = service.users().threads().get(userId='me', id=thread_id).execute()
        messages = thread.get('messages', [])
        
        if not messages:
            return Response({'ok': False, 'error': 'Thread not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Process each message individually
        message_analyses = []
        for msg in messages:
            msg_data = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
            headers = msg_data['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '(no subject)')
            from_email = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), '')
            
            # Extract body
            body = ''
            if 'parts' in msg_data['payload']:
                for part in msg_data['payload']['parts']:
                    if part['mimeType'] == 'text/plain':
                        body_data = part['body'].get('data', '')
                        if body_data:
                            body = base64.urlsafe_b64decode(body_data).decode('utf-8')
                        break
            else:
                if 'body' in msg_data['payload'] and 'data' in msg_data['payload']['body']:
                    body_data = msg_data['payload']['body'].get('data', '')
                    if body_data:
                        body = base64.urlsafe_b64decode(body_data).decode('utf-8')
            
            # Analyze this specific message
            message_analysis = gemini.analyze_email_message(body)
            
            message_analyses.append({
                "message_id": msg['id'],
                "from": from_email,
                "date": date,
                "subject": subject,
                "analysis": message_analysis
            })
        
        return Response({
            'ok': True,
            'thread_id': thread_id,
            'message_analyses': message_analyses,
            'message_count': len(messages)
        })
    except Exception as e:
        logger.error(f"Error in email_thread_analysis_view: {str(e)}", exc_info=True)
        return Response({'ok': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

########################################
# NEW: Email Thread Analysis Views
########################################

@api_view(['POST'])
def email_thread_analysis_from_text_view(request):
    """Analyze email thread from pasted text"""
    try:
        # FIX: Use request.data instead of manually parsing request.body
        # This prevents the RawPostDataException
        email_text = request.data.get("email_text", "")
        
        if not email_text:
            return Response({'ok': False, 'error': 'email_text is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Analyze the thread using Gemini
        thread_analysis = gemini.analyze_email_thread(email_text)
        
        return Response({
            'ok': True,
            'thread_analysis': thread_analysis
        })
    except Exception as e:
        logger.error(f"Error in email_thread_analysis_from_text_view: {str(e)}", exc_info=True)
        return Response({'ok': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

########################################
# NEW: Sentiment Analysis Views
########################################

@api_view(['POST'])
def sentiment_analysis_view(request):
    """Analyze sentiment of email text using Gemini"""
    try:
        # FIX: Use request.data instead of manually parsing request.body
        # This prevents the RawPostDataException
        email_text = request.data.get("email_text", "")
        
        if not email_text:
            return Response({'ok': False, 'error': 'email_text is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Create a prompt for sentiment analysis
        prompt = f"""
        Analyze the sentiment of the following email. Provide:
        1. Overall sentiment (positive, negative, or neutral)
        2. Confidence level (0-100%)
        3. Urgency level (low, medium, high)
        4. Suggested reply tone
        5. Key emotional indicators
        
        Email: {email_text}
        
        Analysis:
        """
        
        # Use the gemini.generate_reply function to get the sentiment analysis
        sentiment_result = gemini.generate_reply(prompt)
        
        # Parse the response to extract structured data
        # For now, return the raw response
        return Response({
            'ok': True,
            'sentiment': sentiment_result
        })
    except Exception as e:
        logger.error(f"Error in sentiment_analysis_view: {str(e)}", exc_info=True)
        return Response({'ok': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

########################################
# NEW: Template Management Views
########################################

@api_view(['GET', 'POST'])
def email_templates_view(request):
    """List or create email templates"""
    if not request.user.is_authenticated:
        return Response({'ok': False, 'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
    
    if request.method == 'GET':
        templates = EmailTemplate.objects.filter(user=request.user)
        serializer = EmailTemplateSerializer(templates, many=True)
        return Response({'ok': True, 'templates': serializer.data})
    
    elif request.method == 'POST':
        serializer = EmailTemplateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response({'ok': True, 'template': serializer.data}, status=status.HTTP_201_CREATED)
        return Response({'ok': False, 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'PUT', 'DELETE'])
def email_template_detail_view(request, template_id):
    """Retrieve, update or delete an email template"""
    if not request.user.is_authenticated:
        return Response({'ok': False, 'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
    
    try:
        template = EmailTemplate.objects.get(id=template_id, user=request.user)
    except EmailTemplate.DoesNotExist:
        return Response({'ok': False, 'error': 'Template not found'}, status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'GET':
        serializer = EmailTemplateSerializer(template)
        return Response({'ok': True, 'template': serializer.data})
    
    elif request.method == 'PUT':
        serializer = EmailTemplateSerializer(template, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({'ok': True, 'template': serializer.data})
        return Response({'ok': False, 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        template.delete()
        return Response({'ok': True})

@api_view(['POST'])
def apply_template_view(request):
    """Apply a template to generate a reply"""
    if not request.user.is_authenticated:
        return Response({'ok': False, 'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
    
    try:
        template_id = request.data.get('template_id')
        email_text = request.data.get('email_text', '')
        
        template = EmailTemplate.objects.get(id=template_id, user=request.user)
        
        # Use Gemini to customize the template based on email content
        prompt = f"""
        Customize the following email template based on the original email content.
        Maintain the {template.tone} tone and structure of the template.
        
        Original Email:
        {email_text}
        
        Template:
        Subject: {template.subject}
        Body: {template.body}
        
        Customized Email:
        """
        
        customized_email = gemini.generate_reply(prompt)
        
        return Response({
            'ok': True,
            'customized_email': customized_email,
            'template_name': template.name
        })
    except EmailTemplate.DoesNotExist:
        return Response({'ok': False, 'error': 'Template not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error applying template: {str(e)}", exc_info=True)
        return Response({'ok': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

########################################
# API: Delete email
########################################
@api_view(['DELETE'])
@csrf_exempt
def delete_email_view(request, message_id):
    """Delete an email by moving it to trash"""
    try:
        service = get_gmail_service(user=request.user if request.user.is_authenticated else None)
        if not service:
            return Response({'ok': False, 'error': 'Failed to authenticate. Please reconnect your Gmail account.'}, 
                          status=status.HTTP_401_UNAUTHORIZED)
        
        # Log the attempt
        logger.info(f"Attempting to delete email {message_id}")
        
        # Delete by moving to trash
        success = delete_email(service, message_id)
        if success:
            # Clear the cache for unread emails to ensure fresh data
            try:
                # Try to clear by pattern if supported
                cache.delete_many([key for key in cache.keys('*gmail_unread_*')])
            except (AttributeError, NotImplementedError):
                # Fallback: clear entire cache if pattern deletion not supported
                cache.clear()
            
            logger.info(f"Successfully deleted email {message_id}")
            return Response({'ok': True})
        else:
            logger.error(f"Failed to delete email {message_id}")
            return Response({'ok': False, 'error': 'Failed to delete email. The email may have been already deleted.'}, 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        logger.error(f"Error deleting email: {str(e)}", exc_info=True)
        return Response({'ok': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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

########################################
# NEW: Workflow Automation Views
########################################

@api_view(['POST'])
def set_reminder_view(request):
    if not request.user.is_authenticated:
        return Response({'ok': False, 'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
    
    email_id = request.data.get('email_id')
    reminder_time = request.data.get('reminder_time')
    message = request.data.get('message', '')
    
    if not email_id or not reminder_time:
        return Response({'ok': False, 'error': 'email_id and reminder_time are required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Parse reminder_time (expecting ISO format)
        from datetime import datetime
        reminder_time = datetime.fromisoformat(reminder_time)
    except ValueError:
        return Response({'ok': False, 'error': 'Invalid reminder_time format. Use ISO format.'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        reminder = ReminderService.set_reminder(request.user, email_id, reminder_time, message)
        return Response({'ok': True, 'reminder_id': reminder.id})
    except Exception as e:
        logger.error(f"Error setting reminder: {str(e)}", exc_info=True)
        
        # Check if the error is due to missing table
        if "does not exist" in str(e):
            return Response({
                'ok': False, 
                'error': 'Reminder table not created yet. Please run migrations.',
                'table_missing': True
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({'ok': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def get_reminders_view(request):
    """Get all reminders for the current user"""
    try:
        if not request.user.is_authenticated:
            return Response({'ok': False, 'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        
        # Check if the Reminder table exists
        from django.db import connection
        table_exists = False
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'inbox_reminder'")
                table_exists = cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Error checking if table exists: {str(e)}")
        
        if not table_exists:
            logger.warning("Reminder table does not exist. Returning empty reminders list.")
            return Response({'ok': True, 'reminders': [], 'table_missing': True})
        
        # Get reminders from the service with error handling
        try:
            reminders = ReminderService.get_reminders(request.user)
        except Exception as e:
            # Check if the error is due to missing table
            if "does not exist" in str(e):
                logger.warning(f"Reminder table does not exist. Returning empty reminders list.")
                return Response({'ok': True, 'reminders': [], 'table_missing': True})
            # Re-raise the exception if it's not about a missing table
            raise
        
        # Format the response
        reminder_data = []
        for reminder in reminders:
            reminder_data.append({
                'id': reminder.id,
                'email_id': reminder.email_id,
                'reminder_time': reminder.reminder_time.isoformat(),
                'message': reminder.message,
                'is_due': reminder.is_due,
                'completed': reminder.completed
            })
        
        return Response({'ok': True, 'reminders': reminder_data})
    except Exception as e:
        logger.error(f"Error fetching reminders: {str(e)}", exc_info=True)
        
        # Check if the error is due to missing table
        if "does not exist" in str(e):
            return Response({
                'ok': True,  # Return ok: True with empty list to avoid breaking the UI
                'reminders': [],
                'table_missing': True,
                'message': 'Reminder table not created yet. Please run migrations.'
            })
        
        return Response({'ok': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
def schedule_email_view(request):
    if not request.user.is_authenticated:
        return Response({'ok': False, 'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
    
    email_id = request.data.get('email_id')
    scheduled_time = request.data.get('scheduled_time')
    
    if not email_id or not scheduled_time:
        return Response({'ok': False, 'error': 'email_id and scheduled_time are required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Parse scheduled_time (expecting ISO format)
        from datetime import datetime
        scheduled_time = datetime.fromisoformat(scheduled_time)
    except ValueError:
        return Response({'ok': False, 'error': 'Invalid scheduled_time format. Use ISO format.'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        scheduled_email = SchedulingService.schedule_email(request.user, email_id, scheduled_time)
        return Response({'ok': True, 'scheduled_email_id': scheduled_email.id})
    except Exception as e:
        logger.error(f"Error scheduling email: {str(e)}", exc_info=True)
        
        # Check if the error is due to missing table
        if "does not exist" in str(e):
            return Response({
                'ok': False, 
                'error': 'Scheduled email table not created yet. Please run migrations.',
                'table_missing': True
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({'ok': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def get_scheduled_emails_view(request):
    if not request.user.is_authenticated:
        return Response({'ok': False, 'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
    
    try:
        scheduled_emails = SchedulingService.get_scheduled_emails(request.user)
        serializer = ScheduledEmailSerializer(scheduled_emails, many=True)
        return Response({'ok': True, 'scheduled_emails': serializer.data})
    except Exception as e:
        logger.error(f"Error fetching scheduled emails: {str(e)}", exc_info=True)
        
        # Check if the error is due to missing table
        if "does not exist" in str(e):
            return Response({
                'ok': True,  # Return ok: True with empty list to avoid breaking the UI
                'scheduled_emails': [],
                'table_missing': True,
                'message': 'Scheduled email table not created yet. Please run migrations.'
            })
        
        return Response({'ok': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
def categorize_email_view(request):
    if not request.user.is_authenticated:
        return Response({'ok': False, 'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
    
    email_id = request.data.get('email_id')
    category = request.data.get('category')
    
    if not email_id or not category:
        return Response({'ok': False, 'error': 'email_id and category are required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        email_categorization = CategorizationService.categorize_email(request.user, email_id, category)
        return Response({'ok': True, 'category': email_categorization.category.name})  # FIXED: Use .name
    except ValueError as e:
        return Response({'ok': False, 'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Error categorizing email: {str(e)}", exc_info=True)
        
        # Check if the error is due to missing table
        if "does not exist" in str(e):
            return Response({
                'ok': False, 
                'error': 'Category tables not created yet. Please run migrations.',
                'table_missing': True
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({'ok': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
def auto_categorize_email_view(request):
    if not request.user.is_authenticated:
        return Response({'ok': False, 'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
    
    email_id = request.data.get('email_id')
    email_content = request.data.get('email_content')
    
    if not email_id or not email_content:
        return Response({'ok': False, 'error': 'email_id and email_content are required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        email_categorization = CategorizationService.auto_categorize_email(request.user, email_id, email_content)
        return Response({'ok': True, 'category': email_categorization.category.name})  # FIXED: Use .name
    except Exception as e:
        logger.error(f"Error auto-categorizing email: {str(e)}", exc_info=True)
        
        # Check if the error is due to missing table
        if "does not exist" in str(e):
            return Response({
                'ok': False, 
                'error': 'Category tables not created yet. Please run migrations.',
                'table_missing': True
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({'ok': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
def set_priority_view(request):
    if not request.user.is_authenticated:
        return Response({'ok': False, 'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
    
    email_id = request.data.get('email_id')
    priority = request.data.get('priority')
    
    if not email_id or priority is None:
        return Response({'ok': False, 'error': 'email_id and priority are required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        priority = int(priority)
    except ValueError:
        return Response({'ok': False, 'error': 'priority must be an integer'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        email_priority = PriorityScoringService.set_priority(request.user, email_id, priority)
        return Response({'ok': True, 'priority': email_priority.priority})
    except ValueError as e:
        return Response({'ok': False, 'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Error setting priority: {str(e)}", exc_info=True)
        
        # Check if the error is due to missing table
        if "does not exist" in str(e):
            return Response({
                'ok': False, 
                'error': 'Priority table not created yet. Please run migrations.',
                'table_missing': True
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({'ok': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
def auto_score_priority_view(request):
    if not request.user.is_authenticated:
        return Response({'ok': False, 'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
    
    email_id = request.data.get('email_id')
    email_content = request.data.get('email_content')
    
    if not email_id or not email_content:
        return Response({'ok': False, 'error': 'email_id and email_content are required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        email_priority = PriorityScoringService.auto_score_priority(request.user, email_id, email_content)
        return Response({'ok': True, 'priority': email_priority.priority})
    except Exception as e:
        logger.error(f"Error auto-scoring priority: {str(e)}", exc_info=True)
        
        # Check if the error is due to missing table
        if "does not exist" in str(e):
            return Response({
                'ok': False, 
                'error': 'Priority table not created yet. Please run migrations.',
                'table_missing': True
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({'ok': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# Add to your views
def debug_gmail_auth(request):
    try:
        service = get_gmail_service(user=request.user)
        if service:
            profile = service.users().getProfile(userId='me').execute()
            return JsonResponse({"status": "authenticated", "email": profile.get('emailAddress')})
        else:
            return JsonResponse({"status": "not_authenticated"})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)})
def create_sample_data_view(request):
    """Create sample data for testing"""
    try:
        if not request.user.is_authenticated:
            return JsonResponse({'ok': False, 'error': 'Authentication required'}, status=401)
        
        # Get the current user
        user = request.user
        
        # Create sample email templates
        templates = [
            {
                'name': 'Meeting Follow-up',
                'subject': 'Following up on our meeting',
                'body': 'Hi {name},\n\nIt was great meeting with you today. As discussed, I will be sending over the {document} by {time}.\n\nBest regards,\n{my_name}',
                'tone': 'professional'
            },
            {
                'name': 'Project Update',
                'subject': 'Project {project_name} Update',
                'body': 'Hi Team,\n\nHere is the weekly update for {project_name}:\n\n- Progress: {progress}%\n- Next milestone: {milestone}\n- blockers: {blockers}\n\nLet me know if you have any questions.\n\nThanks,\n{my_name}',
                'tone': 'professional'
            },
            {
                'name': 'Thank You Note',
                'subject': 'Thank you for your help',
                'body': 'Hi {name},\n\nI wanted to thank you for helping with {task}. Your assistance was invaluable!\n\nBest,\n{my_name}',
                'tone': 'friendly'
            }
        ]
        
        created_templates = []
        for template_data in templates:
            template, created = EmailTemplate.objects.get_or_create(
                user=user,
                name=template_data['name'],
                defaults=template_data
            )
            if created:
                created_templates.append(template.name)
        
        # Create sample reminders
        reminders = [
            {
                'email_id': 'sample_email_1',
                'reminder_time': datetime.now() + timedelta(days=1),
                'message': 'Follow up on the project proposal'
            },
            {
                'email_id': 'sample_email_2',
                'reminder_time': datetime.now() + timedelta(days=3),
                'message': 'Check if client has reviewed the contract'
            },
            {
                'email_id': 'sample_email_3',
                'reminder_time': datetime.now() + timedelta(hours=6),
                'message': 'Reply to the meeting invitation'
            }
        ]
        
        created_reminders = []
        for reminder_data in reminders:
            reminder, created = Reminder.objects.get_or_create(
                user=user,
                email_id=reminder_data['email_id'],
                defaults=reminder_data
            )
            if created:
                created_reminders.append(reminder.message)
        
        return JsonResponse({
            'ok': True,
            'created_templates': created_templates,
            'created_reminders': created_reminders
        })
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)
# Add this view to handle running migrations
@csrf_exempt
@require_POST
def run_migrations_view(request):
    """Run database migrations to create missing tables"""
    try:
        from django.core.management import call_command
        call_command('migrate', 'inbox', verbosity=2)
        return JsonResponse({"ok": True, "message": "Migrations completed successfully"})
    except Exception as e:
        logger.error(f"Error running migrations: {str(e)}", exc_info=True)
        return JsonResponse({"ok": False, "error": str(e)}, status=500)