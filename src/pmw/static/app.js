const $ = selector => document.querySelector(selector);
let data, token = localStorage.pmwToken || '', timer, lastSnapshot = '', dragging = null;
const expanded = new Set(), drafts = new Map();
let busy = false;
if (new URLSearchParams(location.search).has('compact')) document.body.classList.add('compact');
const requestKey = () => Array.from(crypto.getRandomValues(new Uint8Array(24)), x => x.toString(16).padStart(2, '0')).join('');
const headers = () => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' });
async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { ...headers(), ...(options.headers || {}) } });
  if (!response.ok) {
    const error = new Error(response.status === 409 ? '다른 곳에서 내용이 바뀌었습니다. 최신 내용을 확인한 뒤 다시 저장해 주세요.' : `${response.status}: ${await response.text()}`);
    error.status = response.status;
    throw error;
  }
  return response.json();
}
const write = (path, method, body) => api(path, { method, headers: { 'Idempotency-Key': requestKey() }, body: JSON.stringify(body) });
function relative(value) {
  const date = new Date(value), minutes = Math.floor((Date.now() - date) / 60000);
  return minutes < 1 ? '방금' : minutes < 60 ? `${minutes}분 전` : minutes < 1440 ? `${Math.floor(minutes / 60)}시간 전` : date.toLocaleDateString();
}
function esc(value = '') { const span = document.createElement('span'); span.textContent = value; return span.innerHTML; }
function localDate(value) { const d = new Date(value); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; }
function notice(message, error = false) { $('#message').textContent = message; $('#message').classList.toggle('error', error); }
async function action(callback) {
  if (busy) return;
  busy = true;
  try { await callback(); } catch (error) { notice(error.message, true); } finally { busy = false; await refresh(true); }
}
async function saveOrder(projects) {
  await write('/api/projects/reorder', 'POST', { projects: projects.map(p => ({ id: p.id, expected_revision: p.revision })) });
  notice('프로젝트 순서를 저장했습니다.');
}
function clearDropMarks() { document.querySelectorAll('.drop-before,.drop-after').forEach(n => n.classList.remove('drop-before', 'drop-after')); }
function endDrag() { dragging = null; clearDropMarks(); document.querySelectorAll('.dragging').forEach(n => n.classList.remove('dragging')); }
function attachDrag(article, handle, project) {
  handle.ondragstart = event => {
    if (busy) { event.preventDefault(); return; }
    dragging = { id: project.id, projects: data.projects.map(p => ({ ...p })) };
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', project.id);
    article.classList.add('dragging');
  };
  handle.ondragend = () => { endDrag(); refresh(); };
  article.ondragover = event => {
    if (!dragging || dragging.id === project.id) return;
    event.preventDefault(); event.dataTransfer.dropEffect = 'move'; clearDropMarks();
    const rect = article.querySelector('.project-heading').getBoundingClientRect();
    article.classList.add(event.clientY < rect.top + rect.height / 2 ? 'drop-before' : 'drop-after');
  };
  article.ondrop = event => {
    if (!dragging) return;
    event.preventDefault();
    const captured = dragging, after = article.classList.contains('drop-after');
    endDrag();
    if (captured.id === project.id) return;
    const source = captured.projects.find(p => p.id === captured.id);
    const reordered = captured.projects.filter(p => p.id !== captured.id);
    const target = reordered.findIndex(p => p.id === project.id);
    if (!source || target < 0) return;
    reordered.splice(target + (after ? 1 : 0), 0, source);
    action(() => saveOrder(reordered));
  };
}
function render() {
  const root = $('#projects'); root.textContent = '';
  const attention = $('#attention').checked, chosen = $('#date').value;
  const projects = attention ? data.projects.filter(p => data.tasks.some(t => t.project_id === p.id && ['needs_review', 'blocked'].includes(t.state))) : data.projects;
  $('#count').textContent = `${projects.length}개 프로젝트`;
  if (!projects.length) {
    const empty = document.createElement('p'); empty.className = 'empty';
    empty.textContent = attention ? '확인이 필요한 프로젝트가 없습니다.' : '+ 프로젝트 버튼으로 첫 프로젝트를 등록하세요.';
    root.append(empty);
  }
  for (const project of projects) {
    const fragment = $('#project-template').content.cloneNode(true);
    const article = fragment.querySelector('article'), row = fragment.querySelector('.row'), details = fragment.querySelector('.details');
    article.dataset.id = project.id;
    fragment.querySelector('.name').textContent = project.name;
    fragment.querySelector('.name').title = project.name;
    fragment.querySelector('.location').textContent = project.location || '위치 미지정';
    const userStatus = project.user_summary || '', aiStatus = project.ai_summary ?? project.summary ?? '';
    fragment.querySelector('.summary').textContent = `내 상태 · ${userStatus || '상태를 직접 적어보세요.'}`;
    fragment.querySelector('.ai-summary').textContent = `AI · ${(aiStatus || '등록된 상태 없음').replace(/\s+/g, ' ')}`;
    const tasks = data.tasks.filter(t => t.project_id === project.id);
    const needs = tasks.filter(t => ['needs_review', 'blocked'].includes(t.state)).length;
    const badge = fragment.querySelector('.badge');
    badge.textContent = needs ? `확인 ${needs}` : ({ active: '진행', paused: '보류', done: '완료' }[project.state] || project.state);
    if (needs) badge.classList.add('attention');
    fragment.querySelector('time').textContent = relative(project.updated_at);
    const activities = data.activities.filter(a => a.project_id === project.id && (!chosen || localDate(a.occurred_at) === chosen));
    const notes = data.notes.filter(n => n.project_id === project.id);
    details.innerHTML = `
      <section class="status-detail user-status"><h3>내 상태</h3><p class="status-text">${esc(userStatus || '직접 작성한 상태가 없습니다.')}</p>
        <details class="status-edit"><summary>내 상태 수정</summary><form class="status-form"><textarea rows="3" aria-label="내 상태" placeholder="현재 상황이나 우선할 일을 직접 적어주세요."></textarea><button>내 상태 저장</button></form></details>
      </section>
      <section class="status-detail ai-status"><h3>AI 상태</h3><p class="status-text">${esc(aiStatus || 'AI가 작성한 상태가 없습니다.')}</p></section>
      <section><h3>현재 작업 · 다음 할 일</h3>${tasks.map(t => `<div class="item"><b>${esc(t.title)}</b><span class="meta">${esc(t.state)} · ${esc(t.actor)} · r${t.revision}${t.blocking_reason ? ' · ' + esc(t.blocking_reason) : ''}</span></div>`).join('') || '<p class="empty">등록된 작업이 없습니다.</p>'}<form class="forms task"><input required placeholder="새 할 일"><button>추가</button></form></section>
      <section><h3>보존 메모</h3>${notes.map(n => `<div class="item">${esc(n.text)}<span class="meta">${esc(n.author)}</span></div>`).join('') || '<p class="empty">메모가 없습니다.</p>'}<form class="forms note"><input required placeholder="메모"><button>추가</button></form></section>
      <section class="activity"><h3>시간순 활동</h3>${activities.map(a => `<div class="item">${esc(a.summary)}<span class="meta">${esc(a.actor)} · ${new Date(a.occurred_at).toLocaleString()} · 수신 ${new Date(a.received_at).toLocaleString()}</span></div>`).join('') || '<p class="empty">선택한 기간의 활동이 없습니다.</p>'}</section>
      <section class="project-actions"><button type="button" class="ghost move-up" aria-label="프로젝트 위로 이동">↑ 위로</button><button type="button" class="ghost move-down" aria-label="프로젝트 아래로 이동">↓ 아래로</button><button type="button" class="danger delete-project">프로젝트 삭제</button></section>`;
    const open = expanded.has(project.id);
    row.setAttribute('aria-expanded', String(open)); details.hidden = !open;
    row.onclick = () => {
      const wasOpen = expanded.has(project.id);
      row.setAttribute('aria-expanded', String(!wasOpen)); details.hidden = wasOpen;
      if (wasOpen) expanded.delete(project.id); else expanded.add(project.id);
    };
    const textarea = details.querySelector('textarea');
    textarea.value = drafts.get(project.id)?.text ?? userStatus;
    details.querySelector('.status-edit').open = drafts.has(project.id);
    textarea.oninput = () => {
      const previous = drafts.get(project.id);
      drafts.set(project.id, { text: textarea.value, revision: previous?.revision ?? project.revision, conflicted: previous?.conflicted ?? false });
    };
    details.querySelector('.status-form').onsubmit = event => {
      event.preventDefault();
      const draft = drafts.get(project.id) || { text: textarea.value, revision: project.revision };
      if (draft.conflicted) {
        if (!confirm('최신 상태를 확인하셨나요? 보관된 입력 내용으로 내 상태를 저장할까요?')) return;
        draft.revision = project.revision; draft.conflicted = false;
      }
      action(async () => {
        try {
          await write(`/api/projects/${project.id}`, 'PATCH', { user_summary: draft.text, actor: 'human', expected_revision: draft.revision });
        } catch (error) {
          if (error.status === 409) { draft.conflicted = true; drafts.set(project.id, draft); }
          throw error;
        }
        drafts.delete(project.id); notice('내 상태를 저장했습니다.');
      });
    };
    details.querySelector('.task').onsubmit = event => add(event, project, 'tasks');
    details.querySelector('.note').onsubmit = event => add(event, project, 'notes');
    const index = data.projects.findIndex(p => p.id === project.id);
    details.querySelector('.move-up').disabled = index === 0;
    details.querySelector('.move-down').disabled = index === data.projects.length - 1;
    for (const [selector, offset] of [['.move-up', -1], ['.move-down', 1]]) {
      details.querySelector(selector).onclick = () => {
        const reordered = [...data.projects], target = index + offset;
        [reordered[index], reordered[target]] = [reordered[target], reordered[index]];
        action(() => saveOrder(reordered));
      };
    }
    details.querySelector('.delete-project').onclick = () => {
      if (!confirm(`「${project.name}」 프로젝트를 삭제할까요?\n목록에서 제외되며 기록은 보존됩니다.`)) return;
      action(async () => {
        await write(`/api/projects/${project.id}`, 'DELETE', { expected_revision: project.revision });
        drafts.delete(project.id); expanded.delete(project.id); notice('프로젝트를 목록에서 삭제했습니다.');
      });
    };
    attachDrag(article, fragment.querySelector('.drag-handle'), project);
    root.append(fragment);
  }
}
async function add(event, project, type) {
  event.preventDefault(); const input = event.target.querySelector('input');
  const body = type === 'tasks' ? { title: input.value, actor: 'human' } : { text: input.value, author: 'human' };
  await action(async () => { await write(`/api/projects/${project.id}/${type}`, 'POST', body); input.value = ''; input.blur(); notice(type === 'tasks' ? '할 일을 추가했습니다.' : '메모를 추가했습니다.'); });
}
async function refresh(force = false) {
  try {
    const snapshot = await api('/api/snapshot');
    if ($('#date').value) snapshot.activities = await api('/api/activities');
    data = snapshot; $('#login').hidden = true; $('#app').hidden = false;
    $('#dot').className = 'ok'; $('#sync').textContent = `동기화 ${new Date().toLocaleTimeString()}`;
    const signature = JSON.stringify([data.projects, data.tasks, data.notes, data.activities]);
    const editing = document.activeElement?.closest('.details') && document.activeElement.matches('input,textarea,[contenteditable=true]');
    if (!dragging && !busy && (force || signature !== lastSnapshot) && (!editing || force)) { render(); lastSnapshot = signature; }
  } catch (error) {
    $('#dot').className = ''; $('#sync').textContent = '연결 끊김';
    if (error.status === 401) { $('#login').hidden = false; $('#app').hidden = true; }
  }
}
window.pmwConnect = value => { token = value; localStorage.pmwToken = token; refresh(); clearInterval(timer); timer = setInterval(refresh, 3000); };
$('#login-form').onsubmit = event => { event.preventDefault(); window.pmwConnect($('#token').value); };
$('#logout').onclick = () => { localStorage.removeItem('pmwToken'); location.reload(); };
$('#date').onchange = () => refresh(true);
$('#attention').onchange = () => { if (data) render(); };
$('#add-project').onclick = () => {
  const name = prompt('프로젝트 이름'); if (!name?.trim()) return;
  const projectLocation = prompt('프로젝트 위치 (선택): 서버 별칭과 폴더 경로', ''); if (projectLocation === null) return;
  action(async () => { await write('/api/projects', 'POST', { name: name.trim(), location: projectLocation, actor: 'human' }); notice('프로젝트를 등록했습니다.'); });
};
if (token) window.pmwConnect(token);
