from django.contrib.sessions.models import Session
from django.utils import timezone
from django.contrib.sessions.exceptions import SessionInterrupted
from django.shortcuts import redirect
from django.urls import reverse
import logging

logger = logging.getLogger(__name__)

class SessionCleanupMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_response(self, request, response):
        # Clean up expired sessions
        try:
            now = timezone.now()
            expired_sessions = Session.objects.filter(expire_date__lt=now)
            count = expired_sessions.count()
            
            if count > 0:
                expired_sessions.delete()
                logger.info(f"Cleaned up {count} expired sessions")
        except Exception as e:
            logger.error(f"Error cleaning up sessions: {str(e)}")
        
        return response


class CustomSessionMiddleware:
    """
    Custom session middleware to handle SessionInterrupted exceptions
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if isinstance(exception, SessionInterrupted):
            logger.warning("Session interrupted, redirecting to login")
            return redirect(reverse('oauth_start'))
        
        return None

    def process_response(self, request, response):
        # Handle the case where session was deleted during request processing
        try:
            # Check if session is still valid
            if hasattr(request, 'session') and request.session.session_key:
                # Try to access session to see if it's still valid
                try:
                    session_key = request.session.session_key
                except:
                    # If session is invalid, redirect to login
                    logger.warning("Session became invalid during request processing")
                    return redirect(reverse('oauth_start'))
        except Exception as e:
            logger.error(f"Error checking session validity: {str(e)}")
            return redirect(reverse('oauth_start'))
        
        return response