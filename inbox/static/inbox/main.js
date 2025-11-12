// DOM Elements
const emailsDiv = document.getElementById('emails');
const paginationDiv = document.getElementById('pagination');
const loadBtn = document.getElementById('load');
const genBtn = document.getElementById('gen');
const genToneBtn = document.getElementById('gen-tone');
const saveBtn = document.getElementById('save');
const toInput = document.getElementById('to');
const subjectInput = document.getElementById('subject');
const saveStatus = document.getElementById('saveStatus');
const themeBtn = document.getElementById('theme-button');
const sectionTitle = document.getElementById('section-title');
// Reminder elements
const defaultRemindersRadio = document.getElementById('default-reminders');
const customRemindersRadio = document.getElementById('custom-reminders');
const customReminderOptions = document.getElementById('custom-reminder-options');
// Ensure these elements are correctly assigned
const emailArea = document.getElementById('email_text');
const summaryArea = document.getElementById('summary');
const replyArea = document.getElementById('generated_reply');
const draftMessageArea = document.getElementById('draft_message');
// Global variables
let currentPage = 1;
let totalPages = 1;
let perPage = 10;
let currentDraftsPage = 1;
let totalDraftsPages = 1;
let editingDraftId = null;
let currentView = 'emails'; // Track if we're viewing emails or drafts

// Voice Actions Class with Enhanced Logging
class VoiceActions {
    constructor() {
        this.recognition = null;
        this.synthesis = window.speechSynthesis;
        this.listening = false;
        this.voiceButton = document.getElementById('voice-action-btn');
        this.voiceFeedback = document.getElementById('voice-feedback');
        this.voiceStatus = document.getElementById('voice-status');
        this.voiceSpinner = document.getElementById('voice-spinner');
        
        this.init();
    }
    
    init() {
        console.log('VoiceActions: Initializing...');
        
        // Check if browser supports speech recognition
        if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
            console.log('VoiceActions: Speech recognition is supported');
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            this.recognition = new SpeechRecognition();
            
            // Configure recognition
            this.recognition.continuous = false;
            this.recognition.interimResults = false;
            this.recognition.lang = 'en-US';
            
            // Set up event handlers
            this.recognition.onstart = () => this.onRecognitionStart();
            this.recognition.onresult = (event) => this.onRecognitionResult(event);
            this.recognition.onerror = (event) => this.onRecognitionError(event);
            this.recognition.onend = () => this.onRecognitionEnd();
            
            console.log('VoiceActions: Speech recognition initialized successfully');
        } else {
            console.warn('VoiceActions: Speech recognition not supported in this browser');
            this.showVoiceFeedback('Speech recognition not supported', 'error');
            if (this.voiceButton) {
                this.voiceButton.style.display = 'none';
            }
        }
        
        // Add event listeners to stop voice recognition when modal is closed
        this.setupModalEventListeners();
        
        // Add event listener for page unload to stop voice recognition
        window.addEventListener('beforeunload', () => this.stopListening());
    }
    
    setupModalEventListeners() {
        // Set up event listeners for modals to stop voice recognition when closed
        document.addEventListener('hidden.bs.modal', (event) => {
            // Check if the hidden modal is voice modal or email operation menu modal
            const modalId = event.target.id;
            if (modalId === 'voice-modal' || modalId === 'emailOperationMenuModal') {
                console.log('Modal closed, stopping voice recognition');
                this.stopListening();
                this.stopVoiceSpeaking();
            }
        });
        
        // Also stop voice recognition when any modal is shown (to prevent conflicts)
        document.addEventListener('shown.bs.modal', (event) => {
            const modalId = event.target.id;
            // Don't stop if it's the voice help modal
            if (modalId !== 'voiceHelpModal' && modalId !== 'voice-commands-modal') {
                console.log('Modal opened, stopping voice recognition');
                this.stopListening();
            }
        });
    }
    
    onRecognitionStart() {
        console.log('VoiceActions: Recognition started');
        this.listening = true;
        if (this.voiceButton) {
            this.voiceButton.classList.add('active');
        }
        this.showVoiceFeedback('Listening...', 'listening');
        if (this.voiceSpinner) {
            this.voiceSpinner.style.display = 'inline-block';
        }
    }
    
    onRecognitionResult(event) {
        const command = event.results[0][0].transcript.toLowerCase().trim();
        console.log('VoiceActions: Command recognized:', command);
        
        this.showVoiceFeedback(`Processing: "${command}"`, 'processing');
        if (this.voiceSpinner) {
            this.voiceSpinner.style.display = 'inline-block';
        }
        
        // Send command to backend
        this.sendVoiceCommand(command);
    }
    
    onRecognitionError(event) {
        console.error('VoiceActions: Speech recognition error:', event.error);
        this.showVoiceFeedback(`Error: ${event.error}`, 'error');
        this.stopListening();
    }
    
    onRecognitionEnd() {
        console.log('VoiceActions: Recognition ended');
        if (this.listening) {
            this.stopListening();
        }
    }
    
    async sendVoiceCommand(command) {
        console.log('VoiceActions: Sending command to backend:', command);
        
        try {
            // Clear any previous error state
            this.hideVoiceFeedback();
            
            // Show processing state
            this.showVoiceFeedback('Processing command...', 'processing');
            
            // Prepare request data
            const requestData = {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken(),
                    'Accept': 'application/json'
                },
                body: JSON.stringify({ command: command })
            };
            
            console.log('Request details:', {
                url: '/api/voice/command/',
                method: requestData.method,
                headers: requestData.headers,
                body: requestData.body
            });
            
            // Make request with timeout
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout
            
            const response = await fetch('/api/voice/command/', {
                ...requestData,
                signal: controller.signal
            });
            
            // Clear timeout
            clearTimeout(timeoutId);
            
            console.log('Response received:', {
                status: response.status,
                statusText: response.statusText,
                headers: Object.fromEntries(response.headers.entries())
            });
            
            // Check if response is ok
            if (!response.ok) {
                const errorText = await response.text();
                console.error('Backend returned error:', {
                    status: response.status,
                    statusText: response.statusText,
                    body: errorText
                });
                throw new Error(`HTTP ${response.status}: ${errorText || response.statusText}`);
            }
            
            // Parse JSON response
            const data = await response.json();
            console.log('Backend response data:', data);
            
            if (data.ok) {
                console.log('Executing action:', data.action);
                this.executeVoiceAction(data.action);
                this.speak(`Command executed: ${data.action.type}`);
            } else {
                console.error('Backend error:', data.error);
                this.showVoiceFeedback(`Error: ${data.error}`, 'error');
                this.speak(`Error: ${data.error}`);
            }
        } catch (error) {
            console.error('Network error details:', {
                name: error.name,
                message: error.message,
                stack: error.stack
            });
            
            // Handle specific error types
            let errorMessage = 'Network error occurred';
            if (error.name === 'AbortError') {
                errorMessage = 'Request timed out. Please try again.';
            } else if (error.message.includes('Failed to fetch')) {
                errorMessage = 'Cannot connect to server. Please check your connection.';
            } else if (error.message.includes('404')) {
                errorMessage = 'Endpoint not found. Please check server configuration.';
            } else if (error.message.includes('403')) {
                errorMessage = 'Permission denied. Please refresh page.';
            } else if (error.message.includes('500')) {
                errorMessage = 'Server error. Please try again later.';
            } else if (error.message.includes('SyntaxError')) {
                errorMessage = 'Server returned invalid response. Please check server configuration.';
            }
            
            this.showVoiceFeedback(errorMessage, 'error');
            this.speak(errorMessage);
        }
    }
    
    executeVoiceAction(action) {
        console.log('VoiceActions: Executing action:', action);
        
        switch (action.type) {
            case 'load_emails':
                console.log('VoiceActions: Loading emails...');
                currentView = 'emails'; // Ensure we're in email view
                loadEmails(1); // Load first page
                this.showVoiceFeedback('Loading emails...', 'processing');
                break;
                
            case 'mark_all_as_read':
                console.log('VoiceActions: Marking all as read...');
                markAllAsRead();
                this.showVoiceFeedback('Marking all as read...', 'processing');
                break;
                
            case 'mark_current_as_read':
                console.log('VoiceActions: Marking current email as read...');
                const firstEmail = document.querySelector('.email-item');
                if (firstEmail) {
                    const emailId = firstEmail.getAttribute('data-email-id');
                    if (emailId) {
                        markAsRead(emailId, firstEmail.querySelector('.mark-read-btn'));
                        this.showVoiceFeedback('Marked as read', 'success');
                    }
                } else {
                    this.showVoiceFeedback('No email selected', 'error');
                }
                break;
                
            case 'reply_current':
                console.log('VoiceActions: Opening reply...');
                const replyBtn = document.querySelector('.email-item .btn-icon-sm.btn-primary');
                if (replyBtn) {
                    replyBtn.click();
                    this.showVoiceFeedback('Opening reply...', 'processing');
                } else {
                    this.showVoiceFeedback('No email to reply to', 'error');
                }
                break;
                
            case 'compose_email':
                console.log('VoiceActions: Focusing compose field...');
                const toField = document.getElementById('to');
                if (toField) {
                    toField.focus();
                    this.showVoiceFeedback('Ready to compose email', 'success');
                } else {
                    this.showVoiceFeedback('Compose field not found', 'error');
                }
                break;
                
            case 'next_page':
                console.log('VoiceActions: Going to next page...');
                const nextBtn = document.querySelector('.page-numbers button[title="Next"]');
                if (nextBtn && !nextBtn.disabled) {
                    nextBtn.click();
                    this.showVoiceFeedback('Going to next page...', 'processing');
                } else {
                    this.showVoiceFeedback('Already on last page', 'error');
                }
                break;
                
            case 'previous_page':
                console.log('VoiceActions: Going to previous page...');
                const prevBtn = document.querySelector('.page-numbers button[title="Previous"]');
                if (prevBtn && !prevBtn.disabled) {
                    prevBtn.click();
                    this.showVoiceFeedback('Going to previous page...', 'processing');
                } else {
                    this.showVoiceFeedback('Already on first page', 'error');
                }
                break;
                
            case 'generate_reply':
                console.log('VoiceActions: Generating reply...');
                if (genBtn) {
                    genBtn.click();
                    this.showVoiceFeedback('Generating reply...', 'processing');
                } else {
                    this.showVoiceFeedback('Generate button not found', 'error');
                }
                break;
                
            case 'save_draft':
                console.log('VoiceActions: Saving draft...');
                if (saveBtn) {
                    saveBtn.click();
                    this.showVoiceFeedback('Saving draft...', 'processing');
                } else {
                    this.showVoiceFeedback('Save button not found', 'error');
                }
                break;
                
            case 'schedule_meeting':
                console.log('VoiceActions: Opening meeting scheduler...');
                const firstEmailForMeeting = document.querySelector('.email-item');
                if (firstEmailForMeeting) {
                    const emailData = JSON.parse(firstEmailForMeeting.getAttribute('data-email'));
                    openScheduleMeetingModal(emailData);
                    this.showVoiceFeedback('Opening meeting scheduler...', 'processing');
                } else {
                    this.showVoiceFeedback('No email selected for meeting', 'error');
                }
                break;
                
            case 'toggle_theme':
                console.log('VoiceActions: Toggling theme...');
                toggleTheme();
                this.showVoiceFeedback('Theme toggled', 'success');
                break;
                
            case 'help':
                console.log('VoiceActions: Help action received, action:', action);
                this.showVoiceHelp(action);
                break;
                
            case 'archive_current':
                console.log('VoiceActions: Archiving current email...');
                const firstEmailForArchive = document.querySelector('.email-item');
                if (firstEmailForArchive) {
                    const emailId = firstEmailForArchive.getAttribute('data-email-id');
                    if (emailId) {
                        archiveEmail(emailId);
                        this.showVoiceFeedback('Email archived', 'success');
                    }
                } else {
                    this.showVoiceFeedback('No email to archive', 'error');
                }
                break;
                
            case 'delete_current':
                console.log('VoiceActions: Deleting current email...');
                const firstEmailForDelete = document.querySelector('.email-item');
                if (firstEmailForDelete) {
                    const emailId = firstEmailForDelete.getAttribute('data-email-id');
                    if (emailId) {
                        deleteEmail(emailId);
                        this.showVoiceFeedback('Email deleted', 'success');
                    }
                } else {
                    this.showVoiceFeedback('No email to delete', 'error');
                }
                break;
                
            case 'unknown':
                console.log('VoiceActions: Unknown command');
                this.showVoiceFeedback('Command not recognized', 'error');
                this.speak('Command not recognized. Say "help" for available commands.');
                break;
                
            default:
                console.log('VoiceActions: Unhandled action type:', action.type);
                this.showVoiceFeedback(`Action not implemented: ${action.type}`, 'error');
        }
    }
    
    showVoiceFeedback(message, type = 'info') {
        console.log(`VoiceActions: Showing feedback: ${message} (${type})`);
        if (this.voiceStatus) {
            this.voiceStatus.textContent = message;
        }
        if (this.voiceFeedback) {
            this.voiceFeedback.style.display = 'block';
            this.voiceFeedback.className = `position-fixed top-0 start-50 translate-middle-x mt-3 alert-${type === 'error' ? 'danger' : type === 'success' ? 'success' : 'info'}`;
        }
        
        // Auto-hide after 3 seconds for success/info messages
        if (type === 'success' || type === 'info') {
            setTimeout(() => {
                this.hideVoiceFeedback();
            }, 3000);
        }
    }
    
    hideVoiceFeedback() {
        if (this.voiceFeedback) {
            this.voiceFeedback.style.display = 'none';
        }
        if (this.voiceSpinner) {
            this.voiceSpinner.style.display = 'none';
        }
    }
    
    showVoiceHelp(action) {
        try {
            console.log('VoiceActions: Showing help with action:', action);
            
            // Get the voice help modal
            const voiceHelpModal = document.getElementById('voiceHelpModal');
            if (!voiceHelpModal) {
                console.error('VoiceActions: voiceHelpModal not found');
                this.showVoiceFeedback('Error: Help modal not found', 'error');
                return;
            }
            
            // Get the commands list element
            const commandsListDiv = document.getElementById('voice-commands-list');
            if (!commandsListDiv) {
                console.error('VoiceActions: commandsListDiv not found');
                this.showVoiceFeedback('Error: Commands list not found', 'error');
                return;
            }
            
            // Clear existing content
            commandsListDiv.innerHTML = '';
            
            // Get commands from action or use fallback
            let commands = action.commands_list || [];
            
            if (commands.length === 0) {
                console.warn('VoiceActions: No commands in action, using fallback');
                commands = [
                    {"command": "load emails", "description": "Load or refresh your emails"},
                    {"command": "mark all as read", "description": "Mark all emails as read"},
                    {"command": "mark as read", "description": "Mark the current email as read"},
                    {"command": "archive", "description": "Archive the current email"},
                    {"command": "delete", "description": "Delete the current email"},
                    {"command": "reply", "description": "Reply to the current email"},
                    {"command": "compose email", "description": "Compose a new email"},
                    {"command": "next page", "description": "Go to the next page of emails"},
                    {"command": "previous page", "description": "Go to the previous page of emails"},
                    {"command": "generate reply", "description": "Generate an AI reply for the current email"},
                    {"command": "save draft", "description": "Save the current draft"},
                    {"command": "schedule meeting", "description": "Schedule a meeting"},
                    {"command": "toggle theme", "description": "Toggle between dark and light theme"},
                    {"command": "help", "description": "Show available commands"}
                ];
            }
            
            // Create list element
            const list = document.createElement('ul');
            list.className = 'list-group';
            
            // Add each command to the list
            commands.forEach(cmd => {
                const listItem = document.createElement('li');
                listItem.className = 'list-group-item';
                listItem.innerHTML = `<strong>${cmd.command}</strong>: ${cmd.description}`;
                
                // Add click event to speak the command
                listItem.addEventListener('click', function() {
                    if (this.speak) {
                        this.speak(cmd.command);
                    }
                }.bind(this));
                
                list.appendChild(listItem);
            });
            
            // Add the list to the modal
            commandsListDiv.appendChild(list);
            
            // Show the modal
            console.log('VoiceActions: Showing modal');
            try {
                const modal = new bootstrap.Modal(voiceHelpModal);
                modal.show();
            } catch (e) {
                console.error('VoiceActions: Error showing modal:', e);
                this.showVoiceFeedback('Error showing help modal', 'error');
            }
            
            // Speak the commands if voice_output is available
            if (action.voice_output) {
                console.log('VoiceActions: Speaking voice_output:', action.voice_output);
                this.speak(action.voice_output);
            } else {
                console.log('VoiceActions: No voice_output, using fallback text');
                this.speak('Available voice commands: load emails, mark all as read, mark as read, archive, delete, reply, compose email, next page, previous page, generate reply, save draft, schedule meeting, toggle theme, and help.');
            }
            
            // Add event listener to stop voice when modal is closed
            voiceHelpModal.addEventListener('hidden.bs.modal', function () {
                console.log('VoiceActions: Modal closed, stopping voice');
                this.stopVoiceSpeaking();
            }.bind(this), { once: true });
            
        } catch (error) {
            console.error('VoiceActions: Error in showVoiceHelp:', error);
            this.showVoiceFeedback('Error showing help', 'error');
        }
    }
    
    speak(text) {
        if (this.synthesis) {
            console.log('VoiceActions: Speaking:', text);
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.rate = 1.0;
            utterance.pitch = 1.0;
            utterance.volume = 1.0;
            this.synthesis.speak(utterance);
        }
    }
    
    // Method to stop voice speaking
    stopVoiceSpeaking() {
        if (this.synthesis && this.synthesis.speaking) {
            console.log('VoiceActions: Stopping speech synthesis');
            this.synthesis.cancel(); // This stops any ongoing speech
        }
    }
    
    startListening() {
        if (this.recognition && !this.listening) {
            console.log('VoiceActions: Starting recognition...');
            this.recognition.start();
        } else {
            console.log('VoiceActions: Cannot start recognition - already listening or not supported');
        }
    }
    
    stopListening() {
        if (this.listening) {
            console.log('VoiceActions: Stopping recognition');
            this.listening = false;
            
            if (this.voiceButton) {
                this.voiceButton.classList.remove('active');
            }
            if (this.voiceSpinner) {
                this.voiceSpinner.style.display = 'none';
            }
            
            if (this.recognition) {
                try {
                    this.recognition.stop();
                    console.log('VoiceActions: Recognition stopped successfully');
                } catch (e) {
                    console.log('VoiceActions: Recognition already stopped or not started');
                }
            }
            
            // Hide voice feedback
            this.hideVoiceFeedback();
            
            // Stop any ongoing speech
            this.stopVoiceSpeaking();
        }
    }
    
    toggle() {
        console.log('VoiceActions: Toggle called');
        if (this.listening) {
            this.stopListening();
        } else {
            this.startListening();
        }
    }
}

// Initialize Voice Actions
let voiceActions;

// Add markAllAsRead function
async function markAllAsRead() {
    const emailCheckboxes = document.querySelectorAll('.email-item input[type="checkbox"]');
    const emailIds = Array.from(emailCheckboxes).map(cb => cb.value);
    
    if (emailIds.length === 0) {
        showNotification('No emails to mark as read', 'warning');
        return;
    }
    
    try {
        const response = await fetch('/api/bulk-mark-as-read/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({ email_ids: emailIds })
        });
        
        const data = await response.json();
        
        if (data.ok) {
            showNotification(`${data.success_count} emails marked as read`, 'success');
            if (currentView === 'emails') {
                loadEmails(currentPage);
            } else {
                loadDrafts(currentDraftsPage);
            }
        } else {
            showNotification('Failed to mark emails as read', 'error');
        }
    } catch (error) {
        showNotification('Network error', 'error');
    }
}

// Function to toggle voice recognition
function toggleVoiceRecognition() {
    if (voiceActions) {
        voiceActions.toggle();
    }
}

// Function to show voice help
function showVoiceHelp() {
    if (voiceActions) {
        // Send a help command to the backend
        voiceActions.sendVoiceCommand('help');
    }
}

// Initialize the page
document.addEventListener('DOMContentLoaded', function () {
    // Check authentication status first
    checkAuthStatus();
    
    // Check calendar permissions
    checkCalendarPermissions();
    
    // Theme toggle button functionality
    themeBtn.addEventListener('click', toggleTheme);
    
    // Initialize Voice Actions
    console.log('DOM loaded: Initializing Voice Actions');
    voiceActions = new VoiceActions();
    
    // Add voice button to navbar if it exists
    const voiceNavBtn = document.getElementById('voice-nav-btn');
    if (voiceNavBtn) {
        voiceNavBtn.addEventListener('click', function() {
            // Show voice modal with help command option
            showVoiceModal();
        });
    }
    
    // Add event listeners for voice command buttons
    const voiceToggleBtn = document.getElementById('voice-toggle-btn');
    if (voiceToggleBtn) {
        voiceToggleBtn.addEventListener('click', toggleVoiceRecognition);
    }
    
    const voiceHelpBtn = document.getElementById('voice-help-btn');
    if (voiceHelpBtn) {
        console.log('Found help button, attaching event listener');
        voiceHelpBtn.addEventListener('click', showVoiceHelp);
    } else {
        console.warn('Help button not found');
    }
    
    // Reminder radio button event listeners
    if (defaultRemindersRadio && customRemindersRadio) {
        defaultRemindersRadio.addEventListener('change', function() {
            customReminderOptions.style.display = this.checked ? 'none' : 'block';
        });
        
        customRemindersRadio.addEventListener('change', function() {
            customReminderOptions.style.display = this.checked ? 'block' : 'none';
        });
    }
    
    if (loadBtn) {
        loadBtn.addEventListener('click', function () {
            if (currentView === 'emails') {
                loadEmails(1);
            } else {
                loadDrafts(1);
            }
        });
    }
    
    if (genBtn) {
        genBtn.addEventListener('click', generateReply);
    }
    
    // Add event listener for the tone-based reply button
    if (genToneBtn) {
        genToneBtn.addEventListener('click', generateToneReply);
    }
    
    if (saveBtn) {
        saveBtn.addEventListener('click', saveDraft);
    }
    
    // Add event listener for "Select All" checkbox
    const selectAllCheckbox = document.getElementById('select-all-emails');
    if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener('change', function() {
            const emailCheckboxes = document.querySelectorAll('.email-item input[type="checkbox"]');
            emailCheckboxes.forEach(checkbox => {
                checkbox.checked = this.checked;
            });
            toggleBulkActionButton();
        });
    }
    
    // Add event listeners for individual email checkboxes (using event delegation)
    document.addEventListener('change', function(e) {
        if (e.target.classList.contains('form-check-input') && e.target.type === 'checkbox' && e.target.id !== 'select-all-emails') {
            toggleBulkActionButton();
            updateSelectAllCheckbox();
        }
    });
    
    // Add event listener for bulk mark as read button
    const bulkMarkReadBtn = document.getElementById('bulk-mark-read');
    if (bulkMarkReadBtn) {
        bulkMarkReadBtn.addEventListener('click', markSelectedAsRead);
    }
    
    // Initialize theme from localStorage
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark-theme') {
        document.body.classList.add('dark-theme');
        themeBtn.innerText = 'Switch to Light Theme';
        // Update mark as read buttons for initial theme
        updateMarkAsReadButtonsTheme();
    }
    
    // Add event listener for tab changes
    document.addEventListener('click', function(e) {
        // Check if the clicked element is a tab link
        if (e.target.classList.contains('nav-link')) {
            // Stop voice speaking when switching tabs
            if (voiceActions) {
                voiceActions.stopSpeaking();
            }
        }
    });
    
    // Add event listener for voice help modal to stop voice when closed
    const voiceHelpModal = document.getElementById('voiceHelpModal');
    if (voiceHelpModal) {
        voiceHelpModal.addEventListener('hidden.bs.modal', function () {
            if (voiceActions) {
                voiceActions.stopVoiceSpeaking();
            }
        });
    }
});
// // // // // // 
    // END VOICE COMMANDS //
/////// // // //     // 
    // Initialize tooltips
    initializeTooltips();
    
    // Add event listeners for thread analysis and sentiment analysis buttons
    const threadAnalysisBtn = document.getElementById('analyze-thread');
    if (threadAnalysisBtn) {
        threadAnalysisBtn.addEventListener('click', analyzeCurrentThread);
    }

    const sentimentAnalysisBtn = document.getElementById('sentiment-analysis');
    if (sentimentAnalysisBtn) {
        sentimentAnalysisBtn.addEventListener('click', analyzeCurrentSentiment);
    }
;
// Function to initialize tooltips
function initializeTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}
// Function to show voice modal with help command option
function showVoiceModal() {
    // Create modal if it doesn't exist
    let voiceModal = document.getElementById('voice-modal');
    
    if (!voiceModal) {
        voiceModal = document.createElement('div');
        voiceModal.id = 'voice-modal';
        voiceModal.className = 'modal fade';
        voiceModal.innerHTML = `
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Voice Assistant</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <div class="modal-body">
                        <p>Click the button below and speak a command, or click "Help Commands" to see available commands.</p>
                        <div class="d-grid gap-2">
                            <button id="start-voice-btn" class="btn btn-primary">
                                <i class="fas fa-microphone"></i> Start Voice Command
                            </button>
                            <button id="help-commands-btn" class="btn btn-outline-info">
                                <i class="fas fa-question-circle"></i> Help Commands
                            </button>
                        </div>
                        <div id="voice-modal-status" class="mt-3"></div>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(voiceModal);
        
        // Add event listener for start voice button
        document.getElementById('start-voice-btn').addEventListener('click', function() {
            if (voiceActions) {
                voiceActions.toggle();
                // Close modal after starting voice recognition
                const modal = bootstrap.Modal.getInstance(voiceModal);
                modal.hide();
            }
        });
        
        // Add event listener for help commands button
        document.getElementById('help-commands-btn').addEventListener('click', function() {
            if (voiceActions) {
                // Send the help command
                voiceActions.sendVoiceCommand('help');
                // Close modal
                const modal = bootstrap.Modal.getInstance(voiceModal);
                modal.hide();
            }
        });
        
        // Add event listener to stop voice recognition when modal is closed
        voiceModal.addEventListener('hidden.bs.modal', function() {
            if (voiceActions) {
                voiceActions.stopListening();
            }
            // Also stop any speaking voice
            stopVoiceSpeaking();
        });
    }
    
    // Show the modal
    const modal = new bootstrap.Modal(voiceModal);
    modal.show();
}
// Theme toggle function
function toggleTheme() {
    const body = document.body;
    
    if (body.classList.contains('dark-theme')) {
        body.classList.remove('dark-theme');
        themeBtn.innerText = 'Switch to Dark Theme';
        localStorage.setItem('theme', 'light-theme');
    } else {
        body.classList.add('dark-theme');
        themeBtn.innerText = 'Switch to Light Theme';
        localStorage.setItem('theme', 'dark-theme');
    }
    
    // Update mark as read buttons theme
    updateMarkAsReadButtonsTheme();
}
// Function to update mark as read buttons theme
function updateMarkAsReadButtonsTheme() {
    const body = document.body;
    const markAsReadBtns = document.querySelectorAll('.mark-read-btn');
    
    markAsReadBtns.forEach(btn => {
        // Remove any existing theme classes
        btn.classList.remove('light-theme', 'dark-theme');
        
        // Add the appropriate theme class based on the current theme
        if (body.classList.contains('dark-theme')) {
            btn.classList.add('dark-theme');
        } else {
            btn.classList.add('light-theme');
        }
    });
}
// Check authentication status
async function checkAuthStatus() {
    try {
        const response = await fetch('/api/auth/status/');
        const data = await response.json();
        const authSection = document.getElementById('auth-section');
        const authBtn = document.getElementById('auth-btn');
        
        if (data.authenticated) {
            authSection.style.display = 'none';
            // Load emails only if authenticated
            loadEmails(1);
        } else {
            authSection.style.display = 'block';
        }
    } catch (error) {
        console.error('Error checking auth status:', error);
        // Even if there's an error, try to load emails
        loadEmails(1);
    }
}
// Function to check calendar permissions
async function checkCalendarPermissions() {
    try {
        const response = await fetch('/api/check-calendar-permissions/');
        const data = await response.json();
        
        if (data.ok && !data.has_calendar_permissions) {
            // Show a notification that calendar permissions are needed
            const notification = document.createElement('div');
            notification.className = 'alert alert-warning alert-dismissible fade show position-fixed';
            notification.style.top = '20px';
            notification.style.left = '50%';
            notification.style.transform = 'translateX(-50%)';
            notification.style.zIndex = '9999';
            notification.style.minWidth = '400px';
            notification.innerHTML = `
                Calendar access is required to schedule meetings. 
                <a href="/force-reauth/" class="btn btn-sm btn-warning ms-2">Grant Calendar Access</a>
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            `;
            
            document.body.appendChild(notification);
        }
    } catch (error) {
        console.error('Error checking calendar permissions:', error);
    }
}
// Load emails for the current page
async function loadEmails(page = 1) {
    if (page < 1) page = 1;
    if (page > totalPages) page = totalPages;
    currentPage = page;
    currentView = 'emails';
    
    // Update section title
    if (sectionTitle) {
        sectionTitle.textContent = 'Unread Emails';
    }
    
    if (!emailsDiv) return;
    
    // Show loading state
    emailsDiv.innerHTML = `  
        <div class="text-center p-4">
            <div class="spinner-border text-primary mb-2"></div>
            <p class="text-muted">Loading emails...</p>
        </div>
    `;
    
    if (loadBtn) {
        loadBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Loading...';
        loadBtn.disabled = true;
    }
    
    try {
        // Use the global perPage variable
        const response = await fetch(`/api/unread-emails/?page=${page}&per_page=${perPage}`);
        const data = await response.json();
        
        if (data.ok) {
            totalPages = data.total_pages || 1;
            currentPage = data.current_page || currentPage;
            perPage = data.per_page || perPage; // Update perPage from response
            
            renderEmails(data.emails);
            renderPagination(data, false); // Pass false to indicate we are rendering emails
        } else {
            emailsDiv.innerHTML = ` 
                <div class="alert alert-danger m-3">
                    <i class="fas fa-exclamation-triangle me-2"></i>
                    Error: ${data.error}
                </div>
            `;
        }
    } catch (error) {
        emailsDiv.innerHTML = ` 
            <div class="alert alert-danger m-3">
                <i class="fas fa-exclamation-triangle me-2"></i>
                Error loading emails: ${error.message}
            </div>
        `;
    } finally {
        if (loadBtn) {
            loadBtn.innerHTML = '<i class="fas fa-sync-alt me-2"></i>Refresh';
            loadBtn.disabled = false;
        }
    }
}

// ########################
// Load drafts for the current page
// ###########################


async function loadDrafts(page = 1) {
    if (page < 1) page = 1;
    if (page > totalDraftsPages) page = totalDraftsPages;
    currentDraftsPage = page;
    currentView = 'drafts';
    
    // Update section title
    if (sectionTitle) {
        sectionTitle.textContent = 'Drafts';
    }
    
    if (!emailsDiv) return;
    
    // Show loading state
    emailsDiv.innerHTML = `  
        <div class="text-center p-4">
            <div class="spinner-border text-primary mb-2"></div>
            <p class="text-muted">Loading drafts...</p>
        </div>
    `;
    
    if (loadBtn) {
        loadBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Loading...';
        loadBtn.disabled = true;
    }
    
    try {
        const response = await fetch(`/api/drafts/?page=${page}&per_page=${perPage}`);
        const data = await response.json();
        
        if (data.ok) {
            totalDraftsPages = data.total_pages || 1;
            currentDraftsPage = data.current_page || currentDraftsPage;
            perPage = data.per_page || perPage;
            
            renderDrafts(data.drafts);
            renderPagination(data, true); // Pass true to indicate we are rendering drafts
        } else {
            emailsDiv.innerHTML = ` 
                <div class="alert alert-danger m-3">
                    <i class="fas fa-exclamation-triangle me-2"></i>
                    Error: ${data.error}
                </div>
            `;
        }
    } catch (error) {
        emailsDiv.innerHTML = ` 
            <div class="alert alert-danger m-3">
                <i class="fas fa-exclamation-triangle me-2"></i>
                Error loading drafts: ${error.message}
            </div>
        `;
    } finally {
        if (loadBtn) {
            loadBtn.innerHTML = '<i class="fas fa-sync-alt me-2"></i>Refresh';
            loadBtn.disabled = false;
        }
    }
}
// Render emails to the list
function renderEmails(emails) {
    emailsDiv.innerHTML = '';
    if (emails.length === 0) {
        emailsDiv.innerHTML = ` 
            <div class="text-center p-4 text-muted">
                <i class="fas fa-inbox fa-3x mb-3"></i>
                <p>No unread emails found</p>
            </div>
        `;
        return;
    }
    
    emails.forEach(email => {
        const emailItem = document.createElement('div');
        emailItem.classList.add('email-item', 'card', 'mb-2');
        emailItem.setAttribute('data-email-id', email.id);
        
        // Store minimal email data for voice commands
        const minimalEmail = {
            id: email.id,
            subject: email.subject,
            snippet: email.snippet,
            from: email.from
        };
        emailItem.setAttribute('data-email', JSON.stringify(minimalEmail));
        
        emailItem.innerHTML = ` 
            <div class="card-body">
                <!-- Mark as Read button with tooltip - now icon-only -->
                <button class="btn btn-icon btn-icon-sm mark-read-btn" 
                        data-bs-toggle="tooltip" 
                        data-bs-placement="top"
                        title="Mark as read"
                        onclick="markAsRead('${email.id}', this)">
                    <i class="fas fa-check"></i>
                </button>
                <div class="d-flex align-items-start">
                    <div class="form-check me-2">
                        <input class="form-check-input" type="checkbox" value="${email.id}" id="email-${email.id}">
                    </div>
                    <div class="flex-grow-1">
                        <div class="email-meta text-muted small mb-1">
                            <strong>From:</strong> ${email.from || 'Unknown'} •
                            <span>${email.date || ''}</span>
                        </div>
                        <h6 class="email-subject mb-1">${email.subject || '(no subject)'}</h6>
                        <p class="email-snippet text-muted mb-2">${(email.snippet || '').substring(0, 100)}...</p>
                    </div>
                </div>
                <div class="email-actions mt-2 d-flex align-items-center">
                    <!-- Primary actions: Reply and Archive with updated icons -->
                    <button class="btn btn-icon btn-icon-sm btn-primary rounded-circle me-2" 
                            data-bs-toggle="tooltip" 
                            title="Reply" 
                            onclick="useEmail(${JSON.stringify(email).replace(/"/g, '&quot;')})">
                        <i class="fas fa-reply"></i>
                    </button>
                    
                    <button class="btn btn-icon btn-icon-sm btn-warning rounded-circle me-2" 
                            data-bs-toggle="tooltip" 
                            title="Archive" 
                            onclick="archiveEmail('${email.id}')">
                        <i class="fas fa-archive"></i>
                    </button>
                    
                    <!-- Star button -->
                    <button class="btn btn-icon btn-icon-sm star-btn ${email.is_important ? 'text-warning' : ''}" 
                            data-bs-toggle="tooltip" 
                            title="${email.is_important ? 'Unstar' : 'Star'}"
                            onclick="toggleImportant('${email.id}', this)">
                        <i class="${email.is_important ? 'fas' : 'far'} fa-star"></i>
                    </button>
                    
                    <!-- Dropdown for secondary actions -->
                    <div class="dropdown">
                        <button class="btn btn-icon btn-icon-sm btn-secondary rounded-circle" 
                                data-bs-toggle="dropdown" 
                                aria-expanded="false" 
                                data-bs-toggle="tooltip" 
                                title="More actions">
                            <i class="fas fa-ellipsis-v"></i>
                        </button>
                        <ul class="dropdown-menu">
                            <li>
                                <button class="dropdown-item" 
                                        onclick="useEmailForReplyAll(${JSON.stringify(email).replace(/"/g, '&quot;')})">
                                    <i class="fas fa-reply-all me-2"></i> Reply All
                                </button>
                            </li>
                            <li>
                                <button class="dropdown-item" 
                                        onclick="openScheduleMeetingModal(${JSON.stringify(email).replace(/"/g, '&quot;')})">
                                    <i class="fas fa-calendar-plus me-2"></i> Schedule Meeting
                                </button>
                            </li>
                            <li>
                                <hr class="dropdown-divider">
                            </li>
                            <li>
                                <button class="dropdown-item text-danger" 
                                        onclick="deleteEmail('${email.id}')">
                                    <i class="fas fa-trash me-2"></i> Delete
                                </button>
                            </li>
                        </ul>
                    </div>
                </div>
            </div>
        `;
        
        emailsDiv.appendChild(emailItem);
    });
    
    // Update email count
    const emailCount = document.getElementById('email-count');
    if (emailCount) {
        emailCount.textContent = emails.length;
    }
    
    // Update theme for mark as read buttons
    updateMarkAsReadButtonsTheme();
    
    // Initialize tooltips for the newly added elements
    initializeTooltips();
}
// Render drafts to the list
function renderDrafts(drafts) {
    emailsDiv.innerHTML = '';
    if (drafts.length === 0) {
        emailsDiv.innerHTML = ` 
            <div class="text-center p-4 text-muted">
                <i class="fas fa-file-alt fa-3x mb-3"></i>
                <p>No drafts found</p>
            </div>
        `;
        return;
    }
    
    drafts.forEach(draft => {
        const emailItem = document.createElement('div');
        emailItem.classList.add('email-item', 'card', 'mb-2');
        emailItem.setAttribute('data-email-id', draft.id);
        
        // Store minimal email data for voice commands
        const minimalEmail = {
            id: draft.id,
            subject: draft.subject,
            snippet: draft.snippet,
            from: draft.from,
            is_draft: true
        };
        emailItem.setAttribute('data-email', JSON.stringify(minimalEmail));
        
        emailItem.innerHTML = ` 
            <div class="card-body">
                <!-- Edit button for drafts -->
                <button class="btn btn-icon btn-icon-sm btn-primary mark-read-btn" 
                        data-bs-toggle="tooltip" 
                        data-bs-placement="top"
                        title="Edit Draft"
                        onclick="editDraft('${draft.id}')">
                    <i class="fas fa-edit"></i>
                </button>
                <div class="d-flex align-items-start">
                    <div class="form-check me-2">
                        <input class="form-check-input" type="checkbox" value="${draft.id}" id="draft-${draft.id}">
                    </div>
                    <div class="flex-grow-1">
                        <div class="email-meta text-muted small mb-1">
                            <strong>To:</strong> ${draft.from || 'Unknown'} •
                            <span>${draft.date || ''}</span>
                        </div>
                        <h6 class="email-subject mb-1">${draft.subject || '(no subject)'}</h6>
                        <p class="email-snippet text-muted mb-2">${(draft.snippet || '').substring(0, 100)}...</p>
                    </div>
                </div>
                <div class="email-actions mt-2 d-flex align-items-center">
                    <!-- Primary actions: Edit and Delete -->
                    <button class="btn btn-icon btn-icon-sm btn-primary rounded-circle me-2" 
                            data-bs-toggle="tooltip" 
                            title="Edit Draft" 
                            onclick="editDraft('${draft.id}')">
                        <i class="fas fa-edit"></i>
                    </button>
                    
                    <button class="btn btn-icon btn-icon-sm btn-danger rounded-circle me-2" 
                            data-bs-toggle="tooltip" 
                            title="Delete Draft" 
                            onclick="deleteDraft('${draft.id}')">
                        <i class="fas fa-trash"></i>
                    </button>
                    
                    <!-- Dropdown for secondary actions -->
                    <div class="dropdown">
                        <button class="btn btn-icon btn-icon-sm btn-secondary rounded-circle" 
                                data-bs-toggle="dropdown" 
                                aria-expanded="false" 
                                data-bs-toggle="tooltip" 
                                title="More actions">
                            <i class="fas fa-ellipsis-v"></i>
                        </button>
                        <ul class="dropdown-menu">
                            <li>
                                <button class="dropdown-item" 
                                        onclick="useDraft(${JSON.stringify(draft).replace(/"/g, '&quot;')})">
                                    <i class="fas fa-paper-plane me-2"></i> Send Draft
                                </button>
                            </li>
                        </ul>
                    </div>
                </div>
            </div>
        `;
        
        emailsDiv.appendChild(emailItem);
    });
    
    // Update email count
    const emailCount = document.getElementById('email-count');
    if (emailCount) {
        emailCount.textContent = drafts.length;
    }
    
    // Update theme for mark as read buttons
    updateMarkAsReadButtonsTheme();
    
    // Initialize tooltips for the newly added elements
    initializeTooltips();
}




// Generate reply function - COMPLETELY REVISED
async function generateReply() {
    console.log('=== GENERATE REPLY FUNCTION STARTED ===');
    
    // Check if required elements exist
    if (!emailArea || !summaryArea || !replyArea) {
        console.error('Required elements not found:', {
            emailArea: !!emailArea,
            summaryArea: !!summaryArea,
            replyArea: !!replyArea
        });
        showNotification('Required elements not found. Please refresh the page.', 'error');
        return;
    }
    
    const emailText = emailArea.value.trim();
    console.log('Email text length:', emailText.length);
    console.log('Email text preview:', emailText.substring(0, 100) + '...');
    
    if (!emailText) {
        showNotification('Please enter email text first', 'error');
        return;
    }
    
    // Update UI to show loading state
    summaryArea.value = 'Generating summary...';
    replyArea.value = 'Generating reply...';
    
    if (genBtn) {
        genBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Processing...';
        genBtn.disabled = true;
    }
    
    try {
        // Get CSRF token
        const csrfToken = getCSRFToken();
        console.log('CSRF Token:', csrfToken ? 'Found' : 'Not found');
        
        if (!csrfToken) {
            throw new Error('CSRF token not found. Please refresh the page.');
        }
        
        // Prepare request data
        const requestData = {
            email_text: emailText
        };
        console.log('Request data:', requestData);
        
        // Make the API request
        console.log('Sending request to /api/generate-reply/');
        const response = await fetch('/api/generate-reply/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify(requestData)
        });
        
        console.log('Response status:', response.status);
        console.log('Response headers:', response.headers);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('Response data:', data);
        
        if (data.ok) {
            // Update UI with successful response
            summaryArea.value = data.summary || 'No summary generated';
            replyArea.value = data.draft_reply || 'No reply generated';
            
            // Auto-populate draft message if available
            if (draftMessageArea && data.draft_reply) {
                draftMessageArea.value = data.draft_reply;
            }
            
            showNotification('Reply generated successfully!', 'success');
        } else {
            // Handle API error
            const errorMessage = data.error || 'Unknown error occurred';
            summaryArea.value = `Error: ${errorMessage}`;
            replyArea.value = `Error: ${errorMessage}`;
            showNotification(`Failed to generate reply: ${errorMessage}`, 'error');
        }
    } catch (error) {
        console.error('Error in generateReply:', error);
        const errorMessage = error.message || 'Network error occurred';
        summaryArea.value = `Error: ${errorMessage}`;
        replyArea.value = `Error: ${errorMessage}`;
        showNotification(`Error: ${errorMessage}`, 'error');
    } finally {
        // Reset button state
        if (genBtn) {
            genBtn.innerHTML = '<i class="fas fa-robot me-2"></i> Summarize & Generate';
            genBtn.disabled = false;
        }
        console.log('=== GENERATE REPLY FUNCTION ENDED ===');
    }
}
// Generate tone-based reply function
async function generateToneReply() {
    console.log('=== GENERATE TONE REPLY FUNCTION STARTED ===');
    
    // Check if required elements exist
    if (!emailArea || !summaryArea || !replyArea) {
        console.error('Required elements not found:', {
            emailArea: !!emailArea,
            summaryArea: !!summaryArea,
            replyArea: !!replyArea
        });
        showNotification('Required elements not found. Please refresh the page.', 'error');
        return;
    }
    
    const emailText = emailArea.value.trim();
    console.log('Email text length:', emailText.length);
    console.log('Email text preview:', emailText.substring(0, 100) + '...');
    
    if (!emailText) {
        showNotification('Please enter email text first', 'error');
        return;
    }
    
    // Get the selected tone
    const toneSelect = document.getElementById('reply_tone');
    const selectedTone = toneSelect ? toneSelect.value : 'professional';
    
    // Update UI to show loading state
    summaryArea.value = 'Generating summary...';
    replyArea.value = 'Generating reply...';
    
    if (genToneBtn) {
        genToneBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Processing...';
        genToneBtn.disabled = true;
    }
    
    try {
        // Get CSRF token
        const csrfToken = getCSRFToken();
        console.log('CSRF Token:', csrfToken ? 'Found' : 'Not found');
        
        if (!csrfToken) {
            throw new Error('CSRF token not found. Please refresh the page.');
        }
        
        // Prepare request data
        const requestData = {
            email_text: emailText,
            tone: selectedTone
        };
        console.log('Request data:', requestData);
        
        // Make the API request to the new endpoint
        const endpoint = '/api/generate-tone/';
        console.log('Sending request to', endpoint);
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify(requestData)
        });
        
        console.log('Response status:', response.status);
        console.log('Response headers:', response.headers);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('Response data:', data);
        
        if (data.ok) {
            // Update UI with successful response
            summaryArea.value = data.summary || 'No summary generated';
            replyArea.value = data.draft_reply || 'No reply generated';
            
            // Auto-populate draft message if available
            if (draftMessageArea && data.draft_reply) {
                draftMessageArea.value = data.draft_reply;
            }
            
            showNotification('Reply generated successfully!', 'success');
        } else {
            // Handle API error
            const errorMessage = data.error || 'Unknown error occurred';
            summaryArea.value = `Error: ${errorMessage}`;
            replyArea.value = `Error: ${errorMessage}`;
            showNotification(`Failed to generate reply: ${errorMessage}`, 'error');
        }
    } catch (error) {
        console.error('Error in generateToneReply:', error);
        const errorMessage = error.message || 'Network error occurred';
        summaryArea.value = `Error: ${errorMessage}`;
        replyArea.value = `Error: ${errorMessage}`;
        showNotification(`Error: ${errorMessage}`, 'error');
    } finally {
        // Reset button state
        if (genToneBtn) {
            genToneBtn.innerHTML = '<i class="fas fa-robot me-2"></i>Generate with Tone';
            genToneBtn.disabled = false;
        }
        console.log('=== GENERATE TONE REPLY FUNCTION ENDED ===');
    }
}
// Mark email as read function
async function markAsRead(emailId, buttonElement) {
    console.log('markAsRead called with emailId:', emailId);
    try {
        // Disable the button to prevent multiple clicks
        buttonElement.disabled = true;
        buttonElement.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
        
        const csrfToken = getCSRFToken();
        console.log('CSRF Token:', csrfToken);
        
        const response = await fetch(`/api/mark-as-read/${emailId}/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            }
        });
        
        console.log('Response status:', response.status);
        const data = await response.json();
        console.log('Response data:', data);
        
        if (data.ok) {
            // Find the email element and remove it with animation
            const emailElement = document.querySelector(`[data-email-id="${emailId}"]`);
            if (emailElement) {
                // Add fade-out animation
                emailElement.style.transition = 'opacity 0.3s ease';
                emailElement.style.opacity = '0';
                
                // Remove the element after animation completes
                setTimeout(() => {
                    emailElement.remove();
                    
                    // Update email count
                    const emailCount = document.getElementById('email-count');
                    if (emailCount) {
                        const currentCount = parseInt(emailCount.textContent);
                        emailCount.textContent = Math.max(0, currentCount - 1);
                    }
                    
                    // Check if there are any emails left on the current page
                    const remainingEmails = document.querySelectorAll('.email-item');
                    if (remainingEmails.length === 0) {
                        // If we're not on the first page, go back one page
                        if (currentPage > 1) {
                            loadEmails(currentPage - 1);
                        } else {
                            // If we're on the first page, reload the current page
                            loadEmails(currentPage);
                        }
                    }
                }, 300);
            }
            
            showNotification('Email marked as read', 'success');
        } else {
            // Re-enable the button on error
            buttonElement.disabled = false;
            buttonElement.innerHTML = '<i class="fas fa-check"></i>';
            showNotification('Failed to mark email as read: ' + (data.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Error in markAsRead:', error);
        // Re-enable the button on error
        buttonElement.disabled = false;
        buttonElement.innerHTML = '<i class="fas fa-check"></i>';
        showNotification('Network error: ' + error.message, 'error');
    }
}
// Archive email function
async function archiveEmail(emailId) {
    try {
        const response = await fetch(`/api/archive-email/${emailId}/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            }
        });
        
        const data = await response.json();
        
        if (data.ok) {
            // Remove the email from the list with animation
            const emailElement = document.querySelector(`[data-email-id="${emailId}"]`);
            if (emailElement) {
                emailElement.style.transition = 'opacity 0.3s ease';
                emailElement.style.opacity = '0';
                setTimeout(() => emailElement.remove(), 300);
            }
            
            showNotification('Email archived successfully', 'success');
            
            // Update email count
            const emailCount = document.getElementById('email-count');
            if (emailCount) {
                const currentCount = parseInt(emailCount.textContent);
                emailCount.textContent = Math.max(0, currentCount - 1);
            }
            
            // Reload emails if no emails left
            const remainingEmails = document.querySelectorAll('.email-item');
            if (remainingEmails.length === 0) {
                loadEmails(currentPage);
            }
        } else {
            showNotification('Failed to archive email: ' + (data.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        showNotification('Network error: ' + error.message, 'error');
    }
}
// Delete email function
async function deleteEmail(emailId) {
    try {
        const response = await fetch(`/api/delete-email/${emailId}/`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            }
        });
        
        const data = await response.json();
        
        if (data.ok) {
            // Remove the email from the list with animation
            const emailElement = document.querySelector(`[data-email-id="${emailId}"]`);
            if (emailElement) {
                emailElement.style.transition = 'opacity 0.3s ease';
                emailElement.style.opacity = '0';
                setTimeout(() => emailElement.remove(), 300);
            }
            
            showNotification('Email deleted successfully', 'success');
            
            // Update email count
            const emailCount = document.getElementById('email-count');
            if (emailCount) {
                const currentCount = parseInt(emailCount.textContent);
                emailCount.textContent = Math.max(0, currentCount - 1);
            }
            
            // Reload emails if no emails left
            const remainingEmails = document.querySelectorAll('.email-item');
            if (remainingEmails.length === 0) {
                loadEmails(currentPage);
            }
        } else {
            showNotification('Failed to delete email: ' + (data.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        showNotification('Network error: ' + error.message, 'error');
    }
}
// Edit draft function
async function editDraft(draftId) {
    try {
        const response = await fetch(`/api/draft/${draftId}/`);
        const data = await response.json();
        
        if (data.ok) {
            const draft = data.draft;
            // Set the editing draft ID
            editingDraftId = draftId;
            
            // Populate the draft form with the draft data
            if (toInput) toInput.value = draft.to || '';
            if (subjectInput) subjectInput.value = draft.subject || '';
            if (draftMessageArea) draftMessageArea.value = draft.body || '';
            
            // Scroll to the draft form
            document.getElementById('save').scrollIntoView({ behavior: 'smooth', block: 'start' });
        } else {
            showNotification('Failed to load draft: ' + data.error, 'error');
        }
    } catch (error) {
        showNotification('Error loading draft: ' + error.message, 'error');
    }
}
// Delete draft function
async function deleteDraft(draftId) {
    if (!confirm('Are you sure you want to delete this draft?')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/draft/${draftId}/`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            }
        });
        
        const data = await response.json();
        
        if (data.ok) {
            // Remove the draft from the list with animation
            const draftElement = document.querySelector(`[data-email-id="${draftId}"]`);
            if (draftElement) {
                draftElement.style.transition = 'opacity 0.3s ease';
                draftElement.style.opacity = '0';
                setTimeout(() => draftElement.remove(), 300);
            }
            
            showNotification('Draft deleted successfully', 'success');
            
            // Update draft count
            const emailCount = document.getElementById('email-count');
            if (emailCount) {
                const currentCount = parseInt(emailCount.textContent);
                emailCount.textContent = Math.max(0, currentCount - 1);
            }
            
            // Reload drafts if no drafts left
            const remainingDrafts = document.querySelectorAll('.email-item');
            if (remainingDrafts.length === 0) {
                loadDrafts(currentDraftsPage);
            }
        } else {
            showNotification('Failed to delete draft: ' + (data.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        showNotification('Error deleting draft: ' + error.message, 'error');
    }
}
// Use draft function
// Use draft function
function useDraft(draft) {
    if (emailArea) {
        emailArea.value = draft.body || '';
        emailArea.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}
// Save draft function - FIXED
async function saveDraft() {
    console.log('saveDraft called');
    if (!toInput || !subjectInput || !draftMessageArea) {
        console.error('Required elements not found:', { toInput, subjectInput, draftMessageArea });
        showNotification('Required elements not found', 'error');
        return;
    }
    
    const to = toInput.value.trim();
    const subject = subjectInput.value.trim();
    const body = draftMessageArea.value.trim();
    console.log('Draft data:', { to, subject, body: body.substring(0, 50) + '...' });
    
    if (!to || !subject || !body) {
        showNotification('Please fill in To, Subject, and Body', 'error');
        return;
    }
    
    try {
        const csrfToken = getCSRFToken();
        console.log('CSRF Token:', csrfToken);
        
        let url, method;
        if (editingDraftId) {
            // Update existing draft - use correct URL pattern
            url = `/api/drafts/${editingDraftId}/update/`;
            method = 'PUT';
        } else {
            // Create new draft - use correct URL pattern
            url = '/api/drafts/save/';
            method = 'POST';
        }
        
        console.log(`Making ${method} request to ${url}`);
        
        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({ to, subject, body })
        });
        
        console.log('Response status:', response.status);
        
        // Check if response is ok before parsing JSON
        if (!response.ok) {
            const errorText = await response.text();
            console.error('Server error response:', errorText);
            
            // Try to parse as JSON if possible
            let errorMessage = errorText;
            try {
                const errorData = JSON.parse(errorText);
                errorMessage = errorData.error || errorText;
            } catch (e) {
                // Not JSON, use as is
            }
            
            throw new Error(`Server error: ${response.status} - ${errorMessage.substring(0, 100)}`);
        }
        
        // Verify content type is JSON before parsing
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            const text = await response.text();
            console.error('Non-JSON response:', text);
            throw new Error(`Expected JSON response, got: ${text.substring(0, 100)}`);
        }
        
        const data = await response.json();
        console.log('Response data:', data);
        
        if (data.ok) {
            showNotification(editingDraftId ? 'Draft updated successfully!' : 'Draft saved successfully!', 'success');
            subjectInput.value = '';
            draftMessageArea.value = '';
            editingDraftId = null; // Reset to editing draft ID
            
            // Reload drafts if we are on the drafts page
            if (currentView === 'drafts') {
                loadDrafts(currentDraftsPage);
            }
        } else {
            showNotification('Failed to save draft: ' + (data.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Error in saveDraft:', error);
        showNotification('Error saving draft: ' + error.message, 'error');
    }
}
// ################################


// Get CSRF token for Django - IMPROVED
function getCSRFToken() {
    // Method 1: From window object (most reliable)
    if (window.CSRF_TOKEN) {
        return window.CSRF_TOKEN;
    }
    
    // Method 2: From meta tag
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    if (metaTag) {
        return metaTag.getAttribute('content');
    }
    
    // Method 3: From cookie
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, 10) === ('csrftoken=')) {
                return decodeURIComponent(cookie.substring(10));
            }
        }
    }
    
    console.error('CSRF Token not found!');
    return null;
}

// Show notification function - IMPROVED
function showNotification(message, type = 'info') {
    console.log('Showing notification:', message, type);
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `alert alert-${type === 'error' ? 'danger' : type === 'warning' ? 'warning' : 'success'} alert-dismissible fade show position-fixed`;
    notification.style.top = '20px';
    notification.style.right = '20px';
    notification.style.zIndex = '9999';
    notification.style.minWidth = '300px';
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    
    // Add to document
    document.body.appendChild(notification);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        notification.remove();
    }, 5000);
}
// Helper function to extract email address from a string - FIXED
function extractEmailAddress(text) {
    // Handle null/undefined and convert to string
    if (text == null) return '';
    const str = String(text); // Convert to string safely
    
    // Define regex pattern locally to avoid any scope issues
    const emailPattern = /([a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+\.[a-zA-Z0-9._-]+)/;
    const match = str.match(emailPattern);
    return match ? match[0] : '';
}
// Use email function - IMPROVED
async function useEmail(email) {
    if (emailArea) {
        // Show loading state
        emailArea.value = 'Loading email content...';
        
        try {
            // Fetch the full email details
            const response = await fetch(`/api/email/${email.id}/`);
            const data = await response.json();
            
            if (data.ok) {
                const fullEmail = data.email;
                const emailContent = `
From: ${fullEmail.from || 'Unknown'}
Subject: ${fullEmail.subject || 'No Subject'}
Date: ${fullEmail.date || ''}
 ${fullEmail.body_text || fullEmail.body || ''}
                `.trim();
                
                emailArea.value = emailContent;
                
                // Store thread ID for thread analysis
                if (fullEmail.threadId) {
                    emailArea.setAttribute('data-thread-id', fullEmail.threadId);
                }
                
                // Set recipient email address
                if (toInput) {
                    let recipientEmail = '';
                    try {
                        recipientEmail = extractEmailAddress(fullEmail.from);
                    } catch (e) {
                        console.error('Email extraction error:', e);
                        recipientEmail = fullEmail.from || '';
                    }
                    toInput.value = recipientEmail;
                    
                    // Add visual feedback
                    toInput.classList.add('border-success');
                    setTimeout(() => {
                        toInput.classList.remove('border-success');
                    }, 2000);
                    
                    console.log('Set recipient email to:', recipientEmail);
                }
                
                // Set subject
                if (subjectInput) {
                    subjectInput.value = fullEmail.subject ? `Re: ${fullEmail.subject}` : 'Re: Your email';
                }
            } else {
                // Handle the case where the email is not found
                if (response.status === 404) {
                    emailArea.value = 'This email is no longer available. It may have been deleted or moved.';
                    showNotification('Email no longer available', 'warning');
                } else {
                    emailArea.value = `Error loading email: ${data.error}`;
                    showNotification('Failed to load email', 'error');
                }
            }
        } catch (error) {
            emailArea.value = `Error loading email: ${error.message}`;
            showNotification('Network error occurred', 'error');
        }
    }
    
    if (emailArea) {
        emailArea.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}
// Add this function to handle "Reply All"
function useEmailForReplyAll(email) {
    // First, use the existing useEmail function to load email content
    useEmail(email);
    
    // Then, if we have the full email details, add all recipients
    fetch(`/api/email/${email.id}/`)
        .then(response => response.json())
        .then(data => {
            if (data.ok && data.email) {
                const fullEmail = data.email;
                let recipients = [];
                
                // Add original sender
                if (fullEmail.from) {
                    recipients.push(extractEmailAddress(fullEmail.from));
                }
                
                // Add "To" recipients
                if (fullEmail.to) {
                    const toEmails = fullEmail.to.split(',').map(email => extractEmailAddress(email.trim())).filter(email => email);
                    recipients = recipients.concat(toEmails);
                }
                
                // Add "Cc" recipients if available
                if (fullEmail.cc) {
                    const ccEmails = fullEmail.cc.split(',').map(email => extractEmailAddress(email.trim())).filter(email => email);
                    recipients = recipients.concat(ccEmails);
                }
                
                // Remove duplicates and set the recipient field
                const uniqueRecipients = [...new Set(recipients)];
                if (toInput) {
                    toInput.value = uniqueRecipients.join(', ');
                    
                    // Add visual feedback
                    toInput.classList.add('border-info');
                    setTimeout(() => {
                        toInput.classList.remove('border-info');
                    }, 2000);
                }
                
                // Change subject to indicate it's a reply to all
                if (subjectInput) {
                    subjectInput.value = fullEmail.subject ? `Re: ${fullEmail.subject} (Reply All)` : 'Re: Your email (Reply All)';
                }
                
                showNotification('Reply All mode activated', 'info');
            }
        })
        .catch(error => {
            console.error('Error fetching email details for reply all:', error);
            showNotification('Error setting up Reply All', 'error');
        });
}
// Render pagination buttons
function renderPagination(data, isDrafts = false) {
    paginationDiv.innerHTML = ''; // clear existing
    const container = document.createElement('div');
    container.className = 'd-flex justify-content-between align-items-center flex-wrap mt-3';
    
    // Left side: Per page selector
    const perPageDiv = document.createElement('div');
    perPageDiv.className = 'd-flex align-items-center';
    
    const perPageLabel = document.createElement('span');
    perPageLabel.className = 'me-2';
    perPageLabel.textContent = 'Show:';
    
    const perPageSelect = document.createElement('select');
    perPageSelect.className = 'form-select form-select-sm';
    perPageSelect.style.width = 'auto';
    
    [5, 10, 20, 50].forEach(num => {
        const option = document.createElement('option');
        option.value = num;
        option.textContent = num;
        if (num === perPage) { // Use the global perPage variable
            option.selected = true;
        }
        perPageSelect.appendChild(option);
    });
    
    perPageSelect.addEventListener('change', function() {
        perPage = parseInt(this.value); // Update the global perPage variable
        if (isDrafts) {
            loadDrafts(1);
        } else {
            loadEmails(1);
        }
    });
    
    perPageDiv.appendChild(perPageLabel);
    perPageDiv.appendChild(perPageSelect);
    
    // Middle: Page numbers
    const pageNumbersDiv = document.createElement('div');
    pageNumbersDiv.className = 'd-flex align-items-center';
    
    // Previous button
    const prevBtn = document.createElement('button');
    prevBtn.className = 'btn btn-outline-primary btn-sm me-1';
    prevBtn.innerHTML = '<i class="fas fa-chevron-left"></i>';
    prevBtn.disabled = !data.has_previous;
    prevBtn.addEventListener('click', () => {
        if (data.has_previous) {
            if (isDrafts) {
                loadDrafts(currentDraftsPage - 1);
            } else {
                loadEmails(currentPage - 1);
            }
        }
    });
    pageNumbersDiv.appendChild(prevBtn);
    
    // Page numbers
    const maxVisiblePages = 5;
    let startPage = Math.max(1, (isDrafts ? currentDraftsPage : currentPage) - Math.floor(maxVisiblePages / 2));
    let endPage = Math.min(data.total_pages, startPage + maxVisiblePages - 1);
    
    if (endPage - startPage < maxVisiblePages - 1) {
        startPage = Math.max(1, endPage - maxVisiblePages + 1);
    }
    
    // First page
    if (startPage > 1) {
        const firstBtn = document.createElement('button');
        firstBtn.className = 'btn btn-outline-primary btn-sm me-1';
        firstBtn.textContent = '1';
        firstBtn.addEventListener('click', () => {
            if (isDrafts) {
                loadDrafts(1);
            } else {
                loadEmails(1);
            }
        });
        pageNumbersDiv.appendChild(firstBtn);
        
        if (startPage > 2) {
            const ellipsis = document.createElement('span');
            ellipsis.className = 'mx-1';
            ellipsis.textContent = '...';
            pageNumbersDiv.appendChild(ellipsis);
        }
    }
    
    // Visible page numbers
    for (let i = startPage; i <= endPage; i++) {
        const pageBtn = document.createElement('button');
        pageBtn.className = `btn btn-sm me-1 ${i === (isDrafts ? currentDraftsPage : currentPage) ? 'btn-primary' : 'btn-outline-primary'}`;
        pageBtn.textContent = i;
        pageBtn.addEventListener('click', () => {
            if (isDrafts) {
                loadDrafts(i);
            } else {
                loadEmails(i);
            }
        });
        pageNumbersDiv.appendChild(pageBtn);
    }
    
    // Last page
    if (endPage < data.total_pages) {
        if (endPage < data.total_pages - 1) {
            const ellipsis = document.createElement('span');
            ellipsis.className = 'mx-1';
            ellipsis.textContent = '...';
            pageNumbersDiv.appendChild(ellipsis);
        }
        
        const lastBtn = document.createElement('button');
        lastBtn.className = 'btn btn-outline-primary btn-sm me-1';
        lastBtn.textContent = data.total_pages;
        lastBtn.addEventListener('click', () => {
            if (isDrafts) {
                loadDrafts(data.total_pages);
            } else {
                loadEmails(data.total_pages);
            }
        });
        pageNumbersDiv.appendChild(lastBtn);
    }
    
    // Next button
    const nextBtn = document.createElement('button');
    nextBtn.className = 'btn btn-outline-primary btn-sm';
    nextBtn.innerHTML = '<i class="fas fa-chevron-right"></i>';
    nextBtn.disabled = !data.has_next;
    nextBtn.addEventListener('click', () => {
        if (data.has_next) {
            if (isDrafts) {
                loadDrafts(currentDraftsPage + 1);
            } else {
                loadEmails(currentPage + 1);
            }
        }
    });
    pageNumbersDiv.appendChild(nextBtn);
    
    // Right side: Page info
    const pageInfoDiv = document.createElement('div');
    pageInfoDiv.className = 'text-muted small';
    
    const startItem = ((isDrafts ? currentDraftsPage : currentPage) - 1) * perPage + 1;
    const endItem = Math.min((isDrafts ? currentDraftsPage : currentPage) * perPage, data.total_emails || data.total_drafts);
    
    pageInfoDiv.textContent = `Showing ${startItem}-${endItem} of ${data.total_emails || data.total_drafts} ${isDrafts ? 'drafts' : 'emails'}`;
    
    // Add all parts to the container
    container.appendChild(perPageDiv);
    container.appendChild(pageNumbersDiv);
    container.appendChild(pageInfoDiv);
    
    paginationDiv.appendChild(container);
}
// Toggle visibility of bulk action button
function toggleBulkActionButton() {
    const checkedBoxes = document.querySelectorAll('.email-item input[type="checkbox"]:checked');
    const bulkButton = document.getElementById('bulk-mark-read');
    
    if (bulkButton) {
        bulkButton.style.display = checkedBoxes.length > 0 ? 'inline-block' : 'none';
    }
}
// Update the "Select All" checkbox state based on individual checkboxes
function updateSelectAllCheckbox() {
    const selectAllCheckbox = document.getElementById('select-all-emails');
    const emailCheckboxes = document.querySelectorAll('.email-item input[type="checkbox"]');
    
    if (selectAllCheckbox && emailCheckboxes.length > 0) {
        const checkedBoxes = document.querySelectorAll('.email-item input[type="checkbox"]:checked');
        
        if (checkedBoxes.length === 0) {
            selectAllCheckbox.indeterminate = false;
            selectAllCheckbox.checked = false;
        } else if (checkedBoxes.length === emailCheckboxes.length) {
            selectAllCheckbox.indeterminate = false;
            selectAllCheckbox.checked = true;
        } else {
            selectAllCheckbox.indeterminate = true;
        }
    }
}
// Add this function to handle bulk mark as read
async function markSelectedAsRead() {
    const checkboxes = document.querySelectorAll('.email-item input[type="checkbox"]:checked');
    const emailIds = Array.from(checkboxes).map(cb => cb.value);
    
    if (emailIds.length === 0) {
        showNotification('Please select emails to mark as read', 'warning');
        return;
    }
    
    try {
        const response = await fetch('/api/bulk-mark-as-read/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({ email_ids: emailIds })
        });
        
        const data = await response.json();
        
        if (data.ok) {
            // Remove selected emails from the list
            checkboxes.forEach(checkbox => {
                const emailElement = checkbox.closest('.email-item');
                if (emailElement) {
                    emailElement.style.transition = 'opacity 0.3s ease';
                    emailElement.style.opacity = '0';
                    setTimeout(() => emailElement.remove(), 300);
                }
            });
            
            // Update email count
            const emailCount = document.getElementById('email-count');
            if (emailCount) {
                const currentCount = parseInt(emailCount.textContent);
                emailCount.textContent = Math.max(0, currentCount - emailIds.length);
            }
            
            // Reset the "Select All" checkbox
            const selectAllCheckbox = document.getElementById('select-all-emails');
            if (selectAllCheckbox) {
                selectAllCheckbox.indeterminate = false;
                selectAllCheckbox.checked = false;
            }
            
            // Hide the bulk action button
            const bulkButton = document.getElementById('bulk-mark-read');
            if (bulkButton) {
                bulkButton.style.display = 'none';
            }
            
            // Check if we need to reload the page
            const remainingEmails = document.querySelectorAll('.email-item');
            if (remainingEmails.length === 0) {
                // If we're not on the first page, go back one page
                if (currentView === 'emails') {
                    if (currentPage > 1) {
                        loadEmails(currentPage - 1);
                    } else {
                        // If we're on the first page, reload the current page
                        loadEmails(currentPage);
                    }
                } else {
                    if (currentDraftsPage > 1) {
                        loadDrafts(currentDraftsPage - 1);
                    } else {
                        // If we're on the first page, reload the current page
                        loadDrafts(currentDraftsPage);
                    }
                }
            }
            
            showNotification(`${emailIds.length} email(s) marked as read`, 'success');
        } else {
            showNotification('Failed to mark emails as read: ' + data.error, 'error');
        }
    } catch (error) {
        showNotification('Network error: ' + error.message, 'error');
    }
}
// Global function to stop voice speaking
function stopVoiceSpeaking() {
    if ("speechSynthesis" in window && speechSynthesis.speaking) {
        speechSynthesis.cancel();
        console.log('Voice synthesis stopped');
    }
    
    // Also stop through VoiceActions if available
    if (voiceActions) {
        voiceActions.stopVoiceSpeaking();
    }
}
// Function to open schedule meeting modal
function openScheduleMeetingModal(email) {
    console.log('Opening schedule meeting modal for email:', email);
    
    // Set the email ID in the hidden field
    document.getElementById('meeting-email-id').value = email.id;
    
    // Pre-fill title with the email subject
    document.getElementById('meeting-title').value = email.subject ? `Meeting: ${email.subject}` : 'Meeting';
    
    // Pre-fill description with the email snippet
    document.getElementById('meeting-description').value = email.snippet || '';
    
    // Extract the sender's email and set as an attendee
    let senderEmail = '';
    try {
        senderEmail = extractEmailAddress(email.from);
    } catch (e) {
        console.error('Email extraction error:', e);
        senderEmail = '';
    }
    if (senderEmail) {
        document.getElementById('meeting-attendees').value = senderEmail;
    }
    
    // Set default dates (today and tomorrow)
    const today = new Date();
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);
    
    // Format dates as YYYY-MM-DD
    const formatDate = (date) => {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    };
    
    document.getElementById('meeting-start-date').value = formatDate(today);
    document.getElementById('meeting-end-date').value = formatDate(tomorrow);
    
    // Set default times
    document.getElementById('meeting-start-time').value = '09:00';
    document.getElementById('meeting-end-time').value = '10:00';
    
    // Show the modal
    const modal = new bootstrap.Modal(document.getElementById('scheduleMeetingModal'));
    modal.show();
}
// Function to schedule a meeting
async function scheduleMeeting() {
    console.log('Scheduling meeting...');
    
    const form = document.getElementById('scheduleMeetingForm');
    const formData = new FormData(form);
    
    // Get form data
    const emailId = formData.get('email_id');
    const title = formData.get('title');
    const description = formData.get('description');
    const startDate = formData.get('start_date');
    const startTime = formData.get('start_time');
    const endDate = formData.get('end_date');
    const endTime = formData.get('end_time');
    const attendees = formData.get('attendees');
    
    // Validate required fields
    if (!title || !startDate || !startTime || !endDate || !endTime) {
        showNotification('Please fill in all required fields', 'error');
        return;
    }
    
    // Combine date and time
    const startDatetime = `${startDate}T${startTime}:00`;
    const endDatetime = `${endDate}T${endTime}:00`;
    
    // Parse attendees
    const attendeesList = attendees ? attendees.split(',').map(email => email.trim()).filter(email => email) : [];
    
    try {
        const csrfToken = getCSRFToken();
        console.log('CSRF Token:', csrfToken);
        
        const requestData = {
            email_id: emailId,
            title: title,
            description: description,
            start_datetime: startDatetime,
            end_datetime: endDatetime,
            attendees: attendeesList
        };
        
        console.log('Request data:', requestData);
        
        const response = await fetch('/api/schedule-meeting/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify(requestData)
        });
        
        console.log('Response status:', response.status);
        const data = await response.json();
        console.log('Response data:', data);
        
        if (data.ok) {
            // Close the modal
            const modal = bootstrap.Modal.getInstance(document.getElementById('scheduleMeetingModal'));
            modal.hide();
            
            // Show success message with link to the event
            showNotification(
                `Meeting scheduled successfully! <a href="${data.html_link}" target="_blank" class="btn btn-sm btn-light ms-2">View in Calendar</a>`, 
                'success'
            );
        } else {
            // Check if re-authentication is needed
            if (data.needs_reauth) {
                showNotification(
                    `Calendar access permission required. <a href="/force-reauth/" class="btn btn-sm btn-light ms-2">Re-authenticate Now</a>`, 
                    'warning'
                );
            } else {
                showNotification(`Failed to schedule meeting: ${data.error}`, 'error');
            }
        }
    } catch (error) {
        console.error('Error scheduling meeting:', error);
        showNotification(`Error scheduling meeting: ${error.message}`, 'error');
    }
}
// Function to show voice help
function showVoiceHelp() {
    // Fetch voice commands from backend
    fetch("/api/voice-command-help/")
        .then((response) => response.json())
        .then((data) => {
            if (data.ok && data.commands) {
                displayVoiceCommands(data.commands);
                speakVoiceCommands(data.commands);
            } else {
                showNotification("Failed to load voice commands", "error");
            }
        })
        .catch((error) => {
            console.error("Error fetching voice commands:", error);
            showNotification("Error loading voice commands", "error");
        });
}
// Function to display voice commands in modal
function displayVoiceCommands(commands) {
    const modal = document.getElementById("voiceHelpModal");
    const commandsList = document.getElementById("voice-commands-list");
    // Clear existing commands
    commandsList.innerHTML = "";
    // Add each command to the list
    commands.forEach((cmd) => {
        const item = document.createElement("div");
        item.className = "list-group-item list-group-item-action";
        item.innerHTML = `
            <div class="d-flex justify-content-between align-items-center">
                <div>
                    <strong>${cmd.command}</strong>
                    <p class="mb-0 text-muted">${cmd.description}</p>
                </div>
                <button class="btn btn-sm btn-outline-primary" onclick="speakText('${cmd.command}')">
                    <i class="fas fa-volume-up"></i>
                </button>
            </div>
        `;
        commandsList.appendChild(item);
    });
    // Show the modal
    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();
}
// Function to speak all commands
function speakAllCommands() {
    fetch("/api/voice-command-help/")
        .then((response) => response.json())
        .then((data) => {
            if (data.ok && data.commands) {
                speakVoiceCommands(data.commands);
            }
        })
        .catch((error) => {
            console.error("Error fetching voice commands:", error);
        });
}
// Function to speak voice commands
function speakVoiceCommands(commands) {
    if ("speechSynthesis" in window) {
        let text = "Available voice commands are: ";
        commands.forEach((cmd) => {
            text += `${cmd.command}. `;
        });
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 0.9;
        utterance.pitch = 1;
        utterance.volume = 1;
        speechSynthesis.speak(utterance);
    }
}
// Function to speak specific text
function speakText(text) {
    if ("speechSynthesis" in window) {
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 0.9;
        utterance.pitch = 1;
        utterance.volume = 1;
        speechSynthesis.speak(utterance);
    }
}
// Function to toggle voice recognition
function toggleVoiceRecognition() {
    console.log('toggleVoiceRecognition called');
    if (voiceActions) {
        voiceActions.toggle();
    } else {
        console.error('VoiceActions not initialized');
    }
}
// Function to load Gmail drafts (for "My Drafts" section)
async function loadMyDrafts() {
    try {
        const response = await fetch('/api/drafts/', {
            headers: {
                'Content-Type': 'application/json',
            }
        });
        
        const data = await response.json();
        
        if (data.ok) {
            displayMyDrafts(data.drafts);
        } else {
            console.error('Error loading drafts:', data.error);
            document.getElementById('my-drafts-container').innerHTML = 
                `<p class="error">Error loading drafts: ${data.error}</p>`;
        }
    } catch (error) {
        console.error('Error loading drafts:', error);
        document.getElementById('my-drafts-container').innerHTML = 
            `<p class="error">Failed to load drafts. Please try again.</p>`;
    }
}

// Function to display drafts in "My Drafts" section
function displayMyDrafts(drafts) {
    const draftsContainer = document.getElementById('my-drafts-container');
    
    if (!drafts || drafts.length === 0) {
        draftsContainer.innerHTML = `
            <div class="no-drafts">
                <p>No drafts found. Generate a reply to create a draft.</p>
                <p>Or save a draft using the "Save Draft to Gmail" button.</p>
            </div>
        `;
        return;
    }
    
    draftsContainer.innerHTML = drafts.map(draft => `
        <div class="draft-item" data-draft-id="${draft.id}">
            <div class="draft-header">
                <h3 class="draft-subject">${draft.subject}</h3>
                <div class="draft-actions">
                    <button class="btn-edit" onclick="editDraft('${draft.id}')">Edit</button>
                    <button class="btn-delete" onclick="deleteDraft('${draft.id}')">Delete</button>
                </div>
            </div>
            <div class="draft-meta">
                <p><strong>To:</strong> ${draft.from}</p>
                <p><strong>Date:</strong> ${new Date(draft.date).toLocaleString()}</p>
            </div>
            <div class="draft-content">
                <p>${draft.snippet}</p>
            </div>
        </div>
    `).join('');
}

// Load drafts when page loads
document.addEventListener('DOMContentLoaded', function() {
    loadMyDrafts();
});

// Function to load drafts
async function loadMyDrafts() {
    try {
        console.log('Loading drafts...');
        const response = await fetch('/api/drafts/');
        const data = await response.json();
        
        console.log('Drafts response:', data);
        
        if (data.ok) {
            displayDrafts(data.drafts);
        } else {
            console.error('Error loading drafts:', data.error);
            document.getElementById('my-drafts-container').innerHTML = 
                `<p class="error">Error: ${data.error}</p>`;
        }
    } catch (error) {
        console.error('Error loading drafts:', error);
        document.getElementById('my-drafts-container').innerHTML = 
            `<p class="error">Failed to load drafts</p>`;
    }
}

// Function to display drafts
function displayDrafts(drafts) {
    const container = document.getElementById('my-drafts-container');
    
    if (!drafts || drafts.length === 0) {
        container.innerHTML = '<p>No drafts found. Generate a reply to create a draft.</p>';
        return;
    }
    
    container.innerHTML = drafts.map(draft => `
        <div class="draft-item" data-draft-id="${draft.id}">
            <h3>${draft.subject}</h3>
            <p><strong>To:</strong> ${draft.from}</p>
            <p><strong>Date:</strong> ${new Date(draft.date).toLocaleString()}</p>
            <p>${draft.snippet}</p>
            <div class="draft-actions">
                <button onclick="editDraft('${draft.id}')">Edit</button>
                <button onclick="deleteDraft('${draft.id}')">Delete</button>
            </div>
        </div>
    `).join('');
}

// Function to load important emails
function loadImportantEmails() {
    const importantContainer = document.getElementById('important-emails-container');
    const importantLoading = document.getElementById('important-emails-loading');
    const loadImportantBtn = document.getElementById('load-important');
    
    // Show loading
    importantContainer.style.display = 'none';
    importantLoading.style.display = 'block';
    loadImportantBtn.disabled = true;
    
    // Fetch important emails from API
    fetch('/api/important-emails/')
      .then(response => response.json())
      .then(data => {
        if (data.ok) {
          renderImportantEmails(data.emails);
          document.getElementById('important-count').textContent = data.emails.length;
        } else {
          importantContainer.innerHTML = `<div class="alert alert-danger">Error: ${data.error}</div>`;
        }
      })
      .catch(error => {
        importantContainer.innerHTML = `<div class="alert alert-danger">Error loading important emails: ${error.message}</div>`;
      })
      .finally(() => {
        importantContainer.style.display = 'block';
        importantLoading.style.display = 'none';
        loadImportantBtn.disabled = false;
      });
}

// Function to load user settings
function loadUserSettings() {
    fetch('/api/user-settings/')
      .then(response => response.json())
      .then(data => {
        if (data.ok) {
          const settings = data.settings;
          document.getElementById('reply-tone-setting').value = settings.reply_tone;
          document.getElementById('refresh-interval').value = settings.refresh_interval;
          document.getElementById('auto-reply-enabled').checked = settings.auto_reply_enabled;
          document.getElementById('theme-setting').value = settings.theme;
          
          // Apply theme
          if (settings.theme === 'dark') {
            document.body.classList.add('dark-theme');
          }
        }
      })
      .catch(error => {
        console.error('Error loading user settings:', error);
      });
}

// Function to save settings
function saveSettings() {
    const settings = {
      reply_tone: document.getElementById('reply-tone-setting').value,
      refresh_interval: parseInt(document.getElementById('refresh-interval').value),
      auto_reply_enabled: document.getElementById('auto-reply-enabled').checked,
      theme: document.getElementById('theme-setting').value
    };
    
    fetch('/api/user-settings/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCSRFToken()
      },
      body: JSON.stringify(settings)
    })
    .then(response => response.json())
    .then(data => {
      if (data.ok) {
        showNotification('Settings saved successfully!', 'success');
        
        // Apply theme
        if (settings.theme === 'dark') {
          document.body.classList.add('dark-theme');
        } else {
          document.body.classList.remove('dark-theme');
        }
      } else {
        showNotification('Error: ' + data.error, 'error');
      }
    })
    .catch(error => {
      showNotification('Error saving settings: ' + error.message, 'error');
    });
}

// Function to toggle important status
function toggleImportant(messageId) {
    fetch(`/api/toggle-important/${messageId}/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCSRFToken()
      }
    })
    .then(response => response.json())
    .then(data => {
      if (data.ok) {
        // Refresh important emails list
        loadImportantEmails();
        // Also refresh inbox if we're on it
        if (document.getElementById('inbox-section').classList.contains('active')) {
          loadEmails(1);
        }
      } else {
        showNotification('Error: ' + data.error, 'error');
      }
    })
    .catch(error => {
      showNotification('Error toggling important status: ' + error.message, 'error');
    });
}

// Function to send a draft
// Function to send a draft
function sendDraft(draftId) {
    if (confirm('Are you sure you want to send this draft?')) {
      fetch(`/api/send-draft/${draftId}/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCSRFToken()
        }
      })
      .then(response => response.json())
      .then(data => {
        if (data.ok) {
          showNotification('Draft sent successfully!', 'success');
          loadDrafts(); // Refresh drafts list
        } else {
          showNotification('Error: ' + data.error, 'error');
        }
      })
      .catch(error => {
        showNotification('Error sending draft: ' + error.message, 'error');
      });
    }
}

// Function to delete a draft
function deleteDraft(draftId) {
    if (confirm('Are you sure you want to delete this draft?')) {
      fetch(`/api/draft/${draftId}/`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCSRFToken()
        }
      })
      .then(response => response.json())
      .then(data => {
        if (data.ok) {
          showNotification('Draft deleted successfully!', 'success');
          loadDrafts(); // Refresh drafts list
        } else {
          showNotification('Error: ' + data.error, 'error');
        }
      })
      .catch(error => {
        showNotification('Error deleting draft: ' + error.message, 'error');
      });
    }
}
// Edit draft function - FIXED
async function editDraft(draftId) {
    try {
        const response = await fetch(`/api/drafts/${draftId}/`);
        const data = await response.json();
        
        if (data.ok) {
            const draft = data.draft;
            // Set to editing draft ID
            editingDraftId = draftId;
            
            // Populate the draft form with the draft data
            if (toInput) toInput.value = draft.to || '';
            if (subjectInput) subjectInput.value = draft.subject || '';
            if (draftMessageArea) draftMessageArea.value = draft.body || '';
            
            // Scroll to the draft form
            document.getElementById('save').scrollIntoView({ behavior: 'smooth', block: 'start' });
        } else {
            showNotification('Failed to load draft: ' + data.error, 'error');
        }
    } catch (error) {
        showNotification('Error loading draft: ' + error.message, 'error');
    }
}
// Test function to identify correct endpoint
async function testDraftEndpoints() {
    const endpoints = [
        '/api/drafts/save/',
        '/api/save-draft/',
        '/api/drafts/save-to-gmail/',
        '/api/generated-drafts/save/'
    ];
    
    for (const endpoint of endpoints) {
        try {
            console.log(`Testing endpoint: ${endpoint}`);
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken()
                },
                body: JSON.stringify({
                    to: 'test@example.com',
                    subject: 'Test Draft',
                    body: 'Test body'
                })
            });
            
            console.log(`${endpoint} - Status: ${response.status}`);
            
            if (response.status === 200) {
                const data = await response.json();
                console.log(`${endpoint} - SUCCESS:`, data);
                return endpoint; // Return working URL
            } else {
                const errorText = await response.text();
                console.log(`${endpoint} - ERROR:`, errorText);
            }
        } catch (error) {
            console.log(`${endpoint} - EXCEPTION:`, error.message);
        }
    }
}

// Run this in your browser console to test all possible endpoints
// testDraftEndpoints();
// Function to delete a draft
function deleteDraft(draftId) {
    if (confirm('Are you sure you want to delete this draft?')) {
      fetch(`/api/draft/${draftId}/`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCSRFToken()
        }
      })
      .then(response => response.json())
      .then(data => {
        if (data.ok) {
          showNotification('Draft deleted successfully!', 'success');
          loadDrafts(); // Refresh drafts list
        } else {
          showNotification('Error: ' + data.error, 'error');
        }
      })
      .catch(error => {
        showNotification('Error deleting draft: ' + error.message, 'error');
      });
    }
}

// Function to edit draft
function editDraft(draftId) {
    fetch(`/api/draft/${draftId}/`)
        .then(response => response.json())
        .then(data => {
            if (data.ok) {
                const draft = data.draft;
                
                // Create edit modal
                const editModal = document.createElement('div');
                editModal.className = 'modal fade';
                editModal.id = 'editDraftModal';
                editModal.innerHTML = `
                    <div class="modal-dialog">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title">Edit Draft</h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                            </div>
                            <div class="modal-body">
                                <div class="mb-3">
                                    <label for="edit-draft-subject" class="form-label">Subject</label>
                                    <input type="text" class="form-control" id="edit-draft-subject" value="${draft.subject}">
                                </div>
                                <div class="mb-3">
                                    <label for="edit-draft-to" class="form-label">To</label>
                                    <input type="email" class="form-control" id="edit-draft-to" value="${draft.to}">
                                </div>
                                <div class="mb-3">
                                    <label for="edit-draft-body" class="form-label">Message</label>
                                    <textarea class="form-control" id="edit-draft-body" rows="10">${draft.body}</textarea>
                                </div>
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                                <button type="button" class="btn btn-primary" onclick="saveEditedDraft('${draftId}')">Save Changes</button>
                            </div>
                        </div>
                    </div>
                `;
                
                document.body.appendChild(editModal);
                
                // Show modal
                const modal = new bootstrap.Modal(editModal);
                modal.show();
                
                // Remove modal from DOM when hidden
                editModal.addEventListener('hidden.bs.modal', function () {
                    editModal.remove();
                });
            } else {
                showNotification('Error: ' + data.error, 'error');
            }
        })
        .catch(error => {
            showNotification('Error loading draft: ' + error.message, 'error');
        });
}

// Function to save edited draft
async function saveEditedDraft(draftId) {
    const subject = document.getElementById('edit-draft-subject').value;
    const to = document.getElementById('edit-draft-to').value;
    const body = document.getElementById('edit-draft-body').value;
    
    if (!subject || !to) {
        showNotification('Subject and recipient are required', 'error');
        return;
    }
    
    try {
        const response = await fetch(`/api/drafts/${draftId}/`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({
                subject: subject,
                to: to
            })
        });
        
        const data = await response.json();
        
        if (data.ok) {
            showNotification('Draft updated successfully!', 'success');
            
            // Close modal
            const modal = bootstrap.Modal.getInstance(document.getElementById('editDraftModal'));
            modal.hide();
            
            // Refresh drafts list
            loadDrafts();
        } else {
            showNotification('Error: ' + data.error, 'error');
        }
    } catch (error) {
        showNotification('Error saving draft: ' + error.message, 'error');
    }
}

// Update your existing viewDraft function to use the new edit modal
// Function to view draft details
function viewDraft(draftId) {
    fetch(`/api/draft/${draftId}/`)
        .then(response => response.json())
        .then(data => {
            if (data.ok) {
                const draft = data.draft;
                // Show draft content in a modal
                const viewModal = document.createElement('div');
                viewModal.className = 'modal fade';
                viewModal.id = 'viewDraftModal';
                viewModal.innerHTML = `
                    <div class="modal-dialog modal-lg">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title">${draft.subject}</h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                            </div>
                            <div class="modal-body">
                                <div class="mb-3">
                                    <label class="form-label">To</label>
                                    <p>${draft.to}</p>
                                </div>
                                <div class="mb-3">
                                    <label class="form-label">Date</label>
                                    <p>${new Date(draft.date).toLocaleString()}</p>
                                </div>
                                <div class="mb-3">
                                    <label class="form-label">Message</label>
                                    <div class="border rounded p-3 bg-light">
                                        <pre>${draft.body || 'No content available'}</pre>
                                    </div>
                                </div>
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                                <button type="button" class="btn btn-primary" onclick="editDraft('${draftId}')">Edit</button>
                                <button type="button" class="btn btn-success" onclick="sendGmailDraft('${draftId}')">Send</button>
                            </div>
                        </div>
                    </div>
                `;
                
                document.body.appendChild(viewModal);
                
                // Show modal
                const modal = new bootstrap.Modal(viewModal);
                modal.show();
                
                // Remove modal from DOM when hidden
                viewModal.addEventListener('hidden.bs.modal', function () {
                    viewModal.remove();
                });
            } else {
                showNotification('Error: ' + data.error, 'error');
            }
        })
        .catch(error => {
            showNotification('Error viewing draft: ' + error.message, 'error');
        });
}

// Function to copy draft content
function copyDraftContent(draftId) {
    fetch(`/api/draft/${draftId}/`)
        .then(response => response.json())
        .then(data => {
            if (data.ok) {
                const draft = data.draft;
                const textToCopy = draft.body || draft.snippet || '';
                
                navigator.clipboard.writeText(textToCopy).then(() => {
                    showNotification('Draft content copied to clipboard!', 'success');
                }).catch(() => {
                    showNotification('Failed to copy to clipboard', 'error');
                });
            } else {
                showNotification('Error: ' + data.error, 'error');
            }
        })
        .catch(error => {
            showNotification('Error copying draft content: ' + error.message, 'error');
        });
}

// Function to send Gmail draft
function sendGmailDraft(draftId) {
    if (confirm('Are you sure you want to send this draft?')) {
        // This would typically involve getting draft details and sending it
        // For now, we'll show a notification
        showNotification('Send functionality would be implemented here', 'info');
    }
}

// NEW FUNCTIONS FOR THREAD ANALYSIS AND SENTIMENT ANALYSIS

// Function to analyze current thread
async function analyzeCurrentThread() {
    const emailText = emailArea.value.trim();
    if (!emailText) {
        showNotification('Please enter email text first', 'error');
        return;
    }

    try {
        // Show loading state
        const threadAnalysisBtn = document.getElementById('analyze-thread');
        const originalText = threadAnalysisBtn.innerHTML;
        threadAnalysisBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Analyzing...';
        threadAnalysisBtn.disabled = true;

        const response = await fetch('/api/email-thread-analysis-from-text/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({ email_text: emailText })
        });
        
        const data = await response.json();
        
        if (data.ok) {
            // Display the thread analysis in a modal
            displayThreadAnalysisModal(data.thread_analysis);
            showNotification('Thread analysis completed', 'success');
        } else {
            showNotification('Failed to analyze thread: ' + data.error, 'error');
        }
    } catch (error) {
        showNotification('Error analyzing thread: ' + error.message, 'error');
    } finally {
        // Reset button state
        const threadAnalysisBtn = document.getElementById('analyze-thread');
        threadAnalysisBtn.innerHTML = '<i class="fas fa-comments me-2"></i>Analyze Thread';
        threadAnalysisBtn.disabled = false;
    }
}

// Function to analyze current sentiment
async function analyzeCurrentSentiment() {
    const emailText = emailArea.value.trim();
    if (!emailText) {
        showNotification('Please enter email text first', 'error');
        return;
    }

    try {
        // Show loading state
        const sentimentAnalysisBtn = document.getElementById('sentiment-analysis');
        const originalText = sentimentAnalysisBtn.innerHTML;
        sentimentAnalysisBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Analyzing...';
        sentimentAnalysisBtn.disabled = true;

        const response = await fetch('/api/sentiment-analysis/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({ email_text: emailText })
        });
        
        const data = await response.json();
        
        if (data.ok) {
            // Display the sentiment analysis in a modal
            displaySentimentAnalysisModal(data.sentiment);
            showNotification('Sentiment analysis completed', 'success');
        } else {
            showNotification('Failed to analyze sentiment: ' + data.error, 'error');
        }
    } catch (error) {
        showNotification('Error analyzing sentiment: ' + error.message, 'error');
    } finally {
        // Reset button state
        const sentimentAnalysisBtn = document.getElementById('sentiment-analysis');
        sentimentAnalysisBtn.innerHTML = '<i class="fas fa-brain me-2"></i>Sentiment';
        sentimentAnalysisBtn.disabled = false;
    }
}

// Function to display thread analysis in a modal
function displayThreadAnalysisModal(threadAnalysis) {
    // Create modal if it doesn't exist
    let modal = document.getElementById('threadAnalysisModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'threadAnalysisModal';
        modal.className = 'modal fade';
        modal.innerHTML = `
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Thread Analysis</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <div class="modal-body" id="thread-analysis-content">
                        <!-- Content will be inserted here -->
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    }

    const content = document.getElementById('thread-analysis-content');
    
    if (threadAnalysis && threadAnalysis.messages) {
        content.innerHTML = threadAnalysis.messages.map(message => `
            <div class="card mb-3">
                <div class="card-header">
                    <strong>From:</strong> ${message.from}<br>
                    <strong>Date:</strong> ${message.date}<br>
                    <strong>Subject:</strong> ${message.subject}
                </div>
                <div class="card-body">
                    <div class="mb-2">
                        <strong>Sentiment:</strong> 
                        <span class="badge ${getSentimentBadgeClass(message.analysis.sentiment)}">${message.analysis.sentiment}</span>
                    </div>
                    <div class="mb-2">
                        <strong>Key Points:</strong>
                        <ul>
                            ${message.analysis.key_points.map(point => `<li>${point}</li>`).join('')}
                        </ul>
                    </div>
                    <div>
                        <strong>Summary:</strong> ${message.analysis.summary}
                    </div>
                </div>
            </div>
        `).join('');
    } else {
        content.innerHTML = '<div class="alert alert-info">No thread analysis data available.</div>';
    }

    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();
}

// Function to display sentiment analysis in a modal
function displaySentimentAnalysisModal(sentiment) {
    // Create modal if it doesn't exist
    let modal = document.getElementById('sentimentAnalysisModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'sentimentAnalysisModal';
        modal.className = 'modal fade';
        modal.innerHTML = `
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Sentiment Analysis</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <div class="modal-body" id="sentiment-analysis-content">
                        <!-- Content will be inserted here -->
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                        <button type="button" class="btn btn-primary" id="apply-suggested-tone">Apply Suggested Tone</button>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    }

    const content = document.getElementById('sentiment-analysis-content');
    
    if (sentiment) {
        content.innerHTML = `
            <div class="text-center mb-3">
                <span class="badge ${getSentimentBadgeClass(sentiment.overall_sentiment || sentiment.sentiment)} fs-5 p-3">
                    ${sentiment.overall_sentiment || sentiment.sentiment}
                </span>
            </div>
            <div class="mb-3">
                <h6>Confidence Level</h6>
                <div class="progress">
                    <div class="progress-bar" role="progressbar" style="width: ${sentiment.confidence || 70}%">
                        ${sentiment.confidence || 70}%
                    </div>
                </div>
            </div>
            <div class="mb-3">
                <h6>Urgency Level</h6>
                <span class="badge bg-${sentiment.urgency === 'high' ? 'danger' : sentiment.urgency === 'medium' ? 'warning' : 'info'}">
                    ${sentiment.urgency || 'medium'}
                </span>
            </div>
            <div class="mb-3">
                <h6>Suggested Reply Tone</h6>
                <p>${sentiment.suggested_tone || 'professional'}</p>
            </div>
            <div>
                <h6>Key Emotional Indicators</h6>
                <ul>
                    ${(sentiment.emotional_indicators || []).map(indicator => `<li>${indicator}</li>`).join('')}
                </ul>
            </div>
        `;
    } else {
        content.innerHTML = '<div class="alert alert-info">No sentiment analysis data available.</div>';
    }

    // Add event listener for apply suggested tone button
    const applyToneBtn = document.getElementById('apply-suggested-tone');
    if (applyToneBtn && sentiment.suggested_tone) {
        applyToneBtn.onclick = function() {
            const toneSelect = document.getElementById('reply_tone');
            if (toneSelect) {
                toneSelect.value = sentiment.suggested_tone;
                showNotification(`Applied suggested tone: ${sentiment.suggested_tone}`, 'success');
            }
        };
    }

    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();
}

// Helper function to get sentiment badge class
function getSentimentBadgeClass(sentiment) {
    switch (sentiment ? sentiment.toLowerCase() : '') {
        case 'positive':
            return 'bg-success';
        case 'negative':
            return 'bg-danger';
        case 'neutral':
            return 'bg-secondary';
        default:
            return 'bg-light text-dark';
    }
}

async function analyzeEmailThread(threadId) {
    try {
        const response = await fetch(`/api/email-thread-analysis/${threadId}/`);
        const data = await response.json();

        if (data.ok) {
            displayThreadAnalysis(data.message_analyses);
        } else {
            showNotification('Failed to analyze thread: ' + data.error, 'error');
        }
    } catch (error) {
        showNotification('Error analyzing thread: ' + error.message, 'error');
    }
}

function displayThreadAnalysis(messages) {
    const container = document.getElementById('thread-analysis-container');
    if (!container) {
        console.error('Thread analysis container not found');
        return;
    }

    container.innerHTML = '';

    messages.forEach(message => {
        const messageElement = document.createElement('div');
        messageElement.className = 'message-analysis card mb-3';

        // Message header
        const header = document.createElement('div');
        header.className = 'card-header';
        header.innerHTML = `
            <strong>From:</strong> ${message.from}<br>
            <strong>Date:</strong> ${message.date}<br>
            <strong>Subject:</strong> ${message.subject}
        `;
        messageElement.appendChild(header);

        // Analysis body
        const body = document.createElement('div');
        body.className = 'card-body';

        const analysis = message.analysis;
        body.innerHTML = `
            <div class="mb-2">
                <strong>Sentiment:</strong> 
                <span class="badge ${getSentimentBadgeClass(analysis.sentiment)}">${analysis.sentiment}</span>
            </div>
            <div class="mb-2">
                <strong>Key Points:</strong>
                <ul>
                    ${analysis.key_points.map(point => `<li>${point}</li>`).join('')}
                </ul>
            </div>
            <div>
                <strong>Summary:</strong> ${analysis.summary}
            </div>
        `;
        messageElement.appendChild(body);

        container.appendChild(messageElement);
    });
}

// Test function to identify the correct endpoint
async function testVoiceCommandEndpoints() {
    const endpoints = [
        '/api/voice/command/',
        '/api/voice-command/',
        '/api/voice_command/',
        '/voice/command/',
        '/voice-command/'
    ];
    
    for (const endpoint of endpoints) {
        try {
            console.log(`Testing endpoint: ${endpoint}`);
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken()
                },
                body: JSON.stringify({ command: 'test' })
            });
            
            console.log(`${endpoint} - Status: ${response.status}`);
            
            if (response.status === 200) {
                const data = await response.json();
                console.log(`${endpoint} - SUCCESS:`, data);
            } else {
                const errorText = await response.text();
                console.log(`${endpoint} - ERROR:`, errorText);
            }
        } catch (error) {
            console.log(`${endpoint} - EXCEPTION:`, error.message);
        }
    }
}

// Run this in your browser console to test all possible endpoints
// testVoiceCommandEndpoints();

// Comprehensive URL testing function
async function debugVoiceUrls() {
    console.log('=== Testing Voice Command URLs ===');
    
    const possibleUrls = [
        '/voice/command/',           // Without /api/ prefix
        '/api/voice/command/',      // With /api/ prefix
        '/api/api/voice/command/',  // Double /api/ prefix
        '/voice-command/',           // With hyphen instead of slash
        '/api/voice-command/',      // With hyphen and /api/ prefix
    ];
    
    for (const url of possibleUrls) {
        try {
            console.log(`Testing: ${url}`);
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken(),
                    'Accept': 'application/json'
                },
                body: JSON.stringify({ command: 'test' })
            });
            
            const contentType = response.headers.get('content-type');
            console.log(`${url} - Status: ${response.status}, Content-Type: ${contentType}`);
            
            if (response.ok && contentType && contentType.includes('application/json')) {
                const data = await response.json();
                console.log(`${url} - SUCCESS:`, data);
                return url; // Return the working URL
            } else {
                const text = await response.text();
                console.log(`${url} - ERROR (first 200 chars):`, text.substring(0, 200));
                if (text.includes('<!DOCTYPE')) {
                    console.log(`${url} - Returning HTML page (404?)`);
                }
            }
        } catch (error) {
            console.log(`${url} - EXCEPTION:`, error.message);
        }
    }
}

// Run this in your browser console to find the correct URL
// debugVoiceUrls();