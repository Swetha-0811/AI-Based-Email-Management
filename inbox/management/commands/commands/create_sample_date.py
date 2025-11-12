from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from inbox.models import EmailTemplate, Reminder
from datetime import datetime, timedelta

class Command(BaseCommand):
    help = 'Create sample data for testing'

    def handle(self, *args, **options):
        # Get the first user (or create one if none exists)
        user = User.objects.first()
        if not user:
            user = User.objects.create_user(
                username='testuser',
                email='test@example.com',
                password='testpass123'
            )
        
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
        
        for template_data in templates:
            template, created = EmailTemplate.objects.get_or_create(
                user=user,
                name=template_data['name'],
                defaults=template_data
            )
            if created:
                self.stdout.write(f"Created template: {template.name}")
        
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
        
        for reminder_data in reminders:
            reminder, created = Reminder.objects.get_or_create(
                user=user,
                email_id=reminder_data['email_id'],
                defaults=reminder_data
            )
            if created:
                self.stdout.write(f"Created reminder: {reminder.message}")
        
        self.stdout.write(self.style.SUCCESS('Sample data created successfully!'))