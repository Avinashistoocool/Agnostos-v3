// Reveal on scroll
const io = new IntersectionObserver((entries) => {
  for (const e of entries) if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); }
}, { threshold: 0.12 });
document.querySelectorAll('.reveal').forEach((el) => io.observe(el));

// FAQ (rendered in the HTML so crawlers can read it; this only wires the toggles)
const list = document.getElementById('faq-list');
if (list) {
  list.querySelectorAll('.faq').forEach((el) => {
    io.observe(el);
    el.querySelector('button').addEventListener('click', (ev) => {
      const open = el.classList.toggle('open');
      ev.currentTarget.setAttribute('aria-expanded', open);
    });
  });
}

// Waitlist
const form = document.getElementById('waitlist');
if (form) form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const msg = document.getElementById('waitlist-msg');
  const email = form.querySelector('input').value;
  try {
    const r = await fetch('/api/waitlist', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }) });
    msg.textContent = r.ok ? "You're on the list. We'll write, slowly." : 'That address looks off.';
    if (r.ok) form.reset();
  } catch { msg.textContent = 'Could not reach the server.'; }
});
