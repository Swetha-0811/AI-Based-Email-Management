from django.urls import path, include
from . import views

# Use a list for API routes to keep them organized
api_urlpatterns = [
    # ==========================================
    # == User & Authentication
    # ==========================================
    path('auth/status/', views.auth_status, name='auth-status'),
    path('user-settings/', views.user_settings_view, name='user-settings'),

    # ==========================================
    # == Email Management
    # ==========================================
    # --- COMPATIBILITY: Added old 'unread-emails' path for your frontend ---
    path('unread-emails/', views.unread_emails_view, name='unread-emails'),
    path('emails/', views.unread_emails_view, name='unread-emails-list'),

    # --- COMPATIBILITY: Changed from emails/ to email/ to match frontend ---
    path('email/<str:message_id>/', views.email_detail_view, name='email-detail'),
    path('email/<str:message_id>/mark-read/', views.mark_as_read_view, name='mark-as-read'),
    path('email/<str:message_id>/archive/', views.archive_email_view, name='archive-email'),
    path('email/<str:message_id>/delete/', views.delete_email_view, name='delete-email'),
    path('email/<str:message_id>/toggle-important/', views.toggle_important_view, name='toggle-important'),
    path('emails/important/', views.important_emails_view, name='important-emails'),

    # --- Bulk actions ---
    path('emails/bulk-mark-read/', views.bulk_mark_as_read_view, name='bulk-mark-as-read'),
    path('emails/bulk-archive/', views.bulk_archive_emails_view, name='bulk-archive-emails'),

    # ==========================================
    # == Draft Management (Gmail)
    # ==========================================
    path('drafts/', views.drafts_view, name='drafts'),
    path('drafts/save/', views.save_draft_view, name='save-draft'),
    path('drafts/<str:draft_id>/', views.draft_detail_view, name='draft-detail'),
    path('drafts/<str:draft_id>/edit/', views.edit_gmail_draft_view, name='edit-gmail-draft'),
    path('drafts/<str:draft_id>/update/', views.update_draft_view, name='update-draft'),
    path('drafts/<str:draft_id>/delete/', views.delete_draft_view, name='delete-draft'),

    # ==========================================
    # == AI-Powered Features
    # ==========================================
    # --- CRITICAL FIX: Added old 'generate-reply' path for your frontend ---
    path('generate-reply/', views.generate_reply_view, name='generate-reply'),
    path('ai/generate-reply/', views.generate_reply_view, name='ai-generate-reply'),
    path('ai/generate-tone-reply/', views.generate_tone_reply_view, name='generate-tone-reply'),
    path('ai/thread/<str:thread_id>/analyze/', views.email_thread_analysis_view, name='email-thread-analysis'),
    path('ai/thread/analyze-from-text/', views.email_thread_analysis_from_text_view, name='email-thread-analysis-from-text'),
    # --- COMPATIBILITY FIX: Added for frontend that calls the old path ---
    path('email-thread-analysis-from-text/', views.email_thread_analysis_from_text_view, name='email-thread-analysis-from-text-legacy'),
    path('ai/sentiment-analysis/', views.sentiment_analysis_view, name='sentiment-analysis'),

    # ==========================================
    # == Workflow Automation
    # ==========================================
    # Reminder System
    path('workflow/reminders/', views.get_reminders_view, name='get-reminders'),
    path('workflow/reminders/set/', views.set_reminder_view, name='set-reminder'),
    # Email Scheduling
    path('workflow/schedule/', views.get_scheduled_emails_view, name='get-scheduled-emails'),
    path('workflow/schedule/set/', views.schedule_email_view, name='schedule-email'),
    # Email Categorization
    path('workflow/categorize/', views.categorize_email_view, name='categorize-email'),
    path('workflow/categorize/auto/', views.auto_categorize_email_view, name='auto-categorize-email'),
    # Priority Scoring
    path('workflow/priority/', views.set_priority_view, name='set-priority'),
    path('workflow/priority/auto/', views.auto_score_priority_view, name='auto-score-priority'),

    # ==========================================
    # == Email Templates
    # ==========================================
    path('templates/', views.email_templates_view, name='email-templates'),
    path('templates/<int:template_id>/', views.email_template_detail_view, name='email-template-detail'),
    path('templates/apply/', views.apply_template_view, name='apply-template'),

    # ==========================================
    # == Generated Drafts (Internal DB)
    # ==========================================

    # ... existing paths ...

    # ... existing paths ...

    # ... existing paths ...
    path('generated-drafts/', views.generated_drafts_view, name='generated-drafts'),
    path('generated-drafts/save/', views.save_generated_draft_view, name='save-generated-draft'),
    path('generated-drafts/<int:draft_id>/send/', views.send_draft_view, name='send-draft'),
    path('generated-drafts/<int:draft_id>/delete/', views.delete_generated_draft_view, name='delete-generated-draft'),
    path('generated-drafts/debug/', views.debug_drafts_db_view, name='debug-generated-drafts'),
    
    # API endpoints for draft operations
    path('api/save-draft/', views.save_generated_draft_view, name='api-save-draft'),
    path('api/drafts/<int:draft_id>/', views.update_draft_view, name='api-update-draft'),

    # ==========================================
    # == Calendar Integration
    # ==========================================
    # --- COMPATIBILITY: Changed from calendar/permissions/ to check-calendar-permissions/ ---
    path('check-calendar-permissions/', views.check_calendar_permissions_view, name='check-calendar-permissions'),
    path('schedule-meeting/', views.schedule_meeting_view, name='schedule-meeting'),

    # ==========================================
    # == Voice Commands
    # ==========================================

    # Voice command processing
    path('voice/command/', views.voice_command_view, name='voice-command'),
    
    # Voice command help
    path('voice/help/', views.voice_command_help_view, name='voice-help'),
    
    # Other endpoints
    path('reminders/', views.get_reminders_view, name='reminders-simple'),
    path('create-sample-data/', views.create_sample_data_view, name='create-sample-data'),


    # ==========================================
    # == Debug & Utility Endpoints
    # ==========================================
    path('debug/drafts/', views.debug_drafts_view, name='debug-drafts'),
    path('debug/gmail-drafts/', views.test_gmail_drafts_view, name='test-gmail-drafts'),
    path('debug/gemini-models/', views.list_gemini_models, name='list-gemini-models'),
]

# Main URL patterns for the application
urlpatterns = [
    # ==========================================
    # == Core Pages & Authentication
    # ==========================================
    path('', views.home_view, name='home'),
    path('settings/', views.settings_view, name='settings'),
    path('oauth/start/', views.oauth_start, name='oauth_start'),
    path('oauth/callback/', views.oauth_callback, name='oauth_callback'),
    path('logout/', views.logout_view, name='logout'),
    path('force-reauth/', views.force_reauth_view, name='force_reauth'),

    # ==========================================
    # == API Endpoints
    # ==========================================
    # All API routes are prefixed with /api/
    # --- FIX: Added the missing closing parenthesis ')' for the include() function ---
    path('api/', include((api_urlpatterns, 'api'))),

    # ==========================================
    # == Test & Debug Pages
    # ==========================================
    path('test/', views.test_view, name='test'),
    path('debug/urls/', views.debug_urls, name='debug-urls'),
]