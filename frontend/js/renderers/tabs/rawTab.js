export function renderRawTab(data) {
  const code = document.getElementById('raw-jsonld-code');
  if (!code) return;

  const allowedKeys = [
    '@context', '@type', '@id', 'name', 'headline', 'alternateName',
    'description', 'inLanguage', 'datePublished', 'keywords', 'author',
    'hasPart', 'additionalProperty', 'citation', 'sdPublisher', 'action'
  ];
  const cleanObj = {};
  allowedKeys.forEach(k => {
    if (data[k] !== undefined && data[k] !== null && (Array.isArray(data[k]) ? data[k].length > 0 : true)) {
      cleanObj[k] = data[k];
    }
  });
  code.textContent = JSON.stringify(cleanObj, null, 2);
}
