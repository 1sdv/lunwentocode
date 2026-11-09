"""
LunwenToCode Web 服务 - FastAPI 后端

对外提供：
  GET  /                     应用界面（自研前端）
  GET  /site/                项目展示站
  POST /api/tasks            提交生成任务
  GET  /api/tasks/{id}       查询任务状态
  GET  /api/tasks/{id}/stream  SSE 实时进度
  GET  /api/tasks/{id}/files/{name}  下载产出文件
  GET  /api/tasks/{id}/zip   下载完整项目包
  GET  /api/health           健康检查
"""
import asyncio
import json
import os
import re
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.config import web_settings
from server.demo import (
    build_result,
    build_timeline,
    demo_available,
    demo_file_path,
)
from server.task_manager import task_manager

app = FastAPI(
    title="LunwenToCode Web",
    description="研究方案 → 论文初稿 + 验证代码",
    version="1.0.0",
)

if web_settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=web_settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ---------------------------------------------------------------- 鉴权

def check_token(x_access_token: Optional[str]) -> None:
    """站点令牌校验：未配置则放行"""
    if not web_settings.SITE_TOKEN:
        return
    if x_access_token != web_settings.SITE_TOKEN:
        raise HTTPException(status_code=401, detail="访问令牌无效")


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------- 生命周期

@app.on_event("startup")
async def on_startup() -> None:
    web_settings.ensure_dirs()
    # 后台清理过期任务
    asyncio.create_task(_cleanup_loop())


async def _cleanup_loop() -> None:
    while True:
        await asyncio.sleep(3600)
        try:
            await asyncio.to_thread(task_manager.cleanup_expired)
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------- 页面

@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    index_file = Path(web_settings.WEB_DIR) / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>前端未构建</h1>", status_code=500)
    return HTMLResponse(index_file.read_text(encoding="utf-8"))


@app.get("/site/{path:path}")
async def site(path: str):
    """项目展示站"""
    target = (Path(web_settings.SITE_DIR) / path).resolve()
    site_root = Path(web_settings.SITE_DIR).resolve()
    if not str(target).startswith(str(site_root)):
        raise HTTPException(status_code=403, detail="禁止访问")
    if target.is_dir():
        target = target / "index.html"
    if not target.exists():
        raise HTTPException(status_code=404, detail="未找到")
    return FileResponse(target)


@app.get("/site")
async def site_root():
    return RedirectResponse(url="/site/index.html")


# ---------------------------------------------------------------- API

@app.post("/api/tasks")
async def create_task(
    request: Request,
    proposal: UploadFile = File(..., description="研究方案文件 (.md/.pdf/.txt)"),
    data_files: list[UploadFile] = File(default_factory=list, description="数据文件 (.xlsx/.csv)"),
    api_key: str = Form(""),
    analyzer_model: str = Form(""),
    coder_model: str = Form(""),
    writer_model: str = Form(""),
    base_url: str = Form(""),
    x_access_token: Optional[str] = Header(None),
):
    check_token(x_access_token)

    ip = client_ip(request)
    if not task_manager.check_rate_limit(ip):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

    if not api_key.strip():
        raise HTTPException(status_code=400, detail="请填写 LLM API Key")

    # 校验方案文件扩展名
    suffix = Path(proposal.filename or "").suffix.lower()
    if suffix not in {".md", ".markdown", ".pdf", ".txt"}:
        raise HTTPException(status_code=400, detail="研究方案仅支持 .md / .pdf / .txt")

    if len(data_files) > web_settings.MAX_DATA_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"数据文件最多 {web_settings.MAX_DATA_FILES} 个",
        )

    upload_dir = Path(web_settings.UPLOAD_ROOT) / uuid.uuid4().hex
    upload_dir.mkdir(parents=True, exist_ok=True)

    # 保存方案文件
    proposal_path = upload_dir / f"proposal{suffix}"
    size = 0
    with proposal_path.open("wb") as fh:
        while chunk := await proposal.read(1024 * 1024):
            size += len(chunk)
            if size > web_settings.max_upload_bytes:
                fh.close()
                shutil.rmtree(upload_dir, ignore_errors=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"文件超过 {web_settings.MAX_UPLOAD_MB}MB 上限",
                )
            fh.write(chunk)

    # 保存数据文件
    saved_data: list[str] = []
    for f in data_files:
        if not f.filename:
            continue
        ext = Path(f.filename).suffix.lower()
        if ext not in {".xlsx", ".xls", ".csv"}:
            continue
        dest = upload_dir / Path(f.filename).name
        written = 0
        with dest.open("wb") as fh:
            while chunk := await f.read(1024 * 1024):
                written += len(chunk)
                if written > web_settings.max_upload_bytes:
                    fh.close()
                    break
                fh.write(chunk)
        saved_data.append(str(dest))

    record = task_manager.submit(
        proposal_path=str(proposal_path),
        data_paths=saved_data,
        api_key=api_key.strip(),
        analyzer_model=analyzer_model.strip(),
        coder_model=coder_model.strip(),
        writer_model=writer_model.strip(),
        base_url=base_url.strip(),
    )
    return JSONResponse(
        {"task_id": record.task_id, "status": record.status},
        status_code=202,
    )


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str, x_access_token: Optional[str] = Header(None)):
    check_token(x_access_token)
    record = task_manager.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="任务不存在")
    payload = record.public_dict()
    payload["events"] = record.events[-500:]
    if record.status == "done" and record.result:
        payload["result"] = record.result
    return payload


@app.get("/api/tasks/{task_id}/stream")
async def stream_task(
    task_id: str,
    token: Optional[str] = None,
    x_access_token: Optional[str] = Header(None),
):
    """SSE 实时进度（EventSource 无法自定义请求头，故同时支持 ?token= 查询参数）"""
    check_token(token or x_access_token)
    record = task_manager.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="任务不存在")

    async def event_generator():
        # 先补发已有事件（支持断线重连）
        for ev in record.events:
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

        if record.status in ("done", "error"):
            done = {
                "type": "end",
                "status": record.status,
                "result": record.result,
                "error": record.error,
            }
            yield f"data: {json.dumps(done, ensure_ascii=False)}\n\n"
            return

        last_index = len(record.events)
        while True:
            try:
                payload = await asyncio.wait_for(record._queue.get(), timeout=15.0)
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
                continue

            if payload is None:
                done = {
                    "type": "end",
                    "status": record.status,
                    "result": record.result,
                    "error": record.error,
                }
                yield f"data: {json.dumps(done, ensure_ascii=False)}\n\n"
                return

            # 去重：队列消息可能与已补发的事件重复
            if len(record.events) - last_index > 1:
                pass
            last_index += 1
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/tasks/{task_id}/files/{name}")
async def get_file(task_id: str, name: str, x_access_token: Optional[str] = Header(None)):
    check_token(x_access_token)
    work_dir = task_manager.get_work_dir(task_id)
    if not work_dir:
        raise HTTPException(status_code=404, detail="产出不存在")
    # 防目录穿越
    target = (work_dir / name).resolve()
    if not str(target).startswith(str(work_dir.resolve())):
        raise HTTPException(status_code=403, detail="禁止访问")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(target, filename=name)


@app.get("/api/tasks/{task_id}/zip")
async def get_zip(task_id: str, x_access_token: Optional[str] = Header(None)):
    check_token(x_access_token)
    zip_path = Path(web_settings.OUTPUT_ROOT) / task_id / "project.zip"
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="压缩包不存在")
    return FileResponse(zip_path, filename=f"{task_id}.zip")


@app.get("/api/tasks")
async def list_tasks(x_access_token: Optional[str] = Header(None)):
    check_token(x_access_token)
    return {"tasks": task_manager.list_recent(), "active": task_manager.active_count()}


# ---------------------------------------------------------------- 演示模式

@app.get("/api/demo")
async def get_demo(x_access_token: Optional[str] = Header(None)):
    """演示：一次真实运行的产出内容"""
    check_token(x_access_token)
    if not demo_available():
        raise HTTPException(status_code=404, detail="演示数据不可用")
    return build_result()


@app.get("/api/demo/timeline")
async def get_demo_timeline(x_access_token: Optional[str] = Header(None)):
    """演示：脚本化的执行事件时间线"""
    check_token(x_access_token)
    if not demo_available():
        raise HTTPException(status_code=404, detail="演示数据不可用")
    return {"timeline": build_timeline()}


@app.get("/api/demo/files/{name}")
async def get_demo_file(name: str, x_access_token: Optional[str] = Header(None)):
    """演示产出的单个文件（图表等）"""
    check_token(x_access_token)
    target = demo_file_path(name)
    if not target:
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(target)


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "active_tasks": task_manager.active_count(),
        "max_concurrent": web_settings.MAX_CONCURRENT_TASKS,
        "token_required": bool(web_settings.SITE_TOKEN),
    }


@app.get("/api/config")
async def public_config():
    """站点公开配置：供前端预填访问令牌与默认模型

    刻意不需要令牌——否则前端拿不到令牌就无法提交请求。
    若需严格鉴权，把 EXPOSE_SITE_TOKEN 设为 false，令牌改由用户手动填写。
    """
    return {
        "site_token": (
            web_settings.SITE_TOKEN if web_settings.EXPOSE_SITE_TOKEN else ""
        ),
        "token_required": bool(web_settings.SITE_TOKEN),
        "defaults": {
            "base_url": web_settings.DEFAULT_BASE_URL,
            "analyzer_model": web_settings.DEFAULT_ANALYZER_MODEL,
            "coder_model": web_settings.DEFAULT_CODER_MODEL,
            "writer_model": web_settings.DEFAULT_WRITER_MODEL,
        },
    }


# ---------------------------------------------------------------- 静态资源

if Path(web_settings.WEB_DIR).exists():
    app.mount(
        "/static",
        StaticFiles(directory=web_settings.WEB_DIR),
        name="static",
    )
