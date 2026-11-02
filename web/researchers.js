// The contact library is independent of legacy workbook-based sending.
let researcherRows = [];
let researcherOffset = 0;
let researcherQuery = '';
let researcherRequest = 0;
const researcherLimit = 25;

function researcherMessage(message, error = false) {
  const el = $('#researcher-message');
  el.textContent = message;
  el.className = 'text-sm ' + (error ? 'text-red-600' : 'text-muted');
}

async function loadResearchers() {
  const request = ++researcherRequest;
  $('#researcher-count').textContent = 'Loading...';
  $('#researcher-prev').disabled = true;
  $('#researcher-next').disabled = true;
  try {
    const params = new URLSearchParams({ q: researcherQuery, offset: researcherOffset, limit: researcherLimit });
    const result = await api(`/api/researchers?${params}`);
    if (request !== researcherRequest) return;
    $('#researcher-storage').textContent = result.storage === 'postgresql'
      ? 'Database: PostgreSQL' : 'Database: SQLite (local mode)';
    if (researcherOffset > 0 && researcherOffset >= result.total) {
      researcherOffset = Math.max(0, Math.ceil(result.total / researcherLimit) - 1) * researcherLimit;
      return loadResearchers();
    }
    researcherRows = result.items;
    $('#researcher-rows').innerHTML = researcherRows.map(row => `
      <tr class="border-b border-stone-100">
        <td class="p-3"><strong>${esc(row.name)}</strong><p class="text-muted">${esc(row.email || 'No email')}</p></td>
        <td class="p-3">${esc(row.institution)}<p class="text-muted">${esc(row.country)}</p></td>
        <td class="p-3 whitespace-pre-wrap max-w-xs">${esc(row.research_area)}</td>
        <td class="p-3 whitespace-nowrap">
          <button type="button" data-edit-researcher="${row.id}" class="underline mr-3">Edit</button>
          <button type="button" data-delete-researcher="${row.id}" class="underline text-red-600">Delete</button>
        </td>
      </tr>`).join('') || '<tr><td colspan="4" class="p-6 text-muted">No researchers found. Add one or import a workbook.</td></tr>';
    $('#researcher-count').textContent = result.total
      ? `${researcherOffset + 1}-${researcherOffset + result.items.length} of ${result.total}`
      : '0 researchers';
    $('#researcher-prev').disabled = researcherOffset === 0;
    $('#researcher-next').disabled = researcherOffset + researcherLimit >= result.total;
  } catch (error) {
    if (request !== researcherRequest) return;
    researcherMessage(error.message, true);
    $('#researcher-count').textContent = 'Could not load researchers. Search again to retry.';
  }
}

function editResearcher(row = {}) {
  const form = $('#researcher-form');
  form.reset();
  for (const key of ['id', 'updated_at', 'name', 'email', 'institution', 'country', 'research_area', 'notes']) {
    form.elements[key].value = row[key] ?? '';
  }
  $('#researcher-form-title').textContent = row.id ? 'Edit researcher' : 'Add researcher';
  $('#researcher-form-message').textContent = '';
  form.classList.remove('hidden');
  form.elements.name.focus();
}

$('#researcher-new').onclick = () => editResearcher();
$('#researcher-cancel').onclick = () => $('#researcher-form').classList.add('hidden');
$('#researcher-form').onsubmit = async event => {
  event.preventDefault();
  const form = event.target;
  const body = Object.fromEntries(new FormData(form));
  const id = body.id;
  delete body.id;
  if (!id) delete body.updated_at;
  const button = form.querySelector('[type="submit"]');
  button.disabled = true;
  $('#researcher-form-message').textContent = '';
  try {
    await api(id ? `/api/researchers/${id}` : '/api/researchers', {
      method: id ? 'PUT' : 'POST', body,
    });
    form.classList.add('hidden');
    researcherMessage('Saved to your database library. Nothing was approved or sent.');
    await loadResearchers();
  } catch (error) {
    $('#researcher-form-message').textContent = error.message;
  } finally {
    button.disabled = false;
  }
};

$('#researcher-search').onsubmit = event => {
  event.preventDefault();
  researcherQuery = event.target.elements.q.value.trim();
  researcherOffset = 0;
  researcherMessage('');
  loadResearchers();
};
$('#researcher-prev').onclick = () => { researcherOffset -= researcherLimit; loadResearchers(); };
$('#researcher-next').onclick = () => { researcherOffset += researcherLimit; loadResearchers(); };
$('#researcher-rows').onclick = async event => {
  const button = event.target.closest('button');
  if (!button) return;
  const id = Number(button.dataset.editResearcher || button.dataset.deleteResearcher);
  const row = researcherRows.find(item => item.id === id);
  if (!row) return;
  if (button.dataset.editResearcher) return editResearcher(row);
  if (!confirm(`Delete ${row.name} from the contact library? This does not change legacy send history.`)) return;
  button.disabled = true;
  try {
    await api(`/api/researchers/${id}?${new URLSearchParams({ updated_at: row.updated_at })}`, { method: 'DELETE' });
    if (Number($('#researcher-form').elements.id.value) === id) $('#researcher-form').classList.add('hidden');
    researcherMessage('Researcher deleted.');
    await loadResearchers();
  } catch (error) {
    researcherMessage(error.message, true);
  } finally {
    button.disabled = false;
  }
};

$('#researcher-import').onclick = () => $('#researcher-file').click();
$('#researcher-file').onchange = async event => {
  const file = event.target.files[0];
  if (!file) return;
  const button = $('#researcher-import');
  button.disabled = true;
  researcherMessage('Validating and importing workbook...');
  try {
    const body = new FormData();
    body.append('file', file);
    const result = await api('/api/researchers/import', { method: 'POST', body });
    researcherMessage(`Imported ${result.imported}; skipped ${result.skipped} duplicates. ${result.message}`);
    researcherOffset = 0;
    await loadResearchers();
  } catch (error) {
    researcherMessage(error.message, true);
  } finally {
    button.disabled = false;
    event.target.value = '';
  }
};

$('#researcher-export').onclick = async event => {
  const button = event.target;
  button.disabled = true;
  try {
    const response = await fetch('/api/researchers/export', { headers: { Authorization: `Bearer ${token}` } });
    if (response.status === 401) { signOut(); return; }
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Export failed');
    }
    const url = URL.createObjectURL(await response.blob());
    const link = Object.assign(document.createElement('a'), { href: url, download: 'agnostos-researchers.xlsx' });
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    researcherMessage('Exported contact fields only; drafts and send history remain in the legacy pipeline.');
  } catch (error) {
    researcherMessage(error.message, true);
  } finally {
    button.disabled = false;
  }
};
