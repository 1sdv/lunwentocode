# LunwenToCode 部署指南

面向公网部署：FastAPI 后端 + 零构建前端 + 项目展示站。

---

## 架构

```
                    ┌─────────────────────────────────────────┐
  浏览器 ──────────▶ │  Nginx (443)                            │
                    │   /            → 应用界面 (自研前端)      │
                    │   /site/       → 项目展示站              │
                    │   /static/     → 前端静态资源             │
                    │   /api/        → FastAPI                 │
                    └────────────────┬────────────────────────┘
                                     │ proxy_pass (关闭 buffering)
                    ┌────────────────▼────────────────────────┐
                    │  uvicorn server.main:app (:8000) 单进程 │
                    │   ├─ POST /api/tasks      提交任务      │
                    │   ├─ GET  /api/tasks/:id/stream  SSE    │
                    │   ├─ GET  /api/tasks/:id/zip  下载项目包 │
                    │   └─ GET  /api/tasks/:id/files/:name      │
                    └────────────────┬────────────────────────┘
                                     │ 后台线程（并发受限）
                    ┌────────────────▼────────────────────────┐
                    │  ThesisToCodeWorkflow                    │
                    │   Parser → Analyzer → Coder( Jupyter )   │
                    │   → Writer → paper.md + notebook.ipynb    │
                    └──────────────────────────────────────────┘
```

### ⚠️ 必须单进程

任务管理器（并发信号量、限流计数、任务注册表）都是**进程内内存状态**。
`--workers` 必须为 `1`，否则 SSE 可能连到没有该任务的进程，前端永远等不到进度。
并发靠 `MAX_CONCURRENT_TASKS` 控制，不要靠多 worker。

---

## 一、本地快速验证

```bash
pip install -r requirements.txt -r requirements-web.txt
pip install ipykernel          # Jupyter 内核，与 uvicorn 同一解释器

python -m uvicorn server.main:app --host 127.0.0.1 --port 8000
```

| 地址 | 内容 |
|------|------|
| http://127.0.0.1:8000 | 应用界面 |
| http://127.0.0.1:8000/site/ | 项目展示站 |
| http://127.0.0.1:8000/docs | API 文档（Swagger） |
| http://127.0.0.1:8000/api/health | 健康检查 |

前端是纯静态文件（`web/`），**无构建步骤**，改完刷新即可。

---

## 二、方案 A：Docker 部署（最省事，推荐第一次用这个）

### 1. 装 Docker

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin
sudo systemctl enable --now docker
```

### 2. 传代码

```bash
sudo mkdir -p /opt/lunwentocode && sudo chown $USER /opt/lunwentocode
cd /opt/lunwentocode
# 方式一：git clone（推荐，便于后续更新）
git clone <你的仓库> .
# 方式二：本地 scp / 拖拽上传
```

### 3. 配置

```bash
cp .env.web.example .env
nano .env
```

最少要改这一项：

```env
# 访问令牌：用户在页面上填写后才能提交任务。留空 = 任何人可提交（会烧你的额度）
SITE_TOKEN=换成你自己的随机串
```

生成随机串：

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(24))"
```

其余按机器规格调：

```env
# 2 核 4G 机器 → 1；4 核 8G → 2
MAX_CONCURRENT_TASKS=2
# 单文件上限，Nginx 的 client_max_body_size 要 ≥ 这个值
MAX_UPLOAD_MB=20
# 每 IP 每分钟最大提交数，防刷
RATE_LIMIT_PER_MINUTE=5
# 产出保留 24 小时后自动清理
TASK_TTL_HOURS=24
```

### 4. 启动

```bash
docker compose up -d --build
docker compose logs -f web
```

首次构建要装 matplotlib/Jupyter 依赖，约 3–5 分钟。

验证：

```bash
curl http://127.0.0.1:8000/api/health
# {"status":"ok","active_tasks":0,"max_concurrent":2,"token_required":true}
```

### 5. 更新代码

```bash
cd /opt/lunwentocode
git pull
docker compose up -d --build
```

---

## 三、方案 B：systemd + Nginx 部署（省内存、更可控）

### 1. 系统准备

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv nginx git \
                    fonts-wqy-zenhei fonts-noto-cjk
sudo systemctl enable --now nginx

# 专用低权限用户
sudo useradd -r -m -d /opt/lunwentocode -s /bin/bash lunwen
sudo mkdir -p /opt/lunwentocode /var/log/lunwentocode
sudo chown -R lunwen:lunwen /opt/lunwentocode /var/log/lunwentocode
```

> 装中文字体，否则 matplotlib 生成的图表里中文全是方块。

### 2. 拉代码 + 建虚拟环境

```bash
sudo -u lunwen git clone <你的仓库> /opt/lunwentocode
cd /opt/lunwentocode

sudo -u lunwen python3.11 -m venv /opt/venv
sudo -u lunwen /opt/venv/bin/pip install -U pip wheel
sudo -u lunwen /opt/venv/bin/pip install -r requirements.txt -r requirements-web.txt
sudo -u lunwen /opt/venv/bin/pip install jupyterlab ipykernel
sudo -u lunwen /opt/venv/bin/python -m ipykernel install --sys-prefix --name python3
```

**最常见的坑**：`ipykernel` 必须装在**跑 uvicorn 的那个解释器**里。
验证：

```bash
sudo -u lunwen /opt/venv/bin/python -c "import ipykernel; print(ipykernel.__version__)"
sudo -u lunwen /opt/venv/bin/jupyter kernelspec list
```

### 3. 配置

```bash
sudo -u lunwen cp .env.web.example .env
sudo -u lunwen nano .env
```

改 `SITE_TOKEN`（见方案 A），并确认 `OUTPUT_ROOT` / `UPLOAD_ROOT` 指向 `lunwen` 可写的目录：

```env
SITE_TOKEN=换成你自己的随机串
OUTPUT_ROOT=/opt/lunwentocode/web_output
UPLOAD_ROOT=/opt/lunwentocode/web_uploads
MAX_CONCURRENT_TASKS=2
```

### 4. systemd

```bash
sudo cp deploy/lunwentocode-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lunwentocode-web
sudo systemctl status lunwentocode-web
```

日志：

```bash
sudo tail -f /var/log/lunwentocode/web.log    # 应用日志
sudo tail -f /var/log/lunwentocode/web.err    # 错误
sudo journalctl -u lunwentocode-web -f        # systemd 层
```

### 5. Nginx + HTTPS

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/lunwentocode
sudo ln -sf /etc/nginx/sites-available/lunwentocode /etc/nginx/sites-enabled/
sudo nano /etc/nginx/sites-available/lunwentocode
# 改两处：server_name 和 ssl_certificate 路径

sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com -d www.your-domain.com
sudo nginx -t && sudo systemctl reload nginx
```

### 6. 放行端口

云服务器还需在**安全组 / 防火墙**放行 80、443：

```bash
sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
```

---

## 四、域名解析

在域名服务商处加一条 A 记录，指向服务器公网 IP，然后等 DNS 生效：

```bash
dig +short your-domain.com
```

解析生效后再跑 certbot，否则证书签发失败。

---

## 五、部署后自检清单

```bash
# 1. 后端活着
curl http://127.0.0.1:8000/api/health

# 2. Nginx 转发正常（换成你的域名）
curl -I https://your-domain.com/
curl -I https://your-domain.com/site/index.html

# 3. 令牌生效（不带令牌应 401）
curl -i http://127.0.0.1:8000/api/tasks | head -1

# 4. 带令牌应 200
curl -i -H "X-Access-Token: 你的令牌" http://127.0.0.1:8000/api/tasks | head -1

# 5. 内核可用
sudo -u lunwen /opt/venv/bin/jupyter kernelspec list
```

浏览器打开后，页面上传一个 `.md` 文件 + 填自己的 API Key 跑一次真任务，
确认能看到**实时日志滚动**和**最终论文预览**——这两项通了就说明整链路 OK。

---

## 六、安全要点

1. **API Key 由用户自带**，只存在于任务内存与请求体中，不落盘、不进日志。服务端 `.env` 的 Key 仅作可选兜底。
2. **务必设置 `SITE_TOKEN`**。否则任何人可提交任务，白烧你的服务器资源和 LLM 额度。
   用户在页面「模型与接口 → 访问令牌」填写即可，前端会存在本地浏览器。
3. **Jupyter 内核执行的是 LLM 生成的代码**，本质是任意代码执行。公网部署前务必：
   - 用低权限用户运行（`lunwen`），**不要用 root**
   - systemd 已加 `NoNewPrivileges`；容器里限制内存上限
   - 有条件的话把容器放到内网或加网络策略，只暴露 80/443
4. **限流已内置**：每 IP 每分钟 `RATE_LIMIT_PER_MINUTE` 次提交，并发由信号量控制。
5. **磁盘**：产出目录按 `TASK_TTL_HOURS` 自动清理。产出多时建议挂独立卷并配 logrotate。
6. **别把 `.env` 提交进仓库**（已在 `.gitignore`）。

---

## 七、常见问题

| 现象 | 原因 / 处理 |
|------|------------|
| 页面看不到实时进度，只在最后一次性出现 | Nginx 少了 `proxy_buffering off`；也检查 `proxy_read_timeout` 是否够大 |
| 任务卡在「启动 Jupyter 内核」 | `ipykernel` 没装在 uvicorn 所在解释器。`/opt/venv/bin/python -m ipykernel install --sys-prefix --name python3` |
| 提交后 401 | `SITE_TOKEN` 已启用，页面里要填访问令牌 |
| 提交后 429 | 触发限流，等一分钟或调大 `RATE_LIMIT_PER_MINUTE` |
| 图表中文变方块 | 缺中文字体：`apt install fonts-wqy-zenhei fonts-noto-cjk` 后重启服务 |
| 上传大文件 413 | Nginx `client_max_body_size` 要 ≥ 后端 `MAX_UPLOAD_MB` |
| 内存爆掉 / OOM | 调小 `MAX_CONCURRENT_TASKS`；容器加内存上限；给 swap |
| 多用户同时用时进度串台 | `--workers` 必须为 1（见「必须单进程」） |
| 内核报权限错 | systemd 里 `ProtectSystem=full` 需配 `ReadWritePaths=/opt/lunwentocode`（配置文件已含） |

---

## 八、常用运维命令

```bash
# 重启
sudo systemctl restart lunwentocode-web        # systemd
docker compose restart web                      # docker

# 看实时日志
sudo tail -f /var/log/lunwentocode/web.log
docker compose logs -f web

# 清理旧产出（保留最近 2 天）
find /opt/lunwentocode/web_output -maxdepth 1 -type d -mtime +2 -exec rm -rf {} +

# 手动清空上传临时目录
rm -rf /opt/lunwentocode/web_uploads/*
```
