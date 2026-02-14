/* ═══════════════════════════════════════════════
   Cart — Add, load, update, checkout
   ═══════════════════════════════════════════════ */

function addToCart(productId) {
    if (!window._isTelegram) {
        showToast('Open in Telegram to add to cart', 'error');
        return;
    }
    haptic('light');
    fetch('/api/cart/add', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ product_id: productId, quantity: 1 })
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
        if (data.ok) {
            showToast('Added to cart!', 'success');
            haptic('success');
            updateCartBadge();
        } else {
            showToast(data.error || 'Error', 'error');
            haptic('error');
        }
    })
    .catch(function () {
        showToast('Network error', 'error');
    });
}

function buyNow(productId) {
    if (!window._isTelegram) {
        showToast('Open in Telegram to buy', 'error');
        return;
    }
    haptic('medium');
    fetch('/api/cart/add', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ product_id: productId, quantity: 1 })
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
        if (data.ok) {
            window.location.href = '/cart';
        } else {
            showToast(data.error || 'Error', 'error');
        }
    })
    .catch(function () {
        showToast('Network error', 'error');
    });
}

function loadCart() {
    if (!window._isTelegram) {
        var loading = document.getElementById('cartLoading');
        var content = document.getElementById('cartContent');
        if (loading) loading.style.display = 'none';
        if (content) {
            content.style.display = 'block';
            showTelegramRequired('cartContent');
        }
        return;
    }

    // Wait for auth to be ready
    if (!window._authReady) {
        window.addEventListener('tgAuthReady', function () {
            doLoadCart();
        });
        // Also try after a timeout in case event already fired
        setTimeout(function () {
            if (!window._cartLoaded) doLoadCart();
        }, 2000);
    } else {
        doLoadCart();
    }
}

function doLoadCart() {
    window._cartLoaded = true;

    fetch('/api/cart', { headers: getAuthHeaders() })
        .then(function (r) {
            if (!r.ok) throw new Error('Auth required');
            return r.json();
        })
        .then(function (data) {
            var loading = document.getElementById('cartLoading');
            var content = document.getElementById('cartContent');
            if (loading) loading.style.display = 'none';
            if (content) content.style.display = 'block';

            if (data.items.length === 0) {
                document.getElementById('cartEmpty').style.display = 'block';
                var summary = document.getElementById('cartSummary');
                if (summary) summary.style.display = 'none';
                return;
            }

            var container = document.getElementById('cartItems');
            container.innerHTML = '';

            data.items.forEach(function (item) {
                var div = document.createElement('div');
                div.className = 'cart-item';
                var imgHtml = item.thumbnail_url
                    ? '<img class="cart-item-img" src="' + item.thumbnail_url + '" alt="" onerror="this.style.display=\'none\'">'
                    : '<div class="cart-item-img" style="display:flex;align-items:center;justify-content:center;font-size:24px;">📦</div>';
                
                div.innerHTML = imgHtml +
                    '<div class="cart-item-info">' +
                    '<div class="cart-item-title">' + escHtml(item.title) + '</div>' +
                    '<div class="cart-item-price">⭐ ' + item.price_stars + '</div>' +
                    '<div class="cart-item-qty">' +
                    '<button onclick="updateQty(' + item.id + ', ' + (item.quantity - 1) + ')">−</button>' +
                    '<span>' + item.quantity + '</span>' +
                    '<button onclick="updateQty(' + item.id + ', ' + (item.quantity + 1) + ')">+</button>' +
                    '</div></div>' +
                    '<button class="cart-item-remove" onclick="removeItem(' + item.id + ')">✕</button>';
                container.appendChild(div);
            });

            document.getElementById('cartTotal').textContent = data.total;
            document.getElementById('cartSummary').style.display = 'block';
            document.getElementById('cartEmpty').style.display = 'none';
        })
        .catch(function (err) {
            var loading = document.getElementById('cartLoading');
            var content = document.getElementById('cartContent');
            if (loading) loading.style.display = 'none';
            if (content) {
                content.style.display = 'block';
                content.innerHTML = '<div class="empty-state"><p>Could not load cart. Try again.</p></div>';
            }
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
    .then(function (r) { return r.json(); })
    .then(function () {
        doLoadCart();
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
    .then(function (r) { return r.json(); })
    .then(function () {
        doLoadCart();
        updateCartBadge();
    });
}

function checkout() {
    haptic('heavy');
    var btn = document.querySelector('.btn-checkout');
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Processing...';
    }

    fetch('/api/checkout', {
        method: 'POST',
        headers: getAuthHeaders()
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
        if (data.ok) {
            showToast('Invoice sent! Check your Telegram chat.', 'success');
            haptic('success');
            var tg = window.Telegram && window.Telegram.WebApp;
            if (tg) {
                setTimeout(function () { tg.close(); }, 1500);
            }
        } else {
            showToast(data.error || 'Checkout failed', 'error');
            haptic('error');
        }
    })
    .catch(function () {
        showToast('Network error', 'error');
    })
    .finally(function () {
        if (btn) {
            btn.disabled = false;
            btn.textContent = '⚡ Pay with Telegram Stars';
        }
    });
}

function escHtml(str) {
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}
