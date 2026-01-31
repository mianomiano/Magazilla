const tg = window.Telegram?.WebApp;
let userId = null;

document.addEventListener('DOMContentLoaded', function() {
    const params = new URLSearchParams(window.location.search);
    userId = params.get('user_id');
    
    if (tg) {
        tg.ready();
        tg.expand();
        if (tg.initDataUnsafe?.user) {
            userId = tg.initDataUnsafe.user.id;
        }
    }
    
    if (userId) {
        document.querySelectorAll('a[href*="/download/"]').forEach(link => {
            if (!link.href.includes('user_id')) {
                link.href += (link.href.includes('?') ? '&' : '?') + 'user_id=' + userId;
            }
        });
    }
    
    if (params.get('filter') === 'free') {
        filterProducts('free');
    }
    
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            document.querySelectorAll('.filter-btn').forEach(x => x.classList.remove('active'));
            this.classList.add('active');
            filterProducts(this.dataset.category);
        });
    });
});

function filterProducts(category) {
    document.querySelectorAll('.product-card').forEach(card => {
        if (category === 'all') {
            card.style.display = '';
        } else if (category === 'free') {
            card.style.display = card.dataset.free === 'true' ? '' : 'none';
        } else {
            card.style.display = card.dataset.category === category ? '' : 'none';
        }
    });
}

function viewProduct(id) {
    window.location.href = '/product/' + id + (userId ? '?user_id=' + userId : '');
}

function downloadProduct(id) {
    const url = '/download/' + id + (userId ? '?user_id=' + userId : '');
    if (tg) {
        tg.openLink(window.location.origin + url);
    } else {
        window.open(url, '_blank');
    }
}

async function buyProduct(pid, price) {
    if (!tg) {
        showToast('Open in Telegram', 'error');
        return;
    }
    
    showToast('Creating invoice...', 'success');
    
    try {
        const response = await fetch('/api/create-invoice-link', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({product_id: pid})
        });
        
        const data = await response.json();
        
        if (data.invoice_link) {
            tg.openInvoice(data.invoice_link, function(status) {
                if (status === 'paid') {
                    showToast('Payment successful!', 'success');
                    setTimeout(() => {
                        window.location.href = '/product/' + pid + '?user_id=' + userId;
                    }, 1000);
                } else if (status === 'cancelled') {
                    showToast('Payment cancelled', 'error');
                } else if (status === 'failed') {
                    showToast('Payment failed', 'error');
                }
            });
        } else {
            showToast(data.error || 'Failed to create invoice', 'error');
        }
    } catch (e) {
        showToast('Network error', 'error');
    }
}

function previewImage(input, previewId) {
    const preview = document.getElementById(previewId);
    if (input.files && input.files[0]) {
        const file = input.files[0];
        if (file.type.startsWith('video/')) {
            const video = document.createElement('video');
            video.autoplay = video.loop = video.muted = video.playsInline = true;
            video.style.cssText = 'max-width:120px;border-radius:8px;margin-top:10px';
            video.src = URL.createObjectURL(file);
            if (preview) {
                preview.style.display = 'none';
                preview.parentNode.insertBefore(video, preview);
            }
        } else {
            const reader = new FileReader();
            reader.onload = e => {
                preview.src = e.target.result;
                preview.style.display = 'block';
            };
            reader.readAsDataURL(file);
        }
    }
}

function updateFileName(input, labelId) {
    const label = document.getElementById(labelId);
    if (input.files && input.files[0]) {
        label.textContent = input.files[0].name;
    }
}

function togglePriceField() {
    const checkbox = document.getElementById('is_free');
    const priceField = document.getElementById('price_field');
    if (checkbox && priceField) {
        priceField.style.display = checkbox.checked ? 'none' : 'block';
    }
}

function handleCategoryChange(select) {
    const customField = document.getElementById('custom_category_field');
    if (customField) {
        customField.style.display = select.value === '_custom' ? 'block' : 'none';
    }
}

function showToast(message, type) {
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();
    
    const toast = document.createElement('div');
    toast.className = 'toast ' + (type || 'success');
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => toast.remove(), 3000);
}

document.addEventListener('click', e => {
    if (tg?.HapticFeedback && e.target.matches('.neu-btn,.filter-btn,.product-card')) {
        tg.HapticFeedback.impactOccurred('light');
    }
});
