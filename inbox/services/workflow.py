# inbox/services/workflow.py

from datetime import datetime, timedelta
from django.utils import timezone
from ..models import Reminder, ScheduledEmail, EmailCategory, EmailCategorization, EmailPriority
from . import gemini

class ReminderService:
    """Service for managing email reminders"""
    
    @staticmethod
    def set_reminder(user, email_id, reminder_time, message=''):
        """
        Set a reminder for an email
        
        Args:
            user: User object
            email_id: ID of the email
            reminder_time: datetime when reminder should trigger
            message: Optional reminder message
            
        Returns:
            Reminder object
        """
        reminder = Reminder.objects.create(
            user=user,
            email_id=email_id,
            reminder_time=reminder_time,
            message=message
        )
        return reminder
    
    @staticmethod
    def get_reminders(user):
        """
        Get all active reminders for a user
        
        Args:
            user: User object
            
        Returns:
            QuerySet of Reminder objects
        """
        return Reminder.objects.filter(user=user, completed=False).order_by('reminder_time')
    
    @staticmethod
    def complete_reminder(reminder_id):
        """
        Mark a reminder as completed
        
        Args:
            reminder_id: ID of the reminder to complete
        """
        try:
            reminder = Reminder.objects.get(id=reminder_id)
            reminder.completed = True
            reminder.save()
            return True
        except Reminder.DoesNotExist:
            return False


class SchedulingService:
    """Service for scheduling emails"""
    
    @staticmethod
    def schedule_email(user, email_id, scheduled_time):
        """
        Schedule an email to be sent later
        
        Args:
            user: User object
            email_id: ID of the email
            scheduled_time: datetime when email should be sent
            
        Returns:
            ScheduledEmail object
        """
        scheduled_email = ScheduledEmail.objects.create(
            user=user,
            email_id=email_id,
            scheduled_time=scheduled_time
        )
        return scheduled_email
    
    @staticmethod
    def get_scheduled_emails(user):
        """
        Get all unsent scheduled emails for a user
        
        Args:
            user: User object
            
        Returns:
            QuerySet of ScheduledEmail objects
        """
        return ScheduledEmail.objects.filter(user=user, sent=False).order_by('scheduled_time')
    
    @staticmethod
    def send_scheduled_email(scheduled_email_id):
        """
        Send a scheduled email
        
        Args:
            scheduled_email_id: ID of the scheduled email
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            scheduled_email = ScheduledEmail.objects.get(id=scheduled_email_id)
            # Here you would implement the actual email sending logic
            # For now, we'll just mark it as sent
            scheduled_email.sent = True
            scheduled_email.save()
            return True
        except ScheduledEmail.DoesNotExist:
            return False


class CategorizationService:
    """Service for categorizing emails"""
    
    VALID_CATEGORIES = ['Work', 'Personal', 'Social', 'Promotions', 'Finance', 'Travel', 'Other']
    
    @staticmethod
    def categorize_email(user, email_id, category):
        """
        Manually categorize an email
        
        Args:
            user: User object
            email_id: ID of the email
            category: Category name
            
        Returns:
            EmailCategorization object
            
        Raises:
            ValueError: If category is not valid
        """
        if category not in CategorizationService.VALID_CATEGORIES:
            raise ValueError(f"Invalid category. Valid categories are: {', '.join(CategorizationService.VALID_CATEGORIES)}")
        
        # Get or create the category
        category_obj, created = EmailCategory.objects.get_or_create(
            user=user,
            name=category,
            defaults={'color': '#007bff'}
        )
        
        # Create or update the categorization
        categorization, created = EmailCategorization.objects.get_or_create(
            user=user,
            email_id=email_id,
            defaults={'category': category_obj}
        )
        
        if not created:
            categorization.category = category_obj
            categorization.save()
            
        return categorization
    
    @staticmethod
    def get_email_category(user, email_id):
        """
        Get the category for an email
        
        Args:
            user: User object
            email_id: ID of the email
            
        Returns:
            EmailCategory object or None
        """
        try:
            # Fixed: Use EmailCategorization model and select_related to get the category
            categorization = EmailCategorization.objects.select_related('category').get(
                user=user, 
                email_id=email_id
            )
            return categorization.category
        except EmailCategorization.DoesNotExist:
            return None
    
    @staticmethod
    def auto_categorize_email(user, email_id, email_content):
        """
        Automatically categorize an email using AI
        
        Args:
            user: User object
            email_id: ID of the email
            email_content: Content of the email
            
        Returns:
            EmailCategorization object
        """
        # Create a prompt for categorization
        prompt = f"""
        Categorize the following email into one of these categories: {', '.join(CategorizationService.VALID_CATEGORIES)}
        
        Email content:
        {email_content}
        
        Category:
        """
        
        # Use Gemini to determine the category
        category_response = gemini.generate_reply(prompt)
        
        # Extract the category from the response
        category = "Other"  # Default
        for valid_category in CategorizationService.VALID_CATEGORIES:
            if valid_category.lower() in category_response.lower():
                category = valid_category
                break
        
        # Save the category
        return CategorizationService.categorize_email(user, email_id, category)


class PriorityScoringService:
    """Service for scoring email priority"""
    
    @staticmethod
    def set_priority(user, email_id, priority):
        """
        Manually set the priority of an email
        
        Args:
            user: User object
            email_id: ID of the email
            priority: Priority score (1-10)
            
        Returns:
            EmailPriority object
            
        Raises:
            ValueError: If priority is not valid
        """
        if not isinstance(priority, int) or priority < 1 or priority > 10:
            raise ValueError("Priority must be an integer between 1 and 10")
        
        email_priority, created = EmailPriority.objects.get_or_create(
            user=user,
            email_id=email_id,
            defaults={'priority': priority}
        )
        
        if not created:
            email_priority.priority = priority
            email_priority.save()
            
        return email_priority
    
    @staticmethod
    def get_email_priority(user, email_id):
        """
        Get the priority for an email
        
        Args:
            user: User object
            email_id: ID of the email
            
        Returns:
            EmailPriority object or None
        """
        try:
            return EmailPriority.objects.get(user=user, email_id=email_id)
        except EmailPriority.DoesNotExist:
            return None
    
    @staticmethod
    def auto_score_priority(user, email_id, email_content):
        """
        Automatically score the priority of an email using AI
        
        Args:
            user: User object
            email_id: ID of the email
            email_content: Content of the email
            
        Returns:
            EmailPriority object
        """
        # Create a prompt for priority scoring
        prompt = f"""
        Analyze the following email and assign a priority score from 1 to 10, where:
        1-3 = Low priority (can be ignored or dealt with later)
        4-6 = Medium priority (should be addressed within a few days)
        7-10 = High priority (requires immediate attention)
        
        Consider factors like:
        - Urgency of the request
        - Importance of the sender
        - Potential consequences of not responding
        - Time sensitivity
        
        Email content:
        {email_content}
        
        Priority score (1-10):
        """
        
        # Use Gemini to determine the priority
        priority_response = gemini.generate_reply(prompt)
        
        # Extract the priority score from the response
        priority = 5  # Default
        try:
            # Look for a number in the response
            import re
            match = re.search(r'\b([1-9]|10)\b', priority_response)
            if match:
                priority = int(match.group(1))
        except:
            pass
        
        # Ensure priority is within valid range
        priority = max(1, min(10, priority))
        
        # Save the priority
        return PriorityScoringService.set_priority(user, email_id, priority)