import os
from pathlib import Path
from decouple import config
import dj_database_url

# --------------------------------------------------------------------
# BASE DIRECTORY
# --------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------
# SECURITY
# --------------------------------------------------------------------
SECRET_KEY = config("SECRET_KEY", default="insecure-dev-key")  # Make sure to set in production
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS", 
    default="127.0.0.1,localhost,email-assistant-eh8y.onrender.com"
).split(",")

# --------------------------------------------------------------------
# DATABASE
# --------------------------------------------------------------------
DATABASES = {
    "default": dj_database_url.config(
        default=config("DATABASE_URL", default="sqlite:///" + str(BASE_DIR / "db.sqlite3")),
        conn_max_age=600,
        ssl_require=not DEBUG,  # SSL only required in production
    )
}

# --------------------------------------------------------------------
# APPLICATIONS
# --------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "inbox",  # Your app
    "django_extensions",  # Extra management tools
    "rest_framework",
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
]

SITE_ID = 1

# --------------------------------------------------------------------
# MIDDLEWARE
# --------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "inbox.middleware.CustomSessionMiddleware",
    "inbox.middleware.SessionCleanupMiddleware",
]

# --------------------------------------------------------------------
# AUTHENTICATION BACKENDS
# --------------------------------------------------------------------
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",  # Default
    "allauth.account.auth_backends.AuthenticationBackend",  # allauth
]

# --------------------------------------------------------------------
# SESSION SETTINGS
# --------------------------------------------------------------------
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 3600  # 1 hour
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_SECURE = not DEBUG  # Use secure cookies only in production

# --------------------------------------------------------------------
# URLS / WSGI
# --------------------------------------------------------------------
ROOT_URLCONF = "email_assistant.urls"
WSGI_APPLICATION = "email_assistant.wsgi.application"

# --------------------------------------------------------------------
# TEMPLATES
# --------------------------------------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],  # global templates dir
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --------------------------------------------------------------------
# PASSWORD VALIDATION
# --------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --------------------------------------------------------------------
# INTERNATIONALIZATION
# --------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------
# STATIC FILES (CSS, JS, Images)
# --------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# Create static directories if they don't exist
os.makedirs(BASE_DIR / "static" / "css", exist_ok=True)
os.makedirs(BASE_DIR / "static" / "js", exist_ok=True)
os.makedirs(BASE_DIR / "static" / "images", exist_ok=True)

# --------------------------------------------------------------------
# DEFAULT PRIMARY KEY FIELD TYPE
# --------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------
# AUTHENTICATION (Allauth / Google Login)
# --------------------------------------------------------------------
LOGIN_REDIRECT_URL = "/"  # Redirect after login
LOGOUT_REDIRECT_URL = "/"

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": [
            "profile",
            "email",
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/gmail.compose",
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/calendar.events",
        ],
        "APP": {
            "client_id": config("GOOGLE_CLIENT_ID"),
            "secret": config("GOOGLE_CLIENT_SECRET"),
            "key": "",
        },
    }
}

# Allow HTTP in DEBUG for OAuth
if DEBUG:
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

# Google OAuth2 Credentials for direct use if needed
GOOGLE_CLIENT_ID = config("GOOGLE_CLIENT_ID", default="")
GOOGLE_CLIENT_SECRET = config("GOOGLE_CLIENT_SECRET", default="")
GOOGLE_CREDENTIALS_BASE64 = config("GOOGLE_CREDENTIALS_BASE64", default=None)

# --------------------------------------------------------------------
# GEMINI
# --------------------------------------------------------------------
GEMINI_API_KEY = config("GEMINI_API_KEY", default=None)
GEMINI_MODEL = config("GEMINI_MODEL", default="models/gemini-pro")

if DEBUG:
    if GEMINI_API_KEY:
        print("✅ Gemini API Key loaded successfully")
    else:
        print("⚠️  GEMINI_API_KEY not found in .env")

# --------------------------------------------------------------------
# REST FRAMEWORK
# --------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 10,
}

# Use None if using React frontend login
LOGIN_URL = None

# --------------------------------------------------------------------
# LOGGING
# --------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": "email_assistant.log",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "inbox": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "django": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# --------------------------------------------------------------------
# CACHE
# --------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-snowflake",
        "TIMEOUT": 300,
        "OPTIONS": {
            "MAX_ENTRIES": 1000,
            "CULL_FREQUENCY": 3,
        },
        "KEY_PREFIX": "email_assistant",
        "VERSION": 1,
    }
}

# --------------------------------------------------------------------
# CUSTOM SETTINGS FOR EMAIL ASSISTANT
# --------------------------------------------------------------------
DEFAULT_REPLY_TONE = "professional"
DEFAULT_REFRESH_INTERVAL = 5  # in minutes
DEFAULT_THEME = "light"
DEFAULT_AUTO_REPLY_ENABLED = True

# CSRF settings
CSRF_COOKIE_SECURE = False  # Set to True in production with HTTPS
CSRF_COOKIE_HTTPONLY = False
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

# Session settings
SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
SESSION_COOKIE_HTTPONLY = True
