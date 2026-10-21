// MacX site: live release info, YouTube facade, copy buttons, small motion touches.
(() => {
  const REPO = 'Anshul7122/macx';
  const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

  // ---- latest release: point every Download button at the .dmg and show version, size, SHA-256
  const fmtSize = (b) => (b >= 1e9 ? (b / 1e9).toFixed(1) + ' GB' : Math.max(1, Math.round(b / 1e6)) + ' MB');
  fetch(`https://api.github.com/repos/${REPO}/releases/latest`, { headers: { Accept: 'application/vnd.github+json' } })
    .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then((rel) => {
      const dmg = (rel.assets || []).find((a) => a.name.endsWith('.dmg'));
      if (!dmg) return;
      const version = rel.tag_name.replace(/^v/, '');
      document.querySelectorAll('[data-download]').forEach((a) => {
        a.href = dmg.browser_download_url;
        a.setAttribute('download', '');
        a.title = `${dmg.name} (${fmtSize(dmg.size)})`;
      });
      document.querySelectorAll('[data-release-meta]').forEach((el) => {
        el.innerHTML = `Version ${version} · ${fmtSize(dmg.size)} · macOS 14+ · Apple silicon · ` +
          `<a href="${rel.html_url}">Release notes</a>`;
      });
      const sha = (dmg.digest || '').replace(/^sha256:/, '') ||
        ((rel.body || '').match(/\b[0-9a-f]{64}\b/) || [])[0];
      if (sha) document.querySelectorAll('[data-release-sha]').forEach((el) => { el.textContent = `SHA-256 ${sha}`; });
    })
    .catch(() => { /* links already fall back to the latest-release page */ });

  // ---- YouTube: a thumbnail until clicked, then the privacy-enhanced player
  document.querySelectorAll('.video[data-youtube-id]').forEach((box) => {
    const id = box.dataset.youtubeId.trim();
    if (!/^[\w-]{11}$/.test(id)) return;
    const title = box.dataset.title || 'Video';
    box.innerHTML = '';
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'facade';
    btn.setAttribute('aria-label', `Play: ${title}`);
    btn.style.backgroundImage = `url(https://i.ytimg.com/vi/${id}/maxresdefault.jpg), url(https://i.ytimg.com/vi/${id}/hqdefault.jpg)`;
    btn.innerHTML = '<span class="play-ring" aria-hidden="true"><svg viewBox="0 0 24 24" width="30" height="30"><path fill="currentColor" d="M8 5.14v13.72a1 1 0 0 0 1.52.85l11-6.86a1 1 0 0 0 0-1.7l-11-6.86A1 1 0 0 0 8 5.14Z"/></svg></span>';
    btn.addEventListener('click', () => {
      const f = document.createElement('iframe');
      f.src = `https://www.youtube-nocookie.com/embed/${id}?autoplay=1&rel=0&modestbranding=1`;
      f.title = title;
      f.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share';
      f.allowFullscreen = true;
      box.replaceChildren(f);
    }, { once: true });
    box.appendChild(btn);
  });

  // ---- copy buttons
  document.querySelectorAll('.copy').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const text = btn.parentElement.querySelector('code').textContent;
      try {
        await navigator.clipboard.writeText(text);
        btn.textContent = 'Copied';
        btn.classList.add('done');
      } catch {
        btn.textContent = 'Select & copy';
      }
      setTimeout(() => { btn.textContent = 'Copy'; btn.classList.remove('done'); }, 1800);
    });
  });

  // ---- nav background once scrolled
  const nav = document.getElementById('nav');
  const onScroll = () => nav.classList.toggle('scrolled', scrollY > 10);
  addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  // ---- reveal on scroll
  const items = document.querySelectorAll('.reveal');
  if (reduceMotion || !('IntersectionObserver' in window)) {
    items.forEach((el) => el.classList.add('in'));
  } else {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); }
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });
    items.forEach((el) => io.observe(el));
  }

  // ---- HUD ticks through the measured 45–48 fps range
  const fps = document.querySelector('[data-fps]');
  if (fps && !reduceMotion) {
    const seq = [47, 46, 48, 47, 45, 46, 47, 48, 46, 47];
    let i = 0;
    setInterval(() => { fps.textContent = seq[i = (i + 1) % seq.length]; }, 900);
  }
})();
