/* 플랜두씨 다이어리 2 — 화면 로직. 모든 자료는 서버 API(/api/...)에서 읽고 쓴다. */
const root = document.getElementById('tabContent');
const tabsEl = document.getElementById('tabs');
const msgEl = document.getElementById('msg');
let D = { plans: [], todos: [], execRecords: [], today: '' };
let EXP = null;
let ui = {
  tab: 'cal', cal: null, selDate: null, composerType: 'todo', planEditId: null, todoEditId: null, expandedTodo: null, reviewJump: null, msg: null,
  filter: { status: 'all', tag: '', planId: '', search: '', sortBy: 'dueDate', sortDir: 'asc' },
  reviewScope: { type: 'all', value: '' }, refocus: null,
};

const esc = s => (s == null ? '' : String(s)).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmtDT = iso => iso ? new Date(iso).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' }) : '-';
const fmtDate = d => d || '-';
const cookie = name => (document.cookie.split('; ').find(r => r.startsWith(name + '=')) || '').split('=')[1] || '';

async function api(method, url, body) {
  const opts = { method, headers: { 'X-CSRFToken': cookie('csrftoken') }, credentials: 'same-origin' };
  if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  const res = await fetch(url, opts);
  if (res.status === 401) { location.href = '/login/'; return { ok: false, status: 401, data: {} }; }
  let data = {};
  try { data = await res.json(); } catch (e) { /* 본문 없음 */ }
  return { ok: res.ok, status: res.status, data };
}
function fail(r) { alert((r.data && r.data.detail) || '요청을 처리하지 못했습니다.'); }

async function reload() {
  const [a, b] = await Promise.all([api('GET', '/api/data/'), api('GET', '/api/experiment/')]);
  if (a.ok) D = a.data;
  if (b.ok) EXP = b.data;
  render();
}

// ---------- 계산 도우미 ----------
const activeTodos = () => D.todos;
const planTitle = id => (D.plans.find(p => p.id === id) || {}).title || null;
const isOverdue = t => t.status !== 'completed' && t.dueDate && t.dueDate < D.today;
const recordsOf = id => D.execRecords.filter(r => r.todoId === id);
const isBlocked = t => recordsOf(t.id).some(r => (r.blockedReason || '').trim() !== '');
const actualMin = id => recordsOf(id).reduce((s, r) => s + (r.actualMinutes || 0), 0);
function allTags() {
  const s = new Set();
  D.todos.forEach(t => (t.tags || []).forEach(x => s.add(x)));
  D.plans.forEach(p => (p.topicTags || []).forEach(x => s.add(x)));
  return Array.from(s).sort();
}
const splitTags = v => v.split(',').map(s => s.trim()).filter(Boolean);

function filteredTodos() {
  const f = ui.filter;
  let list = D.todos.slice();
  if (f.status !== 'all') {
    if (f.status === 'overdue') list = list.filter(isOverdue);
    else if (f.status === 'blocked') list = list.filter(isBlocked);
    else list = list.filter(t => t.status === f.status);
  }
  if (f.tag) list = list.filter(t => (t.tags || []).includes(f.tag));
  if (f.planId) list = list.filter(t => t.planId === f.planId);
  if (f.search) list = list.filter(t => t.title.toLowerCase().includes(f.search.toLowerCase()));
  const dir = f.sortDir === 'asc' ? 1 : -1;
  const key = { dueDate: t => t.dueDate || '', priority: t => t.priority || 0, estimatedTime: t => t.estimatedTime || 0 }[f.sortBy];
  list.sort((a, b) => {
    const av = key ? key(a) : a.id.padStart(12, '0'), bv = key ? key(b) : b.id.padStart(12, '0');
    return av < bv ? -dir : av > bv ? dir : 0;
  });
  return list;
}

// ---------- 렌더 ----------
const TABS = [['cal', '▦ 캘린더'], ['plans', '계획'], ['todos', '할 일'], ['review', '◷ 돌아보기'], ['exp', '5일 기록'], ['account', '내 계정']];
const TITLES = {
  cal: ['이번 달을 한눈에', '계획과 할 일을 같은 화면에서 관리해 보세요.'],
  plans: ['계획', '기간·성공 기준·예상 시간을 담아 계획을 세웁니다.'],
  todos: ['할 일', '마감일·태그·실행 기록으로 하루를 쌓아 갑니다.'],
  review: ['돌아보기', '숫자를 눌러 어떤 할 일에서 나왔는지 확인하세요.'],
  exp: ['5일 기록', '질문과 지표를 정하고 5일을 기록합니다.'],
  account: ['내 계정', '내보내기·비밀번호·계정 삭제'],
};
function render() {
  if (!ui.cal && D.today) { const [y, m] = D.today.split('-').map(Number); ui.cal = { y, m: m - 1 }; ui.selDate = D.today; }
  tabsEl.innerHTML = TABS.map(([k, l]) => `<div class="tab ${ui.tab === k ? 'active' : ''}" onclick="App.setTab('${k}')">${l}</div>`).join('');
  const [t, sub] = TITLES[ui.tab];
  document.getElementById('pageTitle').textContent = t;
  document.getElementById('pageSub').textContent = sub;
  renderSidebar();
  msgEl.innerHTML = ui.msg ? `<div class="okmsg">${esc(ui.msg)}</div>` : '';
  root.innerHTML = { cal: renderCal, plans: renderPlans, todos: renderTodos, review: renderReview, exp: renderExp, account: renderAccount }[ui.tab]();
  if (ui.tab === 'cal') {
    wireDrag('todoPriorityList', openTodosByPriority, ids => App.reorder('todos', ids));
    wireDrag('planPriorityList', () => D.plans, ids => App.reorder('plans', ids));
  }
  if (ui.tab === 'plans') wireDrag('planDragList', () => D.plans, ids => App.reorder('plans', ids));
  if (ui.tab === 'todos') wireDrag('todoDragList', filteredTodos, ids => App.reorder('todos', ids));
  if (ui.refocus) { const el = document.getElementById(ui.refocus); if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length); } ui.refocus = null; }
}

function renderSidebar() {
  if (!D.today) return;
  const d = new Date(D.today + 'T00:00:00');
  document.getElementById('sideDay').textContent = d.toLocaleDateString('ko-KR', { weekday: 'long' });
  document.getElementById('sideDate').textContent = d.getDate();
  document.getElementById('sideTodoCount').textContent = D.todos.filter(t => t.status !== 'completed').length;
  document.getElementById('sidePlanCount').textContent = D.plans.length;
}

// ---- 캘린더 ----
const pad2 = n => String(n).padStart(2, '0');
const ymd = (y, m, d) => `${y}-${pad2(m + 1)}-${pad2(d)}`;
const openTodosByPriority = () => D.todos.filter(t => t.status !== 'completed').sort((a, b) => (a.priority || 999) - (b.priority || 999));
function dateEvents(ds) {
  const ev = [];
  D.plans.forEach(p => { if (p.periodStart <= ds && ds <= p.periodEnd) ev.push({ kind: 'plan', id: p.id, title: p.title, done: false, item: p }); });
  D.todos.forEach(t => { if (t.dueDate === ds) ev.push({ kind: 'todo', id: t.id, title: t.title, done: t.status === 'completed', item: t }); });
  return ev;
}
function renderCal() {
  const { y, m } = ui.cal, first = new Date(y, m, 1), start = new Date(y, m, 1 - first.getDay());
  let cells = '';
  for (let i = 0; i < 42; i++) {
    const day = new Date(start.getFullYear(), start.getMonth(), start.getDate() + i);
    const ds = ymd(day.getFullYear(), day.getMonth(), day.getDate());
    const other = day.getMonth() !== m, today = ds === D.today, sel = ds === ui.selDate;
    const ev = dateEvents(ds);
    cells += `<div class="day-cell ${other ? 'other' : ''} ${sel ? 'selected' : ''}" data-date="${ds}" onclick="App.selectDate('${ds}')">
      <span class="day-number ${today ? 'today' : ''} ${sel && !today ? 'selected' : ''}">${day.getDate()}</span>
      ${ev.slice(0, 3).map(e => `<span class="event-pill ${e.kind} ${e.done ? 'done' : ''}">${esc(e.title)}</span>`).join('')}
      ${ev.length > 3 ? `<div class="more-count">+ ${ev.length - 3}개 더보기</div>` : ''}</div>`;
  }
  const ev = dateEvents(ui.selDate || D.today);
  const sd = new Date((ui.selDate || D.today) + 'T00:00:00');
  const todos = openTodosByPriority();
  const prItem = (type, x, i) => `<div class="priority-item" data-drag-id="${x.id}"><span class="priority-handle">☷</span><span class="priority-num">${i + 1}</span><span class="priority-title" title="${esc(x.title)}">${esc(x.title)}</span></div>`;
  return `
  <section class="layout">
    <div class="card calendar-card">
      <div class="calendar-head">
        <div class="calendar-tools"><button class="icon-btn" onclick="App.moveMonth(-1)" aria-label="이전 달">‹</button>
          <div class="month-title" id="monthTitle">${y}년 ${m + 1}월</div>
          <button class="icon-btn" onclick="App.moveMonth(1)" aria-label="다음 달">›</button></div>
        <button class="btn secondary" onclick="App.goToday()">오늘로 이동</button>
      </div>
      <div class="weekdays">${['일', '월', '화', '수', '목', '금', '토'].map(w => `<div class="weekday">${w}</div>`).join('')}</div>
      <div class="calendar-grid" id="calendarGrid">${cells}</div>
    </div>
    <aside class="side-panel">
      <div class="card"><div class="panel-title"><h3 id="selectedDateTitle">${sd.toLocaleDateString('ko-KR', { month: 'long', day: 'numeric', weekday: 'short' })}</h3>
        <div class="row"><span class="badge primary">${ev.length}건</span><button class="btn small" onclick="App.openComposer('todo','${ui.selDate}')">＋ 추가</button></div></div>
        <div class="schedule-stack" id="selectedSchedule">${ev.length ? ev.map(e => scheduleBar(e)).join('') : '<div class="empty">이 날짜에 등록된 일정이 없습니다.</div>'}</div></div>
      <div class="card"><div class="panel-title"><h3>우선순위</h3><span class="badge primary">드래그</span></div>
        <div class="muted" style="margin-bottom:8px">항목을 위아래로 끌어 순서를 바꾸면 바로 저장됩니다.</div>
        <div class="priority-group-title">미완료 할 일</div>
        <div id="todoPriorityList" class="priority-list">${todos.length ? todos.map((t, i) => prItem('todo', t, i)).join('') : '<div class="empty">미완료 할 일이 없습니다.</div>'}</div>
        <div class="priority-group-title" style="margin-top:14px">계획</div>
        <div id="planPriorityList" class="priority-list">${D.plans.length ? D.plans.map((p, i) => prItem('plan', p, i)).join('') : '<div class="empty">계획이 없습니다.</div>'}</div></div>
    </aside>
  </section>`;
}
function scheduleBar(e) {
  const t = e.item;
  const meta = e.kind === 'plan' ? `계획 · ${t.periodStart} ~ ${t.periodEnd} · 예상 ${t.estimatedTime}시간` : `할 일 · ${planTitle(t.planId) || '연결된 계획 없음'} · 예상 ${t.estimatedTime}시간`;
  return `<div class="schedule-bar ${e.kind} ${e.done ? 'done' : ''}">
    <div class="schedule-title">${esc(e.title)} ${e.kind === 'plan' ? '<span class="badge orange">계획</span>' : `<span class="badge ${e.done ? 'green' : 'primary'}">${e.done ? '완료' : '할 일'}</span>`}${e.kind === 'todo' && isOverdue(t) ? ' <span class="badge red">지연</span>' : ''}</div>
    <div class="schedule-meta">${esc(meta)}</div>
    <div class="row" style="margin-top:8px">
      ${e.kind === 'todo' ? (e.done ? `<button class="btn small secondary" onclick="App.reopen('${e.id}')">미완료로</button>` : `<button class="btn small green" onclick="App.complete('${e.id}', this)">완료</button>`) : `<button class="btn small" onclick="App.openComposer('todo','${ui.selDate}','${e.id}')">＋ 할 일</button>`}
      <button class="btn small secondary" onclick="App.${e.kind === 'plan' ? 'editPlan' : 'editTodo'}('${e.id}')">수정</button>
      <button class="btn small danger" onclick="App.${e.kind === 'plan' ? 'deletePlan' : 'deleteTodo'}('${e.id}')">삭제</button></div></div>`;
}

function wireDrag(id, getItems, onReorder) {
  const c = document.getElementById(id);
  if (!c) return;
  let dragId = null;
  c.querySelectorAll('[data-drag-id]').forEach(el => {
    el.setAttribute('draggable', 'true');
    el.addEventListener('dragstart', e => { dragId = el.dataset.dragId; e.dataTransfer.effectAllowed = 'move'; });
    el.addEventListener('dragover', e => e.preventDefault());
    el.addEventListener('drop', e => {
      e.preventDefault();
      const target = el.dataset.dragId;
      if (dragId && dragId !== target) {
        const ids = getItems().map(i => i.id);
        const from = ids.indexOf(dragId), to = ids.indexOf(target);
        if (from > -1 && to > -1) { ids.splice(to, 0, ids.splice(from, 1)[0]); onReorder(ids); }
      }
    });
  });
}

// ---- 계획 ----
function renderPlans() {
  const ed = ui.planEditId ? D.plans.find(p => p.id === ui.planEditId) : null;
  return `
  <div class="card"><h3>${ed ? '계획 수정' : '새 계획 만들기'}</h3>
    <form onsubmit="return App.submitPlan(event)">
      <div class="field"><label>제목</label><input id="pf_title" required value="${esc(ed?.title || '')}"></div>
      <div class="grid2">
        <div class="field"><label>시작일 (기간)</label><input type="date" id="pf_start" required value="${ed?.periodStart || ''}"></div>
        <div class="field"><label>종료일 (기간)</label><input type="date" id="pf_end" required value="${ed?.periodEnd || ''}"></div>
      </div>
      <div class="field"><label>주제 태그 (쉼표로 구분, 예: 운동, 러닝)</label><input id="pf_tags" value="${esc((ed?.topicTags || []).join(', '))}"></div>
      <div class="field"><label>성공 기준 (직접 작성)</label><textarea id="pf_success">${esc(ed?.successCriteria || '')}</textarea></div>
      <div class="field"><label>예상 시간 (시간 단위)</label><input type="number" step="0.5" min="0" id="pf_est" required value="${ed?.estimatedTime ?? ''}"></div>
      <div class="row"><button class="btn" type="submit">${ed ? '수정 저장' : '계획 추가'}</button>
        ${ed ? '<button type="button" class="btn secondary" onclick="App.cancelEdit()">취소</button>' : ''}</div>
      <p class="muted">※ 계획을 고쳐도 고치기 전 모습은 "이전 버전"으로 서버에 남습니다.</p>
    </form></div>
  <div class="card"><h3>우선순위 정렬 (드래그해서 순서 변경)</h3>
    ${D.plans.length === 0 ? '<div class="empty">계획이 없습니다.</div>' : `<div id="planDragList">${D.plans.map(p => `
      <div class="drag-item" data-drag-id="${p.id}"><span>#${p.priority} · ${esc(p.title)}</span><span class="muted">${esc((p.topicTags || []).join(', '))}</span></div>`).join('')}</div>`}
  </div>
  <h3 style="margin:16px 0 8px;">계획 목록</h3>
  ${D.plans.length === 0 ? '<div class="empty">등록된 계획이 없습니다.</div>' : D.plans.map(planCard).join('')}`;
}
function planCard(p) {
  const n = D.todos.filter(t => t.planId === p.id).length;
  const hist = (p.history || []).length ? `
    <div class="link-btn" onclick="App.toggle('hist_${p.id}')" style="margin-top:6px;">이전 버전 보기 (${p.history.length}건)</div>
    <div id="hist_${p.id}" style="display:none;margin-top:6px;">${p.history.slice().reverse().map(h => `
      <div class="history-item"><b>${esc(h.title)}</b> · ${h.periodStart}~${h.periodEnd} · 성공기준: ${esc(h.successCriteria || '-')} · 예상 ${h.estimatedTime}h
      <div class="muted">고친 시각: ${fmtDT(h.editedAt)}</div></div>`).join('')}</div>` : '';
  const notes = (p.improvementNotes || []).length ? `<div class="muted" style="margin-top:6px;"><b>돌아보기에서 넘어온 고칠 점</b></div>
    ${p.improvementNotes.map(x => `<div class="history-item">${esc(x.text)}</div>`).join('')}` : '';
  return `<div class="card"><div class="title-row"><div>
    <h3>${esc(p.title)} <span class="badge">우선순위 #${p.priority}</span></h3>
    <div class="muted">${p.periodStart} ~ ${p.periodEnd} · 예상 ${p.estimatedTime}시간 · 딸린 할 일 ${n}개</div>
    <div style="margin-top:6px;">${(p.topicTags || []).map(t => `<span class="tag">${esc(t)}</span>`).join('')}</div>
    <div style="margin-top:6px;"><b>성공 기준:</b> ${esc(p.successCriteria || '-')}</div></div>
    <div class="row"><button class="btn small secondary" onclick="App.editPlan('${p.id}')">수정</button>
    <button class="btn small danger" onclick="App.deletePlan('${p.id}')">삭제</button></div></div>${notes}${hist}</div>`;
}

// ---- 할 일 ----
function renderTodos() {
  const ed = ui.todoEditId ? D.todos.find(t => t.id === ui.todoEditId) : null;
  const f = ui.filter, list = filteredTodos();
  const sel = (v, cur) => v === cur ? 'selected' : '';
  return `
  <div class="card"><h3>${ed ? '할 일 수정' : '새 할 일 만들기'}</h3>
    <form onsubmit="return App.submitTodo(event)">
      <div class="field"><label>제목</label><input id="tf_title" required value="${esc(ed?.title || '')}"></div>
      <div class="field"><label>연결된 계획 (선택)</label><select id="tf_plan"><option value="">— 없음 —</option>
        ${D.plans.map(p => `<option value="${p.id}" ${ed?.planId === p.id ? 'selected' : ''}>${esc(p.title)}</option>`).join('')}</select></div>
      <div class="grid2">
        <div class="field"><label>시작일</label><input type="date" id="tf_start" value="${ed?.periodStart || ''}"></div>
        <div class="field"><label>마감일 (= 기간의 끝)</label><input type="date" id="tf_due" required value="${ed?.dueDate || ''}"></div>
      </div>
      <div class="field"><label>주제 태그 (쉼표 구분)</label><input id="tf_tags" value="${esc((ed?.tags || []).join(', '))}"></div>
      <div class="field"><label>성공 기준 (직접 작성)</label><textarea id="tf_success">${esc(ed?.successCriteria || '')}</textarea></div>
      <div class="field"><label>예상 시간 (시간 단위)</label><input type="number" step="0.5" min="0" id="tf_est" required value="${ed?.estimatedTime ?? ''}"></div>
      <div class="row"><button class="btn" type="submit">${ed ? '수정 저장' : '할 일 추가'}</button>
        ${ed ? '<button type="button" class="btn secondary" onclick="App.cancelEdit()">취소</button>' : ''}</div>
    </form></div>
  <div class="card"><h3>필터 &amp; 검색</h3><div class="row">
    <div class="field" style="flex:2"><label>검색</label><input id="ff_search" value="${esc(f.search)}" oninput="App.setFilter('search',this.value)" placeholder="제목으로 검색"></div>
    <div class="field"><label>상태</label><select onchange="App.setFilter('status',this.value)">
      ${[['all', '전체'], ['in_progress', '진행 중'], ['completed', '완료'], ['overdue', '지연'], ['blocked', '막힘']].map(([v, l]) => `<option value="${v}" ${sel(v, f.status)}>${l}</option>`).join('')}</select></div>
    <div class="field"><label>태그</label><select onchange="App.setFilter('tag',this.value)"><option value="">전체</option>
      ${allTags().map(t => `<option value="${esc(t)}" ${sel(t, f.tag)}>${esc(t)}</option>`).join('')}</select></div>
    <div class="field"><label>계획</label><select onchange="App.setFilter('planId',this.value)"><option value="">전체</option>
      ${D.plans.map(p => `<option value="${p.id}" ${sel(p.id, f.planId)}>${esc(p.title)}</option>`).join('')}</select></div>
    <div class="field"><label>정렬 기준</label><select onchange="App.setFilter('sortBy',this.value)">
      ${[['dueDate', '마감일'], ['priority', '우선순위'], ['estimatedTime', '예상 시간'], ['createdAt', '생성순']].map(([v, l]) => `<option value="${v}" ${sel(v, f.sortBy)}>${l}</option>`).join('')}</select></div>
    <div class="field"><label>방향</label><select onchange="App.setFilter('sortDir',this.value)">
      <option value="asc" ${sel('asc', f.sortDir)}>오름차순</option><option value="desc" ${sel('desc', f.sortDir)}>내림차순</option></select></div>
  </div></div>
  <div class="card"><h3>우선순위 정렬 (드래그, 현재 필터 목록 기준)</h3>
    ${list.length === 0 ? '<div class="empty">표시할 항목이 없습니다.</div>' : `<div id="todoDragList">${list.map(t => `<div class="drag-item" data-drag-id="${t.id}"><span>#${t.priority} · ${esc(t.title)}</span></div>`).join('')}</div>`}</div>
  <h3 style="margin:16px 0 8px;">할 일 목록 (${list.length}건)</h3>
  ${list.length === 0 ? '<div class="empty">조건에 맞는 할 일이 없습니다.</div>' : list.map(todoCard).join('')}`;
}
function todoCard(t) {
  const overdue = isOverdue(t), blocked = isBlocked(t), recs = recordsOf(t.id).slice().reverse();
  const open = ui.expandedTodo === t.id;
  const hist = (t.history || []).length ? `
    <div class="link-btn" onclick="App.toggle('th_${t.id}')" style="margin-top:4px;">이전 버전 보기 (${t.history.length}건)</div>
    <div id="th_${t.id}" style="display:none;margin-top:6px;">${t.history.slice().reverse().map(h => `
      <div class="history-item">${esc(h.title)} · 마감 ${h.dueDate} · 예상 ${h.estimatedTime}h · 성공기준: ${esc(h.successCriteria || '-')}
      <div class="muted">고친 시각: ${fmtDT(h.editedAt)}</div></div>`).join('')}</div>` : '';
  return `<div class="card"><div class="title-row"><div>
    <h3>${esc(t.title)} <span class="badge ${t.status === 'completed' ? 'done' : ''}">${t.status === 'completed' ? '완료' : '진행 중'}</span>
      ${overdue ? '<span class="badge overdue">지연</span>' : ''}${blocked ? '<span class="badge overdue">막힘</span>' : ''}</h3>
    <div class="muted">마감일: ${fmtDate(t.dueDate)}${t.periodStart ? ' · 시작일: ' + t.periodStart : ''} · 우선순위 #${t.priority}${t.planId ? ' · 계획: ' + esc(planTitle(t.planId) || '-') : ''}</div>
    <div style="margin-top:4px;">${(t.tags || []).map(x => `<span class="tag">${esc(x)}</span>`).join('')}</div>
    <div style="margin-top:4px;"><b>성공 기준:</b> ${esc(t.successCriteria || '-')} · <b>예상:</b> ${t.estimatedTime}h · <b>실제:</b> ${(actualMin(t.id) / 60).toFixed(1)}h</div></div>
    <div class="row" style="flex-direction:column;align-items:flex-end;">
      ${t.status === 'completed' ? `<button class="btn small secondary" onclick="App.reopen('${t.id}')">진행 중으로 되돌리기</button>`
      : `<button class="btn small green" onclick="App.complete('${t.id}', this)">완료로 변경</button>`}
      <div class="row"><button class="btn small secondary" onclick="App.editTodo('${t.id}')">수정</button>
      <button class="btn small danger" onclick="App.deleteTodo('${t.id}')">삭제</button></div></div></div>
    ${hist}<hr class="sep">
    <div class="link-btn" onclick="App.expand('${t.id}')">${open ? '실행 기록 접기' : '실행 기록 보기/추가 (' + recs.length + '건)'}</div>
    ${open ? `<div style="margin-top:8px;">
      ${recs.length === 0 ? '<div class="muted">아직 실행 기록이 없습니다.</div>' : recs.map(r => `<div class="exec-item ${r.blockedReason ? 'blocked' : ''}">
        ${fmtDT(r.start)} ~ ${fmtDT(r.end)} · ${(r.actualMinutes / 60).toFixed(2)}시간
        ${r.blockedReason ? `<div class="flag">막혔던 이유: ${esc(r.blockedReason)}</div>` : ''}
        <div><button class="link-btn" onclick="App.deleteRecord('${r.id}')">삭제</button></div></div>`).join('')}
      <form onsubmit="return App.submitRecord(event,'${t.id}')" style="margin-top:8px;">
        <div class="grid3">
          <div class="field"><label>시작 시각</label><input type="datetime-local" id="ef_s_${t.id}" required></div>
          <div class="field"><label>끝난 시각</label><input type="datetime-local" id="ef_e_${t.id}" required></div>
          <div class="field"><label>막혔던 이유 (직접 작성, 선택)</label><input id="ef_b_${t.id}"></div></div>
        <button class="btn small" type="submit">기록 추가</button></form></div>` : ''}</div>`;
}

// ---- 돌아보기 ----
function reviewTargets() {
  const s = ui.reviewScope;
  if (s.type === 'plan' && s.value) return D.todos.filter(t => t.planId === s.value);
  if (s.type === 'topic' && s.value) return D.todos.filter(t => (t.tags || []).includes(s.value));
  return D.todos;
}
function renderReview() {
  const s = ui.reviewScope, tg = reviewTargets();
  const done = tg.filter(t => t.status === 'completed'), late = tg.filter(isOverdue), blk = tg.filter(isBlocked);
  const est = tg.reduce((a, t) => a + (Number(t.estimatedTime) || 0), 0);
  const act = tg.reduce((a, t) => a + actualMin(t.id), 0) / 60;
  const diff = tg.length ? act - est : 0;
  const planCount = s.type === 'plan' && s.value ? 1 : D.plans.length;
  const j = ui.reviewJump;
  return `
  <div class="card"><h3>돌아보기 범위</h3><div class="row">
    <div class="field"><label>범위</label><select onchange="App.setScope(this.value)">
      ${[['all', '전체'], ['plan', '특정 계획'], ['topic', '특정 주제(태그)']].map(([v, l]) => `<option value="${v}" ${s.type === v ? 'selected' : ''}>${l}</option>`).join('')}</select></div>
    ${s.type === 'plan' ? `<div class="field"><label>계획</label><select onchange="App.setScopeValue(this.value)"><option value="">— 선택 —</option>
      ${D.plans.map(p => `<option value="${p.id}" ${s.value === p.id ? 'selected' : ''}>${esc(p.title)}</option>`).join('')}</select></div>` : ''}
    ${s.type === 'topic' ? `<div class="field"><label>주제</label><select onchange="App.setScopeValue(this.value)"><option value="">— 선택 —</option>
      ${allTags().map(t => `<option value="${esc(t)}" ${s.value === t ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select></div>` : ''}
  </div></div>
  <div class="metrics">
    <div class="metric" onclick="App.jump('계획 (딸린 할 일)','all')"><div class="num">${planCount}</div><div class="lab">계획 수 (눌러서 할 일 보기: ${tg.length}건)</div></div>
    <div class="metric" onclick="App.jump('완료','done')"><div class="num">${done.length}</div><div class="lab">완료 수</div></div>
    <div class="metric" onclick="App.jump('지연','late')"><div class="num">${late.length}</div><div class="lab">지연 수</div></div>
    <div class="metric" onclick="App.jump('막힘','blk')"><div class="num">${blk.length}</div><div class="lab">막힘 수</div></div>
    <div class="metric static"><div class="num">${est.toFixed(1)}h</div><div class="lab">예상 시간</div></div>
    <div class="metric static"><div class="num">${act.toFixed(1)}h</div><div class="lab">실제 시간</div></div>
    <div class="metric static"><div class="num">${diff >= 0 ? '+' : ''}${diff.toFixed(1)}h</div><div class="lab">차이 (실제−예상)</div></div></div>
  <div class="card"><h3>계획별 할 일 수 (지우지 않은 할 일만)</h3>
    ${D.plans.length === 0 ? '<div class="empty">계획이 없습니다.</div>' : `<table class="t"><tr><th>계획</th><th>딸린 할 일</th><th>완료</th></tr>
      ${D.plans.map(p => { const ts = D.todos.filter(t => t.planId === p.id); return `<tr><td>${esc(p.title)}</td><td>${ts.length}건</td><td>${ts.filter(t => t.status === 'completed').length}건</td></tr>`; }).join('')}</table>`}</div>
  ${j ? `<div class="card"><h3>${esc(j.label)} (${j.items.length}건)</h3>
    ${j.items.length === 0 ? '<div class="empty">해당하는 할 일이 없습니다.</div>' : j.items.map(t => `<div class="history-item"><b>${esc(t.title)}</b> · 마감 ${fmtDate(t.dueDate)} · ${t.status === 'completed' ? '완료' : '진행 중'}${t.completedAt ? ' · 완료 ' + fmtDT(t.completedAt) : ''}</div>`).join('')}
    <button class="btn small secondary" style="margin-top:8px" onclick="App.closeJump()">닫기</button></div>` : ''}
  <div class="card"><h3>고칠 점 (다음 계획으로 넘기기)</h3>
    <div class="field"><label>고칠 점</label><textarea id="rv_note"></textarea></div>
    <div class="field"><label>반영할 계획</label><select id="rv_plan"><option value="">— 선택 —</option>${D.plans.map(p => `<option value="${p.id}">${esc(p.title)}</option>`).join('')}</select></div>
    <button class="btn" onclick="App.submitNote()">다음 계획에 반영</button></div>`;
}

// ---- 5일 기록 ----
function renderExp() {
  if (!EXP) return '<div class="empty">불러오는 중...</div>';
  const R = EXP.rules, S = EXP.settings;
  const rulesHtml = `<ul class="rules">${[['계산', R.calc], ['값이 빠졌을 때', R.missing], ['값이 중복될 때', R.duplicate], ['값이 유난히 튈 때', R.outlier], ['반올림', R.rounding], ['주 시작 요일', R.week_start]].map(([k, v]) => `<li><b>${k}:</b> ${esc(v)}</li>`).join('')}</ul>`;
  if (!S) return `<div class="card"><h3>1일차: 질문·지표·계획 규칙 정하기</h3>
    <div class="notice">한 번 고정하면 바꿀 수 없습니다. 사람이 읽는 문장으로 적어 주세요.</div>
    <form onsubmit="return App.fixExp(event)">
      <div class="field"><label>답하려는 질문 (한 문장)</label><input id="ex_q" required></div>
      <div class="grid2"><div class="field"><label>관찰 지표 (하나)</label><input id="ex_m" required></div>
        <div class="field"><label>단위</label><input id="ex_u" required></div></div>
      <div class="field"><label>계획 규칙 (지금 쓰는 규칙)</label><textarea id="ex_r" required></textarea></div>
      <button class="btn" type="submit">고정하기</button></form>
    <hr class="sep"><b>고정된 계산·처리 규칙 (코드가 이대로 계산합니다)</b>${rulesHtml}</div>`;
  const n = EXP.days.length, canRule = n === 2 && !EXP.ruleChange, full = n >= EXP.maxDays;
  const todayDone = EXP.days.some(d => d.date === EXP.today);
  const blockedByRule = n === 2 && !EXP.ruleChange && !todayDone;
  const sum = EXP.total;
  const cmp = EXP.comparison;
  return `
  <div class="card"><h3>고정된 질문과 지표</h3>
    <div><b>질문:</b> ${esc(S.question)}</div>
    <div><b>지표:</b> ${esc(S.metricName)} (단위: ${esc(S.unit)})</div>
    <div><b>계획 규칙(처음):</b> ${esc(S.planRule)}</div>
    <div class="muted">고정한 시각: ${fmtDT(S.fixedAt)}</div>
    <hr class="sep"><b>계산·처리 규칙</b>${rulesHtml}</div>
  <div class="card"><h3>일별 기록 (${n}/${EXP.maxDays}일)</h3>
    ${n === 0 ? '<div class="empty">아직 기록이 없습니다.</div>' : `<table class="t"><tr><th>일차</th><th>날짜(서울)</th><th>주 시작(월)</th><th>값 (${esc(S.unit)})</th><th>메모</th><th></th></tr>
      ${EXP.days.map(d => `<tr><td>${d.dayNo}일차</td><td>${d.date}</td><td>${d.weekStart}</td><td>${esc(d.value)}</td><td>${esc(d.note)}</td><td>${d.outlier ? '<span class="flag">튀는 값</span>' : ''}</td></tr>`).join('')}</table>`}
    <div style="margin-top:8px"><b>합계:</b> ${sum.sum ?? '-'} ${esc(S.unit)} · <b>평균:</b> ${sum.average ?? '-'} ${esc(S.unit)}
      <div class="muted">손으로 더해 보기: ${sum.values.length ? sum.values.join(' + ') + ' = ' + sum.sum : '-'} / ${sum.count}일</div></div>
    ${full ? '<div class="okmsg">5일 기록이 모두 채워졌습니다.</div>' : blockedByRule ? '<div class="notice">3일차 기록 전에 아래에서 계획 규칙 변경을 먼저 기록해야 합니다.</div>' : `
    <form onsubmit="return App.addDay(event)" style="margin-top:10px">
      <div class="grid2"><div class="field"><label>오늘(${EXP.today})의 값 (${esc(S.unit)})</label><input id="dy_v" type="number" step="0.01" required></div>
        <div class="field"><label>메모 (선택)</label><input id="dy_n"></div></div>
      <button class="btn" type="submit">${todayDone ? '오늘 값 덮어쓰기' : '오늘 기록 저장'}</button>
      <span class="muted">날짜는 서버가 서울 시간 기준 오늘로 정합니다. 같은 날 다시 저장하면 한 건만 남습니다.</span></form>`}</div>
  <div class="card"><h3>계획 규칙 변경 (2일차 뒤, 3일차 앞)</h3>
    ${EXP.ruleChange ? `<div><b>바꾼 시각:</b> ${fmtDT(EXP.ruleChange.changedAt)}</div>
      <div><b>이유:</b> ${esc(EXP.ruleChange.reason)}</div>
      <div><b>바꾸기 전:</b> ${esc(EXP.ruleChange.beforeRule)}</div>
      <div><b>바꾼 뒤:</b> ${esc(EXP.ruleChange.afterRule)}</div>
      <div class="muted">가리키는 기록: 1일차(${EXP.ruleChange.day1.date}) · 2일차(${EXP.ruleChange.day2.date}) — 이 두 기록 뒤, 3일차 기록 앞에 놓임</div>`
    : canRule ? `<form onsubmit="return App.ruleChange(event)">
      <div class="field"><label>바꾼 이유</label><textarea id="rc_reason" required></textarea></div>
      <div class="field"><label>새 계획 규칙 (하나만 바꾸기)</label><textarea id="rc_rule" required></textarea></div>
      <button class="btn" type="submit">규칙 변경 기록</button></form>`
    : '<div class="muted">2일차 기록이 끝나면 여기서 한 번 기록할 수 있습니다.</div>'}</div>
  ${cmp ? `<div class="card"><h3>규칙 변경 전후 비교</h3>
    <div class="muted">같은 지표(${esc(cmp.metric)}) · 같은 단위(${esc(cmp.unit)}) · 같은 계산 규칙으로 비교합니다.</div>
    <table class="t"><tr><th></th><th>일수</th><th>값들</th><th>합계</th><th>평균</th></tr>
      <tr><td>변경 전 (1~2일차)</td><td>${cmp.before.count}</td><td>${cmp.before.values.join(', ')}</td><td>${cmp.before.sum ?? '-'}</td><td>${cmp.before.average ?? '-'}</td></tr>
      <tr><td>변경 후 (3일차~)</td><td>${cmp.after.count}</td><td>${cmp.after.values.join(', ') || '-'}</td><td>${cmp.after.sum ?? '-'}</td><td>${cmp.after.average ?? '-'}</td></tr></table></div>` : ''}`;
}

// ---- 내 계정 ----
function renderAccount() {
  return `
  <div class="card"><h3>내 자료 내보내기</h3>
    <p class="muted">계획·할 일·실행 기록·5일 기록 전체를 JSON 파일 하나로 받습니다. 비밀번호 정보는 들어 있지 않습니다.</p>
    <a class="btn" href="/api/export/" download>JSON 파일 내보내기</a></div>
  <div class="card"><h3>6번 다이어리 자료 가져오기</h3>
    <p class="muted">6번에서 내보낸 JSON 파일을 고르면 내 계정으로 옮겨집니다.</p>
    <input type="file" id="imp_file" accept="application/json,.json">
    <button class="btn small" style="margin-top:8px" onclick="App.importFile()">내 계정으로 옮기기</button></div>
  <div class="card"><h3>비밀번호 바꾸기</h3>
    <form onsubmit="return App.changePw(event)">
      <div class="grid2"><div class="field"><label>현재 비밀번호</label><input type="password" id="pw_old" autocomplete="current-password" required></div>
        <div class="field"><label>새 비밀번호 (8자 이상)</label><input type="password" id="pw_new" autocomplete="new-password" required></div></div>
      <button class="btn" type="submit">변경</button>
      <span class="muted">바꾸면 다른 곳에서 로그인해 둔 세션은 모두 끊깁니다.</span></form></div>
  <div class="card"><h3>계정 삭제</h3>
    <div class="notice">계정을 지우면 내 계획·할 일·실행 기록·5일 기록이 서버에서 <b>모두 함께 영구 삭제</b>되며 되돌릴 수 없습니다. 필요하면 먼저 내보내기를 하세요.</div>
    <form onsubmit="return App.deleteAccount(event)">
      <div class="field"><label>비밀번호 확인</label><input type="password" id="del_pw" autocomplete="current-password" required></div>
      <button class="btn danger" type="submit">계정과 자료 삭제</button></form></div>`;
}

// ---------- 동작 ----------
const App = {
  selectDate(ds) { ui.selDate = ds; const [y, m] = ds.split('-').map(Number); ui.cal = { y, m: m - 1 }; render(); },
  moveMonth(n) { const d = new Date(ui.cal.y, ui.cal.m + n, 1); ui.cal = { y: d.getFullYear(), m: d.getMonth() }; render(); },
  goToday() { ui.tab = 'cal'; this.selectDate(D.today); },
  openComposer(type = 'todo', ds = null, planId = null) {
    ui.composerType = type; const day = ds || ui.selDate || D.today;
    document.getElementById('cm_type').value = type;
    document.getElementById('composerForm').reset();
    document.getElementById('cm_type').value = type;
    document.getElementById('cm_plan').innerHTML = '<option value="">— 없음 —</option>' + D.plans.map(p => `<option value="${p.id}" ${p.id === planId ? 'selected' : ''}>${esc(p.title)}</option>`).join('');
    document.getElementById('cm_start').value = day; document.getElementById('cm_end').value = day;
    this.composerType();
    document.getElementById('composerModal').classList.add('open');
    setTimeout(() => document.getElementById('cm_title').focus(), 30);
  },
  composerType() {
    const plan = document.getElementById('cm_type').value === 'plan';
    document.getElementById('cm_planWrap').style.display = plan ? 'none' : 'block';
    document.getElementById('cm_startLabel').textContent = plan ? '기간 시작일' : '시작일';
    document.getElementById('cm_endLabel').textContent = plan ? '기간 종료일' : '마감일';
  },
  closeComposer() { document.getElementById('composerModal').classList.remove('open'); },
  backdropClose(e) { if (e.target.id === 'composerModal') this.closeComposer(); },
  async submitComposer(e) {
    e.preventDefault();
    const g = id => document.getElementById(id).value, type = g('cm_type');
    if (g('cm_end') < g('cm_start')) return alert('종료일이 시작일보다 빠를 수 없습니다.'), false;
    const base = { title: g('cm_title'), successCriteria: g('cm_success'), estimatedTime: g('cm_est') };
    const r = type === 'plan'
      ? await api('POST', '/api/plans/', { ...base, periodStart: g('cm_start'), periodEnd: g('cm_end'), topicTags: splitTags(g('cm_tags')) })
      : await api('POST', '/api/todos/', { ...base, planId: g('cm_plan') || null, periodStart: g('cm_start') || null, dueDate: g('cm_end'), tags: splitTags(g('cm_tags')) });
    if (!r.ok) return fail(r), false;
    this.closeComposer(); await reload(); return false;
  },
  setTab(t) { ui.tab = t; ui.reviewJump = null; ui.msg = null; render(); },
  toggle(id) { const el = document.getElementById(id); if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none'; },
  cancelEdit() { ui.planEditId = ui.todoEditId = null; render(); },
  async reorder(kind, ids) { const r = await api('POST', `/api/${kind}/reorder/`, { ids }); if (!r.ok) fail(r); await reload(); },

  async submitPlan(e) {
    e.preventDefault();
    const body = { title: pf_title.value, periodStart: pf_start.value, periodEnd: pf_end.value, topicTags: splitTags(pf_tags.value), successCriteria: pf_success.value, estimatedTime: pf_est.value };
    const r = ui.planEditId ? await api('PUT', `/api/plans/${ui.planEditId}/`, body) : await api('POST', '/api/plans/', body);
    if (!r.ok) return fail(r), false;
    ui.planEditId = null; await reload(); return false;
  },
  editPlan(id) { ui.tab = 'plans'; ui.planEditId = id; render(); window.scrollTo(0, 0); },
  async deletePlan(id) { if (!confirm('이 계획을 삭제할까요?')) return; const r = await api('DELETE', `/api/plans/${id}/`); if (!r.ok) fail(r); await reload(); },

  async submitTodo(e) {
    e.preventDefault();
    const body = { title: tf_title.value, planId: tf_plan.value || null, periodStart: tf_start.value || null, dueDate: tf_due.value, tags: splitTags(tf_tags.value), successCriteria: tf_success.value, estimatedTime: tf_est.value };
    const r = ui.todoEditId ? await api('PUT', `/api/todos/${ui.todoEditId}/`, body) : await api('POST', '/api/todos/', body);
    if (!r.ok) return fail(r), false;
    ui.todoEditId = null; await reload(); return false;
  },
  editTodo(id) { ui.tab = 'todos'; ui.todoEditId = id; render(); window.scrollTo(0, 0); },
  async deleteTodo(id) { if (!confirm('이 할 일을 삭제할까요?')) return; const r = await api('DELETE', `/api/todos/${id}/`); if (!r.ok) fail(r); await reload(); },
  async complete(id, btn) { if (btn) btn.disabled = true; const r = await api('POST', `/api/todos/${id}/complete/`); if (!r.ok) fail(r); await reload(); },
  async reopen(id) { const r = await api('POST', `/api/todos/${id}/reopen/`); if (!r.ok) fail(r); await reload(); },
  expand(id) { ui.expandedTodo = ui.expandedTodo === id ? null : id; render(); },
  async submitRecord(e, todoId) {
    e.preventDefault();
    const btn = e.target.querySelector('button[type=submit]'); btn.disabled = true;
    // 요청마다 한 번만 만든 열쇠: 연타·재전송이 와도 서버에는 한 건만 남는다
    const requestId = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random());
    const r = await api('POST', `/api/todos/${todoId}/records/`, { start: document.getElementById('ef_s_' + todoId).value, end: document.getElementById('ef_e_' + todoId).value, blockedReason: document.getElementById('ef_b_' + todoId).value, requestId });
    if (!r.ok) fail(r);
    await reload(); return false;
  },
  async deleteRecord(id) { const r = await api('DELETE', `/api/records/${id}/`); if (!r.ok) fail(r); await reload(); },

  setFilter(k, v) { ui.filter[k] = v; if (k === 'search') ui.refocus = 'ff_search'; render(); },

  setScope(v) { ui.reviewScope = { type: v, value: '' }; ui.reviewJump = null; render(); },
  setScopeValue(v) { ui.reviewScope.value = v; ui.reviewJump = null; render(); },
  jump(label, kind) {
    const tg = reviewTargets();
    const items = { all: tg, done: tg.filter(t => t.status === 'completed'), late: tg.filter(isOverdue), blk: tg.filter(isBlocked) }[kind];
    ui.reviewJump = { label, items }; render();
  },
  closeJump() { ui.reviewJump = null; render(); },
  async submitNote() {
    if (!rv_note.value.trim()) return alert('내용을 입력해 주세요.');
    if (!rv_plan.value) return alert('반영할 계획을 선택해 주세요.');
    const r = await api('POST', `/api/plans/${rv_plan.value}/notes/`, { text: rv_note.value });
    if (!r.ok) return fail(r);
    ui.msg = '고칠 점이 선택한 계획으로 넘어갔습니다.'; ui.tab = 'plans'; await reload();
  },

  async fixExp(e) {
    e.preventDefault();
    const r = await api('POST', '/api/experiment/fix/', { question: ex_q.value, metricName: ex_m.value, unit: ex_u.value, planRule: ex_r.value });
    if (!r.ok) return fail(r), false;
    await reload(); return false;
  },
  async addDay(e) {
    e.preventDefault();
    const r = await api('POST', '/api/experiment/days/', { value: dy_v.value, note: dy_n.value });
    if (!r.ok) return fail(r), false;
    await reload(); return false;
  },
  async ruleChange(e) {
    e.preventDefault();
    const r = await api('POST', '/api/experiment/rule-change/', { reason: rc_reason.value, newRule: rc_rule.value });
    if (!r.ok) return fail(r), false;
    await reload(); return false;
  },

  async importFile() {
    const f = document.getElementById('imp_file').files[0];
    if (!f) return alert('파일을 먼저 골라 주세요.');
    let json;
    try { json = JSON.parse(await f.text()); } catch (e) { return alert('JSON 파일을 읽을 수 없습니다.'); }
    const r = await api('POST', '/api/import/', json);
    if (!r.ok) return fail(r);
    ui.msg = `옮겨 왔습니다: 계획 ${r.data.plans}건, 할 일 ${r.data.todos}건`; ui.tab = 'plans'; await reload();
  },
  async changePw(e) {
    e.preventDefault();
    const r = await api('POST', '/api/account/password/', { oldPassword: pw_old.value, newPassword: pw_new.value });
    if (!r.ok) return fail(r), false;
    ui.msg = '비밀번호를 바꿨습니다. 다른 곳의 로그인은 모두 끊겼습니다.'; pw_old.value = pw_new.value = ''; render(); return false;
  },
  async deleteAccount(e) {
    e.preventDefault();
    if (!confirm('정말 계정과 모든 자료를 영구 삭제할까요?')) return false;
    const r = await api('POST', '/api/account/delete/', { password: del_pw.value });
    if (!r.ok) return fail(r), false;
    location.href = '/'; return false;
  },
};

reload();
