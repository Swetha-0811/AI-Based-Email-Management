from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class GmailCredentials(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    token = models.TextField()
    refresh_token = models.TextField()
    token_uri = models.CharField(max_length=255)
    client_id = models.CharField(max_length=255)
    client_secret = models.CharField(max_length=255)
    scopes = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Gmail Credential"
        verbose_name_plural = "Gmail Credentials"
        
    def __str__(self):
        return f"{self.user.username if self.user else 'Anonymous'} - {self.client_id}"

class GeneratedDraft(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    original_email_id = models.CharField(max_length=255)  # ID of the original email
    subject = models.CharField(max_length=255)
    recipient = models.CharField(max_length=255)
    reply_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_sent = models.BooleanField(default=False)
    
    def __str__(self):
        return f"Draft for {self.subject} to {self.recipient}"

class ImportantEmail(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    email_id = models.CharField(max_length=255)  # Changed from message_id to email_id
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('user', 'email_id')  # Updated to use email_id
    
    def __str__(self):
        return f"Important email {self.email_id} for {self.user.username}"

class UserSettings(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    reply_tone = models.CharField(max_length=20, choices=[
        ('professional', 'Professional'),
        ('friendly', 'Friendly'),
        ('casual', 'Casual'),
    ], default='professional')
    auto_reply_enabled = models.BooleanField(default=True)
    refresh_interval = models.IntegerField(default=5, help_text="Refresh interval in minutes")
    theme = models.CharField(max_length=10, choices=[
        ('light', 'Light'),
        ('dark', 'Dark'),
    ], default='light')
    
    def __str__(self):
        return f"Settings for {self.user.username}"

class EmailTemplate(models.Model):
    """Email template model for storing reusable email templates"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    subject = models.CharField(max_length=200)
    body = models.TextField()
    tone = models.CharField(max_length=20, choices=[
        ('professional', 'Professional'),
        ('friendly', 'Friendly'),
        ('casual', 'Casual'),
        ('formal', 'Formal'),
        ('apologetic', 'Apologetic'),
    ], default='professional')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_default = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ['user', 'name']
        verbose_name = "Email Template"
        verbose_name_plural = "Email Templates"
        
    def __str__(self):
        return f"{self.name} - {self.user.username}"

class ThreadAnalysis(models.Model):
    """Store results of email thread analysis"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    thread_id = models.CharField(max_length=255)
    main_topic = models.TextField()
    key_points = models.JSONField(default=list)
    decisions = models.TextField(blank=True)
    action_items = models.TextField(blank=True)
    overall_sentiment = models.CharField(max_length=20, choices=[
        ('positive', 'Positive'),
        ('negative', 'Negative'),
        ('neutral', 'Neutral'),
    ])
    message_count = models.IntegerField()
    analyzed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['user', 'thread_id']
        verbose_name = "Thread Analysis"
        verbose_name_plural = "Thread Analyses"
        
    def __str__(self):
        return f"Thread Analysis {self.thread_id} for {self.user.username}"

class MessageAnalysis(models.Model):
    """Store analysis of individual messages within a thread"""
    thread_analysis = models.ForeignKey(ThreadAnalysis, on_delete=models.CASCADE, related_name='message_analyses')
    message_id = models.CharField(max_length=255)
    from_email = models.EmailField()
    date = models.DateTimeField()
    subject = models.CharField(max_length=255)
    sentiment = models.CharField(max_length=20, choices=[
        ('positive', 'Positive'),
        ('negative', 'Negative'),
        ('neutral', 'Neutral'),
    ])
    key_points = models.JSONField(default=list)
    summary = models.TextField()
    
    class Meta:
        unique_together = ['thread_analysis', 'message_id']
        verbose_name = "Message Analysis"
        verbose_name_plural = "Message Analyses"
        
    def __str__(self):
        return f"Message Analysis {self.message_id} in thread {self.thread_analysis.thread_id}"

class SentimentAnalysis(models.Model):
    """Store sentiment analysis results for emails"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    email_id = models.CharField(max_length=255)  # Gmail message ID
    sentiment = models.CharField(max_length=20, choices=[
        ('positive', 'Positive'),
        ('negative', 'Negative'),
        ('neutral', 'Neutral'),
    ])
    confidence = models.DecimalField(max_digits=5, decimal_places=2)  # 0.00 to 100.00
    urgency = models.CharField(max_length=10, choices=[
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ])
    suggested_tone = models.CharField(max_length=20, choices=[
        ('professional', 'Professional'),
        ('friendly', 'Friendly'),
        ('casual', 'Casual'),
        ('formal', 'Formal'),
        ('apologetic', 'Apologetic'),
    ])
    key_indicators = models.JSONField(default=list)
    analyzed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['user', 'email_id']
        verbose_name = "Sentiment Analysis"
        verbose_name_plural = "Sentiment Analyses"
        
    def __str__(self):
        return f"Sentiment Analysis for {self.email_id}: {self.sentiment}"

class VoiceCommandLog(models.Model):
    """Log voice commands for analytics and debugging"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    command = models.CharField(max_length=255)
    action_type = models.CharField(max_length=50)
    recognized = models.BooleanField(default=True)
    response_time = models.DurationField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Voice Command Log"
        verbose_name_plural = "Voice Command Logs"
        
    def __str__(self):
        return f"Voice Command: {self.command} by {self.user.username}"

class EmailCategory(models.Model):
    """Categorize emails for better organization"""
    CATEGORY_CHOICES = [
        ('work', 'Work'),
        ('personal', 'Personal'),
        ('social', 'Social'),
        ('promotions', 'Promotions'),
        ('updates', 'Updates'),
        ('forums', 'Forums'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    color = models.CharField(max_length=7, default='#007bff')  # Hex color code
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['user', 'name']
        verbose_name = "Email Category"
        verbose_name_plural = "Email Categories"
        
    def __str__(self):
        return f"{self.name} - {self.user.username}"

class EmailCategorization(models.Model):
    """Link emails to categories"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    email_id = models.CharField(max_length=255)
    category = models.ForeignKey(EmailCategory, on_delete=models.CASCADE)
    confidence = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['user', 'email_id']
        verbose_name = "Email Categorization"
        verbose_name_plural = "Email Categorizations"
        
    def __str__(self):
        return f"Email {self.email_id} categorized as {self.category.name}"

# NEW MODELS FOR WORKFLOW AUTOMATION

class Reminder(models.Model):
    """Follow-up reminder system for emails"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    email_id = models.CharField(max_length=255)  # Gmail message ID
    reminder_time = models.DateTimeField()
    message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed = models.BooleanField(default=False)
    
    class Meta:
        verbose_name = "Reminder"
        verbose_name_plural = "Reminders"
    
    def __str__(self):
        return f"Reminder for {self.email_id} at {self.reminder_time}"
    
    @property
    def is_due(self):
        """Check if the reminder is due"""
        return timezone.now() >= self.reminder_time and not self.completed

class ScheduledEmail(models.Model):
    """Email scheduling capability"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    email_id = models.CharField(max_length=255)  # Gmail message ID
    scheduled_time = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    sent = models.BooleanField(default=False)
    
    class Meta:
        verbose_name = "Scheduled Email"
        verbose_name_plural = "Scheduled Emails"
    
    def __str__(self):
        return f"Scheduled email {self.email_id} at {self.scheduled_time}"
    
    @property
    def is_ready_to_send(self):
        """Check if the email is ready to be sent"""
        return timezone.now() >= self.scheduled_time and not self.sent

class EmailPriority(models.Model):
    """Priority scoring algorithm for emails"""
    PRIORITY_CHOICES = [
        (1, 'Low'),
        (2, 'Medium'),
        (3, 'High'),
        (4, 'Urgent'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    email_id = models.CharField(max_length=255)  # Gmail message ID
    priority = models.IntegerField(choices=PRIORITY_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['user', 'email_id']
        verbose_name = "Email Priority"
        verbose_name_plural = "Email Priorities"
    
    def __str__(self):
        return f"{self.email_id} - Priority {self.priority}"
    
    @property
    def priority_label(self):
        """Get the human-readable priority label"""
        return dict(self.PRIORITY_CHOICES).get(self.priority, 'Unknown')