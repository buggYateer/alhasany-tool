"""الواجهة: سيرفر صغير على الجهاز بيتفتح من المتصفح — على الكمبيوتر، أو من الموبايل على نفس الواي فاي (QR).
python -m alhasany ui
"""
import json
import mimetypes
import os
import secrets as pysecrets
import socket
import threading
import traceback
import urllib.parse
import webbrowser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import pipeline, setup, site, tg, titles
from .config import APP_DIR, load_secrets, load_settings, save_secrets, update_settings, work_dir

PORT = 8770
WEB = Path(__file__).parent / "web"
AUDIO = (".wav", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".amr", ".3gp", ".wma", ".mp4")
JOBS = {}             # id ← {"state", "log", "kind"}
GPU_LOCK = threading.Lock()  # ملف واحد في المرة (كارت الشاشة)


# ---------- مساعدات ----------
def access_key():
    sec = load_secrets()
    if not sec.get("access_key"):
        sec["access_key"] = pysecrets.token_urlsafe(9)
        save_secrets(sec)
    return sec["access_key"]


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def phone_url():
    return f"http://{lan_ip()}:{PORT}/?k={access_key()}"


def qr_svg(text):
    try:
        import qrcode
        import qrcode.image.svg
        img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
        return img.to_string(encoding="unicode")
    except Exception:  # noqa: BLE001 — المكتبة مش متثبتة: اللينك بيظهر مكتوب
        return ""


def raw_dirs():
    out = []
    r = setup.root_dir()
    if r:
        out.append(r / "Raw")
    extra = load_settings().get("raw_dir")
    if extra and Path(extra).is_dir():
        out.append(Path(extra))
    return out


def job_path(jid):
    return work_dir() / f"job_{jid}.json"


def load_job(jid):
    p = job_path(jid)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def save_job(jid, job):
    job_path(jid).write_text(json.dumps(job, ensure_ascii=False, indent=1), encoding="utf-8")


def allowed_file(p):
    """الملفات اللي ينفع تتسمع/تتنزل من الواجهة: جوه فولدر Alhasany أو الخام أو ملفات الشغل بس."""
    try:
        p = Path(p).resolve()
    except OSError:
        return False
    bases = [b.resolve() for b in raw_dirs() + [APP_DIR]] + ([setup.root_dir().resolve()] if setup.root_dir() else [])
    if any(p.is_relative_to(b) for b in bases):
        return True
    for f in work_dir().glob("job_*.json"):
        try:
            if any(Path(x["file"]).resolve() == p for x in json.loads(f.read_text(encoding="utf-8"))["files"]):
                return True
        except (OSError, ValueError, KeyError):
            pass
    return False


def run_bg(jid, kind, fn):
    JOBS[jid] = {"state": "running", "log": [], "kind": kind}

    def log(msg):
        JOBS[jid]["log"].append(str(msg))

    def go():
        try:
            with GPU_LOCK:
                fn(log)
            JOBS[jid]["state"] = "done"
        except Exception as e:  # noqa: BLE001
            log(f"✗ {e}")
            traceback.print_exc()
            JOBS[jid]["state"] = "error"
    threading.Thread(target=go, daemon=True).start()


# ---------- الـ API ----------
def api_status(q, body):
    root = setup.root_dir()
    r = setup.report(root)
    sec = load_secrets()
    s = load_settings()
    return {"root": str(root or ""), "report": r, "drives": setup.drives() if not root else [],
            "suggest": setup.suggest_drive() if not root else "",
            "phone_url": phone_url(), "qr": qr_svg(phone_url()),
            "has_bot": bool(sec.get("bot_token")), "has_gemini": bool(sec.get("gemini_key")),
            "admin_chat": bool(sec.get("admin_chat_id")), "site_sync": bool(s.get("site_sync")),
            "busy": any(j["state"] == "running" for j in JOBS.values())}


def api_setup(q, body):
    if not setup.root_dir():
        setup.make_root(body["parent"])
    root = setup.root_dir()
    jid = "setup"
    if not body.get("install"):  # اختيار الفولدر بس — التنزيل بزرار لوحده وبعد ما تأكد
        return {"root": str(root)}

    def work(log):
        r = setup.report(root)
        if r["missing_packages"]:
            if not setup.install_packages(r["missing_packages"], log):
                raise RuntimeError("تنزيل المكتبات فشل — اتأكد من النت")
        if not r["ffmpeg"]:
            setup.install_ffmpeg(root, log)
        if not r["model"]:
            setup.install_model(root, log)
        log("✓ الجهاز جاهز")
    run_bg(jid, "setup", work)
    return {"job": jid, "root": str(root)}


def api_raw(q, body):
    jobs = {p.stem[4:]: p for p in work_dir().glob("job_*.json")}
    out = []
    for d in raw_dirs():
        for f in sorted(d.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if f.is_file() and f.suffix.lower() in AUDIO:
                st = f.stat()
                out.append({"path": str(f), "name": f.name, "dir": str(d), "mb": round(st.st_size / 2**20, 1),
                            "mtime": st.st_mtime, "job": f.stem if f.stem in jobs else None})
    return {"files": out[:200], "dirs": [str(d) for d in raw_dirs()]}


def api_meta(q, body):
    s = load_settings()
    m = pipeline.default_meta(q["file"], s)
    return {"meta": m, "sheikhs": s["sheikhs"], "guests": s["guest_tags"], "series": s["series"]}


def api_process(q, body):
    path, meta = body["file"], body["meta"]
    if not Path(path).is_file():
        raise ValueError("الملف مش موجود")
    jid = Path(path).stem
    if JOBS.get(jid, {}).get("state") == "running":
        return {"job": jid}

    def work(log):
        job = pipeline.process(path, meta, log=log)
        save_job(jid, job)
    run_bg(jid, "process", work)
    return {"job": jid}


def api_job(q, body):
    jid = q["id"]
    j = JOBS.get(jid, {})
    return {"state": j.get("state") or ("done" if job_path(jid).exists() else "missing"),
            "log": j.get("log", [])[-400:], "job": load_job(jid)}


def api_jobs(q, body):
    out = []
    for p in sorted(work_dir().glob("job_*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:60]:
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append({"id": p.stem[4:], "date": j["meta"].get("date"), "kind": j["meta"].get("kind"),
                    "files": [{"name": f["name"], "role": f["role"], "msg_id": f.get("msg_id"), "published": f.get("published")}
                              for f in j["files"]]})
    running = [{"id": k, "kind": v["kind"]} for k, v in JOBS.items() if v["state"] == "running"]
    return {"jobs": out, "running": running}


def api_caption(q, body):
    jid, idx = body["id"], int(body["idx"])
    job = load_job(jid)
    f = job["files"][idx]
    for k in ("title", "subtitle", "verses", "index_line", "index_section"):
        if k in body:
            f[k] = body[k]
    if body.get("caption") is not None and body.get("manual"):
        f["caption"] = body["caption"]
        f["manual"] = True
    elif f.get("cap_args"):
        f["caption"] = pipeline.build_caption(load_settings(), f["cap_args"], f.get("title", ""), f.get("subtitle"), f.get("verses"))
        f["manual"] = False
    save_job(jid, job)
    return {"file": f}


def api_title(q, body):
    job = load_job(body["id"])
    f = job["files"][int(body["idx"])]
    if not f.get("prompt"):
        raise ValueError("الملف ده ملوش عنوان (تلاوة)")
    return titles.suggest(f["prompt"])


def api_settings(q, body):
    s = load_settings()
    if body:
        allowed = {"sheikhs", "guest_tags", "series", "raw_dir", "hijri_offset_days", "site_sync", "site_update_cmd",
                   "site_channel_json", "site_series_py", "gemini_model"}
        update_settings({k: v for k, v in body.items() if k in allowed})
        s = load_settings()
    sec = load_secrets()
    return {"settings": s, "secrets": {"bot_token": bool(sec.get("bot_token")), "gemini_key": bool(sec.get("gemini_key")),
                                       "admin_chat_id": bool(sec.get("admin_chat_id"))}}


def api_secrets(q, body):
    sec = load_secrets()
    for k in ("bot_token", "gemini_key"):
        v = (body.get(k) or "").strip()
        if v:
            sec[k] = v
            if k == "bot_token":
                sec.pop("admin_chat_id", None)
        if body.get("clear_" + k):
            sec.pop(k, None)
    save_secrets(sec)
    return {"ok": True}


def api_tg_check(q, body):
    info = tg.bot_info()
    chat = tg.admin_chat()
    return {"bot": info, "admin_chat": bool(chat)}


def api_tg_find(q, body):
    jid = body["id"]
    job = load_job(jid)
    names = [f["name"] for f in job["files"] if not f.get("msg_id")]
    logs = []
    found = tg.find_uploads(names, log=logs.append, start=body.get("start"))
    for f in job["files"]:
        if f["name"] in found:
            f["msg_id"] = found[f["name"]]["id"]
            f["current_caption"] = found[f["name"]]["caption"]
    save_job(jid, job)
    return {"found": {k: v["id"] for k, v in found.items()}, "log": logs, "job": job}


def api_tg_setmsg(q, body):
    job = load_job(body["id"])
    f = job["files"][int(body["idx"])]
    mid = int(str(body["msg_id"]).rstrip("/").split("/")[-1])
    m = tg.peek(mid)
    if m is None:
        raise ValueError(f"الرسالة {mid} مش موجودة في القناة")
    f["msg_id"] = mid
    f["current_caption"] = tg.to_html(m.get("caption"), m.get("caption_entities"))
    save_job(body["id"], job)
    return {"file": f}


def api_tg_index_preview(q, body):
    job = load_job(body["id"])
    f = job["files"][int(body["idx"])]
    ser = series_of(job, f)
    if not ser or not ser.get("index_msg"):
        return {"index": None}
    cur = tg.read_index(ser["index_msg"])
    return {"index": ser["index_msg"], "sections": tg.index_sections(cur), "default_line": default_index_line(f, ser),
            "section": tg.section_of(cur, ser.get("last_msg"))}


def series_of(job, f):
    if f["role"] != "lesson":
        return None
    key = (f.get("cap_args") or {}).get("series") or job["meta"].get("series")
    return next((s for s in load_settings()["series"] if s["key"] == key), None)


def default_index_line(f, ser):
    if ser.get("style") == "ayah" and f.get("verses"):
        return f"({f['verses']}) {f.get('subtitle') or f.get('title') or ''}".strip()
    return f.get("title") or ""


def api_tg_publish(q, body):
    """بعد موافقتك: الوصف على الرسالة ← سطر في الفهرس ← الموقع (لو مفتوح)."""
    jid, idx = body["id"], int(body["idx"])
    job = load_job(jid)
    f = job["files"][idx]
    if not f.get("msg_id"):
        raise ValueError("لسه ملقيتش الرسالة بتاعة الملف ده في القناة")
    if "…" in f.get("caption", "").replace("...", "…").split("\n")[0] and not body.get("force"):
        raise ValueError("العنوان لسه فاضي (…) — اكتبه الأول")
    steps, root = [], setup.root_dir()
    if f.get("current_caption"):
        tg.backup(root, f"caption_{f['msg_id']}", f["current_caption"])
    tg.set_caption(f["msg_id"], f["caption"])
    steps.append(f"✓ الوصف اتحط على الرسالة {f['msg_id']}")
    ser = series_of(job, f)
    if ser and ser.get("index_msg") and body.get("add_index", True):
        cur = tg.read_index(ser["index_msg"])
        tg.backup(root, f"index_{ser['index_msg']}", cur)
        line = body.get("index_line") or default_index_line(f, ser)
        new = tg.index_add(cur, f["msg_id"], line, body.get("index_section"), ser.get("numbered", False))
        if new != cur:
            tg.set_index(ser["index_msg"], new)
            steps.append(f"✓ الدرس اتضاف لفهرس {ser['name']} (رسالة {ser['index_msg']})")
        f["index_line"] = line
        # السلسلة: آخر رسالة + آخر رقم (عشان «الدرس السابق» في المرة الجاية)
        s = load_settings()
        for x in s["series"]:
            if x["key"] == ser["key"]:
                x["last_msg"] = f["msg_id"]
                if x.get("numbered") and (f.get("cap_args") or {}).get("number"):
                    x["last_number"] = f["cap_args"]["number"]
        update_settings({"series": s["series"]})
    f["published"] = True
    save_job(jid, job)
    try:
        steps += site.sync(job, f, ser)
    except Exception as e:  # noqa: BLE001 — الموقع ميأثرش على النشر
        steps.append(f"⚠ تحديث الموقع فشل: {e} — هيتعمل المرة الجاية")
    return {"steps": steps, "file": f}


ROUTES = {
    ("GET", "/api/status"): api_status, ("POST", "/api/setup"): api_setup,
    ("GET", "/api/raw"): api_raw, ("GET", "/api/meta"): api_meta,
    ("POST", "/api/process"): api_process, ("GET", "/api/job"): api_job, ("GET", "/api/jobs"): api_jobs,
    ("POST", "/api/caption"): api_caption, ("POST", "/api/title"): api_title,
    ("GET", "/api/settings"): api_settings, ("POST", "/api/settings"): api_settings,
    ("POST", "/api/secrets"): api_secrets,
    ("POST", "/api/tg/check"): api_tg_check, ("POST", "/api/tg/find"): api_tg_find,
    ("POST", "/api/tg/setmsg"): api_tg_setmsg, ("POST", "/api/tg/index"): api_tg_index_preview,
    ("POST", "/api/tg/publish"): api_tg_publish,
}


class Handler(BaseHTTPRequestHandler):
    server_version = "Alhasany"

    def log_message(self, *a):
        pass

    # --- الحماية: الجهاز نفسه مسموح، والموبايل لازم الكود اللي في الـ QR ---
    def _authed(self, q):
        if self.client_address[0] in ("127.0.0.1", "::1"):
            return True
        c = SimpleCookie(self.headers.get("Cookie", ""))
        return (c.get("k") and c["k"].value == access_key()) or q.get("k") == access_key()

    def _send(self, code, body, ctype="application/json; charset=utf-8", headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _route(self, method):
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        if not self._authed(q):
            return self._send(403, "<h2 dir=rtl style='font-family:sans-serif'>افتح الأداة من الـ QR اللي على شاشة الكمبيوتر</h2>",
                              "text/html; charset=utf-8")
        extra = {}
        if q.get("k") == access_key():
            extra["Set-Cookie"] = f"k={access_key()}; Path=/; Max-Age=31536000; SameSite=Lax"
        try:
            if u.path == "/api/upload" and method == "POST":
                return self._send(200, self._upload(q), headers=extra)
            if u.path == "/media":
                return self._media(q)
            fn = ROUTES.get((method, u.path))
            if fn:
                body = {}
                if method == "POST":
                    n = int(self.headers.get("Content-Length") or 0)
                    body = json.loads(self.rfile.read(n) or b"{}") if n else {}
                return self._send(200, fn(q, body), headers=extra)
            return self._static(u.path, extra)
        except (tg.TgError, titles.TitleError, ValueError, KeyError, FileNotFoundError) as e:
            return self._send(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._send(500, {"error": f"حصل خطأ: {e}"})

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def _static(self, path, extra):
        p = (WEB / ("index.html" if path in ("/", "") else path.lstrip("/"))).resolve()
        if not p.is_relative_to(WEB.resolve()) or not p.is_file():
            p = WEB / "index.html"  # روابط الصفحات (#/...) كلها نفس الصفحة
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
            ctype += "; charset=utf-8"
        self._send(200, p.read_bytes(), ctype, extra)

    def _upload(self, q):
        """رفع تسجيل من الموبايل لفولدر Raw (على دفعات، من غير ما يتحمل كله في الذاكرة)."""
        root = setup.root_dir()
        if not root:
            raise ValueError("اختار فولدر الشغل الأول")
        name = Path(q.get("name") or "recording").name
        if Path(name).suffix.lower() not in AUDIO:
            raise ValueError("ده مش ملف صوت")
        dst = root / "Raw" / name
        n = int(self.headers.get("Content-Length") or 0)
        tmp = dst.with_suffix(dst.suffix + ".part")
        with open(tmp, "wb") as out:
            left = n
            while left > 0:
                chunk = self.rfile.read(min(1 << 20, left))
                if not chunk:
                    break
                out.write(chunk)
                left -= len(chunk)
        if left:
            tmp.unlink(missing_ok=True)
            raise ValueError("الرفع اتقطع — جرّب تاني")
        os.replace(tmp, dst)
        return {"path": str(dst), "name": name}

    def _media(self, q):
        """تشغيل/تنزيل ملف صوت (بيدعم التقديم في المشغل)."""
        p = Path(q.get("path", ""))
        if not p.is_file() or not allowed_file(p):
            return self._send(404, {"error": "الملف مش موجود"})
        size = p.stat().st_size
        ctype = mimetypes.guess_type(p.name)[0] or "audio/mpeg"
        start, end = 0, size - 1
        rng = self.headers.get("Range", "")
        if rng.startswith("bytes="):
            a, _, b = rng[6:].split(",")[0].partition("-")
            if a:
                start = int(a)
                end = int(b) if b else end
            else:
                start = size - int(b)
        end = min(end, size - 1)
        self.send_response(206 if rng else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if rng:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if q.get("dl"):
            self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + urllib.parse.quote(p.name))
        self.end_headers()
        with open(p, "rb") as fh:
            fh.seek(start)
            left = end - start + 1
            try:
                while left > 0:
                    chunk = fh.read(min(1 << 18, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                pass


def serve(open_browser=True, port=PORT):
    global PORT
    # لو الرقم مستخدم (زي سيرفر الموقع)، ناخد اللي بعده — ويندوز بيسمح لبرنامجين على نفس الرقم
    # لو واحد على 127.0.0.1 والتاني على 0.0.0.0، فبنتأكد من الاتنين
    def free(p):
        for host in ("127.0.0.1", "0.0.0.0"):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                if s.connect_ex(("127.0.0.1", p)) == 0:
                    return False
                s.close()
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1) if os.name == "nt" else None
                s.bind((host, p))
            except OSError:
                return False
            finally:
                s.close()
        return True
    while not free(port):
        port += 1
    PORT = port
    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    local = f"http://localhost:{port}/"
    # الشاشة السودا بتعرض العربي بالمقلوب ← رسايلها إنجليزي وقصيرة
    print("=" * 56 + "\n  Alhasany tool is running - it opened in your browser.\n"
          "  Keep this window open while you use the tool.\n  Close this window to stop the tool.\n" + "=" * 56)
    print(f"  PC:    {local}\n  Phone: scan the QR code on the home page of the tool")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(local)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
