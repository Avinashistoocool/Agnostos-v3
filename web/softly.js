// Reveal on scroll
const io = new IntersectionObserver((entries) => {
  for (const e of entries) if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); }
}, { threshold: 0.12 });
document.querySelectorAll('.reveal').forEach((el) => io.observe(el));

// FAQ
const FAQ = [
  ['Does it send from my own email?', 'Yes. You connect your university or Gmail account with an app password. Mail goes out from your address, and replies land in your normal inbox.'],
  ['Will it invent achievements?', "No. Drafts are told to describe what you built and tried, never results you don't have. Anything it can't know is left as [FILL] for you."],
  ['How many emails a day?', 'Forty by default, five to ten minutes apart, only between 9 and 5 in each professor\'s own time zone, on weekdays. You can lower it.'],
  ['What does it cost?', 'The app is free. Drafting uses your own model key (Groq is free; OpenAI gpt-5-mini costs about half a cent per email).'],
  ['Can I read emails before they go?', 'Always. Send review copies to yourself, export .eml files, or approve replies one by one before anything leaves.'],
  ['Is my password safe?', 'Credentials are encrypted at rest on the server and are only handed to your own sending job. You can delete them at any time.'],
];
const list = document.getElementById('faq-list');
if (list) {
  list.innerHTML = FAQ.map(([q, a]) => `
    <div class="faq reveal"><button type="button" aria-expanded="false"><span>${q}</span><span class="icon">+</span></button>
    <div class="body"><div><p>${a}</p></div></div></div>`).join('');
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
