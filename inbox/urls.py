from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('oauth/start/', views.oauth_start, name='oauth_start'),
    path('oauth/callback/', views.oauth_callback, name='oauth_callback'),
    path('unread-emails/', views.unread_emails_view, name='unread_emails'),
    path('generate/', views.generate_reply_view, name='generate_reply'),
    path('save-draft/', views.save_draft_view, name='save_draft'),
     path('debug/<path:path>', views.debug_urls, name='debug_urls'),
    #   path('oauth/status/', views.oauth_status, name='oauth_status'),
    path('logout/', views.logout_view, name='logout'),
]