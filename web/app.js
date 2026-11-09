/* LunwenToCode Web 前端逻辑（零依赖） */
(() => {
  'use strict';

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  const state = {
    taskId: null,
    es: null,
    files: [],
    result: null,
  };

  // ------------------------------------------------------------ 工具

  const TOKEN_KEY = 'lunwen_site_token';

  function getToken() {
    const input = document.querySelector('#site_token');
    const v = (input && input.value.trim()) || localStorage.getItem(TOKEN_KEY) || '';
    if (v) localStorage.setItem(TOKEN_KEY, v);
    return v;
  }

  /** 统一的 fetch 包装：自动附带访问令牌 */
  async function apiFetch(url, opts = {}) {
    const token = getToken();
    const headers = Object.assign({}, opts.headers || {});
    if (token) headers['X-Access-Token'] = token;
    return fetch(url, Object.assign({}, opts, { headers }));
  }

  function toast(msg, ms = 3200) {
    const el = $('#toast');
    el.textContent = msg;
    el.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => { el.hidden = true; }, ms);
  }

  function fmtBytes(n) {
    if (!n && n !== 0) return '';
    if (n < 1024) return n + ' B';
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
    return (n / 1024 / 1024).toFixed(2) + ' MB';
  }

  function setConn(kind, label) {
    const el = $('#conn');
    el.className = 'conn' + (kind ? ' ' + kind : '');
    el.innerHTML = '<i></i>' + label;
  }

  // ------------------------------------------------------------ 文件选择

  function bindDrop(dropSel, inputSel, pickedSel, listSel, multi) {
    const drop = $(dropSel);
    const input = $(inputSel);
    const picked = pickedSel ? $(pickedSel) : null;
    const list = listSel ? $(listSel) : null;

    const open = () => input.click();
    drop.addEventListener('click', open);
    drop.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); }
    });

    ['dragenter', 'dragover'].forEach(ev =>
      drop.addEventListener(ev, (e) => {
        e.preventDefault();
        drop.classList.add('over');
      })
    );
    ['dragleave', 'drop'].forEach(ev =>
      drop.addEventListener(ev, (e) => {
        e.preventDefault();
        drop.classList.remove('over');
      })
    );
    drop.addEventListener('drop', (e) => {
      if (e.dataTransfer?.files?.length) {
        input.files = e.dataTransfer.files;
        input.dispatchEvent(new Event('change'));
      }
    });

    input.addEventListener('change', () => {
      const files = Array.from(input.files || []);
      drop.classList.toggle('has-file', files.length > 0);

      if (picked) {
        if (files.length) {
          picked.textContent = files[0].name + '　' + fmtBytes(files[0].size);
          picked.hidden = false;
        } else {
          picked.hidden = true;
        }
      }
      if (list) {
        list.innerHTML = '';
        files.forEach((f) => {
          const li = document.createElement('li');
          const b = document.createElement('b');
          b.textContent = f.name;
          const s = document.createElement('span');
          s.textContent = fmtBytes(f.size);
          li.append(b, s);
          list.appendChild(li);
        });
      }
    });
  }

  bindDrop('#drop-proposal', '#proposal', '#picked-proposal', null, false);
  bindDrop('#drop-data', '#data_files', null, '#picked-data', true);

  // ------------------------------------------------------------ 提交

  $('#form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const err = $('#form-error');
    err.hidden = true;

    const proposal = $('#proposal').files[0];
    const apiKey = $('#api_key').value.trim();

    if (!proposal) {
      return fail('请上传研究方案文件');
    }
    if (!apiKey) {
      $('#adv').open = true;
      $('#api_key').focus();
      return fail('请填写 API Key');
    }

    const btn = $('#submit');
    btn.disabled = true;
    $('.go-label', btn).textContent = '提交中…';

    const fd = new FormData();
    fd.append('proposal', proposal);
    fd.append('api_key', apiKey);
    fd.append('base_url', $('#base_url').value.trim());
    fd.append('analyzer_model', $('#analyzer_model').value.trim());
    fd.append('coder_model', $('#coder_model').value.trim());
    fd.append('writer_model', $('#writer_model').value.trim());
    Array.from($('#data_files').files || []).forEach((f) => fd.append('data_files', f));

    try {
      const res = await apiFetch('/api/tasks', { method: 'POST', body: fd });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || ('提交失败 (' + res.status + ')'));
      startTask(data.task_id);
    } catch (ex) {
      fail(ex.message || '提交失败');
    } finally {
      btn.disabled = false;
      $('.go-label', btn).textContent = '开始生成';
    }
  });

  function fail(msg) {
    const err = $('#form-error');
    err.textContent = msg;
    err.hidden = false;
  }

  // ------------------------------------------------------------ 执行页

  $('#btn-back').addEventListener('click', () => {
    if (state.es) state.es.close();
    state.es = null;
    state.taskId = null;
    $('#log-block').hidden = true;
    $('#result-panel').hidden = true;
    $('#btn-back').hidden = true;
    $('#log').innerHTML = '';
    $('#run-task-id').textContent = '尚未提交任务';
    $('#run-state').textContent = '准备中';
    setProgress(0);
    setConn('', '未连接任务');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });

  function startTask(taskId) {
    state.taskId = taskId;
    state.files = [];
    $('#log').innerHTML = '';
    $('#log-block').hidden = false;
    $('#result-panel').hidden = true;
    $('#run-task-id').textContent = taskId;
    $('#run-state').textContent = '排队中';
    $('#btn-back').hidden = false;
    setProgress(0);
    setConn('live', '任务运行中');
    connect(taskId);
  }

  function setProgress(pct) {
    $('#bar-fill').style.width = pct + '%';
    $('#bar-num').textContent = pct + '%';
  }

  function appendLog(ev) {
    const log = $('#log');
    const line = document.createElement('div');
    line.className = 'log-line ' + (ev.type || 'system');
    const p = document.createElement('span');
    p.className = 'mark';
    p.textContent = ev.prefix || '·';
    const c = document.createElement('span');
    c.textContent = ev.content || '';
    line.append(p, c);
    log.appendChild(line);
    log.scrollTop = log.scrollHeight;
  }

  function connect(taskId) {
    if (state.es) state.es.close();
    const token = getToken();
    const url = '/api/tasks/' + taskId + '/stream' + (token ? '?token=' + encodeURIComponent(token) : '');
    const es = new EventSource(url);
    state.es = es;

    es.onmessage = (msg) => {
      let data;
      try { data = JSON.parse(msg.data); } catch { return; }

      if (data.type === 'end') {
        es.close();
        if (data.status === 'done') {
          setConn('done', '任务完成');
          $('#run-state').textContent = '已完成';
          setProgress(100);
          showResult(data.result);
        } else {
          setConn('error', '任务失败');
          $('#run-state').textContent = data.error || '执行失败';
          appendLog({ type: 'error', prefix: '✕', content: data.error || '任务失败' });
        }
        return;
      }

      appendLog(data);
      // 进度条：system 阶段事件里带阶段号
      const m = (data.content || '').match(/Phase (\d)\/6/);
      if (m) {
        const base = { 1: 10, 2: 16, 3: 28, 4: 38, 5: 55, 6: 90 }[m[1]] || 0;
        setProgress(Math.max(parseInt($('#bar-num').textContent) || 0, base));
      }
    };

    es.onerror = () => {
      // 浏览器会自动重连；仅在任务已结束时才停止
      if (state.es === es) {
        setConn('', '连接中断，重试中');
      }
    };
  }

  // ------------------------------------------------------------ 结果

  function showResult(result) {
    if (!result) return;
    state.result = result;

    $('#run-state').textContent = '已完成';
    $('#result-title').textContent = result.title || '';
    $('#paper').innerHTML = renderMarkdown(result.report || '');
    renderFiles(result.files || []);
    renderMeta(result);

    $('#result-panel').hidden = false;
    setTimeout(() => {
      $('#result-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 120);
  }

  function renderFiles(files) {
    const ul = $('#files');
    ul.innerHTML = '';
    files.forEach((name) => {
      const li = document.createElement('li');
      const a = document.createElement('a');
      a.href = '/api/tasks/' + state.taskId + '/files/' + encodeURIComponent(name);
      a.target = '_blank';
      a.rel = 'noopener';
      const label = document.createElement('span');
      label.textContent = name;
      const ext = name.includes('.') ? name.split('.').pop() : '';
      const tag = document.createElement('span');
      tag.textContent = ext.toUpperCase();
      a.append(label, tag);
      li.appendChild(a);
      ul.appendChild(li);
    });
  }

  function renderMeta(result) {
    const dl = $('#meta');
    dl.innerHTML = '';
    const rows = [
      ['论文标题', result.title || '—'],
      ['支撑任务', (result.tasks_success || 0) + ' / ' + (result.tasks_total || 0) + ' 成功'],
      ['论文章节', (result.sections || []).length + ' 节'],
      ['正文字数', (result.report || '').length + ' 字符'],
      ['Notebook', result.notebook || '—'],
      ['依赖库', (result.requirements || []).join(', ') || '无额外依赖'],
      ['压缩包', (result.zip_name || '') + ' · ' + fmtBytes(result.zip_size)],
    ];
    rows.forEach(([k, v]) => {
      const dt = document.createElement('dt');
      dt.textContent = k;
      const dd = document.createElement('dd');
      dd.textContent = v;
      dl.append(dt, dd);
    });
  }

  $('#btn-download').addEventListener('click', () => {
    if (!state.taskId) return;
    window.location.href = '/api/tasks/' + state.taskId + '/zip';
  });

  $('#btn-copy-log').addEventListener('click', async () => {
    const text = Array.from($('#log').children)
      .map((l) => l.textContent)
      .join('\n');
    try {
      await navigator.clipboard.writeText(text);
      toast('执行记录已复制');
    } catch {
      toast('复制失败，请手动选择');
    }
  });

  // ------------------------------------------------------------ Tabs

  $$('.tab').forEach((tab) => {
    tab.addEventListener('click', () => {
      $$('.tab').forEach((t) => t.classList.remove('active'));
      tab.classList.add('active');
      ['paper', 'files', 'meta'].forEach((name) => {
        $('#tab-' + name).hidden = name !== tab.dataset.tab;
      });
    });
  });

  // ------------------------------------------------------------ Markdown 渲染

  /** 极简 Markdown → HTML（标题/列表/表格/代码/图片/引用/强调/链接） */
  function renderMarkdown(md) {
    const esc = (s) => s
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

    const lines = md.split(/\r?\n/);
    const out = [];
    let inCode = false, codeLang = '', codeBuf = [];
    let inTable = false, tableBuf = [];

    // 论文正文中的图片是裸文件名（如 fig1.png），需指向任务产出目录
    const assetUrl = (src) => {
      if (!src) return '';
      if (/^(https?:)?\/\//i.test(src) || src.startsWith('data:')) return src;
      if (src.startsWith('/')) return src;
      return state.taskId
        ? '/api/tasks/' + state.taskId + '/files/' + encodeURIComponent(src)
        : src;
    };

    const inline = (s) => esc(s)
      .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_, alt, src) =>
        `<img src="${assetUrl(src)}" alt="${alt}">`)
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, t, href) =>
        `<a href="${assetUrl(href)}" target="_blank" rel="noopener">${t}</a>`)
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
      .replace(/`([^`]+)`/g, '<code>$1</code>');

    const flushTable = () => {
      if (!inTable) return;
      const rows = tableBuf.map((r) => r.split('|').slice(1, -1).map((c) => c.trim()));
      const head = rows[0] || [];
      const body = rows.slice(rows.length > 1 && /^-{2,}$/.test(rows[1][0] || '') ? 2 : 1);
      out.push('<table><thead><tr>' +
        head.map((h) => `<th>${inline(h)}</th>`).join('') +
        '</tr></thead><tbody>' +
        body.map((r) => '<tr>' + r.map((c) => `<td>${inline(c)}</td>`).join('') + '</tr>').join('') +
        '</tbody></table>');
      inTable = false;
      tableBuf = [];
    };

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];

      // 代码块
      if (/^```/.test(line)) {
        if (!inCode) {
          inCode = true;
          codeLang = line.slice(3).trim();
          codeBuf = [];
        } else {
          out.push(`<pre><code class="lang-${esc(codeLang)}">${esc(codeBuf.join('\n'))}</code></pre>`);
          inCode = false;
        }
        continue;
      }
      if (inCode) { codeBuf.push(line); continue; }

      // 表格
      if (/^\|/.test(line.trim())) {
        inTable = true;
        tableBuf.push(line.trim());
        continue;
      }
      flushTable();

      // 标题
      const h = line.match(/^(#{1,6})\s+(.*)$/);
      if (h) {
        const lv = Math.min(h[1].length, 4);
        out.push(`<h${lv}>${inline(h[2])}</h${lv}>`);
        continue;
      }

      // 水平线
      if (/^\s*([-*_])\1{2,}\s*$/.test(line)) { out.push('<hr>'); continue; }

      // 引用
      if (/^>\s?/.test(line)) {
        out.push(`<blockquote>${inline(line.replace(/^>\s?/, ''))}</blockquote>`);
        continue;
      }

      // 列表
      const ul = line.match(/^(\s*)[-*+]\s+(.*)$/);
      const ol = line.match(/^(\s*)(\d+)\.\s+(.*)$/);
      if (ul || ol) {
        const tag = ul ? 'ul' : 'ol';
        const items = [];
        let j = i;
        while (j < lines.length) {
          const m = lines[j].match(ul ? /^(\s*)[-*+]\s+(.*)$/ : /^(\s*)(\d+)\.\s+(.*)$/);
          if (!m) break;
          items.push(m[ul ? 2 : 3]);
          j++;
        }
        out.push(`<${tag}>` + items.map((it) => `<li>${inline(it)}</li>`).join('') + `</${tag}>`);
        i = j - 1;
        continue;
      }

      // 段落
      if (line.trim() === '') { continue; }
      out.push(`<p>${inline(line)}</p>`);
    }
    if (inCode && codeBuf.length) {
      out.push(`<pre><code>${esc(codeBuf.join('\n'))}</code></pre>`);
    }
    flushTable();
    return out.join('\n');
  }

  // 页面加载时如果 URL 带 task 参数，直接恢复查看
  const params = new URLSearchParams(location.search);
  const tid = params.get('task');
  if (tid) {
    apiFetch('/api/tasks/' + tid)
      .then((r) => r.json())
      .then((d) => {
        if (!d.task_id) return;
        startTask(tid);
        (d.events || []).forEach(appendLog);
        if (d.status === 'done') {
          setConn('done', '任务完成');
          setProgress(100);
          showResult(d.result);
        } else if (d.status === 'error') {
          setConn('error', '任务失败');
          $('#run-state').textContent = d.error || '执行失败';
          appendLog({ type: 'error', prefix: '✕', content: d.error || '任务失败' });
        } else {
          connect(tid);
        }
      })
      .catch(() => {});
  }
})();
