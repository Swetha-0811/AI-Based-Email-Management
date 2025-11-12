import os
import logging
import json
import time
import google.generativeai as genai
from django.conf import settings

# Set up logger
logger = logging.getLogger(__name__)

# Use API key from Django settings
GEMINI_API_KEY = getattr(settings, "GEMINI_API_KEY", None)

# Configure once per process
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Try multiple model options in order of preference
MODEL_OPTIONS = [
    "models/gemini-pro",      # First choice
    "models/gemini-1.0-pro",  # Fallback option
    "models/gemini-1.5-pro",  # Another option
]

# Get model from settings or use the first option
MODEL_NAME = getattr(settings, "GEMINI_MODEL", MODEL_OPTIONS[0])

# Log the model being used
logger.info(f"Configured Gemini model: {MODEL_NAME}")

def get_working_model():
    """Try to find a working model from the available options"""
    # Check if we've recently hit quota limits
    if hasattr(get_working_model, '_last_quota_error_time'):
        # If we hit quota within the last hour, use a fallback
        if time.time() - get_working_model._last_quota_error_time < 3600:
            logger.warning("Recently hit quota limit, using fallback model")
            return MODEL_OPTIONS[-1]  # Use the last option as fallback
    
    for model_name in MODEL_OPTIONS:
        try:
            model = genai.GenerativeModel(model_name)
            # Test if the model works with a simple prompt
            test_response = model.generate_content("Test")
            logger.info(f"Successfully using model: {model_name}")
            return model_name
        except Exception as e:
            # Check if this is a quota error
            if "429" in str(e) or "quota" in str(e).lower():
                # Remember when we hit the quota
                get_working_model._last_quota_error_time = time.time()
                logger.warning(f"Hit quota limit with model {model_name}")
                continue
            logger.warning(f"Model {model_name} failed: {str(e)}")
            continue
    
    # If none of the preferred models work, try to list available models
    try:
        logger.info("Trying to find available models...")
        models = genai.list_models()
        for model in models:
            if "generateContent" in model.supported_generation_methods:
                logger.info(f"Found available model: {model.name}")
                # Try this model
                try:
                    test_model = genai.GenerativeModel(model.name)
                    test_response = test_model.generate_content("Test")
                    logger.info(f"Successfully using fallback model: {model.name}")
                    return model.name
                except Exception as e:
                    # Check if this is a quota error
                    if "429" in str(e) or "quota" in str(e).lower():
                        # Remember when we hit the quota
                        get_working_model._last_quota_error_time = time.time()
                        logger.warning(f"Hit quota limit with model {model.name}")
                        continue
                    logger.warning(f"Fallback model {model.name} failed: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to list models: {str(e)}")
    
    # If nothing works, return the default and let it fail with a clear error
    logger.error("No working model found")
    return MODEL_OPTIONS[0]

def summarize_email(text: str) -> str:
    """
    Produce a brief, helpful summary suitable for a reply assistant.
    """
    if not GEMINI_API_KEY:
        return "[Gemini API key not configured]"

    try:
        prompt = (
            "Summarize the following email in 3-4 concise bullet points, "
            "including the sender's main request and any deadlines:\n\n"
            f"{text}"
        )
        model = genai.GenerativeModel(WORKING_MODEL)
        logger.info(f"Using model for summarization: {WORKING_MODEL}")
        resp = model.generate_content(prompt)

        if hasattr(resp, "text") and resp.text:
            return resp.text.strip()
        elif getattr(resp, "candidates", None):
            # Fallback if resp.text is missing
            return resp.candidates[0].content.parts[0].text.strip()

        return "No summary generated."
    except Exception as e:
        logger.error(f"Error in summarize_email: {str(e)}")
        return f"[Gemini error: {e}]"


def generate_reply(email_text: str, summary: str | None = None) -> str:
    """
    Generate a polite, professional reply draft.
    """
    if not GEMINI_API_KEY:
        return "[Gemini API key not configured]"

    try:
        prompt = (
            "Write a concise, professional reply to the email below. "
            "Be helpful, keep it under 150 words, and use plain language. "
            "If a summary is provided, consider it.\n\n"
            f"Summary (optional): {summary or 'N/A'}\n\n"
            f"Email:\n{email_text}\n\n"
            "Reply:"
        )
        model = genai.GenerativeModel(WORKING_MODEL)
        logger.info(f"Using model for reply generation: {WORKING_MODEL}")
        resp = model.generate_content(prompt)

        if hasattr(resp, "text") and resp.text:
            return resp.text.strip()
        elif getattr(resp, "candidates", None):
            return resp.candidates[0].content.parts[0].text.strip()

        return "No reply generated."
    except Exception as e:
        logger.error(f"Error in generate_reply: {str(e)}")
        return f"[Gemini error: {e}]"
    
def detect_sentiment(text: str) -> dict:
    """
    Detect sentiment in email text and return detailed analysis
    """
    if not GEMINI_API_KEY:
        return {"error": "Gemini API key not configured"}

    try:
        prompt = (
            "Analyze the sentiment of the following email text and provide:\n"
            "1. Overall sentiment (positive, negative, or neutral)\n"
            "2. Confidence level (0-100%)\n"
            "3. Urgency level (low, medium, high)\n"
            "4. Suggested reply tone\n"
            "5. Key emotional indicators\n\n"
            f"Email: {text}\n\n"
            "Analysis (in JSON format):"
        )
        model = genai.GenerativeModel(WORKING_MODEL)
        logger.info(f"Using model for sentiment detection: {WORKING_MODEL}")
        resp = model.generate_content(prompt)

        if hasattr(resp, "text") and resp.text:
            # Try to parse as JSON, fallback to text if not valid JSON
            try:
                result = json.loads(resp.text.strip())
                return result
            except json.JSONDecodeError:
                return {
                    "sentiment": resp.text.strip(),
                    "confidence": "medium",
                    "urgency": "medium",
                    "suggested_tone": "professional"
                }
        elif getattr(resp, "candidates", None):
            return {
                "sentiment": resp.candidates[0].content.parts[0].text.strip(),
                "confidence": "medium",
                "urgency": "medium",
                "suggested_tone": "professional"
            }

        return {"error": "No sentiment analysis generated."}
    except Exception as e:
        logger.error(f"Error in detect_sentiment: {str(e)}")
        return {"error": f"[Gemini error: {e}]"}
    
def analyze_email_message(email_text):
    """
    Analyze a single email message and return sentiment, key points, and summary.
    """
    prompt = f"""
    Analyze the following email message and provide:
    1. Sentiment (positive, negative, or neutral)
    2. Key points (list of main points, at most 5)
    3. A brief summary (one sentence)

    Email:
    {email_text}

    Analysis (in JSON format):
    {{
        "sentiment": "...",
        "key_points": ["...", "..."],
        "summary": "..."
    }}
    """
    try:
        # FIX: Use the global WORKING_MODEL
        model = genai.GenerativeModel(WORKING_MODEL)
        response = model.generate_content(prompt)
        # Try to parse the response as JSON
        try:
            result = json.loads(response.text)
            return result
        except json.JSONDecodeError:
            # If the response is not valid JSON, return a default structure
            return {
                "sentiment": "unknown",
                "key_points": [],
                "summary": response.text
            }
    except Exception as e:
        logger.error(f"Error in analyze_email_message: {str(e)}")
        return {
            "sentiment": "error",
            "key_points": [],
            "summary": f"Error analyzing message: {str(e)}"
        }

def analyze_email_thread(email_text):
    """
    Analyze an entire email thread and provide a comprehensive summary.
    """
    prompt = f"""
    Analyze the following email thread and provide:
    1. Main topic or subject
    2. Key points from the conversation
    3. Decisions made (if any)
    4. Action items or next steps
    5. Overall sentiment of the thread

    Email Thread:
    {email_text}

    Analysis (in JSON format):
    {{
        "main_topic": "...",
        "key_points": ["...", "..."],
        "decisions": "...",
        "action_items": "...",
        "overall_sentiment": "..."
    }}
    """
    try:
        # FIX: Use the global WORKING_MODEL
        model = genai.GenerativeModel(WORKING_MODEL)
        response = model.generate_content(prompt)
        # Try to parse the response as JSON
        try:
            result = json.loads(response.text)
            return result
        except json.JSONDecodeError:
            # If the response is not valid JSON, return a default structure
            return {
                "main_topic": "Could not determine topic",
                "key_points": [],
                "decisions": "None identified",
                "action_items": "None identified",
                "overall_sentiment": "neutral",
                "raw_response": response.text
            }
    except Exception as e:
        logger.error(f"Error in analyze_email_thread: {str(e)}")
        return {
            "main_topic": "Error analyzing thread",
            "key_points": [],
            "decisions": "None identified",
            "action_items": "None identified",
            "overall_sentiment": "neutral",
            "error": str(e)
        }

def customize_template_with_content(template, email_text):
    """
    Customize an email template based on the content of the original email.
    """
    prompt = f"""
    Customize the following email template based on the original email content.
    Maintain the template's tone and structure, but personalize it where appropriate.

    Original Email:
    {email_text}

    Template:
    Subject: {template.subject}
    Body: {template.body}

    Customized Email (in JSON format with subject and body):
    {{
        "subject": "...",
        "body": "..."
    }}
    """
    try:
        # FIX: Use the global WORKING_MODEL
        model = genai.GenerativeModel(WORKING_MODEL)
        response = model.generate_content(prompt)
        # Try to parse the response as JSON
        try:
            result = json.loads(response.text)
            return result
        except json.JSONDecodeError:
            # If the response is not valid JSON, extract subject and body
            lines = response.text.strip().split('\n')
            subject = template.subject
            body = template.body
            
            for line in lines:
                if line.startswith("Subject:"):
                    subject = line.replace("Subject:", "").strip()
                elif line.startswith("Body:"):
                    body = line.replace("Body:", "").strip()
            
            return {
                "subject": subject,
                "body": body
            }
    except Exception as e:
        logger.error(f"Error in customize_template_with_content: {str(e)}")
        return {
            "subject": template.subject,
            "body": f"Error customizing template: {str(e)}"
        }

def extract_email_entities(email_text):
    """
    Extract key entities from email text like dates, names, locations, etc.
    """
    prompt = f"""
    Extract key entities from the following email text:
    1. People mentioned
    2. Dates and times
    3. Locations
    4. Companies or organizations
    5. Action items or commitments

    Email:
    {email_text}

    Entities (in JSON format):
    {{
        "people": ["...", "..."],
        "dates": ["...", "..."],
        "locations": ["...", "..."],
        "organizations": ["...", "..."],
        "action_items": ["...", "..."]
    }}
    """
    try:
        # FIX: Use the global WORKING_MODEL
        model = genai.GenerativeModel(WORKING_MODEL)
        response = model.generate_content(prompt)
        # Try to parse the response as JSON
        try:
            result = json.loads(response.text)
            return result
        except json.JSONDecodeError:
            # If the response is not valid JSON, return a default structure
            return {
                "people": [],
                "dates": [],
                "locations": [],
                "organizations": [],
                "action_items": [],
                "raw_response": response.text
            }
    except Exception as e:
        logger.error(f"Error in extract_email_entities: {str(e)}")
        return {
            "people": [],
            "dates": [],
            "locations": [],
            "organizations": [],
            "action_items": [],
            "error": str(e)
        }

def categorize_email(email_text):
    """
    Categorize an email into predefined categories.
    """
    prompt = f"""
    Categorize the following email into one of these categories:
    1. Work/Professional
    2. Personal
    3. Marketing/Promotional
    4. Notification/Alert
    5. Financial/Billing
    6. Travel
    7. Other

    Email:
    {email_text}

    Category (in JSON format):
    {{
        "category": "...",
        "confidence": 0.0,
        "reason": "..."
    }}
    """
    try:
        # FIX: Use the global WORKING_MODEL
        model = genai.GenerativeModel(WORKING_MODEL)
        response = model.generate_content(prompt)
        # Try to parse the response as JSON
        try:
            result = json.loads(response.text)
            return result
        except json.JSONDecodeError:
            # If the response is not valid JSON, return a default structure
            return {
                "category": "Other",
                "confidence": 0.5,
                "reason": response.text.strip()
            }
    except Exception as e:
        logger.error(f"Error in categorize_email: {str(e)}")
        return {
            "category": "Other",
            "confidence": 0.0,
            "reason": f"Error categorizing email: {str(e)}"
        }

def generate_smart_reply(email_text, user_context=None):
    """
    Generate a smart reply that considers context and user preferences.
    """
    context_info = ""
    if user_context:
        context_info = f"""
        User Context:
        - Preferred tone: {user_context.get('reply_tone', 'professional')}
        - Auto-reply enabled: {user_context.get('auto_reply_enabled', False)}
        - Common phrases: {user_context.get('common_phrases', [])}
        """
    
    prompt = f"""
    Generate a smart reply to the following email.
    Consider the user's context and preferences.

    {context_info}

    Email:
    {email_text}

    Reply (in JSON format with subject, body, and suggested_actions):
    {{
        "subject": "...",
        "body": "...",
        "suggested_actions": ["...", "..."]
    }}
    """
    try:
        # FIX: Use the global WORKING_MODEL
        model = genai.GenerativeModel(WORKING_MODEL)
        response = model.generate_content(prompt)
        # Try to parse the response as JSON
        try:
            result = json.loads(response.text)
            return result
        except json.JSONDecodeError:
            # If the response is not valid JSON, extract subject and body
            lines = response.text.strip().split('\n')
            subject = "Re: Your email"
            body = response.text.strip()
            
            for line in lines:
                if line.startswith("Subject:"):
                    subject = line.replace("Subject:", "").strip()
                elif line.startswith("Body:"):
                    body = line.replace("Body:", "").strip()
            
            return {
                "subject": subject,
                "body": body,
                "suggested_actions": []
            }
    except Exception as e:
        logger.error(f"Error in generate_smart_reply: {str(e)}")
        return {
            "subject": "Re: Your email",
            "body": f"Error generating reply: {str(e)}",
            "suggested_actions": []
        }

def detect_email_intent(email_text):
    """
    Detect the primary intent of the email (question, request, information, etc.).
    """
    prompt = f"""
    Detect the primary intent of the following email.
    Possible intents:
    1. Question - The sender is asking for information
    2. Request - The sender is requesting an action or resource
    3. Information - The sender is providing information
    4. Confirmation - The sender is confirming something
    5. Invitation - The sender is inviting to an event
    6. Follow-up - The sender is following up on a previous conversation
    7. Other - None of the above

    Email:
    {email_text}

    Intent (in JSON format):
    {{
        "intent": "...",
        "confidence": 0.0,
        "details": "..."
    }}
    """
    try:
        # FIX: Use the global WORKING_MODEL
        model = genai.GenerativeModel(WORKING_MODEL)
        response = model.generate_content(prompt)
        # Try to parse the response as JSON
        try:
            result = json.loads(response.text)
            return result
        except json.JSONDecodeError:
            # If the response is not valid JSON, return a default structure
            return {
                "intent": "Information",
                "confidence": 0.5,
                "details": response.text.strip()
            }
    except Exception as e:
        logger.error(f"Error in detect_email_intent: {str(e)}")
        return {
            "intent": "Other",
            "confidence": 0.0,
            "details": f"Error detecting intent: {str(e)}"
        }
        
def generate_reply_fallback(email_text: str, summary: str | None = None) -> str:
    """
    Generate a simple reply when Gemini API is unavailable.
    """
    if summary:
        return f"Thank you for your email. {summary}\n\nI'll get back to you soon."
    else:
        return "Thank you for your email. I'll review it and get back to you soon."

# ==============================================================================
# KEY FIX: Define the global WORKING_MODEL by calling the helper function.
# This should be at the end of the file so all functions are defined first.
# ==============================================================================
WORKING_MODEL = get_working_model()
logger.info(f"Selected working model: {WORKING_MODEL}")