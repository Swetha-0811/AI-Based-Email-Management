import os
import json
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator
from .services.gmail import (
    build_flow, get_gmail_service, fetch_unread, create_gmail_draft, _save_creds_to_db
)
from .services import gemini
from django.urls import resolve

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
            "status": "not_matched",
            "error": str(e),
            "path": path_info
        })

########################################
# Home page
########################################
def home_view(request):
    service = get_gmail_service(user=request.user if request.user.is_authenticated else None)
    if not service:
        return render(request, "inbox/home.html", {"authed": False})
    return render(request, "inbox/home.html", {"authed": True})

########################################
# OAuth start & callback
########################################
def oauth_start(request):
    redirect_uri = request.build_absolute_uri("/oauth/callback/")
    flow = build_flow(redirect_uri)

    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    request.session["oauth_state"] = state
    return redirect(auth_url)

def oauth_callback(request):
    expected = request.session.get("oauth_state")
    returned = request.GET.get("state")
    if not expected or expected != returned:
        return HttpResponseBadRequest("Invalid OAuth state. Please try again.")

    redirect_uri = request.build_absolute_uri("/oauth/callback/")
    flow = build_flow(redirect_uri)

    flow.fetch_token(authorization_response=request.build_absolute_uri())
    creds = flow.credentials

    _save_creds_to_db(
        creds,
        user=request.user if request.user.is_authenticated else None
    )

    request.session.pop("oauth_state", None)
    return redirect("home")

########################################
# API: unread emails with pagination
########################################
@require_GET
def unread_emails_view(request):
    # Get Gmail service object
    service = get_gmail_service(user=request.user if request.user.is_authenticated else None)
    if not service:
        return JsonResponse({"ok": False, "error": "Not authorized. Connect Gmail first."}, status=401)

    try:
        # Fetch unread emails
        emails = fetch_unread(service)

        if not emails:
            return JsonResponse({"ok": False, "error": "No unread emails found."}, status=404)

        # Paginate emails (10 per page)
        paginator = Paginator(emails, 10)
        page_number = request.GET.get('page', 1)  # Default to page 1 if not specified
        page_obj = paginator.get_page(page_number)

        # Serialize emails to make them JSON serializable
        email_list = []
        for email in page_obj.object_list:
            email_data = {
                'id': email.get('id'),
                'from': email.get('from'),
                'subject': email.get('subject'),
                'snippet': email.get('snippet'),
                'date': email.get('date'),
                'unread': email.get('unread', False),
                'body_text': email.get('body_text')
            }
            email_list.append(email_data)

        # Return the paginated data
        return JsonResponse({
            "ok": True,
            "emails": email_list,  # List of emails for the current page
            "total_pages": paginator.num_pages,  # Total number of pages
            "current_page": page_obj.number,  # Current page number
        })
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)

########################################
# API: generate reply with Gemini
########################################
@csrf_exempt
@require_POST
def generate_reply_view(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
        email_text = payload.get("email_text", "")
        if not email_text:
            return HttpResponseBadRequest("email_text is required")

        summary = gemini.summarize_email(email_text)
        draft = gemini.generate_reply(email_text, summary=summary)

        return JsonResponse({"ok": True, "summary": summary, "draft_reply": draft})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)

########################################
# API: save draft to Gmail
########################################
@csrf_exempt
@require_POST
def save_draft_view(request):
    service = get_gmail_service(user=request.user if request.user.is_authenticated else None)
    if not service:
        return JsonResponse({"ok": False, "error": "Not authorized. Connect Gmail first."}, status=401)

    try:
        payload = json.loads(request.body.decode("utf-8"))
        to_email = payload.get("to")
        subject = payload.get("subject")
        body = payload.get("body")
        if not all([to_email, subject, body]):
            return HttpResponseBadRequest("to, subject, body are required")

        draft_id = create_gmail_draft(service, to_email, subject, body)
        return JsonResponse({"ok": True, "draft_id": draft_id})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)

# Logout view
def logout_view(request):
    # Clear any OAuth-related session data
    request.session.flush()  # This clears the entire session data

    # Optionally, delete any saved credentials from the database, if required
    # _clear_credentials_from_db(user=request.user if request.user.is_authenticated else None)

    # Redirect to the Gmail OAuth start view
    return redirect('oauth_start')  # This will trigger the OAuth flow

