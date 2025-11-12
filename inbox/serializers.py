from rest_framework import serializers
from .models import (
    EmailTemplate, ThreadAnalysis, MessageAnalysis, 
    SentimentAnalysis, VoiceCommandLog, EmailCategory, 
    EmailCategorization, Reminder, ScheduledEmail, EmailPriority
)

class EmailSerializer(serializers.Serializer):
    id = serializers.CharField()
    threadId = serializers.CharField(required=False, allow_blank=True)
    snippet = serializers.CharField(allow_blank=True)
    subject = serializers.CharField(allow_blank=True)
    from_field = serializers.SerializerMethodField()  # Changed to SerializerMethodField
    to = serializers.SerializerMethodField()  # Changed to SerializerMethodField
    date = serializers.CharField(allow_blank=True)
    body_text = serializers.CharField(allow_blank=True, required=False, default='')
    is_important = serializers.BooleanField(required=False, default=False)
    # New fields for workflow automation
    category = serializers.CharField(allow_blank=True, required=False, default='')
    priority = serializers.IntegerField(required=False, default=0)
    
    def get_from_field(self, obj):
        """Extract and format sender information from Gmail API object"""
        from_data = obj.get('from', '')
        
        # If it's already a string, return as is
        if isinstance(from_data, str):
            return from_data
        
        # If it's a dictionary, extract name and email
        if isinstance(from_data, dict):
            name = from_data.get('name', '')
            email = from_data.get('emailAddress', '')
            
            if name and email:
                return f"{name} <{email}>"
            elif email:
                return email
            elif name:
                return name
            else:
                return 'Unknown'
        
        # Fallback for any other type
        return str(from_data) if from_data else 'Unknown'
    
    def get_to(self, obj):
        """Extract and format recipient information from Gmail API object"""
        to_data = obj.get('to', '')
        
        # If it's already a string, return as is
        if isinstance(to_data, str):
            return to_data
        
        # If it's a list of dictionaries (multiple recipients)
        if isinstance(to_data, list):
            recipients = []
            for recipient in to_data:
                if isinstance(recipient, dict):
                    name = recipient.get('name', '')
                    email = recipient.get('emailAddress', '')
                    if name and email:
                        recipients.append(f"{name} <{email}>")
                    elif email:
                        recipients.append(email)
                    elif name:
                        recipients.append(name)
                elif isinstance(recipient, str):
                    recipients.append(recipient)
            return ', '.join(recipients)
        
        # If it's a single dictionary
        if isinstance(to_data, dict):
            name = to_data.get('name', '')
            email = to_data.get('emailAddress', '')
            if name and email:
                return f"{name} <{email}>"
            elif email:
                return email
            elif name:
                return name
        
        # Fallback
        return str(to_data) if to_data else ''
    
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['subject'] = representation.get('subject') or '(no subject)'
        representation['from_field'] = representation.get('from_field') or '(unknown sender)'
        representation['body_text'] = representation.get('body_text') or ''
        return representation

class DraftSerializer(serializers.Serializer):
    """Separate serializer for drafts that doesn't require body_text"""
    id = serializers.CharField()
    subject = serializers.CharField(allow_blank=True)
    from_field = serializers.SerializerMethodField()  # Changed to SerializerMethodField
    date = serializers.CharField(allow_blank=True)
    snippet = serializers.CharField(allow_blank=True)
    is_draft = serializers.BooleanField(default=True)
    
    def get_from_field(self, obj):
        """Extract and format sender information from Gmail API object"""
        from_data = obj.get('from', '')
        
        # If it's already a string, return as is
        if isinstance(from_data, str):
            return from_data
        
        # If it's a dictionary, extract name and email
        if isinstance(from_data, dict):
            name = from_data.get('name', '')
            email = from_data.get('emailAddress', '')
            
            if name and email:
                return f"{name} <{email}>"
            elif email:
                return email
            elif name:
                return name
            else:
                return 'Unknown'
        
        # Fallback for any other type
        return str(from_data) if from_data else 'Unknown'
    
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        # Ensure subject and from_field have fallback values
        representation['subject'] = representation.get('subject', '(no subject)')
        representation['from_field'] = representation.get('from_field', 'Unknown')
        return representation

class EmailTemplateSerializer(serializers.ModelSerializer):
    """Serializer for EmailTemplate model"""
    class Meta:
        model = EmailTemplate
        fields = ['id', 'name', 'subject', 'body', 'tone', 'created_at', 'updated_at', 'is_default']
        read_only_fields = ['created_at', 'updated_at']

class ThreadAnalysisSerializer(serializers.ModelSerializer):
    """Serializer for ThreadAnalysis model"""
    message_analyses = serializers.SerializerMethodField()
    
    class Meta:
        model = ThreadAnalysis
        fields = [
            'id', 'thread_id', 'main_topic', 'key_points', 
            'decisions', 'action_items', 'overall_sentiment', 
            'message_count', 'analyzed_at', 'message_analyses'
        ]
        read_only_fields = ['analyzed_at']
    
    def get_message_analyses(self, obj):
        """Get all message analyses for this thread"""
        analyses = MessageAnalysis.objects.filter(thread_analysis=obj)
        return MessageAnalysisSerializer(analyses, many=True).data

class MessageAnalysisSerializer(serializers.ModelSerializer):
    """Serializer for MessageAnalysis model"""
    class Meta:
        model = MessageAnalysis
        fields = [
            'id', 'message_id', 'from_email', 'date', 'subject',
            'sentiment', 'key_points', 'summary'
        ]

class SentimentAnalysisSerializer(serializers.ModelSerializer):
    """Serializer for SentimentAnalysis model"""
    sentiment_display = serializers.CharField(source='get_sentiment_display', read_only=True)
    urgency_display = serializers.CharField(source='get_urgency_display', read_only=True)
    suggested_tone_display = serializers.CharField(source='get_suggested_tone_display', read_only=True)
    
    class Meta:
        model = SentimentAnalysis
        fields = [
            'id', 'email_id', 'sentiment', 'confidence', 'urgency',
            'suggested_tone', 'key_indicators', 'analyzed_at',
            'sentiment_display', 'urgency_display', 'suggested_tone_display'
        ]
        read_only_fields = ['analyzed_at']

class VoiceCommandLogSerializer(serializers.ModelSerializer):
    """Serializer for VoiceCommandLog model"""
    action_type_display = serializers.CharField(source='get_action_type_display', read_only=True)
    
    class Meta:
        model = VoiceCommandLog
        fields = [
            'id', 'command', 'action_type', 'recognized', 
            'response_time', 'created_at', 'action_type_display'
        ]
        read_only_fields = ['created_at']

class EmailCategorySerializer(serializers.ModelSerializer):
    """Serializer for EmailCategory model"""
    class Meta:
        model = EmailCategory
        fields = ['id', 'name', 'color', 'created_at']
        read_only_fields = ['created_at']

class EmailCategorizationSerializer(serializers.ModelSerializer):
    """Serializer for EmailCategorization model"""
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_color = serializers.CharField(source='category.color', read_only=True)
    
    class Meta:
        model = EmailCategorization
        fields = [
            'id', 'email_id', 'category', 'category_name', 
            'category_color', 'confidence', 'created_at'
        ]
        read_only_fields = ['created_at']

# NEW SERIALIZERS FOR WORKFLOW AUTOMATION

class ReminderSerializer(serializers.ModelSerializer):
    """Serializer for Reminder model"""
    is_due = serializers.BooleanField(read_only=True)
    priority_label = serializers.CharField(source='priority', read_only=True)
    
    class Meta:
        model = Reminder
        fields = [
            'id', 'email_id', 'reminder_time', 'message', 
            'created_at', 'completed', 'is_due'
        ]
        read_only_fields = ['created_at', 'is_due']

class ScheduledEmailSerializer(serializers.ModelSerializer):
    """Serializer for ScheduledEmail model"""
    is_ready_to_send = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = ScheduledEmail
        fields = [
            'id', 'email_id', 'scheduled_time', 
            'created_at', 'sent', 'is_ready_to_send'
        ]
        read_only_fields = ['created_at', 'is_ready_to_send']

class EmailPrioritySerializer(serializers.ModelSerializer):
    """Serializer for EmailPriority model"""
    priority_label = serializers.CharField(source='get_priority_display', read_only=True)
    
    class Meta:
        model = EmailPriority
        fields = [
            'id', 'email_id', 'priority', 'priority_label', 'created_at'
        ]
        read_only_fields = ['created_at']

# Serializers for API responses that don't directly map to models

class ThreadAnalysisResponseSerializer(serializers.Serializer):
    """Serializer for thread analysis API response"""
    thread_id = serializers.CharField()
    main_topic = serializers.CharField()
    key_points = serializers.ListField(child=serializers.CharField())
    decisions = serializers.CharField(allow_blank=True)
    action_items = serializers.CharField(allow_blank=True)
    overall_sentiment = serializers.CharField()
    message_count = serializers.IntegerField()
    message_analyses = MessageAnalysisSerializer(many=True)

class SentimentAnalysisResponseSerializer(serializers.Serializer):
    """Serializer for sentiment analysis API response"""
    sentiment = serializers.CharField()
    confidence = serializers.FloatField()
    urgency = serializers.CharField()
    suggested_tone = serializers.CharField()
    key_indicators = serializers.ListField(child=serializers.CharField())
    sentiment_score = serializers.FloatField(required=False)  # For future use

class TemplateApplicationSerializer(serializers.Serializer):
    """Serializer for template application request/response"""
    template_id = serializers.IntegerField()
    email_text = serializers.CharField()
    customized_email = serializers.CharField(required=False, read_only=True)
    template_name = serializers.CharField(required=False, read_only=True)

class VoiceCommandRequestSerializer(serializers.Serializer):
    """Serializer for voice command requests"""
    command = serializers.CharField(max_length=255)

class VoiceCommandResponseSerializer(serializers.Serializer):
    """Serializer for voice command responses"""
    ok = serializers.BooleanField()
    action = serializers.DictField()
    command = serializers.CharField()
    message = serializers.CharField()
    voice_output = serializers.CharField(required=False, allow_blank=True)
    commands_list = serializers.ListField(
        child=serializers.DictField(), 
        required=False
    )

class EmailThreadRequestSerializer(serializers.Serializer):
    """Serializer for email thread analysis requests"""
    email_text = serializers.CharField()
    thread_id = serializers.CharField(required=False, allow_blank=True)

class EmailAnalysisSummarySerializer(serializers.Serializer):
    """Serializer for email analysis summary"""
    total_emails = serializers.IntegerField()
    analyzed_emails = serializers.IntegerField()
    average_sentiment_score = serializers.FloatField()
    most_common_topics = serializers.ListField(child=serializers.CharField())
    urgency_distribution = serializers.DictField()
    response_suggestions = serializers.ListField(child=serializers.CharField())

# NEW SERIALIZERS FOR WORKFLOW AUTOMATION API REQUESTS/RESPONSES

class ReminderRequestSerializer(serializers.Serializer):
    """Serializer for reminder creation requests"""
    email_id = serializers.CharField(max_length=255)
    reminder_time = serializers.DateTimeField()
    message = serializers.CharField(required=False, allow_blank=True)

class ReminderResponseSerializer(serializers.Serializer):
    """Serializer for reminder responses"""
    ok = serializers.BooleanField()
    reminder_id = serializers.IntegerField(required=False)

class ScheduledEmailRequestSerializer(serializers.Serializer):
    """Serializer for email scheduling requests"""
    email_id = serializers.CharField(max_length=255)
    scheduled_time = serializers.DateTimeField()

class ScheduledEmailResponseSerializer(serializers.Serializer):
    """Serializer for scheduled email responses"""
    ok = serializers.BooleanField()
    scheduled_email_id = serializers.IntegerField(required=False)

class CategorizeEmailRequestSerializer(serializers.Serializer):
    """Serializer for email categorization requests"""
    email_id = serializers.CharField(max_length=255)
    category = serializers.ChoiceField(choices=[
        ('work', 'Work'),
        ('personal', 'Personal'),
        ('social', 'Social'),
        ('promotions', 'Promotions'),
        ('updates', 'Updates'),
        ('forums', 'Forums'),
    ])

class CategorizeEmailResponseSerializer(serializers.Serializer):
    """Serializer for categorization responses"""
    ok = serializers.BooleanField()
    category = serializers.CharField()

class SetPriorityRequestSerializer(serializers.Serializer):
    """Serializer for priority setting requests"""
    email_id = serializers.CharField(max_length=255)
    priority = serializers.ChoiceField(choices=[1, 2, 3, 4])

class SetPriorityResponseSerializer(serializers.Serializer):
    """Serializer for priority setting responses"""
    ok = serializers.BooleanField()
    priority = serializers.IntegerField()

# Utility serializers for nested data

class KeyPointSerializer(serializers.Serializer):
    """Serializer for key points in analysis"""
    text = serializers.CharField()
    importance = serializers.ChoiceField(choices=['low', 'medium', 'high'])
    category = serializers.CharField(required=False, allow_blank=True)

class EmotionalIndicatorSerializer(serializers.Serializer):
    """Serializer for emotional indicators"""
    emotion = serializers.CharField()
    strength = serializers.FloatField(min_value=0.0, max_value=1.0)
    context = serializers.CharField(required=False, allow_blank=True)

class ActionItemSerializer(serializers.Serializer):
    """Serializer for action items"""
    description = serializers.CharField()
    assignee = serializers.CharField(required=False, allow_blank=True)
    due_date = serializers.DateField(required=False, allow_null=True)
    priority = serializers.ChoiceField(choices=['low', 'medium', 'high'], default='medium')