(() => {
  const root = document.querySelector('.app, .page');
  if (!root || document.querySelector('.app-nav')) return;

  const stylesheet = document.createElement('link');
  stylesheet.rel = 'stylesheet';
  stylesheet.href = '/app-nav.css';
  document.head.append(stylesheet);

  const inLibrary = location.pathname === '/library.html';
  const nav = document.createElement('nav');
  const compact = root.classList.contains('app') || root.classList.contains('compact-page');
  nav.className = 'app-nav' + (compact ? ' compact' : '');
  nav.setAttribute('aria-label', '主要页面');
  nav.setAttribute('data-i18n-aria', 'nav.aria');

  const items = [
    { href: '/', icon: '⌂', label: '主页', key: 'nav.home', current: !inLibrary },
    { href: '/library.html', icon: '▦', label: '素材库', key: 'nav.library', current: inLibrary },
  ];

  items.forEach((item) => {
    const link = document.createElement('a');
    link.href = item.href;
    if (item.current) link.setAttribute('aria-current', 'page');

    const icon = document.createElement('span');
    icon.className = 'app-nav-icon';
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = item.icon;

    const label = document.createElement('span');
    label.textContent = item.label;
    label.setAttribute('data-i18n', item.key);
    link.append(icon, label);
    nav.append(link);
  });

  document.body.classList.add('has-app-nav');
  document.body.append(nav);
  if (window.I18N) {
    nav.setAttribute('aria-label', window.I18N.t('nav.aria'));
    window.I18N.apply(nav);
  }
})();
