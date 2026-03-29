/**
 * Telegram Shop Mini App - Main JavaScript
 * Handles Telegram WebApp integration and secure API calls
 */

// Initialize Telegram WebApp
const tg = window.Telegram?.WebApp;
let initData = '';
let telegramUser = null;

// Initialize on load
document.addEventListener('DOMContentLoaded', function() {
    if (tg) {
        tg.ready();
        tg.expand();
        
        // Store initData for authenticated requests
        initData = tg.initData || '';
        telegramUser = tg.initDataUnsafe?.user || null;
        
        // Apply Telegram theme
        applyTelegramTheme();
        
        // Set up back button if needed
        if (window.location.pathname !== '/') {
            tg.BackButton.show();
            tg.BackButton.onClick(() => window.history.back());
        }
        
        console.log('✅ Telegram WebApp initialized');
    } else {
        console.log('⚠️ Not running in Telegram WebApp');
    }
});

/**
 * Apply Telegram theme colors to CSS variables
 */
function applyTelegramTheme() {
    if (!tg || !tg.themeParams) return;
    
    const theme = tg.themeParams;
    const root = document.documentElement;
    
    if (theme.bg_color) root.style.setProperty('--tg-bg', theme.bg_color);
    if (theme.text_color) root.style.setProperty('--tg-text', theme.text_color);
    if (theme.hint_color) root.style.setProperty('--tg-hint', theme.hint_color);
    if (theme.link_color) root.style.setProperty('--tg-link', theme.link_color);
    if (theme.button_color) root.style.setProperty('--tg-button', theme.button_color);
    if (theme.button_text_color) root.style.setProperty('--tg-button-text', theme.button_text_color);
    if (theme.secondary_bg_color) root.style.setProperty('--tg-secondary-bg', theme.secondary_bg_color);
}

/**
 * Get current Telegram user ID (from validated initData)
 */
function getTelegramUserId() {
    return telegramUser?.id || null;
}

/**
 * Make authenticated API request
 */
async function apiRequest(url, options = {}) {
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers
    };
    
    // Add Telegram auth header
    if (initData) {
        headers['X-Telegram-Init-Data'] = initData;
    }
    
    // Add CSRF token for POST/PUT/DELETE requests
    if (['POST', 'PUT', 'DELETE'].includes(options.method?.toUpperCase())) {
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
        if (csrfToken) {
            headers['X-CSRFToken'] = csrfToken;
        }
    }
    
    try {
        const response = await fetch(url, {
            ...options,
            headers
        });
        return response;
    } catch (error) {
        console.error('API request failed:', error);
        throw error;
    }
}

/**
 * Download product file (with authentication)
 */
function downloadProduct(productId) {
    if (!initData) {
        showToast('Please open this app from Telegram', 'error');
        return;
    }
    
    // Redirect to download with initData for verification
    const url = `/download/${productId}?initData=${encodeURIComponent(initData)}`;
    window.location.href = url;
}

/**
 * Buy product with Telegram Stars
 */
async function buyProduct(productId, productName) {
    if (!tg) {
        showToast('Please open from Telegram', 'error');
        return;
    }
    
    if (!initData) {
        showToast('Authentication required', 'error');
        return;
    }
    
    // Show loading state
    const button = event?.target;
    const originalText = button?.textContent;
    if (button) {
        button.textContent = 'Loading...';
        button.disabled = true;
    }
    
    try {
        const response = await apiRequest('/api/create-invoice-link', {
            method: 'POST',
            body: JSON.stringify({ product_id: productId })
        });
        
        const data = await response.json();
        
        if (data.invoice_link) {
            // Open Telegram's native payment UI
            tg.openInvoice(data.invoice_link, (status) => {
                if (status === 'paid') {
                    showToast('Payment successful! ⭐', 'success');
                    // Reload page after short delay to show updated purchase status
                    setTimeout(() => location.reload(), 1500);
                } else if (status === 'cancelled') {
                    showToast('Payment cancelled', 'info');
                } else if (status === 'failed') {
                    showToast('Payment failed. Please try again.', 'error');
                } else if (status === 'pending') {
                    showToast('Payment pending...', 'info');
                }
            });
        } else {
            showToast(data.error || 'Failed to create invoice', 'error');
        }
    } catch (error) {
        console.error('Buy error:', error);
        showToast('Error processing purchase. Please try again.', 'error');
    } finally {
        // Restore button state
        if (button) {
            button.textContent = originalText;
            button.disabled = false;
        }
    }
}

/**
 * Check if user has purchased a product
 */
async function checkPurchase(productId) {
    if (!initData) return false;
    
    try {
        const response = await apiRequest('/api/check-purchase', {
            method: 'POST',
            body: JSON.stringify({ product_id: productId })
        });
        
        const data = await response.json();
        return data.purchased === true;
    } catch (error) {
        console.error('Check purchase error:', error);
        return false;
    }
}

/**
 * View product detail page
 */
function viewProduct(productId) {
    let url = `/product/${productId}`;
    if (initData) {
        url += `?initData=${encodeURIComponent(initData)}`;
    }
    window.location.href = url;
}

/**
 * Show toast notification
 */
function showToast(message, type = 'info') {
    // Remove existing toasts
    const existing = document.querySelectorAll('.toast');
    existing.forEach(t => t.remove());
    
    // Create new toast
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    
    // Style the toast
    Object.assign(toast.style, {
        position: 'fixed',
        bottom: '80px',
        left: '50%',
        transform: 'translateX(-50%) translateY(20px)',
        padding: '12px 24px',
        borderRadius: '8px',
        color: '#fff',
        fontSize: '14px',
        fontWeight: '500',
        zIndex: '10000',
        opacity: '0',
        transition: 'all 0.3s ease',
        maxWidth: '90%',
        textAlign: 'center'
    });
    
    // Set background color based on type
    const colors = {
        success: '#10b981',
        error: '#ef4444',
        warning: '#f59e0b',
        info: '#3b82f6'
    };
    toast.style.backgroundColor = colors[type] || colors.info;
    
    document.body.appendChild(toast);
    
    // Animate in
    requestAnimationFrame(() => {
        toast.style.opacity = '1';
        toast.style.transform = 'translateX(-50%) translateY(0)';
    });
    
    // Remove after delay
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(-50%) translateY(20px)';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

/**
 * Category filter functionality
 */
document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', function() {
        // Update active state
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        
        const category = this.dataset.category;
        
        // Filter products
        document.querySelectorAll('.product-card').forEach(card => {
            if (category === 'all') {
                card.style.display = 'block';
            } else if (category === 'free') {
                card.style.display = card.dataset.free === 'true' ? 'block' : 'none';
            } else {
                card.style.display = card.dataset.category === category ? 'block' : 'none';
            }
        });
    });
});

// ----- ADMIN FORM HELPERS -----

/**
 * Toggle price field based on "is_free" checkbox
 */
function togglePriceField() {
    const isFree = document.getElementById('is_free')?.checked;
    const priceField = document.getElementById('price_field');
    if (priceField) {
        priceField.style.display = isFree ? 'none' : 'block';
        const priceInput = priceField.querySelector('input');
        if (priceInput) {
            if (isFree) {
                priceInput.value = '0';
                priceInput.disabled = true;    // Disabled inputs skip browser validation
                priceInput.removeAttribute('min');
            } else {
                priceInput.disabled = false;
                priceInput.setAttribute('min', '1');
                if (priceInput.value === '0' || priceInput.value === '') {
                    priceInput.value = '1';
                }
            }
        }
    }
}

/**
 * Handle category change (show/hide custom category field)
 */
function handleCategoryChange(select) {
    const customField = document.getElementById('custom_category_field');
    if (customField) {
        customField.style.display = select.value === '_custom' ? 'block' : 'none';
    }
}

/**
 * Preview image before upload
 */
function previewImage(input, previewId) {
    const preview = document.getElementById(previewId);
    if (!preview) return;
    
    if (input.files && input.files[0]) {
        const reader = new FileReader();
        reader.onload = (e) => {
            preview.src = e.target.result;
            preview.style.display = 'block';
        };
        reader.readAsDataURL(input.files[0]);
    }
}

/**
 * Update file name label after selection
 */
function updateFileName(input, labelId) {
    const label = document.getElementById(labelId);
    if (label && input.files && input.files[0]) {
        label.textContent = input.files[0].name;
    }
}

/**
 * Confirm dangerous actions
 */
function confirmDelete(message) {
    return confirm(message || 'Are you sure you want to delete this item?');
}
