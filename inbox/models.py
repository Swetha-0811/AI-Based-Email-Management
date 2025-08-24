from django.db import models
from django.contrib.auth.models import User

class GmailToken(models.Model):
    # If you don't have auth yet, you can use a single-row table or session.
    # This model supports per-user tokens if you later add login.
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    token_json = models.TextField()          # stores the full credentials as JSON (access + refresh + expiry)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"GmailToken(user={self.user_id})"
