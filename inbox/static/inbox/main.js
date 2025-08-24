// DOM Elements
const emailsDiv = document.getElementById('emails');
const paginationDiv = document.getElementById('pagination');
const loadBtn = document.getElementById('load');
const genBtn = document.getElementById('gen');
const saveBtn = document.getElementById('save');
const toInput = document.getElementById('to');
const subjectInput = document.getElementById('subject');
const saveStatus = document.getElementById('saveStatus');
const themeBtn = document.getElementById('theme-button');  // Theme button to toggle theme

// Ensure these elements are correctly assigned
const emailArea = document.getElementById('email_text');
const summaryArea = document.getElementById('summary');
const replyArea = document.getElementById('reply');

let currentPage = 1;
let totalPages = 1;

// Initialize the page
document.addEventListener('DOMContentLoaded', function () {
    loadEmails(currentPage);

    // Theme toggle button functionality
    themeBtn.addEventListener('click', function () {
        document.body.classList.toggle('dark-theme');  // Toggle dark theme class
        const isDark = document.body.classList.contains('dark-theme');
        themeBtn.innerText = isDark ? 'Switch to Light Theme' : 'Switch to Dark Theme';  // Toggle button text
    });

    if (loadBtn) {
        loadBtn.addEventListener('click', function () {
            loadEmails(currentPage);  // Reload emails for the current page
        });
    }

    if (genBtn) {
        genBtn.addEventListener('click', generateReply);
    }

    if (saveBtn) {
        saveBtn.addEventListener('click', saveDraft);
    }
});

// Load emails for the current page
async function loadEmails(page = 1) {
    currentPage = page;

    if (!emailsDiv) return;

    // Show loading state
    emailsDiv.innerHTML = `  
        <div class="text-center p-4">
            <div class="loading-spinner text-primary mx-auto mb-2"></div>
            <p class="text-muted">Loading emails...</p>
        </div>
    `;

    if (loadBtn) {
        loadBtn.innerHTML = '<span class="loading-spinner"></span> Loading...';
        loadBtn.disabled = true;
    }

    try {
        const response = await fetch(`/unread-emails/?page=${page}`);
        const data = await response.json();

        if (data.ok) {
            renderEmails(data.emails);
            renderPagination(data.total_pages, data.current_page);  // Ensure pagination works
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

// Render emails to the list
function renderEmails(emails) {
    emailsDiv.innerHTML = ''; // Clear existing emails

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
        emailItem.classList.add('email-item');
        emailItem.innerHTML = ` 
            <div class="d-flex justify-content-between align-items-start">
                <div class="flex-grow-1">
                    <div class="email-meta">
                        <strong>From:</strong> ${email.from || 'Unknown'} •
                        <span>${email.date || ''}</span>
                    </div>
                    <h6 class="email-subject">${email.subject || '(no subject)'}</h6>
                    <p class="email-snippet">${(email.snippet || '').replace(/</g, '&lt;')}</p>
                </div>
                <div class="ms-3">
                    <span class="badge bg-${email.unread ? 'primary' : 'secondary'}">
                        ${email.unread ? 'Unread' : 'Read'}
                    </span>
                </div>
            </div>
            <div class="email-actions">
                <button class="btn btn-sm btn-outline-primary use-email-btn" data-index="${email.id}">
                    <i class="fas fa-envelope me-1"></i> Use this email
                </button>
            </div>
        `;
        emailsDiv.appendChild(emailItem);
    });

    // Add event listeners to "Use this email" buttons
    document.querySelectorAll('.use-email-btn').forEach(btn => {
        btn.addEventListener('click', function () {
            const emailId = this.getAttribute('data-index');
            const selectedEmail = emails.find(email => email.id == emailId);
            useEmail(selectedEmail);
        });
    });
}

// Render pagination buttons
function renderPagination(totalPages, currentPage) {
    let paginationHTML = '';

    // Previous Button
    if (currentPage > 1) {
        paginationHTML += ` 
            <button class="btn btn-outline-secondary" onclick="loadEmails(${currentPage - 1})">Previous</button>
        `;
    }

    // Page Info (e.g., Page 1 of 3)
    paginationHTML += `<div class="mt-2">Page ${currentPage} of ${totalPages}</div>`;

    // Next Button
    if (currentPage < totalPages) {
        paginationHTML += ` 
            <button class="btn btn-outline-secondary" onclick="loadEmails(${currentPage + 1})">Next</button>
        `;
    }

    paginationDiv.innerHTML = paginationHTML;
}

// Use email function
function useEmail(email) {
    // Set the original email's body in the reply area
    if (emailArea) emailArea.value = email.body_text || email.snippet || '';

    // Set the email fields
    if (toInput) toInput.value = email.from || '';
    if (subjectInput) subjectInput.value = email.subject ? `Re: ${email.subject}` : 'Re:';

    // Ensure that emailArea is scrollable
    if (emailArea) {
        emailArea.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

// Generate reply function
async function generateReply() {
    if (!emailArea || !summaryArea || !replyArea) return;

    const emailText = emailArea.value.trim();

    if (!emailText) {
        showNotification('Please enter email text first', 'error');
        return;
    }

    summaryArea.value = 'Generating summary...';
    replyArea.value = '';  // Clear the reply area before generating a new reply

    if (genBtn) {
        genBtn.innerHTML = '<span class="loading-spinner"></span> Processing...';
        genBtn.disabled = true;
    }

    try {
        const response = await fetch('/generate/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({ email_text: emailText })
        });

        const data = await response.json();

        if (data.error) {
            summaryArea.value = 'Error: ' + data.error;
            showNotification('Failed to generate reply', 'error');
        } else {
            summaryArea.value = data.summary || 'No summary generated';
            // Ensure the reply area gets the combined email text and the generated reply
            replyArea.value = `${emailText}\n\nGenerated Reply:\n${data.draft_reply || 'No reply generated'}`;
            showNotification('Reply generated successfully!', 'success');
        }
    } catch (error) {
        summaryArea.value = 'Error: ' + error.message;
        showNotification('Network error occurred', 'error');
    } finally {
        if (genBtn) {
            genBtn.innerHTML = '<i class="fas fa-robot me-2"></i> Summarize & Generate';
            genBtn.disabled = false;
        }
    }
}

// Save draft function
async function saveDraft() {
    if (!toInput || !subjectInput || !replyArea) return;

    const to = toInput.value.trim();
    const subject = subjectInput.value.trim();
    const body = replyArea.value.trim();

    if (!to || !subject || !body) {
        showNotification('Please fill in all fields', 'error');
        return;
    }

    if (saveBtn) {
        saveBtn.innerHTML = '<span class="loading-spinner"></span> Saving...';
        saveBtn.disabled = true;
    }

    if (saveStatus) {
        saveStatus.innerHTML = '<div class="status-info"><i class="fas fa-spinner fa-spin me-2"></i>Saving draft...</div>';
    }

    try {
        const response = await fetch('/save-draft/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({ to, subject, body })
        });

        const data = await response.json();

        if (data.error) {
            if (saveStatus) {
                saveStatus.innerHTML = `<div class="status-error"><i class="fas fa-exclamation-circle me-2"></i>Error: ${data.error}</div>`;
            }
            showNotification('Failed to save draft', 'error');
        } else {
            if (saveStatus) {
                saveStatus.innerHTML = `<div class="status-success"><i class="fas fa-check-circle me-2"></i>Draft saved (ID: ${data.draft_id})</div>`;
            }
            showNotification('Draft saved successfully!', 'success');

            // Clear form after successful save
            setTimeout(() => {
                if (saveStatus) saveStatus.innerHTML = '';
                if (replyArea) replyArea.value = '';  // Clear the replyArea field
            }, 3000);
        }
    } catch (error) {
        if (saveStatus) {
            saveStatus.innerHTML = `<div class="status-error"><i class="fas fa-exclamation-circle me-2"></i>Error: ${error.message}</div>`;
        }
        showNotification('Network error occurred', 'error');
    } finally {
        if (saveBtn) {
            saveBtn.innerHTML = '<i class="fas fa-save me-2"></i> Save Draft to Gmail';
            saveBtn.disabled = false;
        }
    }
}

// Show notification
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `alert alert-${type === 'error' ? 'danger' : type === 'success' ? 'success' : 'info'} alert-dismissible fade show`;
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;

    document.body.appendChild(notification);

    setTimeout(() => {
        if (notification.parentNode) {
            notification.remove();
        }
    }, 5000);
}

// Get CSRF token for Django
function getCSRFToken() {
    const cookieValue = document.cookie.match('(^|;)\\s*csrftoken\\s*=\\s*([^;]+)');
    return cookieValue ? cookieValue.pop() : '';
}

// Export functions for global access
window.EmailAssistant = {
    loadEmails,
    generateReply,
    saveDraft,
    useEmail
};
