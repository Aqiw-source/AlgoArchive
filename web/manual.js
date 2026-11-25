const search = document.querySelector('#chapter-search');
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
