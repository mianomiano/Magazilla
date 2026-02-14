/* ═══════════════════════════════════════════════
   Admin — Minimal utilities
   ═══════════════════════════════════════════════ */
(function () {
    // Auto-generate slug from name for categories
    const nameInput = document.getElementById('catName');
    const slugInput = document.getElementById('catSlug');
    if (nameInput && slugInput) {
        nameInput.addEventListener('input', function () {
            if (!document.getElementById('catId').value) {
                slugInput.value = this.value
                    .toLowerCase()
                    .replace(/[^a-z0-9\s-]/g, '')
                    .replace(/\s+/g, '-')
                    .replace(/-+/g, '-')
                    .trim();
            }
        });
    }

    // Confirm before dangerous actions
    document.querySelectorAll('[data-confirm]').forEach(el => {
        el.addEventListener('click', function (e) {
            if (!confirm(this.dataset.confirm)) {
                e.preventDefault();
            }
        });
    });
})();
