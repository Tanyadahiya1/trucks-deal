/* TrucksDeal – main.js */

// ── Navbar scroll effect ──────────────────────────────────────────────────────
(function() {
  const nav = document.getElementById('navbar');
  if (!nav) return;
  function onScroll() {
    nav.classList.toggle('scrolled', window.scrollY > 30);
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
})();

// ── Hamburger menu ────────────────────────────────────────────────────────────
(function() {
  const btn   = document.getElementById('hamburger');
  const links = document.getElementById('navLinks');
  if (!btn || !links) return;
  btn.addEventListener('click', () => {
    links.classList.toggle('open');
    btn.classList.toggle('open');
  });
  // Close on outside click
  document.addEventListener('click', e => {
    if (!btn.contains(e.target) && !links.contains(e.target)) {
      links.classList.remove('open');
      btn.classList.remove('open');
    }
  });
})();

// ── Intersection observer for scroll reveals ──────────────────────────────────
(function() {
  const selectors = '.reveal, .reveal-up, .reveal-left, .reveal-right';
  const els = document.querySelectorAll(selectors);
  if (!els.length) return;

  const obs = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        obs.unobserve(entry.target);
      }
    });
  }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });

  els.forEach(el => obs.observe(el));
})();

// ── Hero parallax ─────────────────────────────────────────────────────────────
(function() {
  const heroBg = document.querySelector('.hero-bg img');
  if (!heroBg) return;
  window.addEventListener('scroll', () => {
    const y = window.scrollY;
    heroBg.style.transform = `scale(1.05) translateY(${y * 0.25}px)`;
  }, { passive: true });
})();

// ── Smooth counter animation ──────────────────────────────────────────────────
(function() {
  const counters = document.querySelectorAll('.stat-num');
  if (!counters.length) return;

  const obs = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      const el  = entry.target;
      const raw = el.textContent.trim();
      const num = parseFloat(raw.replace(/[^0-9.]/g, ''));
      if (isNaN(num)) return;
      const prefix = raw.match(/^[^0-9]*/)?.[0] || '';
      const suffix = raw.match(/[^0-9.]*$/)?.[0] || '';
      let start = 0;
      const dur = 1200;
      const step = 16;
      const inc  = num / (dur / step);
      const timer = setInterval(() => {
        start += inc;
        if (start >= num) { start = num; clearInterval(timer); }
        el.textContent = prefix + (Number.isInteger(num) ? Math.round(start) : start.toFixed(1)) + suffix;
      }, step);
      obs.unobserve(el);
    });
  }, { threshold: 0.5 });

  counters.forEach(c => obs.observe(c));
})();

// ── Vehicle card hover image preview strip ────────────────────────────────────
// (placeholder for multi-image cards if needed in future)

// ── Sticky filter highlight on mobile ────────────────────────────────────────
(function() {
  const form = document.getElementById('filterForm');
  if (!form) return;
  form.querySelectorAll('input, select').forEach(el => {
    el.addEventListener('change', () => form.submit());
  });
  // Don't auto-submit text/number inputs – only select/checkbox
  form.querySelectorAll('input[type="text"], input[type="number"]').forEach(el => {
    el.removeEventListener('change', () => form.submit());
  });
})();
