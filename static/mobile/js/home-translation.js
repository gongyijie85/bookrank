'use strict';

(function () {
    function initHomeTranslation() {
        if (document.documentElement.getAttribute('data-lang') !== 'zh') return;
        if (!window.MobileApp || typeof window.MobileApp.csrfFetch !== 'function') return;

        const cards = Array.from(document.querySelectorAll('.m-book-card[data-needs-translation="1"][data-isbn]')).slice(0, 15);
        let stopped = false;

        function applyTranslation(card, book) {
            const title = typeof book.title_zh === 'string' ? book.title_zh.trim() : '';
            const description = typeof book.description_zh === 'string' ? book.description_zh.trim() : '';
            const titleEl = card.querySelector('.m-book-title');
            if (title && titleEl) {
                const original = titleEl.textContent.trim();
                if (original && original !== title && !card.querySelector('.m-book-original-title')) {
                    const originalEl = document.createElement('p');
                    originalEl.className = 'm-book-original-title';
                    originalEl.textContent = original;
                    titleEl.insertAdjacentElement('afterend', originalEl);
                }
                titleEl.textContent = title;
                const ariaLabel = card.getAttribute('aria-label');
                if (ariaLabel && original && ariaLabel.includes(original)) {
                    card.setAttribute('aria-label', ariaLabel.replace(original, title));
                }
                const cover = card.querySelector('.m-book-cover img');
                const alt = cover && cover.getAttribute('alt');
                if (alt && original && alt.includes(original)) cover.setAttribute('alt', alt.replace(original, title));
                card.removeAttribute('data-needs-title');
            }
            const descEl = card.querySelector('.m-book-card-desc');
            if (description && descEl) {
                const chars = Array.from(description);
                descEl.textContent = chars.length > 80 ? chars.slice(0, 80).join('') + '…' : description;
                card.removeAttribute('data-needs-description');
            }
            if (!card.getAttribute('data-needs-title') && !card.getAttribute('data-needs-description')) {
                card.removeAttribute('data-needs-translation');
            }
        }

        function next() {
            if (stopped || !cards.length) return;
            const card = cards.shift();
            const isbn = (card.getAttribute('data-isbn') || '').replace(/[^0-9Xx]/g, '');
            if (!isbn) { next(); return; }
            window.MobileApp.csrfFetch('/api/translate/book/' + encodeURIComponent(isbn), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}),
            }).then(function (response) {
                if (!response.ok) {
                    if ([401, 429, 500, 503].includes(response.status)) stopped = true;
                    throw new Error('http ' + response.status);
                }
                return response.json();
            }).then(function (result) {
                const book = result && result.data && result.data.book;
                if (book) applyTranslation(card, book);
                next();
            }).catch(function () { next(); });
        }

        if (cards.length) setTimeout(next, 1500);
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initHomeTranslation);
    else initHomeTranslation();
})();
