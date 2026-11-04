/*
 * app.js — Giao diện web (SPA thuần JavaScript, không cần build).
 * Mọi nghiệp vụ chạy ở máy chủ Python; tệp này chỉ gọi REST API và hiển thị.
 * Mỗi màn hình ứng với một làn (lane) BPMN: Sinh viên · Khoa · Phòng Đào tạo · Phó phòng.
 */
(function () {
  'use strict';
  const TZ = 'Asia/Ho_Chi_Minh';
  const DAY = 86400000, HOUR = 3600000;
  const ROLE_LABEL = { SV: 'Sinh viên', KHOA: 'Khoa', PDT: 'Phòng Đào tạo', PP: 'Phó phòng' };

  const app = {
    me: null, csrf: null, demo: null, demoMode: true,
    cat: null, svg: null, state: null, detail: null,
  };
  const ui = {
    route: 'home', tab: {}, open: null, dtab: 'overview', zoom: 0.42, pzoom: 0.42, highlight: null,
    verify: '', verifyResult: null, tests: null, confirm: null, filter: '', statusFilter: '',
    importText: { students: '', grades: '', requests: '' }, bulkResult: null, gradeFilter: '', adminGrades: null,
  };

  /* ------------------------------ Tiện ích ------------------------------ */
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = (t) => (t ? new Intl.DateTimeFormat('vi-VN', { timeZone: TZ, day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }).format(t) : '');
  const fmtDay = (t) => new Intl.DateTimeFormat('vi-VN', { timeZone: TZ, day: '2-digit', month: '2-digit', year: 'numeric' }).format(t);
  const dmy = (iso) => (iso ? String(iso).split('-').reverse().join('/') : '');
  const partsOf = (t) => {
    const p = new Intl.DateTimeFormat('vi-VN', { timeZone: TZ, day: '2-digit', month: '2-digit' }).formatToParts(t);
    return { d: p.find((x) => x.type === 'day').value, m: p.find((x) => x.type === 'month').value };
  };
  function dur(ms) {
    const a = Math.abs(ms), d = Math.floor(a / DAY), h = Math.floor((a % DAY) / HOUR), m = Math.floor((a % HOUR) / 60000);
    return d ? `${d} ngày ${h} giờ` : h ? `${h} giờ ${m} phút` : `${m} phút`;
  }
  const num = (x, d) => (typeof x === 'number' ? x.toFixed(d) : '');
  const ST = (k) => (app.cat && app.cat.status[k]) || { label: k, tone: 'info' };
  const stepName = (id) => (app.cat && app.cat.steps[id] ? app.cat.steps[id].name : id);
  const pill = (k) => `<span class="pill ${ST(k).tone}">${esc(ST(k).label)}</span>`;
  const role = () => app.me && app.me.role;
  const reqs = () => (app.state ? app.state.requests : []);
  const nowT = () => (app.state ? app.state.now + (Date.now() - app.stateAt) : Date.now());

  function toast(msg, kind) {
    const el = document.createElement('div');
    el.className = 'toast ' + (kind || '');
    el.textContent = msg;
    $('#toasts').appendChild(el);
    setTimeout(() => el.remove(), kind === 'err' ? 6000 : 3800);
  }

  /* ------------------------------ Gọi API ------------------------------ */
  async function api(method, url, data) {
    const opt = { method, headers: { Accept: 'application/json' }, credentials: 'same-origin' };
    if (method !== 'GET') {
      opt.headers['Content-Type'] = 'application/json';
      opt.headers['X-CSRF-Token'] = app.csrf || '';
      opt.body = JSON.stringify(data || {});
    }
    const res = await fetch(url, opt);
    let body = null;
    try { body = await res.json(); } catch (e) { body = null; }
    if (res.status === 401 && app.me) { app.me = null; render(); }
    if (!res.ok) throw new Error((body && body.error) || `Lỗi máy chủ (${res.status})`);
    return body;
  }
  async function loadState() {
    app.state = await api('GET', '/api/state');
    app.stateAt = Date.now();
    return app.state;
  }
  async function loadDetail() {
    if (!ui.open) { app.detail = null; return; }
    try { app.detail = await api('GET', '/api/requests/' + encodeURIComponent(ui.open)); } catch (e) { toast(e.message, 'err'); ui.open = null; app.detail = null; }
  }
  /** Gọi một thao tác nghiệp vụ, nạp lại dữ liệu và vẽ lại. */
  async function act(method, url, data, okMsg) {
    try {
      const r = await api(method, url, data);
      await loadState();
      await loadDetail();
      const msg = typeof okMsg === 'function' ? okMsg(r) : okMsg;
      if (msg) toast(msg, 'ok');
      if (r && r.fired && r.fired.length) toast(`${r.fired.length} sự kiện thời gian được kích hoạt: ${r.fired.map((f) => `${f.reqId} (${stepName(f.timer)})`).join(', ')}`, 'ok');
      render();
      return r;
    } catch (e) {
      toast(e.message, 'err');
      return null;
    }
  }
  function confirmOnce(key, fn) {
    if (ui.confirm === key) { ui.confirm = null; fn(); } else { ui.confirm = key; render(); setTimeout(() => { if (ui.confirm === key) { ui.confirm = null; render(); } }, 5000); }
  }

  /* ------------------------------ Khung chung ------------------------------ */
  function navItems() {
    const items = [['home', 'Trang chủ']];
    const r = role();
    if (r === 'SV') items.push(['sinh-vien', 'Yêu cầu bảng điểm']);
    if (r === 'KHOA') items.push(['khoa', 'Rà soát điểm']);
    if (r === 'PDT') items.push(['dao-tao', 'Phòng Đào tạo']);
    if (r === 'PP') items.push(['pho-phong', 'Phê duyệt']);
    items.push(['quy-trinh', 'Quy trình BPMN']);
    if (r === 'PDT') items.push(['he-thong', 'Hệ thống & dữ liệu']);
    items.push(['tra-cuu', 'Tra cứu']);
    return items;
  }
  function myQueue() {
    const r = role();
    return reqs().filter((x) => ST(x.status).role === r && !ST(x.status).final);
  }
  function renderChrome() {
    const right = $('#topbar-right');
    if (!app.me) {
      right.innerHTML = '<a class="chip-btn" href="#tra-cuu" style="text-decoration:none">Tra cứu bảng điểm</a>';
      $('#nav').innerHTML = `<a href="#home" class="${ui.route !== 'tra-cuu' ? 'active' : ''}">Đăng nhập</a><a href="#tra-cuu" class="${ui.route === 'tra-cuu' ? 'active' : ''}">Tra cứu</a>`;
      $('#banner').innerHTML = '';
      return;
    }
    const s = app.state;
    const off = s ? s.clockOffset : 0;
    right.innerHTML = `${s && app.demoMode ? `<span class="chip-btn" title="Đồng hồ hệ thống (có thể tua để thử các mốc thời gian)">${fmt(nowT())}${off ? ` · +${Math.round(off / HOUR)} giờ` : ''}</span><button class="chip-btn solid" data-action="advance" data-ms="${DAY}" title="Tua đồng hồ thêm 1 ngày để thử hủy tự động / nhắc việc">+1 ngày</button>` : ''}
      <span class="who">${esc(app.me.full_name)}</span><span class="role">${ROLE_LABEL[app.me.role]}</span><button class="chip-btn" data-action="logout">Đăng xuất</button>`;
    const q = myQueue().length;
    const main = { SV: 'sinh-vien', KHOA: 'khoa', PDT: 'dao-tao', PP: 'pho-phong' }[role()];
    $('#nav').innerHTML = navItems().map(([id, label]) => `<a href="#${id}" class="${ui.route === id ? 'active' : ''}">${esc(label)}${id === main && q ? `<span class="count">${q}</span>` : ''}</a>`).join('');
    $('#banner').innerHTML = s && s.fault ? `<div class="banner-fault"><div class="wrap"><span><b>Đang giả lập sự cố CSDL điểm.</b> Yêu cầu mới sẽ đi vào nhánh "Lỗi truy xuất" của BPMN.</span>${role() === 'PDT' ? '<button class="btn small danger" data-action="fault" data-on="0">Tắt giả lập</button>' : ''}</div></div>` : '';
  }
  function render() {
    renderChrome();
    $('#search-form').style.display = app.me ? '' : 'none';
    let html;
    if (!app.me) html = ui.route === 'tra-cuu' ? viewVerify() : viewLogin();
    else if (!app.state) html = '<div class="empty">Đang tải dữ liệu…</div>';
    else {
      const allowed = navItems().map((x) => x[0]);
      if (!allowed.includes(ui.route)) ui.route = 'home';
      html = (VIEWS[ui.route] || viewHome)();
    }
    $('#view').innerHTML = html;
    renderDrawer();
    mountDiagrams();
  }
  function sidenav(title, acctHtml, page, items) {
    const cur = ui.tab[page] || items[0][0];
    return `<aside class="sidenav"><div class="head">${esc(title)}</div>${acctHtml || ''}<ul>${items.map(([id, label, n, hot]) =>
      `<li><button data-action="tab" data-page="${page}" data-tab="${id}" class="${cur === id ? 'active' : ''}"><span>${esc(label)}</span>${n !== undefined ? `<span class="n ${hot && n ? 'hot' : ''}">${n}</span>` : ''}</button></li>`).join('')}</ul></aside>`;
  }
  function acct(extra) {
    const u = app.me;
    return `<div class="acct"><label>Tài khoản</label><div class="who">${esc(u.full_name)}</div><div class="meta">${ROLE_LABEL[u.role]}${u.department ? ' · ' + esc(u.department) : ''}<br><span class="mono">${esc(u.username)}</span>${extra || ''}</div></div>`;
  }
  function deadlineHtml(r) {
    const d = r.deadline;
    if (d) {
      const left = d.at - nowT();
      return `<span class="${left < DAY / 2 ? 'pill warn' : 'muted'}" style="font-size:12px">${esc(d.label)} sau ${dur(left)}</span>`;
    }
    if (r.status === 'CHO_KHOA' && r.timers && r.timers.khoaReminded) return '<span class="tag orange">Đã nhắc Khoa</span>';
    if (r.status === 'CHO_PHE_DUYET' && r.timers && r.timers.ppReminded) return '<span class="tag orange">Đã nhắc</span>';
    return `<span class="muted" style="font-size:12px">${fmt(r.updatedAt)}</span>`;
  }
  function reqTable(list, opts = {}) {
    if (!list.length) return `<div class="empty">${esc(opts.empty || 'Không có yêu cầu nào.')}</div>`;
    return `<div class="table-wrap"><table class="grid"><thead><tr><th>Mã</th><th>Sinh viên</th><th>Mục đích</th><th>Hình thức</th><th>Trạng thái</th><th>Mốc thời gian</th><th></th></tr></thead><tbody>${
      list.map((r) => { const mine = ST(r.status).role === role(); return `<tr class="click" data-action="open" data-id="${r.id}">
        <td class="mono" style="white-space:nowrap">${r.id}</td>
        <td><b>${esc(r.form.hoTen)}</b><div class="muted mono" style="font-size:12px">${esc(r.form.mssv)}</div></td>
        <td style="min-width:160px">${esc(r.form.mucDich)}</td>
        <td style="white-space:nowrap">Điện tử${r.form.banGiay ? ` + ${r.form.soBan} bản giấy` : ''}<div class="muted" style="font-size:12px">${r.form.ngonNgu === 'en' ? 'Tiếng Anh' : 'Tiếng Việt'}</div></td>
        <td>${pill(r.status)}</td><td>${deadlineHtml(r)}</td>
        <td><button class="btn small ${mine ? 'primary' : ''}" data-action="open" data-id="${r.id}">${mine ? 'Xử lý' : 'Xem'}</button></td></tr>`; }).join('')}</tbody></table></div>`;
  }
  const sortNew = (a, b) => b.updatedAt - a.updatedAt;
  const sortOld = (a, b) => a.updatedAt - b.updatedAt;
  function mailHtml(m) {
    return `<details class="mail"><summary><span class="subj">${esc(m.subject)}</span><span class="muted num" style="font-size:12px">${fmt(m.t)}</span><span class="to">Đến: ${esc(m.to)}${m.reqId ? ` · ${m.reqId}` : ''} · bước "${esc(stepName(m.step))}"${m.delivery && m.delivery !== 'outbox' ? ` · ${esc(m.delivery)}` : ''}</span></summary><pre>${esc(m.body)}</pre></details>`;
  }

  /* ------------------------------ Đăng nhập ------------------------------ */
  function viewLogin() {
    const d = app.demo;
    const groups = d ? ['SV', 'KHOA', 'PDT', 'PP'].map((r) => [r, d.accounts.filter((a) => a.role === r)]) : [];
    return `<div class="login">
      <section class="card">
        <h1>Đăng nhập</h1>
        <p class="muted" style="margin:0">Sinh viên đăng nhập bằng họ và tên, mật khẩu là MSSV. Cán bộ Khoa, Phòng Đào tạo, Phó phòng dùng tài khoản được cấp. Hệ thống phân quyền đúng 4 làn của BPMN.</p>
        <form class="stack" data-form="login" style="gap:12px">
          <div class="field"><label for="lg-u">Tên đăng nhập (SV: Họ và tên)</label><input id="lg-u" name="username" autocomplete="username" required></div>
          <div class="field"><label for="lg-p">Mật khẩu</label><input id="lg-p" name="password" type="password" autocomplete="current-password" required></div>
          <div class="btns"><button class="btn primary" type="submit">Đăng nhập</button><a href="#tra-cuu">Tra cứu bảng điểm bằng mã xác thực</a></div>
        </form>
      </section>
      ${d ? `<section class="panel"><div class="title">Tài khoản demo <span class="sub">Sinh viên: tên đăng nhập là họ và tên, mật khẩu là MSSV · Cán bộ: <b class="mono">${esc(d.password)}</b></span></div>
        <p style="margin-top:0;font-size:13px">Bấm vào một tài khoản để đăng nhập nhanh. Mỗi sinh viên mẫu đi qua một nhánh khác nhau của quy trình.</p>
        ${groups.map(([r, list]) => `<div class="acc-group"><h4>${ROLE_LABEL[r]}</h4><div class="acc-list">${list.map((a) => `<button class="acc" data-action="quick-login" data-u="${esc(a.username)}"><b>${esc(a.name)}</b><span>${a.role === 'SV' ? `MSSV: ${esc(a.mssv)}` : esc(a.username)}</span></button>`).join('')}</div></div>`).join('')}
      </section>` : ''}
    </div>`;
  }

  /* ------------------------------ Trang chủ ------------------------------ */
  function viewHome() {
    const s = app.state, list = reqs();
    const c = {};
    for (const r of list) c[r.status] = (c[r.status] || 0) + 1;
    const n = (...ks) => ks.reduce((a, k) => a + (c[k] || 0), 0);
    const lanes = [
      ['Sinh viên', 'Gửi, bổ sung, hủy yêu cầu', n('CHO_BO_SUNG')],
      ['Khoa', 'Rà soát & hiệu chỉnh điểm', n('CHO_KHOA')],
      ['Phòng Đào tạo', 'Kiểm tra, chỉnh sửa, in, giao', n('CHO_KIEM_TRA', 'CHO_CHINH_SUA', 'CHO_IN', 'CHO_XAC_NHAN_GIAY')],
      ['Phó phòng', 'Phê duyệt, ký số, đóng dấu', n('CHO_PHE_DUYET', 'CHO_DONG_DAU')],
    ];
    const mails = s.outbox.slice().sort((a, b) => b.t - a.t).slice(0, 6);
    const events = [];
    for (const r of list) for (const h of r.history) if (h.note && h.kind !== 'gateway') events.push({ ...h, req: r });
    events.sort((a, b) => b.t - a.t);
    const st = s.stats;
    const main = { SV: 'sinh-vien', KHOA: 'khoa', PDT: 'dao-tao', PP: 'pho-phong' }[role()];
    const q = myQueue().length;
    return `<div class="stack">
      <section class="hero">
        <div class="copy">
          <div class="eyebrow">Xin chào, ${esc(app.me.full_name)} · ${ROLE_LABEL[role()]}</div>
          <h1>${role() === 'SV' ? 'Xin bảng điểm trực tuyến, theo dõi từng bước xét duyệt' : q ? `Bạn có ${q} việc đang chờ xử lý` : 'Không có việc nào đang chờ bạn'}</h1>
          <p>Sinh viên đăng nhập SSO và gửi yêu cầu. Hệ thống tự xác thực thông tin, truy xuất và đối chiếu điểm, rồi tạo bảng điểm điện tử. Khoa chỉ xử lý khi điểm có vấn đề, Phó phòng phê duyệt và ký số trước khi bảng điểm được gửi qua email hoặc in bản giấy.</p>
          <div class="btns">
            <a class="btn primary" href="#${main}" ${role() === 'SV' ? 'data-action="goto" data-to="sinh-vien" data-tab="new"' : ''}>${role() === 'SV' ? 'Tạo yêu cầu bảng điểm' : 'Mở hàng đợi công việc'}</a>
            <a class="btn" href="#quy-trinh">Xem sơ đồ quy trình</a>
          </div>
        </div>
        <div class="flow">
          <h3>${role() === 'SV' ? 'Yêu cầu của bạn đang chờ ở' : 'Việc đang chờ theo làn'}</h3>
          ${lanes.map(([name, desc, k]) => `<div class="lane-row"><span class="lname">${name}</span><span class="ldesc">${desc}</span><b>${k}</b></div>`).join('')}
        </div>
      </section>
      ${st ? `<section class="stats">
        <div class="stat"><span class="v">${st.total}</span><span class="k">Yêu cầu đã tiếp nhận</span></div>
        <div class="stat"><span class="v">${st.issued}</span><span class="k">Bảng điểm đã cấp</span></div>
        <div class="stat"><span class="v">${st.avgLeadH === null ? '—' : st.avgLeadH + ' giờ'}</span><span class="k">Thời gian xử lý TB (gửi → hoàn tất)</span></div>
        <div class="stat"><span class="v">${st.total ? Math.round((st.autoPass / st.total) * 100) : 0}%</span><span class="k">Qua đối chiếu tự động, không cần Khoa</span></div>
      </section>` : ''}
      <div class="cols-2">
        <section class="panel">
          <div class="title">Thông báo mới <span class="sub">${s.smtp ? 'Gửi qua SMTP + lưu hộp thư' : 'Hộp thư hệ thống'}</span></div>
          ${mails.length ? `<ul class="notify">${mails.map((m) => { const p = partsOf(m.t); return `<li><div class="date-box"><div class="m">Th ${p.m}</div><div class="d">${p.d}</div></div><div><div class="t">${m.step === 't_guidt' ? '<span class="tag new">Mới</span> ' : m.toRole !== 'SV' ? '<span class="tag blue">Nhắc việc</span> ' : ''}${esc(m.subject)}</div><div class="s">Gửi ${esc(m.to)} · ${fmt(m.t)}</div></div></li>`; }).join('')}</ul>` : '<div class="empty">Chưa có email nào.</div>'}
        </section>
        <section class="panel">
          <div class="title">Hoạt động gần đây</div>
          ${events.length ? `<ul class="timeline">${events.slice(0, 7).map((h) => `<li><span class="when">${fmt(h.t)}</span><span class="dot ${h.kind}"></span><div><div class="what"><a href="#" data-action="open" data-id="${h.req.id}">${h.req.id}</a> · ${esc(stepName(h.step))}</div><div class="note">${esc(h.note)}</div></div></li>`).join('')}</ul>` : '<div class="empty">Chưa có hoạt động.</div>'}
        </section>
      </div>
    </div>`;
  }

  /* ------------------------------ Sinh viên ------------------------------ */
  function viewSV() {
    const st = app.state.students[0];
    if (!st) return '<div class="empty">Tài khoản chưa gắn với hồ sơ trong CSDL sinh viên. Liên hệ Phòng Đào tạo.</div>';
    const mine = reqs().slice().sort(sortNew);
    const inbox = app.state.outbox.slice().sort((a, b) => b.t - a.t);
    const waiting = mine.filter((r) => r.status === 'CHO_BO_SUNG').length;
    if (!ui.tab['sinh-vien']) ui.tab['sinh-vien'] = mine.length ? 'list' : 'new';
    const tab = ui.tab['sinh-vien'];
    let main;
    if (tab === 'new') main = svForm(st, mine);
    else if (tab === 'inbox') main = `<section class="panel"><div class="title">Hộp thư <span class="sub">${esc(st.email)}</span></div>${inbox.length ? inbox.map(mailHtml).join('') : '<div class="empty">Chưa có email nào.</div>'}</section>`;
    else main = `<section class="panel"><div class="title">Yêu cầu của tôi <span class="sub"><button class="btn small primary" data-action="tab" data-page="sinh-vien" data-tab="new">+ Tạo yêu cầu</button></span></div>
        ${waiting ? `<div class="callout warn" style="margin-bottom:12px">Bạn có ${waiting} yêu cầu cần bổ sung thông tin. Quá ${app.state.config.supplementDays} ngày không bổ sung, yêu cầu sẽ tự hủy.</div>` : ''}
        ${reqTable(mine, { empty: 'Bạn chưa gửi yêu cầu nào.' })}</section>`;
    const extra = `<br>${esc(st.lop)} · ${esc(st.nganh)}<br>${esc(st.email)}`;
    return `<div class="page">${sidenav('Sinh viên', acct(extra), 'sinh-vien', [['new', 'Tạo yêu cầu bảng điểm'], ['list', 'Yêu cầu của tôi', mine.length, false], ['inbox', 'Hộp thư', inbox.length]])}<div class="stack">${main}</div></div>`;
  }
  function svForm(st, mine) {
    const open = mine.filter((r) => !ST(r.status).final);
    return `<section class="panel">
      <div class="title">Tạo yêu cầu cấp bảng điểm <span class="sub">Bước "Đăng nhập SSO & điền yêu cầu"</span></div>
      ${open.length ? `<div class="callout info" style="margin-bottom:12px">Bạn đang có ${open.length} yêu cầu chưa hoàn tất (${open.map((r) => r.id).join(', ')}).</div>` : ''}
      <p class="muted" style="margin-top:0">Thông tin được điền sẵn từ tài khoản SSO. Nếu cần, bạn có thể sửa; hệ thống đối chiếu với CSDL sinh viên ngay khi gửi.</p>
      <form class="form" data-form="sv-new">
        <div class="field"><label>MSSV (từ SSO)</label><input value="${esc(st.mssv)}" disabled></div>
        <div class="field"><label for="f-hoTen">Họ và tên</label><input id="f-hoTen" name="hoTen" value="${esc(st.hoTen)}" required></div>
        <div class="field"><label for="f-ngaySinh">Ngày sinh</label><input id="f-ngaySinh" name="ngaySinh" type="date" value="${esc(st.ngaySinh)}" required></div>
        <div class="field"><label for="f-email">Email nhận bảng điểm</label><input id="f-email" name="email" type="email" value="${esc(st.email)}" required></div>
        <div class="field"><label for="f-sdt">Số điện thoại</label><input id="f-sdt" name="sdt" inputmode="tel" placeholder="0xxxxxxxxx" required></div>
        <div class="field"><label for="f-ngonNgu">Ngôn ngữ bảng điểm</label><select id="f-ngonNgu" name="ngonNgu"><option value="vi">Tiếng Việt</option><option value="en">Tiếng Anh</option></select></div>
        <div class="field full"><label for="f-mucDich">Mục đích sử dụng</label><input id="f-mucDich" name="mucDich" list="purposes" placeholder="Ví dụ: Nộp hồ sơ học bổng" required>
          <datalist id="purposes"><option value="Nộp hồ sơ học bổng"><option value="Nộp hồ sơ thực tập tại doanh nghiệp"><option value="Hồ sơ du học"><option value="Hồ sơ xin việc"><option value="Chuyển trường"></datalist></div>
        <div class="field full"><label>Hình thức nhận</label>
          <div class="check"><input type="checkbox" checked disabled id="f-dt"><label for="f-dt" style="font-weight:400">Bản điện tử ký số (luôn gửi qua email)</label></div>
          <div class="check"><input type="checkbox" name="banGiay" id="f-banGiay"><label for="f-banGiay" style="font-weight:400">Thêm bản giấy có dấu đỏ, số bản:</label><input name="soBan" id="f-soBan" type="number" min="1" max="${app.state.config.maxCopies}" value="1" style="width:70px;padding:4px 6px;border:1px solid var(--line);border-radius:3px;background:var(--surface)"></div>
        </div>
        <div class="field full"><label for="f-ghiChu">Ghi chú (không bắt buộc)</label><textarea id="f-ghiChu" name="ghiChu" placeholder="Ví dụ: nhận bản giấy tại Phòng Đào tạo"></textarea></div>
        <div class="full btns"><button class="btn primary" type="submit">Gửi yêu cầu</button><span class="muted" style="font-size:12.5px">Sau khi gửi, bạn theo dõi tiến trình trên sơ đồ BPMN.</span></div>
      </form></section>`;
  }

  /* ------------------------------ Khoa ------------------------------ */
  function viewKhoa() {
    const list = reqs();
    const waiting = list.filter((r) => r.status === 'CHO_KHOA').sort(sortOld);
    const handled = list.filter((r) => r.status !== 'CHO_KHOA' && r.history.some((h) => h.step === 't_khoa' || h.step === 'g_kh')).sort(sortNew);
    const inbox = app.state.outbox.slice().sort((a, b) => b.t - a.t);
    const tab = ui.tab.khoa || 'cho';
    const body = tab === 'cho'
      ? `<section class="panel"><div class="title">Chờ rà soát & hiệu chỉnh điểm <span class="sub">Tự động nhắc sau ${app.state.config.khoaRemindDays} ngày</span></div>${reqTable(waiting, { empty: 'Không có yêu cầu nào cần Khoa rà soát.' })}</section>`
      : tab === 'xong' ? `<section class="panel"><div class="title">Đã xử lý</div>${reqTable(handled, { empty: 'Chưa có yêu cầu nào.' })}</section>`
        : tab === 'all' ? `<section class="panel"><div class="title">Tất cả yêu cầu của SV thuộc Khoa</div>${reqTable(list.slice().sort(sortNew))}</section>`
          : `<section class="panel"><div class="title">Hộp thư văn phòng Khoa</div>${inbox.length ? inbox.map(mailHtml).join('') : '<div class="empty">Chưa có email nhắc việc.</div>'}</section>`;
    return `<div class="page">${sidenav('Khoa', acct('<br>Chỉ thấy yêu cầu của SV thuộc Khoa.'), 'khoa', [['cho', 'Chờ rà soát', waiting.length, true], ['xong', 'Đã xử lý', handled.length], ['all', 'Tất cả', list.length], ['mail', 'Hộp thư nhắc việc', inbox.length]])}<div class="stack">${body}</div></div>`;
  }

  /* ------------------------------ Phòng Đào tạo ------------------------------ */
  function viewPDT() {
    const list = reqs();
    const by = (s) => list.filter((r) => r.status === s).sort(sortOld);
    const items = [
      ['kiem-tra', 'Chờ kiểm tra bảng điểm', by('CHO_KIEM_TRA').length, true],
      ['chinh-sua', 'Chờ chỉnh sửa theo góp ý', by('CHO_CHINH_SUA').length, true],
      ['in', 'Chờ in bản giấy', by('CHO_IN').length, true],
      ['giao', 'Chờ xác nhận cấp bản giấy', by('CHO_XAC_NHAN_GIAY').length, true],
      ['tat-ca', 'Tất cả yêu cầu', list.length],
      ['so', 'Sổ cấp phát', app.state.issuance.length],
    ];
    const tab = ui.tab['dao-tao'] || 'kiem-tra';
    const map = { 'kiem-tra': 'CHO_KIEM_TRA', 'chinh-sua': 'CHO_CHINH_SUA', in: 'CHO_IN', giao: 'CHO_XAC_NHAN_GIAY' };
    let body;
    if (map[tab]) {
      body = `<section class="panel"><div class="title">${esc(items.find((i) => i[0] === tab)[1])}</div>${reqTable(by(map[tab]), { empty: 'Không có việc nào trong hàng đợi này.' })}</section>`;
    } else if (tab === 'so') {
      const iss = app.state.issuance;
      body = `<section class="panel"><div class="title">Sổ cấp phát bảng điểm <span class="sub"><a class="btn small" href="/api/admin/export/issuance.csv">Xuất CSV</a></span></div>${iss.length ? `<div class="table-wrap"><table class="grid"><thead><tr><th>Thời điểm</th><th>Mã YC</th><th>Sinh viên</th><th>Mã xác thực</th><th class="r">Bản giấy</th><th>Mục đích</th><th>Người duyệt</th><th class="r">Thời gian xử lý</th></tr></thead><tbody>${iss.slice().reverse().map((x) => `<tr class="click" data-action="open" data-id="${x.reqId}"><td class="num">${fmt(x.t)}</td><td class="mono">${x.reqId}</td><td>${esc(x.hoTen)}<div class="muted mono" style="font-size:12px">${x.mssv}</div></td><td class="mono">${x.code}</td><td class="r num">${x.soBanGiay}</td><td>${esc(x.mucDich)}</td><td>${esc(x.approvedBy)}</td><td class="r num">${x.leadTimeH} giờ</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">Chưa cấp bảng điểm nào.</div>'}</section>`;
    } else {
      const q = ui.filter.trim().toLowerCase();
      const strip = (s) => String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/đ/g, 'd').toLowerCase();
      const fl = list.filter((r) => (!ui.statusFilter || r.status === ui.statusFilter) && (!q || r.id.toLowerCase().includes(q) || r.form.mssv.includes(q) || strip(r.form.hoTen).includes(strip(q)))).sort(sortNew);
      body = `<section class="panel"><div class="title">Tất cả yêu cầu</div>
        <form class="btns" data-form="filter" style="margin-bottom:12px">
          <input name="q" value="${esc(ui.filter)}" aria-label="Lọc" placeholder="Mã yêu cầu, MSSV hoặc họ tên" style="padding:7px 10px;border:1px solid var(--line);border-radius:4px;background:var(--surface);min-width:0;flex:1 1 220px">
          <select name="st" aria-label="Trạng thái" style="padding:7px 10px;border:1px solid var(--line);border-radius:4px;background:var(--surface)"><option value="">Mọi trạng thái</option>${Object.entries(app.cat.status).map(([k, s]) => `<option value="${k}" ${ui.statusFilter === k ? 'selected' : ''}>${esc(s.label)}</option>`).join('')}</select>
          <button class="btn" type="submit">Lọc</button></form>
        ${reqTable(fl, { empty: 'Không có yêu cầu phù hợp.' })}</section>`;
    }
    return `<div class="page">${sidenav('Phòng Đào tạo', acct(), 'dao-tao', items)}<div class="stack">${body}</div></div>`;
  }

  /* ------------------------------ Phó phòng ------------------------------ */
  function viewPP() {
    const list = reqs();
    const by = (s) => list.filter((r) => r.status === s).sort(sortOld);
    const signed = list.filter((r) => r.signature).sort(sortNew);
    const rejected = list.filter((r) => r.status === 'PP_TU_CHOI').sort(sortNew);
    const tab = ui.tab['pho-phong'] || 'duyet';
    const body = {
      duyet: `<section class="panel"><div class="title">Chờ xem xét & phê duyệt <span class="sub">Tự động nhắc sau ${app.state.config.ppRemindDays} ngày</span></div>${reqTable(by('CHO_PHE_DUYET'), { empty: 'Không có bảng điểm chờ duyệt.' })}</section>`,
      dau: `<section class="panel"><div class="title">Chờ ký tên, đóng dấu đỏ bản giấy</div>${reqTable(by('CHO_DONG_DAU'), { empty: 'Không có bản giấy chờ đóng dấu.' })}</section>`,
      da: `<section class="panel"><div class="title">Đã phê duyệt & ký số</div>${reqTable(signed)}</section>`,
      tc: `<section class="panel"><div class="title">Đã từ chối</div>${reqTable(rejected, { empty: 'Chưa từ chối yêu cầu nào.' })}</section>`,
    }[tab];
    const extra = `<br>Khóa ký số: <span class="mono">${esc(app.state.signer.keyId)}</span>`;
    return `<div class="page">${sidenav('Phó phòng', acct(extra), 'pho-phong', [['duyet', 'Chờ phê duyệt', by('CHO_PHE_DUYET').length, true], ['dau', 'Chờ đóng dấu', by('CHO_DONG_DAU').length, true], ['da', 'Đã phê duyệt', signed.length], ['tc', 'Đã từ chối', rejected.length]])}<div class="stack">${body}</div></div>`;
  }

  /* ------------------------------ Quy trình ------------------------------ */
  const UI_MAP = [
    ['s_task', 'Màn hình "Tạo yêu cầu" (SV, SSO điền sẵn)', 'POST /api/requests'],
    ['ca_xt', 'Tự động: luật X1–X8, so khớp họ tên theo ngưỡng', 'engine.validate_form'],
    ['g_hl', 'Hợp lệ khi đạt cả 8 luật', 'engine.run_validation'],
    ['Activity_0ze94gf', 'Email tự động liệt kê lỗi', 'mailer'],
    ['s_bs_task', 'Chi tiết yêu cầu › Bổ sung (SV)', 'POST /api/requests/{id}/supplement'],
    ['e_t3', 'Timer 3 ngày: tự hủy + email (thử bằng "+1 ngày")', 'engine.tick'],
    ['t_truyxuat', 'Tự động truy xuất điểm theo từng học kỳ', 'engine.retrieve_grades'],
    ['Boundary_LoiTruyXuat', 'Sự cố CSDL điểm → ghi log, email SV thử lại sau', 'engine.retrieval_failed'],
    ['t_doichieu', 'Luật D0–D7 + phát hiện điểm bất thường, chấm độ tin cậy', 'engine.check_grades'],
    ['g_diem', 'Đi tiếp khi 0 lỗi và độ tin cậy ≥ ngưỡng', 'engine.reconcile'],
    ['t_khoa', 'Màn hình Khoa: sửa điểm, xóa dòng trùng, xác nhận bất thường', 'POST /api/requests/{id}/grades/{gid}'],
    ['g_kh', 'Khoa chọn "Đã hiệu chỉnh" hoặc "Từ chối cấp"', 'POST /api/requests/{id}/khoa-decision'],
    ['b_khoa', 'Timer 2 ngày: email nhắc Khoa (không ngắt)', 'engine.tick'],
    ['t_tao', 'Tự động tạo bảng điểm, tính GPA hệ 4 và 10', 'engine.create_transcript'],
    ['g_dat', 'PĐT: Đạt / Chưa đạt + góp ý', 'POST /api/requests/{id}/qc'],
    ['t_chinh', 'PĐT: chỉnh ngôn ngữ, ghi chú, học kỳ, người ký', 'POST /api/requests/{id}/edit'],
    ['t_pd', 'Màn hình ký duyệt của Phó phòng', 'GET /api/requests/{id}'],
    ['g_pd', 'Phê duyệt / Yêu cầu chỉnh sửa / Từ chối', 'POST /api/requests/{id}/pp-decision'],
    ['b_pp', 'Timer 1 ngày: email nhắc Phó phòng (không ngắt)', 'engine.tick'],
    ['t_dongdau', 'Tự động ký số RSA-PSS, cấp mã xác thực, lưu kho', 'signing.Signer.sign'],
    ['Gateway_0m52u6m', 'Cổng bao hàm: email luôn gửi, bản giấy nếu SV chọn', 'engine.sign_and_dispatch'],
    ['t_in', 'PĐT › Chờ in', 'POST /api/requests/{id}/print'],
    ['Activity_0xvx345', 'Phó phòng › Chờ đóng dấu', 'POST /api/requests/{id}/stamp'],
    ['Activity_15aejsy', 'PĐT › Xác nhận đã giao', 'POST /api/requests/{id}/deliver'],
    ['t_nhatky', 'Tự động ghi Sổ cấp phát khi đủ các nhánh', 'engine.join_and_finish'],
    ['EventSub_SVChuDongHuy', 'SV bấm "Hủy yêu cầu" (trước khi ký số)', 'POST /api/requests/{id}/cancel'],
  ];
  function viewProcess() {
    const per = {};
    for (const r of reqs()) { const s = ST(r.status); if (!s.final) per[s.step] = (per[s.step] || 0) + 1; }
    return `<div class="stack">
      <section class="panel"><div class="title">Sơ đồ BPMN to-be (bản đã sửa) <span class="sub">Số trên mỗi bước = số yêu cầu đang chờ tại đó</span></div>
        ${diagramBlock('proc', null)}
      </section>
      <section class="panel"><div class="title">Ánh xạ BPMN → chức năng hệ thống</div>
        <p style="margin-top:0;font-size:13px">User task → màn hình; service/send task → API hoặc hàm tự động; cổng XOR → điều kiện duyệt; làn → quyền truy cập. Bấm một dòng để tô sáng phần tử trên sơ đồ.</p>
        <div class="table-wrap"><table class="grid"><thead><tr><th>Phần tử BPMN</th><th>Làn (quyền)</th><th>Loại</th><th>Thực hiện trong ứng dụng</th><th>API / hàm</th><th class="r">Đang chờ</th></tr></thead><tbody>
        ${UI_MAP.map(([id, how, apiName]) => { const s = app.cat.steps[id]; return `<tr class="click" data-action="hl" data-step="${id}"><td><b>${esc(s.name)}</b><div class="muted mono" style="font-size:11.5px">${id}</div></td><td>${esc(app.cat.lanes[s.lane])}</td><td>${esc(app.cat.typeLabel[s.type] || s.type)}</td><td>${esc(how)}</td><td class="mono" style="font-size:12px">${esc(apiName)}</td><td class="r num">${per[id] || ''}</td></tr>`; }).join('')}
        </tbody></table></div></section></div>`;
  }
  function diagramBlock(key, req) {
    const z = key === 'proc' ? ui.pzoom : ui.zoom;
    return `<div class="diagram-tools"><div class="btns"><button class="btn small" data-action="zoom" data-key="${key}" data-d="-0.1" aria-label="Thu nhỏ">−</button><span class="num">${Math.round(z * 100)}%</span><button class="btn small" data-action="zoom" data-key="${key}" data-d="0.1" aria-label="Phóng to">+</button></div>
      <div class="legend">${req ? '<span><i class="l-cur"></i>Đang ở bước này / kết thúc tại đây</span><span><i class="l-done"></i>Đã đi qua</span>' : '<span><i class="l-cur"></i>Có yêu cầu đang chờ</span>'}</div></div>
      <div class="diagram" data-diagram="${key}" ${req ? `data-req="${req.id}"` : ''}></div>`;
  }
  function mountDiagrams() {
    document.querySelectorAll('[data-diagram]').forEach((host) => {
      if (!app.svg) { host.innerHTML = '<div class="empty">Không tải được sơ đồ.</div>'; return; }
      host.innerHTML = app.svg;
      const svg = host.querySelector('svg');
      const z = host.dataset.diagram === 'proc' ? ui.pzoom : ui.zoom;
      const w = Number(svg.getAttribute('width')) || 3585, h = Number(svg.getAttribute('height')) || 1160;
      svg.setAttribute('width', Math.round(w * z));
      svg.setAttribute('height', Math.round(h * z));
      const el = (id) => svg.querySelector(`[data-element-id="${id}"]`);
      if (host.dataset.req) {
        const req = app.detail && app.detail.request;
        if (!req) return;
        const steps = req.history.map((x) => x.step);
        for (const s of new Set(steps)) { const g = el(s); if (g) g.classList.add('is-done'); }
        for (let i = 1; i < steps.length; i++) {
          const f = app.cat.flows.find((x) => x.s === steps[i - 1] && x.t === steps[i]);
          if (f) { const g = el(f.id); if (g) g.classList.add('is-done'); }
        }
        const cur = el(ST(req.status).step);
        if (cur) { cur.classList.remove('is-done'); cur.classList.add('is-current'); requestAnimationFrame(() => scrollToEl(host, cur)); }
      } else {
        const per = {};
        for (const r of reqs()) { const s = ST(r.status); if (!s.final) per[s.step] = (per[s.step] || 0) + 1; }
        for (const [step, n] of Object.entries(per)) { const g = el(step); if (g) { g.classList.add('is-current'); badge(svg, g, n); } }
        if (ui.highlight) { const g = el(ui.highlight); if (g) { g.classList.add('hover-step'); requestAnimationFrame(() => scrollToEl(host, g)); } }
      }
    });
  }
  function badge(svg, g, n) {
    try {
      const bb = g.getBBox();
      const m = g.transform.baseVal.consolidate();
      const x = (m ? m.matrix.e : 0) + bb.x + bb.width, y = (m ? m.matrix.f : 0) + bb.y;
      const NS = 'http://www.w3.org/2000/svg';
      const gg = document.createElementNS(NS, 'g');
      const c = document.createElementNS(NS, 'circle');
      c.setAttribute('cx', x); c.setAttribute('cy', y); c.setAttribute('r', 13);
      c.setAttribute('fill', '#0867b0'); c.setAttribute('stroke', '#fff'); c.setAttribute('stroke-width', 2);
      const t = document.createElementNS(NS, 'text');
      t.setAttribute('x', x); t.setAttribute('y', y + 5); t.setAttribute('text-anchor', 'middle');
      t.setAttribute('font-size', 14); t.setAttribute('font-weight', 700); t.setAttribute('fill', '#fff'); t.setAttribute('font-family', 'Arial');
      t.textContent = n;
      gg.appendChild(c); gg.appendChild(t); svg.appendChild(gg);
    } catch (e) { /* sơ đồ chưa hiển thị */ }
  }
  function scrollToEl(host, g) {
    try {
      const hr = host.getBoundingClientRect(), gr = g.getBoundingClientRect();
      host.scrollLeft += gr.left - hr.left - hr.width / 2 + gr.width / 2;
      host.scrollTop += gr.top - hr.top - hr.height / 2 + gr.height / 2;
    } catch (e) { /* bỏ qua */ }
  }

  /* ------------------------------ Hệ thống (PĐT) ------------------------------ */
  function viewSystem() {
    const s = app.state;
    const tab = ui.tab['he-thong'] || 'clock';
    const items = [
      ['clock', 'Đồng hồ & sự cố'], ['config', 'Cấu hình ngưỡng'], ['students', 'CSDL sinh viên', s.students.length],
      ['grades', 'CSDL điểm'], ['bulk', 'Nhập yêu cầu hàng loạt'], ['mail', 'Hộp thư hệ thống', s.outbox.length],
      ['logs', 'Nhật ký hệ thống', s.logs.length], ['tests', 'Kiểm thử tự động'], ['reset', 'Khôi phục dữ liệu'],
    ];
    return `<div class="page">${sidenav('Hệ thống & dữ liệu', acct(), 'he-thong', items)}<div class="stack">${(SYS[tab] || SYS.clock)()}</div></div>`;
  }
  const SYS = {
    clock() {
      const s = app.state;
      const pend = reqs().filter((r) => r.deadline).sort((a, b) => a.deadline.at - b.deadline.at);
      return `<section class="panel"><div class="title">Đồng hồ mô phỏng</div>
        <p style="margin-top:0">Ba sự kiện thời gian của BPMN (hủy sau 3 ngày, nhắc Khoa sau 2 ngày, nhắc Phó phòng sau 1 ngày) chạy theo đồng hồ máy chủ. Tua đồng hồ để kiểm tra mà không phải chờ thật.</p>
        <dl class="kv"><dt>Giờ thực</dt><dd class="num">${fmt(Date.now())}</dd><dt>Giờ hệ thống</dt><dd class="num">${fmt(nowT())}</dd><dt>Độ lệch</dt><dd>${dur(s.clockOffset || 0)}</dd></dl>
        <div class="btns" style="margin-top:12px"><button class="btn" data-action="advance" data-ms="${HOUR}">+1 giờ</button><button class="btn" data-action="advance" data-ms="${6 * HOUR}">+6 giờ</button><button class="btn primary" data-action="advance" data-ms="${DAY}">+1 ngày</button><button class="btn" data-action="advance" data-ms="${3 * DAY}">+3 ngày</button><button class="btn" data-action="reset-clock">Về giờ thực</button></div>
      </section>
      <section class="panel"><div class="title">Giả lập sự cố CSDL điểm <span class="sub">Nhánh "Lỗi truy xuất" của BPMN</span></div>
        <p style="margin-top:0">Khi bật, bước "Truy xuất điểm theo từng học kỳ" của mọi yêu cầu mới sẽ gặp lỗi: hệ thống ghi nhận sự cố, gửi email đề nghị sinh viên thử lại sau và kết thúc tại "Dừng do lỗi hệ thống".</p>
        <div class="btns">${s.fault ? '<button class="btn danger" data-action="fault" data-on="0">Tắt giả lập sự cố</button><span class="pill bad">Đang bật</span>' : '<button class="btn" data-action="fault" data-on="1">Bật giả lập sự cố</button><span class="pill ok">Hoạt động bình thường</span>'}</div>
      </section>
      <section class="panel"><div class="title">Mốc thời gian sắp tới</div>${pend.length ? `<div class="table-wrap"><table class="grid"><thead><tr><th>Yêu cầu</th><th>Trạng thái</th><th>Sự kiện</th><th>Đến hạn</th><th>Còn lại</th></tr></thead><tbody>${pend.map((r) => `<tr class="click" data-action="open" data-id="${r.id}"><td class="mono" style="white-space:nowrap">${r.id}</td><td>${pill(r.status)}</td><td>${esc(r.deadline.label)}</td><td class="num">${fmt(r.deadline.at)}</td><td>${dur(r.deadline.at - nowT())}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">Không có mốc nào đang chạy.</div>'}</section>`;
    },
    config() {
      const c = app.state.config;
      const f = (id, label, val, hint, attrs) => `<div class="field"><label for="cfg-${id}">${label}</label><input id="cfg-${id}" name="${id}" value="${esc(val)}" ${attrs || ''}>${hint ? `<span class="hint">${hint}</span>` : ''}</div>`;
      return `<section class="panel"><div class="title">Cấu hình ngưỡng & tham số quy trình</div>
        <form class="form" data-form="config">
          ${f('nameSimilarityThreshold', 'Ngưỡng khớp họ tên (0–1)', c.nameSimilarityThreshold, 'Bước "Xác thực & kiểm tra thông tin SV".', 'type="number" step="0.01" min="0.5" max="1"')}
          ${f('confidenceThreshold', 'Ngưỡng độ tin cậy đối chiếu điểm (0–1)', c.confidenceThreshold, 'Cổng "Điểm đầy đủ, chính xác?". Thấp hơn → chuyển Khoa.', 'type="number" step="0.01" min="0" max="1"')}
          ${f('warningPenalty', 'Mức trừ cho mỗi điểm bất thường', c.warningPenalty, 'Mỗi lỗi chắc chắn trừ ' + c.errorPenalty + '.', 'type="number" step="0.01" min="0" max="1"')}
          ${f('outlierGap', 'Độ lệch coi là bất thường (điểm)', c.outlierGap, 'So với điểm trung bình của chính sinh viên.', 'type="number" step="0.1" min="1" max="10"')}
          ${f('supplementDays', 'Hạn bổ sung (ngày)', c.supplementDays, 'Timer "Quá 3 ngày"', 'type="number" min="1" max="30"')}
          ${f('khoaRemindDays', 'Nhắc Khoa sau (ngày)', c.khoaRemindDays, 'Timer "Sau 2 ngày"', 'type="number" min="1" max="30"')}
          ${f('ppRemindDays', 'Nhắc Phó phòng sau (ngày)', c.ppRemindDays, 'Timer "Sau 1 ngày"', 'type="number" min="1" max="30"')}
          ${f('maxCopies', 'Số bản giấy tối đa', c.maxCopies, '', 'type="number" min="1" max="50"')}
          ${f('signerName', 'Người ký mặc định (Phó phòng)', c.signerName)}
          ${f('emailDomain', 'Tên miền email sinh viên', c.emailDomain)}
          <div class="full btns"><button class="btn primary" type="submit">Lưu cấu hình</button></div>
        </form></section>
        <section class="panel"><div class="title">Thang quy đổi điểm</div><div class="table-wrap"><table class="grid"><thead><tr><th>Điểm chữ</th><th class="r">Từ điểm (hệ 10)</th><th class="r">Hệ 4</th></tr></thead><tbody>${c.scale.map((s) => `<tr><td><b>${s.letter}</b></td><td class="r num">${s.min.toFixed(1)}</td><td class="r num">${s.gpa.toFixed(1)}</td></tr>`).join('')}</tbody></table></div>
        <p class="muted" style="font-size:12.5px">Xếp loại theo GPA hệ 4: Xuất sắc ≥ 3.6 · Giỏi ≥ 3.2 · Khá ≥ 2.5 · Trung bình ≥ 2.0. Học phần học lại lấy điểm cao nhất; tín chỉ tích lũy chỉ tính học phần đạt (≥ 4.0).</p></section>`;
    },
    students() {
      const s = app.state;
      return importPanel('students', 'Nhập CSDL sinh viên', 'Cột: mssv, ho_ten, ngay_sinh, gioi_tinh, lop, khoa, nganh, khoa_hoc, email, trang_thai. Sinh viên đăng nhập bằng họ tên, mật khẩu là MSSV; mỗi Khoa mới được tạo tài khoản văn phòng Khoa.') +
        `<section class="panel"><div class="title">CSDL sinh viên <span class="sub">${s.students.length} sinh viên · <a href="/api/admin/export/students.csv">Xuất CSV</a></span></div><div class="table-wrap"><table class="grid"><thead><tr><th>MSSV</th><th>Họ tên</th><th>Ngày sinh</th><th>Lớp</th><th>Khoa</th><th>Email</th><th>Tình trạng</th><th class="r">Dòng điểm</th></tr></thead><tbody>${s.students.map((x) => `<tr><td class="mono">${x.mssv}</td><td>${esc(x.hoTen)}</td><td class="num">${dmy(x.ngaySinh)}</td><td>${esc(x.lop)}</td><td>${esc(x.khoa)}</td><td>${esc(x.email)}</td><td>${esc(x.trangThai)}</td><td class="r num">${s.gradeCounts[x.mssv] || 0}</td></tr>`).join('')}</tbody></table></div></section>`;
    },
    grades() {
      const g = ui.adminGrades;
      if (!g) { loadAdminGrades(); return '<div class="empty">Đang tải CSDL điểm…</div>'; }
      return importPanel('grades', 'Nhập CSDL điểm', 'Cột: mssv, nam_hoc, hoc_ky, ma_hp, ten_hp, so_tc, diem_10, diem_chu. Chế độ "gộp" thay toàn bộ điểm của các MSSV có trong tệp.') +
        `<section class="panel"><div class="title">CSDL điểm <span class="sub">${g.total} dòng · <a href="/api/admin/export/grades.csv">Xuất CSV</a></span></div>
        <form class="btns" data-form="grade-filter" style="margin-bottom:10px"><select name="mssv" aria-label="Sinh viên" style="padding:7px 10px;border:1px solid var(--line);border-radius:4px;background:var(--surface);max-width:100%"><option value="">Tất cả sinh viên</option>${app.state.students.map((s) => `<option value="${s.mssv}" ${ui.gradeFilter === s.mssv ? 'selected' : ''}>${s.mssv} · ${esc(s.hoTen)}</option>`).join('')}</select><button class="btn" type="submit">Lọc</button></form>
        <div class="table-wrap" style="max-height:520px"><table class="grid"><thead><tr><th>MSSV</th><th>Năm học</th><th>HK</th><th>Mã HP</th><th>Tên học phần</th><th class="r">TC</th><th class="r">Điểm</th><th>Chữ</th></tr></thead><tbody>${g.grades.map((x) => `<tr><td class="mono">${x.mssv}</td><td>${esc(x.namHoc)}</td><td>${esc(x.hocKy)}</td><td class="mono">${esc(x.maHP)}</td><td>${esc(x.tenHP)}</td><td class="r num">${x.soTC ?? ''}</td><td class="r num">${x.diem10 ?? '<span class="pill bad">trống</span>'}</td><td>${esc(x.diemChu)}</td></tr>`).join('')}</tbody></table></div></section>`;
    },
    bulk() {
      const res = ui.bulkResult;
      return `<section class="panel"><div class="title">Nhập yêu cầu hàng loạt (dữ liệu test)</div>
        <p style="margin-top:0">Mỗi dòng là một yêu cầu, chạy ngay qua quy trình như khi sinh viên tự gửi. Cột: <span class="mono">mssv, ho_ten, ngay_sinh, email, sdt, muc_dich, ngon_ngu (vi/en), ban_giay (1/0), so_ban</span>. Ô để trống lấy theo CSDL sinh viên; ô có giá trị được dùng nguyên văn để kiểm tra luật xác thực.</p>
        <form class="stack" data-form="bulk">
          <div class="field"><label for="imp-requests">Nội dung CSV hoặc JSON</label><textarea id="imp-requests" name="text" rows="7" class="mono" style="min-height:140px">${esc(ui.importText.requests)}</textarea></div>
          <div class="btns"><input type="file" accept=".csv,.json,.txt" data-file="requests" aria-label="Chọn tệp yêu cầu"><button class="btn" type="button" data-action="sample" data-kind="requests">Điền dữ liệu mẫu</button><button class="btn primary" type="submit">Gửi các yêu cầu</button></div>
        </form>
        ${res ? `<div class="table-wrap" style="margin-top:12px"><table class="grid"><thead><tr><th>#</th><th>MSSV</th><th>Kết quả</th><th>Ghi chú</th></tr></thead><tbody>${res.map((x, i) => `<tr class="click" data-action="open" data-id="${x.id}"><td>${i + 1}</td><td class="mono">${esc(x.mssv)}</td><td><span class="mono">${x.id}</span> ${pill(x.status)}</td><td>${esc(x.note)}</td></tr>`).join('')}</tbody></table></div>` : ''}
      </section>`;
    },
    mail() {
      const list = app.state.outbox.slice().sort((a, b) => b.t - a.t);
      return `<section class="panel"><div class="title">Hộp thư hệ thống <span class="sub">${list.length} email · ${app.state.smtp ? 'SMTP đang bật' : 'SMTP chưa cấu hình (chỉ lưu hộp thư)'}</span></div>${list.length ? list.map(mailHtml).join('') : '<div class="empty">Chưa có email.</div>'}</section>`;
    },
    logs() {
      const list = app.state.logs.slice().sort((a, b) => b.t - a.t);
      const tone = { warn: 'warn', audit: 'info', error: 'bad', info: 'ok' };
      return `<section class="panel"><div class="title">Nhật ký hệ thống <span class="sub">Hủy yêu cầu, hiệu chỉnh điểm, sự cố, cấu hình</span></div>${list.length ? `<div class="table-wrap" style="max-height:560px"><table class="grid"><thead><tr><th>Thời điểm</th><th>Mức</th><th>Nội dung</th><th>Người thực hiện</th><th>Yêu cầu</th></tr></thead><tbody>${list.map((l) => `<tr><td class="num" style="white-space:nowrap">${fmt(l.t)}</td><td><span class="pill ${tone[l.level] || 'info'}">${l.level}</span></td><td>${esc(l.msg)}</td><td>${esc(l.actor || 'Hệ thống')}</td><td class="mono">${l.reqId ? `<a href="#" data-action="open" data-id="${l.reqId}">${l.reqId}</a>` : ''}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">Chưa có nhật ký.</div>'}</section>`;
    },
    tests() {
      const res = ui.tests;
      const pass = res ? res.filter((r) => r.pass).length : 0;
      return `<section class="panel"><div class="title">Kiểm thử tự động <span class="sub">Chạy trên CSDL tạm, không ảnh hưởng dữ liệu đang dùng</span></div>
        <p style="margin-top:0">Bộ kịch bản <span class="mono">tests/test_quy_trinh.py</span> phủ toàn bộ cổng XOR, cổng bao hàm, 3 timer, nhánh lỗi truy xuất và event sub-process hủy. Chạy bằng dòng lệnh: <span class="mono">python -m unittest discover -s tests -v</span> (kèm cả kiểm thử API).</p>
        <div class="btns"><button class="btn primary" data-action="run-tests">Chạy bộ kiểm thử quy trình</button>${res ? `<span class="pill ${pass === res.length ? 'ok' : 'bad'}">${pass}/${res.length} đạt</span>` : ''}</div>
        ${res ? `<div style="margin-top:10px">${res.map((r) => `<div class="scn"><span class="id">${esc(r.id)}</span><div><b>${esc(r.name)}</b><div class="p">${esc(r.test)}</div>${r.detail ? `<div style="font-size:12.5px;margin-top:2px;color:var(--bad)">${esc(r.detail)}</div>` : ''}</div>${r.pass ? '<span class="pill ok">Đạt</span>' : '<span class="pill bad">Lỗi</span>'}</div>`).join('')}</div>` : ''}</section>`;
    },
    reset() {
      return `<section class="panel"><div class="title">Khôi phục dữ liệu</div>
        <p style="margin-top:0">Dữ liệu được lưu bền vững trong tệp SQLite <span class="mono">data/bangdiem.db</span> trên máy chủ. Có thể khôi phục bộ dữ liệu mẫu, hoặc xóa sạch để nạp dữ liệu test của giảng viên (tài khoản cán bộ được giữ lại).</p>
        <div class="btns"><button class="btn danger" data-action="reset" data-mode="sample">${ui.confirm === 'reset-sample' ? 'Bấm lần nữa để xác nhận' : 'Khôi phục dữ liệu mẫu'}</button>
          <button class="btn danger" data-action="reset" data-mode="empty">${ui.confirm === 'reset-empty' ? 'Bấm lần nữa để xác nhận' : 'Xóa sạch để nạp dữ liệu giảng viên'}</button></div>
      </section>`;
    },
  };
  async function loadAdminGrades() {
    try {
      ui.adminGrades = await api('GET', '/api/admin/grades?mssv=' + encodeURIComponent(ui.gradeFilter));
      if (ui.route === 'he-thong') render();
    } catch (e) { toast(e.message, 'err'); }
  }
  function importPanel(kind, title, help) {
    return `<section class="panel"><div class="title">${esc(title)}</div><p style="margin-top:0;font-size:13px">${esc(help)} Dấu phân cách: phẩy, chấm phẩy hoặc tab; tiêu đề tiếng Việt có dấu được chấp nhận. Có thể dán JSON dạng mảng.</p>
      <form class="stack" data-form="import" data-kind="${kind}">
        <div class="field"><label for="imp-${kind}">Nội dung CSV hoặc JSON</label><textarea id="imp-${kind}" name="text" class="mono" rows="5" style="min-height:110px">${esc(ui.importText[kind])}</textarea></div>
        <div class="btns"><input type="file" accept=".csv,.json,.txt" data-file="${kind}" aria-label="Chọn tệp">
          <select name="mode" aria-label="Chế độ nhập" style="padding:7px 10px;border:1px solid var(--line);border-radius:4px;background:var(--surface)"><option value="merge">Gộp vào dữ liệu hiện có</option><option value="replace">Thay thế toàn bộ</option></select>
          <button class="btn primary" type="submit">Nhập</button></div>
      </form></section>`;
  }

  /* ------------------------------ Tra cứu (công khai) ------------------------------ */
  function viewVerify() {
    const r = ui.verifyResult;
    const codes = (app.state && app.state.recentCodes) || [];
    return `<div class="page single"><div class="stack">
      <section class="panel"><div class="title">Tra cứu tính xác thực bảng điểm <span class="sub">Không cần đăng nhập</span></div>
        <p style="margin-top:0">Đơn vị tiếp nhận nhập mã xác thực in trên bảng điểm. Máy chủ băm lại nội dung đã lưu (SHA-256) và kiểm chữ ký RSA bằng khóa công khai của Phòng Đào tạo để phát hiện sửa đổi.</p>
        <form class="btns" data-form="verify"><input name="code" value="${esc(ui.verify)}" aria-label="Mã xác thực" placeholder="VD: A1B2-C3D4-E5F6" class="mono" style="padding:8px 10px;border:1px solid var(--line);border-radius:4px;background:var(--surface);flex:1 1 220px;min-width:0"><button class="btn primary" type="submit">Tra cứu</button><a class="btn" href="/api/public-key" target="_blank" rel="noopener">Khóa công khai</a></form>
        ${codes.length ? `<p class="muted" style="font-size:12.5px">Mã đã cấp gần đây: ${codes.map((c) => `<a href="#" data-action="try-code" data-code="${c}" class="mono">${c}</a>`).join(' · ')}</p>` : ''}
      </section>
      ${r ? (r.found ? `<div class="callout ${r.valid ? 'ok' : 'bad'}"><b>${r.valid ? 'Bảng điểm hợp lệ.' : 'Cảnh báo: nội dung hoặc chữ ký không khớp.'}</b> Mã ${r.entry.code} · ký lúc ${fmt(r.entry.signedAt)} · ${esc(r.algorithm)} · khóa ${esc(r.entry.keyId)} · băm ${r.hashOk ? 'khớp' : 'KHÔNG khớp'} · chữ ký ${r.signatureOk ? 'hợp lệ' : 'KHÔNG hợp lệ'}</div>${renderSheet(r.entry.transcript, { signature: { code: r.entry.code, hash: r.entry.hash, signer: r.entry.transcript.signer, signedAt: r.entry.signedAt }, transcript: r.entry.transcript })}`
        : '<div class="callout bad">Không tìm thấy bảng điểm với mã này.</div>') : ''}
    </div></div>`;
  }

  /* ------------------------------ Bảng điểm ------------------------------ */
  const LBL = {
    vi: { title: 'BẢNG ĐIỂM HỌC TẬP', sub: 'Theo hệ thống tín chỉ', name: 'Họ và tên', dob: 'Ngày sinh', id: 'Mã sinh viên', sex: 'Giới tính', cls: 'Lớp', major: 'Ngành', dept: 'Khoa', code: 'Mã HP', subj: 'Tên học phần', cr: 'TC', s10: 'Điểm 10', let: 'Điểm chữ', s4: 'Điểm 4', tgpa: 'TB học kỳ (hệ 4)', gpa: 'GPA (hệ 4)', gpa10: 'TB tích lũy (hệ 10)', acc: 'Tín chỉ tích lũy', rank: 'Xếp loại', note: 'Ghi chú', sign: 'TL. HIỆU TRƯỞNG<br>KT. TRƯỞNG PHÒNG ĐÀO TẠO<br>PHÓ TRƯỞNG PHÒNG', purpose: 'Mục đích' },
    en: { title: 'ACADEMIC TRANSCRIPT', sub: 'Credit-based system', name: 'Full name', dob: 'Date of birth', id: 'Student ID', sex: 'Gender', cls: 'Class', major: 'Major', dept: 'Faculty', code: 'Code', subj: 'Course title', cr: 'Cr', s10: 'Score', let: 'Grade', s4: 'Points', tgpa: 'Term GPA', gpa: 'Cumulative GPA', gpa10: 'Average (10-point)', acc: 'Credits earned', rank: 'Classification', note: 'Remarks', sign: 'FOR THE RECTOR<br>DEPUTY HEAD, ACADEMIC AFFAIRS OFFICE', purpose: 'Purpose' },
  };
  const RANK_EN = { 'Xuất sắc': 'Excellent', 'Giỏi': 'Very good', 'Khá': 'Good', 'Trung bình': 'Average', 'Yếu': 'Weak' };
  function renderSheet(tr, req) {
    if (!tr) return '<div class="empty">Chưa có bảng điểm.</div>';
    const L = LBL[tr.lang] || LBL.vi, en = tr.lang === 'en';
    const sig = req && req.signature && req.transcript && req.transcript.version === tr.version ? req.signature : null;
    const stamped = req && req.paper && req.paper.stampedAt;
    return `<article class="sheet">
      <div class="wm">BẢN DEMO MIS3047<br>KHÔNG CÓ GIÁ TRỊ PHÁP LÝ</div>
      <div class="sh-top"><div><b>${en ? 'ACADEMIC AFFAIRS OFFICE' : 'PHÒNG ĐÀO TẠO'}</b>${en ? 'Simulated system · MIS3047 project' : 'Hệ thống mô phỏng · Đồ án MIS3047'}</div><div><b>${en ? 'SOCIALIST REPUBLIC OF VIETNAM' : 'CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM'}</b>${en ? 'Independence – Freedom – Happiness' : 'Độc lập – Tự do – Hạnh phúc'}</div></div>
      <h2 class="sh-title">${L.title}</h2><div class="sh-sub">${L.sub} · ${en ? 'Version' : 'Phiên bản'} ${tr.version} · ${fmtDay(tr.createdAt)}</div>
      <div class="sh-info">
        <div><span>${L.name}:</span> <b>${esc(tr.student.hoTen)}</b></div><div><span>${L.id}:</span> <b class="mono">${esc(tr.student.mssv)}</b></div>
        <div><span>${L.dob}:</span> ${dmy(tr.student.ngaySinh)}</div><div><span>${L.sex}:</span> ${esc(en ? ({ Nam: 'Male', Nữ: 'Female' }[tr.student.gioiTinh] || tr.student.gioiTinh) : tr.student.gioiTinh)}</div>
        <div><span>${L.cls}:</span> ${esc(tr.student.lop)} · ${esc(tr.student.khoaHoc)}</div><div><span>${L.major}:</span> ${esc(tr.student.nganh)}</div>
        <div><span>${L.dept}:</span> ${esc(tr.student.khoa)}</div><div><span>${L.purpose}:</span> ${esc(tr.mucDich)}</div>
      </div>
      ${tr.semesters.map((t) => `<div class="sh-term"><h4>${esc(en ? t.key.replace('HK', 'Semester ') : t.key.replace('HK', 'Học kỳ '))}</h4><table><thead><tr><th>${L.code}</th><th>${L.subj}</th><th class="c">${L.cr}</th><th class="c">${L.s10}</th><th class="c">${L.let}</th><th class="c">${L.s4}</th></tr></thead><tbody>${t.rows.map((r) => `<tr><td>${esc(r.maHP)}</td><td>${esc(r.tenHP)}</td><td class="c">${r.soTC}</td><td class="c">${num(r.diem10, 1)}</td><td class="c">${r.diemChu}</td><td class="c">${num(r.diem4, 1)}</td></tr>`).join('')}<tr><td colspan="2" style="text-align:right"><b>${L.tgpa}</b></td><td class="c"><b>${t.tc}</b></td><td colspan="3" class="c"><b>${num(t.gpa4, 2)}</b></td></tr></tbody></table></div>`).join('')}
      <div class="sh-sum"><div>${L.gpa}<b>${num(tr.summary.gpa4, 2)}</b></div><div>${L.gpa10}<b>${num(tr.summary.gpa10, 2)}</b></div><div>${L.acc}<b>${tr.summary.tcTichLuy}</b></div><div>${L.rank}<b>${esc(en ? RANK_EN[tr.summary.xepLoai] : tr.summary.xepLoai)}</b></div></div>
      ${tr.ghiChu ? `<p style="margin:10px 0 0"><b>${L.note}:</b> ${esc(tr.ghiChu)}</p>` : ''}
      <div class="sh-sign"><div style="font-size:11.5px;color:#555">${sig ? `${en ? 'Verification code' : 'Mã xác thực'}: <b class="mono" style="color:#1b1b1b;font-size:13px">${sig.code}</b><br>SHA-256: <span class="mono" style="word-break:break-all">${sig.hash}</span>` : ''}</div>
        <div class="who"><b style="font-size:11.5px">${L.sign}</b>
          ${sig ? `<div class="digital">✔ ${en ? 'Digitally signed by' : 'Đã ký số bởi'} ${esc(sig.signer)}<br>${fmt(sig.signedAt)}</div>` : `<div class="pending-sign">${en ? 'Pending approval' : 'Chờ phê duyệt & ký số'}</div>`}
          <div style="margin-top:8px"><b>${esc(tr.signer)}</b></div>
          ${stamped ? `<div class="stamp">PHÒNG ĐÀO TẠO<br>ĐÃ ĐÓNG DẤU<br>${fmtDay(req.paper.stampedAt)}<br>(mô phỏng)</div>` : ''}
        </div></div>
    </article>`;
  }

  /* ------------------------------ Chi tiết yêu cầu ------------------------------ */
  function renderDrawer() {
    const host = $('#drawer-host');
    if (!ui.open || !app.detail) { host.innerHTML = ''; document.body.style.overflow = ''; return; }
    const req = app.detail.request;
    const keep = host.querySelector('.drawer')?.scrollTop || 0;
    const st = ST(req.status);
    const mails = app.state.outbox.filter((m) => m.reqId === req.id).sort((a, b) => b.t - a.t);
    const tabs = [['overview', 'Tổng quan & xử lý'], ['bpmn', 'Vị trí trên sơ đồ BPMN'], ['timeline', `Tiến trình (${req.history.length})`], ['transcript', 'Bảng điểm'], ['mail', `Email (${mails.length})`]];
    let body;
    if (ui.dtab === 'bpmn') body = `<section class="panel">${diagramBlock('req', req)}</section>`;
    else if (ui.dtab === 'timeline') body = `<section class="panel">${timelineHtml(req)}</section>`;
    else if (ui.dtab === 'transcript') {
      body = req.transcript ? `<div class="btns"><button class="btn" data-action="print">In / lưu PDF</button>${req.signature ? `<a class="btn" href="/api/requests/${encodeURIComponent(req.id)}/signed.json">Tải gói bảng điểm đã ký số (JSON)</a>` : ''}</div>${renderSheet(req.transcript, req)}` : '<div class="empty">Bảng điểm chưa được tạo. Bảng điểm được tạo sau khi thông tin hợp lệ và điểm được đối chiếu xong.</div>';
    } else if (ui.dtab === 'mail') body = mails.length ? mails.map(mailHtml).join('') : '<div class="empty">Chưa có email nào cho yêu cầu này.</div>';
    else body = overviewHtml(req);
    host.innerHTML = `<div class="drawer-back" data-action="close-back"><div class="drawer" role="dialog" aria-modal="true" aria-label="Chi tiết yêu cầu ${req.id}">
      <div class="dhead"><div><h2>${req.id} · ${esc(req.form.hoTen)}</h2><div class="meta">Gửi ${fmt(req.createdAt)} · ${st.final ? 'Kết thúc tại' : 'Bước hiện tại'}: <b>${esc(stepName(st.step))}</b>${st.role ? ` (${ROLE_LABEL[st.role]})` : ''}</div></div>
      <div class="btns">${pill(req.status)}<button class="close" data-action="close">Đóng ✕</button></div></div>
      <div class="dbody"><div class="tabs">${tabs.map(([k, l]) => `<button data-action="dtab" data-t="${k}" class="${ui.dtab === k ? 'active' : ''}">${l}</button>`).join('')}</div>${body}</div></div></div>`;
    document.body.style.overflow = 'hidden';
    const d = host.querySelector('.drawer');
    if (d && keep) d.scrollTop = keep;
  }
  function timelineHtml(req) {
    return `<ul class="timeline">${req.history.map((h) => { const s = app.cat.steps[h.step] || {}; return `<li><span class="when">${fmt(h.t)}</span><span class="dot ${h.kind || ''}"></span><div><div class="what">${esc(stepName(h.step))}<span class="lane">${esc(app.cat.lanes[s.lane] || '')} · ${esc(h.actor)}</span></div>${h.note ? `<div class="note">${esc(h.note)}</div>` : ''}</div></li>`; }).join('')}</ul>`;
  }
  function overviewHtml(req) {
    const f = req.form;
    const info = `<section class="panel"><div class="title">Thông tin yêu cầu</div><dl class="kv">
      <dt>MSSV</dt><dd class="mono">${esc(f.mssv)}</dd><dt>Họ tên</dt><dd>${esc(f.hoTen)}</dd><dt>Ngày sinh</dt><dd>${dmy(f.ngaySinh)}</dd>
      <dt>Email</dt><dd>${esc(f.email)}</dd><dt>Điện thoại</dt><dd>${esc(f.sdt)}</dd><dt>Khoa</dt><dd>${esc(req.dept)}</dd>
      <dt>Mục đích</dt><dd>${esc(f.mucDich)}</dd><dt>Ngôn ngữ</dt><dd>${f.ngonNgu === 'en' ? 'Tiếng Anh' : 'Tiếng Việt'}</dd>
      <dt>Hình thức</dt><dd>Bản điện tử${f.banGiay ? ` + ${f.soBan} bản giấy` : ''}</dd>${f.ghiChu ? `<dt>Ghi chú</dt><dd>${esc(f.ghiChu)}</dd>` : ''}
      <dt>Mốc thời gian</dt><dd>${deadlineHtml(req)}</dd>${req.signature ? `<dt>Mã xác thực</dt><dd class="mono">${req.signature.code}</dd>` : ''}
      ${req.decisionNote ? `<dt>Lý do</dt><dd>${esc(req.decisionNote)}</dd>` : ''}</dl></section>`;
    const checks = `<section class="panel"><div class="title">Kết quả kiểm tra tự động</div>${checksHtml(req)}</section>`;
    return `${actionHtml(req)}${cancelHtml(req)}<div class="overview">${info}${checks}</div>${req.feedback.length ? `<section class="panel"><div class="title">Góp ý chỉnh sửa</div><ul class="checks">${req.feedback.map((x) => `<li><span class="ic warn">!</span><div><b>${esc(x.from)}</b> · ${esc(x.actor || '')} · ${fmt(x.t)}<br>${esc(x.text)}</div></li>`).join('')}</ul></section>` : ''}`;
  }
  function checksHtml(req) {
    let h = '';
    if (req.validation) h += `<div style="font-weight:700;margin-bottom:6px">Xác thực thông tin SV · lần ${req.attempts}</div><ul class="checks">${req.validation.items.map((i) => `<li><span class="ic ${i.ok ? 'ok' : 'bad'}">${i.ok ? '✓' : '✕'}</span><span><b class="mono">${i.code}</b> ${esc(i.msg)}</span></li>`).join('')}</ul>`;
    if (req.check) {
      const c = req.check;
      h += `<div style="font-weight:700;margin:14px 0 6px">Đối chiếu điểm · ${c.rows} dòng · độ tin cậy <span class="pill ${c.pass ? 'ok' : 'warn'}">${Math.round(c.confidence * 100)}%</span> <span class="muted" style="font-weight:400">ngưỡng ${Math.round(c.threshold * 100)}%</span></div>
        <ul class="checks">${c.errors.map((e) => `<li><span class="ic bad">✕</span><span><b class="mono">${e.code}</b> ${esc(e.msg)}</span></li>`).join('')}${c.warnings.map((e) => `<li><span class="ic warn">!</span><span><b class="mono">${e.code}</b> ${esc(e.msg)}</span></li>`).join('')}${c.infos.map((e) => `<li><span class="ic info">i</span><span>${esc(e.msg)}</span></li>`).join('')}${!c.errors.length && !c.warnings.length ? '<li><span class="ic ok">✓</span><span>Điểm đầy đủ, đúng thang, không trùng lặp, không bất thường</span></li>' : ''}</ul>`;
    }
    if (req.status === 'LOI_HE_THONG') h += '<div class="callout bad" style="margin-top:10px">Không truy xuất được CSDL điểm. Sự cố đã được ghi nhận; sinh viên được đề nghị gửi lại yêu cầu sau.</div>';
    return h || '<div class="empty">Chưa có kết quả.</div>';
  }
  function cancelHtml(req) {
    if (role() !== 'SV' || !app.cat.cancellable.includes(req.status)) return '';
    return `<section class="panel" style="border-color:color-mix(in srgb, var(--bad) 30%, var(--line))"><div class="title" style="font-size:14px">Hủy yêu cầu <span class="sub">Event sub-process "Sinh viên chủ động hủy"</span></div>
      <div class="btns"><input id="cancel-reason" aria-label="Lý do hủy" placeholder="Lý do (không bắt buộc)" style="flex:1 1 240px;min-width:0;padding:7px 10px;border:1px solid var(--line);border-radius:4px;background:var(--surface)">
      <button class="btn danger" data-action="cancel">${ui.confirm === 'cancel' ? 'Bấm lần nữa để xác nhận hủy' : 'Hủy yêu cầu này'}</button></div>
      <p class="muted" style="margin:6px 0 0;font-size:12px">Chỉ hủy được trước khi bảng điểm được ký số. Bước đang chờ và các mốc nhắc việc sẽ bị dừng ngay.</p></section>`;
  }

  /* Khung hành động: chỉ hiện khi vai trò đăng nhập trùng với làn của bước hiện tại */
  function actionHtml(req) {
    const st = ST(req.status);
    if (st.final) {
      const tone = req.status === 'HOAN_TAT' ? 'ok' : 'bad';
      return `<div class="callout ${tone}"><b>${esc(st.label)}.</b> ${req.status === 'HOAN_TAT' ? `Bảng điểm đã gửi tới ${esc(req.form.email)}${req.form.banGiay ? ` và đã giao ${req.form.soBan} bản giấy cho ${esc(req.paper.receiver || '')}` : ''}. Mã xác thực <span class="mono">${req.signature.code}</span>.` : esc(req.decisionNote || 'Quy trình đã kết thúc.')}</div>`;
    }
    if (role() !== st.role) return `<div class="callout info">Bước "${esc(stepName(st.step))}" do <b>${ROLE_LABEL[st.role]}</b> thực hiện. Bạn đang xem với vai trò ${ROLE_LABEL[role()]}.</div>`;
    const box = (title, inner) => `<section class="action-box"><h3>${esc(title)}</h3>${inner}</section>`;
    const f = req.form;
    switch (req.status) {
      case 'CHO_BO_SUNG': {
        const bad = new Set(req.validation.items.filter((i) => !i.ok).map((i) => i.field));
        const msg = (k) => req.validation.items.filter((i) => !i.ok && i.field === k).map((i) => `<span class="err">${esc(i.msg)}</span>`).join('');
        const fld = (k, label, type, val) => `<div class="field ${bad.has(k) ? 'bad' : ''}"><label for="s-${k}">${label}</label><input id="s-${k}" name="${k}" type="${type || 'text'}" value="${esc(val)}">${msg(k)}</div>`;
        return box('Bổ sung thông tin trực tuyến', `<div class="callout warn">Hạn bổ sung: <b>${fmt(req.timers.supplementDue)}</b> (còn ${dur(req.timers.supplementDue - nowT())}). Sửa các ô tô đỏ rồi gửi lại.</div>
          <form class="form" data-form="sv-supp" data-id="${req.id}">
            ${fld('hoTen', 'Họ và tên', 'text', f.hoTen)}${fld('ngaySinh', 'Ngày sinh', 'date', f.ngaySinh)}${fld('email', 'Email', 'email', f.email)}${fld('sdt', 'Số điện thoại', 'text', f.sdt)}
            <div class="field full ${bad.has('mucDich') ? 'bad' : ''}"><label for="s-mucDich">Mục đích sử dụng</label><input id="s-mucDich" name="mucDich" value="${esc(f.mucDich)}">${msg('mucDich')}</div>
            ${f.banGiay ? fld('soBan', 'Số bản giấy', 'number', f.soBan) : ''}${bad.has('mssv') ? `<div class="full">${msg('mssv')}</div>` : ''}
            <div class="full btns"><button class="btn primary" type="submit">Gửi bổ sung</button></div></form>`);
      }
      case 'CHO_KHOA': return khoaBox(req, box);
      case 'CHO_KIEM_TRA':
        return box('Kiểm tra bảng điểm: đạt yêu cầu?', `<ul class="checks">${(req.autoChecks || []).map((c) => `<li><span class="ic ${c.ok ? 'ok' : 'bad'}">${c.ok ? '✓' : '✕'}</span><span>${esc(c.msg)}</span></li>`).join('')}</ul>
          <p class="muted" style="margin:0;font-size:12.5px">Hệ thống đã tự kiểm 5 tiêu chí; chuyên viên xem bản xem trước ở tab "Bảng điểm" rồi quyết định.</p>
          <div class="field"><label for="qc-note">Góp ý (bắt buộc nếu chưa đạt)</label><textarea id="qc-note" placeholder="Ví dụ: cần bản tiếng Anh; ghi chú tình trạng tốt nghiệp"></textarea></div>
          <div class="btns"><button class="btn primary" data-action="qc" data-ok="1">Đạt, chuyển Phó phòng duyệt</button><button class="btn danger" data-action="qc" data-ok="0">Chưa đạt, chuyển chỉnh sửa</button><button class="btn" data-action="dtab" data-t="transcript">Xem bảng điểm</button></div>`);
      case 'CHO_CHINH_SUA': {
        const terms = app.detail.terms || [];
        const hidden = req.options.hiddenSemesters || [];
        const fb = req.feedback[req.feedback.length - 1] || {};
        return box('Chỉnh sửa theo góp ý', `<div class="callout warn">${esc(fb.from || '')}: ${esc(fb.text || '')}</div>
          <form class="form" data-form="edit-tr" data-id="${req.id}">
            <div class="field"><label for="e-lang">Ngôn ngữ</label><select id="e-lang" name="ngonNgu"><option value="vi" ${f.ngonNgu === 'vi' ? 'selected' : ''}>Tiếng Việt</option><option value="en" ${f.ngonNgu === 'en' ? 'selected' : ''}>Tiếng Anh</option></select></div>
            <div class="field"><label for="e-signer">Người ký</label><input id="e-signer" name="signer" value="${esc(req.options.signer)}"></div>
            <div class="field full"><label for="e-note">Ghi chú trên bảng điểm</label><input id="e-note" name="ghiChuBangDiem" value="${esc(req.options.ghiChuBangDiem)}"></div>
            <div class="field full"><label>Học kỳ hiển thị</label><div class="btns">${terms.map((t, i) => `<label class="check" style="font-weight:400"><input type="checkbox" name="term" value="${esc(t)}" id="term-${i}" ${hidden.includes(t) ? '' : 'checked'}>${esc(t)}</label>`).join('')}</div></div>
            <div class="full btns"><button class="btn primary" type="submit">Lưu và tạo lại bảng điểm</button></div></form>`);
      }
      case 'CHO_PHE_DUYET':
        return box('Xem xét & quyết định', `<p style="margin:0">Bảng điểm phiên bản ${req.transcript.version}: GPA <b>${num(req.transcript.summary.gpa4, 2)}</b>, ${req.transcript.summary.tcTichLuy} tín chỉ tích lũy, ${req.transcript.semesters.length} học kỳ. Phê duyệt sẽ ký số RSA, gửi email${f.banGiay ? ' và chuyển in bản giấy' : ''}.</p>
          <div class="field"><label for="pp-note">Góp ý / lý do (bắt buộc khi yêu cầu chỉnh sửa hoặc từ chối)</label><textarea id="pp-note"></textarea></div>
          <div class="btns"><button class="btn primary" data-action="pp" data-d="approve">Phê duyệt & ký số</button><button class="btn" data-action="pp" data-d="revise">Yêu cầu chỉnh sửa</button><button class="btn danger" data-action="pp" data-d="reject">Từ chối</button><button class="btn" data-action="dtab" data-t="transcript">Xem bảng điểm</button></div>`);
      case 'CHO_IN':
        return box('In bản giấy', `<p style="margin:0">In <b>${f.soBan}</b> bản ${f.ngonNgu === 'en' ? 'tiếng Anh' : 'tiếng Việt'} từ bảng điểm đã ký số (mã ${req.signature.code}).</p><div class="btns"><button class="btn" data-action="print">Mở bản in</button><button class="btn primary" data-action="paper" data-step="print">Đã in ${f.soBan} bản, chuyển đóng dấu</button></div>`);
      case 'CHO_DONG_DAU':
        return box('Đóng dấu đỏ xác nhận', `<p style="margin:0">Ký tên và đóng dấu đỏ lên ${f.soBan} bản giấy đã in.</p><div class="btns"><button class="btn primary" data-action="paper" data-step="stamp">Đã ký & đóng dấu</button></div>`);
      case 'CHO_XAC_NHAN_GIAY':
        return box('Xác nhận đã cấp bản giấy', `<div class="field"><label for="recv">Người nhận</label><input id="recv" value="${esc(f.hoTen)}"></div><div class="btns"><button class="btn primary" data-action="paper" data-step="confirm">Xác nhận đã giao, hoàn tất</button></div>`);
      default: return '';
    }
  }
  function khoaBox(req, box) {
    const live = app.detail.liveCheck;
    const rows = app.detail.grades || [];
    const flagged = {};
    for (const e of live.errors) if (e.gradeId) flagged[e.gradeId] = 'err';
    for (const w of live.warnings) if (w.gradeId && !flagged[w.gradeId]) flagged[w.gradeId] = 'warnrow';
    const show = rows.filter((r) => flagged[r.id]).concat(rows.filter((r) => !flagged[r.id]));
    return box('Rà soát & hiệu chỉnh điểm', `
      <div class="callout ${live.pass ? 'ok' : 'warn'}">Kiểm tra lại theo dữ liệu hiện tại: <b>${live.errors.length} lỗi, ${live.warnings.length} bất thường</b>, độ tin cậy ${Math.round(live.confidence * 100)}% (ngưỡng ${Math.round(live.threshold * 100)}%). ${live.pass ? 'Đã đủ điều kiện, bấm "Đã hiệu chỉnh xong".' : 'Sửa các dòng tô màu hoặc xác nhận điểm bất thường.'}</div>
      ${live.errors.length ? `<ul class="checks">${live.errors.map((e) => `<li><span class="ic bad">✕</span><span><b class="mono">${e.code}</b> ${esc(e.msg)}</span></li>`).join('')}</ul>` : ''}
      ${live.warnings.length ? `<ul class="checks">${live.warnings.map((w) => `<li><span class="ic warn">!</span><span>${esc(w.msg)} <button class="btn small" data-action="khoa-ack" data-key="${w.key}">Xác nhận điểm đúng</button></span></li>`).join('')}</ul>` : ''}
      ${rows.length ? `<div class="table-wrap" style="max-height:360px"><table class="grid"><thead><tr><th>Học kỳ</th><th>Mã HP</th><th>Tên học phần</th><th class="r">TC</th><th class="r">Điểm</th><th>Chữ</th><th></th></tr></thead><tbody>${show.map((g) => `<tr class="${flagged[g.id] || ''}" data-grow="${g.id}">
        <td style="white-space:nowrap">${esc(g.hocKy)} ${esc(g.namHoc)}</td><td class="mono">${esc(g.maHP)}</td><td>${esc(g.tenHP)}</td>
        <td class="r"><input aria-label="Số tín chỉ" data-k="soTC" value="${g.soTC ?? ''}" style="width:48px"></td>
        <td class="r"><input aria-label="Điểm hệ 10" data-k="diem10" value="${g.diem10 ?? ''}" style="width:58px"></td>
        <td><input aria-label="Điểm chữ" data-k="diemChu" value="${esc(g.diemChu)}" style="width:48px"></td>
        <td style="white-space:nowrap"><button class="btn small" data-action="khoa-save" data-gid="${g.id}">Lưu</button> ${live.errors.some((e) => e.gradeId === g.id && e.code === 'D5') ? `<button class="btn small danger" data-action="khoa-del" data-gid="${g.id}">Xóa dòng trùng</button>` : ''}</td></tr>`).join('')}</tbody></table></div>
        <p class="muted" style="margin:0;font-size:12px">"Lưu" ghi thẳng vào CSDL điểm kèm nhật ký kiểm toán. Để trống ô "Chữ" thì hệ thống tự quy đổi từ điểm số.</p>` : '<div class="empty">Sinh viên không có dòng điểm nào trong CSDL điểm.</div>'}
      <div class="field"><label for="khoa-note">Ghi chú / lý do</label><textarea id="khoa-note" placeholder="Ví dụ: đã đối chiếu bảng điểm gốc của giảng viên"></textarea></div>
      <div class="btns"><button class="btn primary" data-action="khoa-decide" data-yes="1">Đã hiệu chỉnh xong, đối chiếu lại</button><button class="btn danger" data-action="khoa-decide" data-yes="0">Không hiệu chỉnh được, từ chối cấp</button></div>`);
  }

  /* ------------------------------ Sự kiện ------------------------------ */
  const enc = encodeURIComponent;
  const R = (sub) => `/api/requests/${enc(ui.open)}/${sub}`;
  const ACTIONS = {
    goto(d) { if (d.tab) ui.tab[d.to] = d.tab; if (location.hash === '#' + d.to) render(); else location.hash = d.to; },
    tab(d) { ui.tab[d.page] = d.tab; if (d.page === 'he-thong' && d.tab === 'grades') ui.adminGrades = null; render(); },
    async open(d) { if (!d.id || d.id === 'undefined') return; ui.open = d.id; ui.dtab = 'overview'; ui.confirm = null; await loadDetail(); renderDrawer(); },
    close() { ui.open = null; app.detail = null; render(); },
    'close-back'(d, el, ev) { if (ev.target === el) ACTIONS.close(); },
    dtab(d) { ui.dtab = d.t; renderDrawer(); mountDiagrams(); const dr = $('.drawer'); if (dr) dr.scrollTop = 0; },
    advance(d) { act('POST', '/api/admin/clock', { ms: Number(d.ms) }, (r) => (r.fired.length ? '' : 'Đã tua đồng hồ. Chưa có sự kiện thời gian nào đến hạn.')); },
    'reset-clock'() { act('POST', '/api/admin/clock', { reset: true }, 'Đã đưa đồng hồ về giờ thực'); },
    fault(d) { act('POST', '/api/admin/fault', { on: d.on === '1' }, d.on === '1' ? 'Đã bật giả lập sự cố CSDL điểm' : 'Đã tắt giả lập sự cố'); },
    qc(d) { act('POST', R('qc'), { ok: d.ok === '1', feedback: $('#qc-note')?.value || '' }, d.ok === '1' ? 'Bảng điểm đạt, đã chuyển Phó phòng' : 'Đã chuyển chỉnh sửa'); },
    pp(d) { act('POST', R('pp-decision'), { decision: d.d, note: $('#pp-note')?.value || '' }, (r) => (d.d === 'approve' ? `Đã ký số, mã ${r.request.signature.code}` : d.d === 'revise' ? 'Đã yêu cầu chỉnh sửa' : 'Đã từ chối yêu cầu')); },
    paper(d) {
      if (d.step === 'print') act('POST', R('print'), {}, 'Đã in, chuyển Phó phòng đóng dấu');
      if (d.step === 'stamp') act('POST', R('stamp'), {}, 'Đã đóng dấu');
      if (d.step === 'confirm') act('POST', R('deliver'), { receiver: $('#recv')?.value || '' }, 'Đã hoàn tất cấp phát');
    },
    'khoa-save'(d) {
      const tr = document.querySelector(`[data-grow="${d.gid}"]`);
      const v = (k) => tr.querySelector(`[data-k="${k}"]`).value;
      const letter = v('diemChu').trim();
      act('POST', R('grades/' + enc(d.gid)), { soTC: v('soTC'), diem10: v('diem10'), diemChu: letter, autoLetter: !letter }, 'Đã lưu dòng điểm');
    },
    'khoa-del'(d) { act('POST', R('grades/' + enc(d.gid)), { delete: true }, 'Đã xóa dòng trùng'); },
    'khoa-ack'(d) { act('POST', R('acknowledge'), { key: d.key }, 'Đã xác nhận'); },
    'khoa-decide'(d) {
      act('POST', R('khoa-decision'), { canFix: d.yes === '1', note: $('#khoa-note')?.value || '' },
        (r) => (d.yes === '1' ? (r.request.status === 'CHO_KHOA' ? 'Đối chiếu lại vẫn chưa đạt, yêu cầu vẫn ở Khoa' : 'Đối chiếu đạt, đã tạo bảng điểm') : 'Đã từ chối cấp bảng điểm'));
    },
    cancel() { confirmOnce('cancel', () => act('POST', R('cancel'), { reason: $('#cancel-reason')?.value || '' }, 'Đã hủy yêu cầu')); },
    zoom(d) { const k = d.key === 'proc' ? 'pzoom' : 'zoom'; ui[k] = Math.min(1.2, Math.max(0.25, Math.round((ui[k] + Number(d.d)) * 100) / 100)); if (ui.open) { renderDrawer(); mountDiagrams(); } else render(); },
    hl(d) { ui.highlight = d.step; render(); $('[data-diagram]')?.scrollIntoView({ behavior: 'smooth', block: 'center' }); },
    async 'run-tests'() {
      toast('Đang chạy kiểm thử…');
      try { ui.tests = (await api('POST', '/api/admin/run-tests', {})).results; const p = ui.tests.filter((r) => r.pass).length; toast(`${p}/${ui.tests.length} kịch bản đạt`, p === ui.tests.length ? 'ok' : 'err'); render(); } catch (e) { toast(e.message, 'err'); }
    },
    sample(d) {
      if (d.kind === 'requests') {
        const s = app.state.students;
        ui.importText.requests = 'mssv,ho_ten,ngay_sinh,email,sdt,muc_dich,ngon_ngu,ban_giay,so_ban\n' +
          [s[0] && `${s[0].mssv},,,,,Nộp hồ sơ học bổng,vi,0,`, s[4] && `${s[4].mssv},,,,,Hồ sơ thực tập,vi,1,2`, s[3] && `${s[3].mssv},${s[3].hoTen},03/11/2004,,,Hồ sơ học bổng,vi,0,`, '999999999999,Người Lạ,01/01/2000,abc@gmail.com,0905123456,Thử MSSV không tồn tại,vi,0,'].filter(Boolean).join('\n');
      }
      render();
    },
    reset(d) {
      confirmOnce('reset-' + d.mode, async () => {
        try {
          await api('POST', '/api/admin/reset', { mode: d.mode });
          ui.tests = null; ui.bulkResult = null; ui.adminGrades = null; ui.open = null; app.detail = null;
          await loadState();
          toast(d.mode === 'sample' ? 'Đã khôi phục dữ liệu mẫu' : 'Đã xóa sạch. Hãy nhập CSDL sinh viên và CSDL điểm.', 'ok');
          if (d.mode === 'empty') ui.tab['he-thong'] = 'students';
          render();
        } catch (e) { toast(e.message, 'err'); }
      });
    },
    async 'try-code'(d) { ui.verify = d.code; await doVerify(); },
    print() { ui.dtab = 'transcript'; renderDrawer(); setTimeout(() => window.print(), 50); },
    async 'quick-login'(d) {
      const account = app.demo.accounts.find((a) => a.username === d.u);
      await doLogin(d.u, account && account.role === 'SV' ? account.mssv : app.demo.password);
    },
    async logout() { try { await api('POST', '/api/logout', {}); } catch (e) { /* bỏ qua */ } app.me = null; app.state = null; ui.open = null; app.detail = null; await boot(); },
  };
  async function doVerify() {
    try { ui.verifyResult = await api('GET', '/api/verify/' + enc(ui.verify.trim() || '-')); } catch (e) { toast(e.message, 'err'); }
    render();
  }
  async function doLogin(username, password) {
    try {
      const r = await api('POST', '/api/login', { username, password });
      app.me = r.user; app.csrf = r.csrf; app.demoMode = r.demoMode;
      ui.tab = {};
      await loadState();
      toast('Xin chào ' + r.user.full_name, 'ok');
      if (location.hash !== '#home') location.hash = 'home'; else render();
    } catch (e) { toast(e.message, 'err'); }
  }
  const FORMS = {
    login(fd) { doLogin(String(fd.get('username') || ''), String(fd.get('password') || '')); },
    search(fd) {
      const q = String(fd.get('q') || '').trim();
      if (!q) return;
      const r = reqs().find((x) => x.id.toLowerCase() === q.toLowerCase());
      if (r) { ACTIONS.open({ id: r.id }); return; }
      if (/^[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}$/i.test(q)) { ui.verify = q; location.hash = 'tra-cuu'; doVerify(); return; }
      if (role() === 'PDT') { ui.filter = q; ui.statusFilter = ''; ui.tab['dao-tao'] = 'tat-ca'; ACTIONS.goto({ to: 'dao-tao' }); return; }
      toast('Không tìm thấy yêu cầu ' + q + ' trong phạm vi bạn được xem', 'err');
    },
    async 'sv-new'(fd) {
      const form = Object.fromEntries(fd.entries());
      form.banGiay = fd.get('banGiay') === 'on';
      form.soBan = form.banGiay ? form.soBan : 0;
      const r = await act('POST', '/api/requests', form);
      if (r) {
        const s = r.request.status;
        toast(s === 'CHO_BO_SUNG' ? `${r.request.id}: thông tin chưa hợp lệ, đã gửi email yêu cầu bổ sung` : `${r.request.id}: ${ST(s).label}`, s === 'CHO_BO_SUNG' || s === 'LOI_HE_THONG' ? 'err' : 'ok');
        ui.tab['sinh-vien'] = 'list';
        render();
        ACTIONS.open({ id: r.request.id });
      }
    },
    'sv-supp'(fd, form) { act('POST', `/api/requests/${enc(form.dataset.id)}/supplement`, Object.fromEntries(fd.entries()), (r) => (r.request.status === 'CHO_BO_SUNG' ? 'Thông tin vẫn chưa hợp lệ' : 'Bổ sung hợp lệ: ' + ST(r.request.status).label)); },
    'edit-tr'(fd, form) {
      const terms = app.detail.terms || [];
      const shown = fd.getAll('term');
      act('POST', `/api/requests/${enc(form.dataset.id)}/edit`, { ngonNgu: fd.get('ngonNgu'), signer: fd.get('signer'), ghiChuBangDiem: fd.get('ghiChuBangDiem'), hiddenSemesters: terms.filter((t) => !shown.includes(t)) }, (r) => `Đã tạo bảng điểm phiên bản ${r.request.transcript.version}`);
    },
    filter(fd) { ui.filter = String(fd.get('q') || ''); ui.statusFilter = String(fd.get('st') || ''); render(); },
    'grade-filter'(fd) { ui.gradeFilter = String(fd.get('mssv') || ''); ui.adminGrades = null; render(); },
    config(fd) { act('POST', '/api/admin/config', Object.fromEntries(fd.entries()), 'Đã lưu cấu hình'); },
    async import(fd, form) {
      const kind = form.dataset.kind;
      ui.importText[kind] = String(fd.get('text') || '');
      const r = await act('POST', '/api/admin/import/' + kind, { text: ui.importText[kind], mode: fd.get('mode') },
        (x) => (kind === 'students' ? `Đã nhập: thêm ${x.result.added}, cập nhật ${x.result.updated}, bỏ qua ${x.result.skipped}` : `Đã nhập ${x.result.added} dòng điểm, bỏ qua ${x.result.skipped}`));
      if (r) { ui.importText[kind] = ''; ui.adminGrades = null; render(); }
    },
    async bulk(fd) {
      ui.importText.requests = String(fd.get('text') || '');
      const r = await act('POST', '/api/admin/bulk', { text: ui.importText.requests }, (x) => `Đã gửi ${x.results.length} yêu cầu`);
      if (r) { ui.bulkResult = r.results; render(); }
    },
    verify(fd) { ui.verify = String(fd.get('code') || ''); doVerify(); },
  };

  document.addEventListener('click', (ev) => {
    const el = ev.target.closest('[data-action]');
    if (!el) return;
    const name = el.dataset.action;
    if (!ACTIONS[name]) return;
    if (el.tagName === 'A' || el.tagName === 'BUTTON') ev.preventDefault();
    if (name === 'open' && el.tagName === 'TR' && ev.target.closest('button')) return;
    if (name === 'close-back' && ev.target !== el) return;
    ev.stopPropagation();
    ACTIONS[name](el.dataset, el, ev);
  });
  document.addEventListener('submit', (ev) => {
    const form = ev.target.closest('[data-form]');
    if (!form) return;
    ev.preventDefault();
    const fn = FORMS[form.dataset.form];
    if (fn) fn(new FormData(form), form);
  });
  document.addEventListener('change', (ev) => {
    const t = ev.target;
    if (t.dataset.file && t.files && t.files[0]) {
      const kind = t.dataset.file;
      const reader = new FileReader();
      reader.onload = () => { ui.importText[kind] = String(reader.result || ''); render(); toast(`Đã đọc tệp ${t.files[0].name}, bấm nút để nhập`, 'ok'); };
      reader.readAsText(t.files[0], 'utf-8');
    }
  });
  document.addEventListener('keydown', (ev) => { if (ev.key === 'Escape' && ui.open) ACTIONS.close(); });

  const VIEWS = { home: viewHome, 'sinh-vien': viewSV, khoa: viewKhoa, 'dao-tao': viewPDT, 'pho-phong': viewPP, 'quy-trinh': viewProcess, 'he-thong': viewSystem, 'tra-cuu': viewVerify };
  function route() {
    const h = location.hash.replace('#', '');
    ui.route = VIEWS[h] ? h : 'home';
    if (ui.route !== 'quy-trinh') ui.highlight = null;
    render();
    window.scrollTo(0, 0);
  }
  window.addEventListener('hashchange', route);

  async function boot() {
    try {
      const [me, cat, svg] = await Promise.all([
        api('GET', '/api/me'),
        app.cat ? Promise.resolve(app.cat) : api('GET', '/api/bpmn'),
        app.svg ? Promise.resolve(app.svg) : fetch('bpmn/to-be.svg').then((r) => r.text()),
      ]);
      app.cat = cat; app.svg = svg;
      app.me = me.user; app.csrf = me.csrf || null; app.demo = me.demo; app.demoMode = me.demoMode !== false;
      if (app.me) await loadState();
    } catch (e) {
      $('#view').innerHTML = `<div class="callout bad">Không kết nối được máy chủ: ${esc(e.message)}. Hãy chạy <span class="mono">python app.py</span>.</div>`;
      return;
    }
    route();
  }
  // Làm mới định kỳ: máy chủ quét timer ở mỗi lời gọi. Chỉ vẽ lại khi có thay đổi để không mất dữ liệu đang nhập.
  setInterval(async () => {
    if (!app.me) return;
    try {
      const before = JSON.stringify(app.state.requests.map((r) => [r.id, r.status, r.history.length]));
      await loadState();
      const after = JSON.stringify(app.state.requests.map((r) => [r.id, r.status, r.history.length]));
      if (before !== after) { await loadDetail(); render(); toast('Dữ liệu vừa được cập nhật', 'ok'); } else renderChrome();
    } catch (e) { /* mạng chập chờn: thử lại lần sau */ }
  }, 30000);
  boot();
})();
