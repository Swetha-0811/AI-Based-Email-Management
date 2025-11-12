from django.core.management.base import BaseCommand
from django.contrib.sessions.models import Session
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Clean up expired sessions'

    def handle(self, *args, **options):
        try:
            now = timezone.now()
            expired_sessions = Session.objects.filter(expire_date__lt=now)
            count = expired_sessions.count()
            
            if count > 0:
                expired_sessions.delete()
                self.stdout.write(self.style.SUCCESS(f'Successfully cleaned up {count} expired sessions'))
                logger.info(f"Successfully cleaned up {count} expired sessions via management command")
            else:
                self.stdout.write(self.style.SUCCESS('No expired sessions to clean up'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error cleaning up sessions: {str(e)}'))
            logger.error(f"Error cleaning up sessions via management command: {str(e)}")