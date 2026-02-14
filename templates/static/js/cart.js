/* ═══════════════════════════════════════════════
   Cart — Add, load, update, checkout
   ═══════════════════════════════════════════════ */

// Add to cart (called from product page)
function addToCart(productId) {
    haptic('light');
    fetch('/api/cart/add', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ product_id: productId, quantity: 1 })
    })
    .then(r => r.json())
    .then(data => {
        if (data.ok) {
            showToast('✅ Added to cart!', 'success');
            haptic('success');
            updateCartBadge();
        } else {
            showToast(data.error || 'Error', 'error');
            haptic('error');
        }
    })
    .catch(() => {
        showToast('Network error', 'error');
    });
}

// Buy now = add + go to cart
function buyNow(productId) {
    haptic('medium');
    fetch('/api/cart/add', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ product_id: productId, quantity: 1 })
    })
    .then(r => r.json())
    .then(data => {
        if (data.ok) {
            window.location.href = '/cart';
        } else {
            showToast(data.error || 'Error', 'error');
        }
    })
    .catch(() => {
        showToast('Network error', 'error');
    });
}

// Load cart (cart page)
function loadCart() {
    fetch('/api/cart', { headers: getAuthHeaders() })
        .then(r => {
            if (!r.ok) throw new Error('Auth required');
            return r.json();
        })
        .then(data => {
            document.getElementById('cartLoading').style.display = 'none';
            document.getElementById('cartContent').style.display = 'block';

            if (data.items.length === 0) {
                document.getElementById('cartEmpty').style.display = 'block';
                document.getElementById('cartSummary').style.display = 'none';
                return;
            }

            const container = document.getElementById('cartItems');
            container.innerHTML = '';

            data.items.forEach(item => {
                const div = document.createElement('div');
                div.className = 'cart-item';
                div.innerHTML = `
                    <img class="cart-item-img" src="${item.thumbnail_url || ''}" alt="" onerror="this.style.display='none'">
                    <div class="cart-item-info">
                        <div class="cart-item-title">${escHtml(item.title)}</div>
                        <div class="cart-item-price">⭐ ${item.price_stars}</div>
                        <div class="cart-item-qty">
                            <button onclick="updateQty(${item.id}, ${item.quantity - 1})">−</button>
                            <span>${item.quantity}</span>
                            <button onclick="updateQty(${item.id}, ${item.quantity + 1})">+</button>
                        </div>
                    </div>
                    <button class="cart-item-remove" onclick="removeItem(${item.id})">✕</button>
                `;
                container.appendChild(div);
            });

            document.getElementById('cartTotal').textContent = data.total;
            document.getElementById('cartSummary').style.display = 'block';
            document.getElementById('cartEmpty').style.display = 'none';
        })
        .catch(() => {
            document.getElementById('cartLoading').innerHTML = '<p>Please open this app from Telegram</p>';
        });
}

function updateQty(itemId, qty) {
    haptic('light');
    if (qty <= 0) {
        removeItem(itemId);
        return;
    }
    fetch('/api/cart/update', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ item_id: itemId, quantity: qty })
    })
    .then(r => r.json())
    .then(() => {
        loadCart();
        updateCartBadge();
    });
}

function removeItem(itemId) {
    haptic('medium');
    fetch('/api/cart/remove', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ item_id: itemId })
    })
    .then(r => r.json())
    .then(() => {
        loadCart();
        updateCartBadge();
    });
}

function checkout() {
    haptic('heavy');
    const btn = document.querySelector('.btn-checkout');
    if (btn) {
        btn.disabled = true;
        btn.textContent = '⏳ Processing...';
    }

    fetch('/api/checkout', {
        method: 'POST',
        headers: getAuthHeaders()
    })
    .then(r => r.json())
    .then(data => {
        if (data.ok) {
            if (data.method === 'invoice_sent') {
                showToast('⭐ Invoice sent! Check your Telegram chat.', 'success');
                haptic('success');
                // Close mini app so user sees the invoice in chat
                const tg = window.Telegram && window.Telegram.WebApp;
                if (tg) {
                    setTimeout(() => tg.close(), 1500);
                }
            } else {
                showToast('Order created! Complete payment in the bot chat.', 'success');
            }
        } else {
            showToast(data.error || 'Checkout failed', 'error');
            haptic('error');
        }
    })
    .catch(() => {
        showToast('Network error', 'error');
    })
    .finally(() => {
        if (btn) {
            btn.disabled = false;
            btn.textContent = '⚡ Pay with Telegram Stars';
        }
    });
}

// HTML escape helper
function escHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}
