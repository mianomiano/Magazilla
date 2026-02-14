/* ═══════════════════════════════════════════════
   Shop — Search filtering
   ═══════════════════════════════════════════════ */
(function () {
    const searchInput = document.getElementById('searchInput');
    const grid = document.getElementById('productsGrid');

    if (searchInput && grid) {
        searchInput.addEventListener('input', function () {
            const query = this.value.toLowerCase().trim();
            const cards = grid.querySelectorAll('.product-card');

            cards.forEach(card => {
                const title = card.dataset.title || '';
                card.style.display = title.includes(query) ? '' : 'none';
            });
        });
    }
})();
