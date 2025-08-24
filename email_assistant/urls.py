from django.contrib import admin
from django.urls import path, include 
from django.conf import settings
from django.conf.urls.static import static# ✅ include is needed

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('inbox.urls')),   # ✅ connect assistant app URLs
    path("accounts/", include("allauth.urls")),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
