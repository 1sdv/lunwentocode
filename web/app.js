/* LunwenToCode Web 前端逻辑（零依赖） */
(() => {
  'use strict';

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));
  /** 在指定容器内查找（$ 只接受一个参数，第二个参数会被忽略） */
  const $in = (root, sel) => (root || document).querySelector(sel);

  const state = {
    taskId: null,
    es: null,
    files: [],
    result: null,
    isDemo: false,
    tokenRequired: false,
    siteConfig: null,
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

  // ------------------------------------------------------------ 站点配置

  /** 只在输入框为空时填默认值，不覆盖用户已填的内容 */
  function fillIfEmpty(sel, value) {
    if (!value) return;
    const el = $(sel);
    if (el && !el.value.trim()) el.value = value;
  }

  /** 拉取服务端公开配置：预填访问令牌与默认模型 */
  async function loadSiteConfig() {
    let cfg;
    try {
      const res = await fetch('/api/config', { cache: 'no-store' });
      if (!res.ok) return;
      cfg = await res.json();
    } catch (e) {
      return; // 拿不到配置不影响主流程
    }
    if (!cfg) return;

    state.siteConfig = cfg;
    state.tokenRequired = !!cfg.token_required;
    const d = cfg.defaults || {};

    fillIfEmpty('#base_url', d.base_url);
    fillIfEmpty('#analyzer_model', d.analyzer_model);
    fillIfEmpty('#coder_model', d.coder_model);
    fillIfEmpty('#writer_model', d.writer_model);

    // 访问令牌：服务端下发即自动填入，用户无需手动输入
    const tok = $('#site_token');
    const label = $('#token-state');
    const note = $('#token-note');
    if (cfg.site_token) {
      if (tok && !tok.value.trim()) {
        tok.value = cfg.site_token;
        localStorage.setItem(TOKEN_KEY, cfg.site_token);
      }
      if (label) {
        label.textContent = '已自动填入';
        label.className = 'mark-ok';
      }
      if (note) note.textContent = '已由站点自动填入，可直接开始生成';
    } else if (!state.tokenRequired) {
      if (label) {
        label.textContent = '本站点未启用';
        label.className = 'mark-optional';
      }
      if (note) note.textContent = '当前站点不校验令牌，留空即可';
    } else {
      if (label) {
        label.textContent = '需要填写';
        label.className = 'mark-required';
      }
      if (note) note.textContent = '站点要求令牌，请向管理员获取';
    }
  }

  // ------------------------------------------------------------ 配置指引弹窗

  function openConfigGuide() {
    const dlg = $('#dlg-config');
    if (!dlg) return;
    const tag = $('#dlg-token-tag');
    const note = $('#dlg-token-note');
    const filled = !!((state.siteConfig && state.siteConfig.site_token)) || !!getToken();
    if (tag) {
      tag.textContent = filled ? '已自动填入' : '需手动填写';
      tag.className = 'tag ' + (filled ? 'tag-auto' : 'tag-req');
    }
    if (note) {
      note.textContent = filled
        ? '站点令牌已由服务端自动填入，无需手动输入。'
        : (state.tokenRequired
          ? '本站点校验令牌，请向管理员获取后填入。'
          : '当前站点不校验令牌，留空即可。');
    }
    if (typeof dlg.showModal === 'function') dlg.showModal();
    else dlg.setAttribute('open', '');
  }

  function closeConfigGuide() {
    const dlg = $('#dlg-config');
    if (!dlg) return;
    if (typeof dlg.close === 'function') dlg.close();
    else dlg.removeAttribute('open');
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

  /** 规范化接口地址：去掉末尾斜杠，保留用户填写的原样路径。

    不自动补 /v1 —— 自定义代理可能用非标准路径。
    漏填 /v1 时后端会在收到 404 后自动补全重试。
  */
  function normalizeBaseUrl(url) {
    const u = (url || '').trim().replace(/\/+$/, '');
    return u;
  }

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
    $in(btn, '.go-label').textContent = '提交中…';

    const fd = new FormData();
    fd.append('proposal', proposal);
    fd.append('api_key', apiKey);
    fd.append('base_url', normalizeBaseUrl($('#base_url').value));
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
      $in(btn, '.go-label').textContent = '开始生成';
    }
  });

  function fail(msg) {
    const err = $('#form-error');
    err.textContent = msg;
    err.hidden = false;
  }

  // ------------------------------------------------------------ 演示模式

  /** 回放一次真实运行的流程：终端逐条输出，最后展示真实产出 */
  async function runDemo() {
    const btn = $('#btn-demo');
    const err = $('#form-error');
    err.hidden = true;

    btn.disabled = true;
    $in(btn, '.go-label').textContent = '回放中…';

    try {
      const [tlRes, resultRes] = await Promise.all([
        apiFetch('/api/demo/timeline'),
        apiFetch('/api/demo'),
      ]);
      if (!tlRes.ok) {
        const d = await tlRes.json().catch(() => ({}));
        throw new Error(d.detail || '演示数据不可用');
      }
      const { timeline } = await tlRes.json();
      const result = await resultRes.json();

      // 复用真实任务的状态机
      state.taskId = result.task_id;
      state.isDemo = true;
      $('#log').innerHTML = '';
      $('#log-block').hidden = false;
      $('#result-panel').hidden = true;
      $('#demo-flag').hidden = true;
      $('#run-task-id').textContent = result.task_id;
      $('#run-state').textContent = '回放中';
      $('#btn-back').hidden = false;
      setProgress(0);
      setConn('live', '示例回放中');

      // 逐条推送，进度条随阶段推进
      const total = timeline.length;
      for (let i = 0; i < total; i++) {
        const ev = timeline[i];
        appendLog(ev);
        const m = (ev.content || '').match(/Phase (\d)\/6/);
        if (m) {
          const base = { 1: 10, 2: 16, 3: 28, 4: 38, 5: 55, 6: 90 }[m[1]] || 0;
          setProgress(Math.max(currentProgress(), base));
        } else if (ev.type === 'report') {
          setProgress(Math.min(94, currentProgress() + 1));
        }
        await sleep(demoDelay(ev, i));
      }

      setProgress(100);
      setConn('done', '示例回放完成');
      $('#run-state').textContent = '已完成';
      showResult(result);
      $('#demo-flag').hidden = false;
      toast('示例已回放完毕');
    } catch (ex) {
      fail(ex.message || '演示回放失败');
      setConn('error', '示例不可用');
    } finally {
      btn.disabled = false;
      $in(btn, '.go-label').textContent = '运行示例';
    }
  }

  /** 不同类型的事件给不同的停留时间，模拟真实节奏 */
  function demoDelay(ev, i) {
    if (ev.type === 'code' && ev.content.indexOf('执行代码') === 0) return 620;
    if (ev.type === 'code_output') return 300;
    if (ev.type === 'code') return 200;
    if (ev.type === 'report') return 260;
    if (ev.type === 'system') return 340;
    return 200;
  }

  function currentProgress() {
    return parseInt($('#bar-num').textContent) || 0;
  }

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  $('#btn-demo').addEventListener('click', runDemo);

  // 配置指引：summary 内的按钮不能触发折叠
  $('#btn-config').addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    openConfigGuide();
  });

  $('#dlg-close').addEventListener('click', closeConfigGuide);
  $('#dlg-cancel').addEventListener('click', closeConfigGuide);
  $('#dlg-goto').addEventListener('click', () => {
    closeConfigGuide();
    $('#adv').open = true;
    $('#api_key').focus();
  });

  // 点击弹窗外部遮罩关闭
  $('#dlg-config').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeConfigGuide();
  });

  // 页面加载时拉取站点配置，预填令牌与默认模型
  loadSiteConfig();

  // ------------------------------------------------------------ 执行页

  $('#btn-back').addEventListener('click', () => {
    if (state.es) state.es.close();
    state.es = null;
    state.taskId = null;
    state.isDemo = false;
    $('#log-block').hidden = true;
    $('#result-panel').hidden = true;
    $('#demo-flag').hidden = true;
    $('#btn-back').hidden = true;
    $('#log').innerHTML = '';
    $('#run-task-id').textContent = '尚未提交任务';
    $('#run-state').textContent = '准备中';
    setProgress(0);
    setConn('', '未连接任务');
    window.scrollTo({ top: 0, behavior: 'smooth' });
    loadHistory();
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
    loadHistory();
  }

  // ------------------------------------------------------------ 历史任务

  const STATE_TEXT = {
    pending: '排队',
    running: '运行中',
    done: '已完成',
    error: '失败',
  };

  /** 拉取历史任务列表（包含服务重启前的记录） */
  async function loadHistory() {
    const ul = $('#history');
    if (!ul) return;
    let data;
    try {
      const res = await apiFetch('/api/tasks');
      if (!res.ok) return;
      data = await res.json();
    } catch (e) {
      return;
    }
    const tasks = (data && data.tasks) || [];
    if (!tasks.length) {
      $('#history-block').hidden = true;
      return;
    }
    ul.innerHTML = '';
    tasks.slice(0, 12).forEach((t) => {
      const li = document.createElement('li');
      if (t.task_id === state.taskId) li.classList.add('active');
      const id = document.createElement('span');
      id.className = 'history-id';
      id.textContent = t.task_id;
      const st = document.createElement('span');
      st.className = 'history-state ' + (t.status || 'pending');
      st.textContent = STATE_TEXT[t.status] || t.status;
      li.append(id, st);
      li.addEventListener('click', () => openHistoryTask(t.task_id));
      ul.appendChild(li);
    });
    $('#history-block').hidden = false;
  }

  /** 打开一个历史任务：拉取记录并渲染 */
  async function openHistoryTask(taskId) {
    if (state.es) {
      state.es.close();
      state.es = null;
    }
    state.taskId = taskId;
    state.isDemo = false;
    $('#log').innerHTML = '';
    $('#log-block').hidden = false;
    $('#result-panel').hidden = true;
    $('#demo-flag').hidden = true;
    $('#btn-back').hidden = false;
    $('#run-task-id').textContent = taskId;
    setConn('live', '载入历史任务');
    setProgress(0);

    try {
      const res = await apiFetch('/api/tasks/' + taskId);
      if (!res.ok) throw new Error('任务不存在或已过期');
      const d = await res.json();

      (d.events || []).forEach(appendLog);
      setProgress(d.progress || 0);
      $('#run-state').textContent = STATE_TEXT[d.status] || d.status;

      if (d.status === 'done' && d.result) {
        setConn('done', '任务完成');
        setProgress(100);
        showResult(d.result);
      } else if (d.status === 'error') {
        setConn('error', '任务失败');
        $('#run-state').textContent = d.error || '执行失败';
      } else {
        // 仍在运行 → 继续接 SSE
        connect(taskId);
      }
      loadHistory();
      $('#result-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (ex) {
      setConn('error', '载入失败');
      fail(ex.message || '载入历史任务失败');
    }
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
        loadHistory();
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
    const base = state.isDemo
      ? '/api/demo/files/'
      : '/api/tasks/' + state.taskId + '/files/';
    const t = getToken();
    const q = t ? '?token=' + encodeURIComponent(t) : '';
    files.forEach((name) => {
      const li = document.createElement('li');
      const a = document.createElement('a');
      a.href = base + name.split('/').map(encodeURIComponent).join('/') + q;
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
    ];
    if (result.demo) {
      rows.push(['产物来源', '一次真实运行的产出（示例）']);
      rows.push(['任务 ID', result.task_id || '—']);
    }
    if (result.zip_name) {
      rows.push(['压缩包', result.zip_name + ' · ' + fmtBytes(result.zip_size)]);
    }
    if (result.metrics) {
      Object.keys(result.metrics).forEach((k) => {
        rows.push([k, String(result.metrics[k])]);
      });
    }
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
    // 演示与真实任务都有项目包，只是路径不同
    // 下载走 <a> 导航，无法自定义请求头，令牌放查询参数
    const base = state.isDemo
      ? '/api/demo/zip'
      : '/api/tasks/' + state.taskId + '/zip';
    const t = getToken();
    // 演示包首次访问需现场打包（约 5500 个文件），给个提示免得以为卡死
    if (state.isDemo && !(state.result && state.result.zip_size)) {
      toast('正在打包示例项目包，约需十几秒…', 6000);
    }
    window.location.href = base + (t ? '?token=' + encodeURIComponent(t) : '');
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

  /** 极简 Markdown → HTML（标题/列表/表格/代码/图片/引用/强调/链接/LaTeX 公式） */
  function renderMarkdown(md) {
    const esc = (s) => s
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

    const lines = md.split(/\r?\n/);
    const out = [];
    let inCode = false, codeLang = '', codeBuf = [];
    let inTable = false, tableBuf = [];

    // 论文正文中的图片是裸文件名或带子目录的相对路径，需指向产出目录
    // <img> / 下载链接无法自定义请求头，令牌走 ?token= 查询参数
    const assetUrl = (src) => {
      if (!src) return '';
      if (/^(https?:)?\/\//i.test(src) || src.startsWith('data:')) return src;
      if (src.startsWith('/')) return src;
      if (!state.taskId) return src;
      const base = state.isDemo
        ? '/api/demo/files/'
        : '/api/tasks/' + state.taskId + '/files/';
      // 保留路径分隔符，只编码各段，否则子目录图片会 404
      return base + src.split('/').map(encodeURIComponent).join('/') + tokenQuery();
    };

    /** 令牌查询参数（仅在站点启用令牌时附加） */
    const tokenQuery = () => {
      const t = getToken();
      return t ? '?token=' + encodeURIComponent(t) : '';
    };

    // ---- LaTeX 公式 ----
    // 块公式 $$...$$ 与行内公式 $...$ 都交给 KaTeX 渲染
    const hasKatex = typeof window.katex !== 'undefined';

    /** 渲染单个 LaTeX（displayMode 决定块/行内） */
    const tex = (src, display) => {
      const clean = src.trim();
      if (!hasKatex) {
        // 兜底：无 KaTeX 时保留源码，但排版上仍区别块/行内
        return display
          ? `<pre class="tex-raw">${esc(clean)}</pre>`
          : `<code class="tex-raw">${esc(clean)}</code>`;
      }
      try {
        return window.katex.renderToString(clean, {
          displayMode: !!display,
          throwOnError: false,
          strict: false,
          trust: false,
          output: 'html',
        });
      } catch (e) {
        return `<code class="tex-raw">${esc(clean)}</code>`;
      }
    };

    // 行内公式先抽成占位符，避免 LaTeX 里的 * _ ` 等被 Markdown 语法误伤
    const MATH_SLOT = ' MATH ';
    let mathSlot = [];

    const protectMath = (s) => {
      mathSlot = [];
      const stash = (html) => {
        mathSlot.push(html);
        return MATH_SLOT + (mathSlot.length - 1) + MATH_SLOT;
      };
      return s
        // 块公式（行内出现时也识别）
        .replace(/\$\$([\s\S]+?)\$\$/g, (_, body) => stash(tex(body, true)))
        // 行内公式：不跨行、两侧不紧邻 $
        .replace(/(?<!\\)\$([^$\n]+?)\$/g, (m, body) => {
          if (!body.trim()) return m;
          return stash(tex(body, false));
        });
    };

    const restoreMath = (html) =>
      html.replace(
        new RegExp(MATH_SLOT + '(\\d+)' + MATH_SLOT, 'g'),
        (_, i) => mathSlot[Number(i)] || ''
      );

    /** 段落级文本：Markdown 内联语法 + 行内公式 */
    const inline = (s) => {
      const withMath = protectMath(s);
      const protectedText = esc(withMath)
        .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_, alt, src) =>
          `<img src="${assetUrl(src)}" alt="${alt}">`)
        .replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, t, href) =>
          `<a href="${assetUrl(href)}" target="_blank" rel="noopener">${t}</a>`)
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
        .replace(/`([^`]+)`/g, '<code>$1</code>');
      return restoreMath(protectedText);
    };

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

      // 块公式 $$ ... $$（可能跨多行）
      if (/^\s*\$\$/.test(line)) {
        const buf = [];
        const first = line.trim();
        // 同一行闭合
        if (first.length > 4 && first.endsWith('$$') && !first.endsWith('$$$$')) {
          const body = first.slice(2, -2);
          out.push(`<div class="math-block">${tex(body, true)}</div>`);
          continue;
        }
        buf.push(first.slice(2));
        let j = i + 1;
        let closed = false;
        while (j < lines.length) {
          const l = lines[j];
          if (/\s*\$\$\s*$/.test(l)) {
            buf.push(l.replace(/\s*\$\$\s*$/, ''));
            closed = true;
            break;
          }
          buf.push(l);
          j++;
        }
        out.push(`<div class="math-block">${tex(buf.join('\n'), true)}</div>`);
        i = closed ? j : lines.length - 1;
        continue;
      }

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
  } else {
    // 没有指定任务 → 拉历史列表供查看
    loadHistory();
  }
})();
