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

  const items = [
    { href: '/', icon: '⌂', label: '主页', current: !inLibrary },
    { href: '/library.html', icon: '▦', label: '素材库', current: inLibrary },
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
    link.append(icon, label);
    nav.append(link);
  });

  document.body.classList.add('has-app-nav');
  document.body.append(nav);
})();
