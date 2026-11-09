FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/root \
    MPLBACKEND=Agg

WORKDIR /app

# 系统依赖：Jupyter 内核需要 git，matplotlib 需要中文字体，curl 用于健康检查
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        curl \
        fonts-wqy-zenhei \
        fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt requirements-web.txt ./
# ipykernel 必须与 uvicorn 同一个解释器，否则 Jupyter 内核起不来
RUN pip install --no-cache-dir -r requirements.txt -r requirements-web.txt \
    && pip install --no-cache-dir jupyterlab ipykernel \
    && python -m ipykernel install --sys-prefix --name python3

# 项目代码
COPY . /app

# 运行目录
RUN mkdir -p /app/web_output /app/web_uploads /root/.ipython_kernels

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

# 必须单 worker：任务管理器（信号量 / 限流 / 任务注册表）是进程内状态
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-keep-alive", "120"]
