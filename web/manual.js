const search = document.querySelector('#chapter-search');

if (search) {
  const cards = [...document.querySelectorAll('.chapter-card')];
  const status = document.querySelector('#result-count');
  const empty = document.querySelector('#no-results');
  const normalize = (value) => value.toLocaleLowerCase().replace(/\s+/gu, '');
  const titles = cards.map((card) => normalize(card.textContent));

  function filterChapters() {
    const query = normalize(search.value);
    let count = 0;
    cards.forEach((card, index) => {
      card.hidden = !titles[index].includes(query);
      if (!card.hidden) count += 1;
    });
    empty.hidden = count !== 0;
    status.textContent = '找到 ' + count + ' 个章节';
  }

  search.closest('label').hidden = false;
  search.addEventListener('input', filterChapters);
  window.addEventListener('pageshow', filterChapters);
}

document.querySelectorAll('[data-settings-link]').forEach((link) => {
  link.addEventListener('click', async (event) => {
    const parent = link.parentElement;
    const fallback = parent?.querySelector('.settings-link-fallback');
    const showFallback = () => {
      if (!fallback) return;
      fallback.hidden = false;
      fallback.focus();
    };
    if (location.protocol === 'file:') {
      event.preventDefault();
      showFallback();
      return;
    }
    if (document.documentElement.hasAttribute('data-static-demo')) return;
    if (!['127.0.0.1', 'localhost'].includes(location.hostname)) return;
    event.preventDefault();
    try {
      const response = await fetch('/api/health', { cache: 'no-store' });
      if (!response.ok) throw new Error('Local service is unavailable');
      location.assign(link.href);
    } catch (_) {
      showFallback();
    }
  });
});
