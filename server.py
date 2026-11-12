#!/usr/bin/env python3
"""CCTV mosaic server v3: persistent ffmpeg mjpeg streamer per cam (last-frame atomic write) + HTTP."""
import http.server, socketserver, subprocess, threading, time, os

PORT = 8090
DIR = os.path.dirname(os.path.abspath(__file__))
FRAMES = os.path.join(DIR, "frames")
LOG = os.path.join(DIR, "server.log")
FF = "/mnt/emmc/.hermes/tools/ffmpeg-9.0.1-linux-arm64/bin/ffmpeg"

# sub-stream dulu (main stream sering dipakai app HP), lalu main stream
CAMS = [
    ("CAM 1 - V380",  ["rtsp://192.168.1.5:554/live/ch00_1", "rtsp://192.168.1.5:554/live/ch00_0"]),
    ("CAM 2 - V380",  ["rtsp://192.168.1.8:554/live/ch00_1", "rtsp://192.168.1.8:554/live/ch00_0"]),
    ("CAM 3 - Han River", None),
    ("CAM 4 - Han River", None),
]

SHOLAT_URL = "https://sihat.kemenag.dev/widget/jadwal?wilayah=610201&tampilan=ringkas&tema=otomatis&aksen=netral"

def log(msg):
    try:
        with open(LOG, "a") as f:
            f.write(time.strftime("%H:%M:%S ") + msg + "\n")
    except Exception:
        pass

WIDGET_HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
html,body{height:100%;margin:0;background:#070A14;color:#E7F5F5;font:400 13px/1.3 system-ui,Arial}
.wrap{height:100%;display:flex;flex-direction:column;gap:6px;padding:6px}
.sholat{flex:0 0 34%;border-radius:10px;overflow:hidden;background:#0C3839}
.sholat iframe{width:100%;height:100%;border:0}
.grid{flex:1;display:grid;grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr;gap:6px}
.cell{position:relative;border-radius:10px;overflow:hidden;background:#11151c}
.cell img{width:100%;height:100%;object-fit:cover;display:block}
.tag{position:absolute;left:6px;bottom:4px;font-size:11px;font-weight:600;background:rgba(0,0,0,.55);padding:1px 6px;border-radius:6px}
</style></head><body><div class="wrap">
<div class="sholat"><iframe src="__SHOLAT__"></iframe></div>
<div class="grid">
__CELLS__
</div></div>
<script>
function tick(){var t=Date.now();document.querySelectorAll('.cell img').forEach(function(im){im.src='/frame/'+im.dataset.n+'.jpg?t='+t;});}
tick();setInterval(tick,1200);
</script></body></html>"""

def streamer(idx, urls):
    """Satu ffmpeg persisten per kamera; frame terakhir ditulis atomic ke camN.jpg.
    Ada watchdog: kalau tidak ada data >15 detik, ffmpeg di-kill dan konek ulang."""
    out = os.path.join(FRAMES, f"cam{idx+1}.jpg")
    i = 0
    while True:
        url = urls[i % len(urls)]
        i += 1
        try:
            p = subprocess.Popen([FF, "-hide_banner", "-loglevel", "error", "-rtsp_transport", "tcp",
                                  "-i", url, "-f", "mjpeg", "-q:v", "4", "-an", "pipe:1"],
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            log(f"stream cam{idx+1} start {url}")
            buf = b""
            while True:
                import select as _sel
                r, _, _ = _sel.select([p.stdout], [], [], 15)
                if not r:
                    log(f"stream cam{idx+1} watchdog: no data 15s, kill & reconnect")
                    try: p.kill()
                    except Exception: pass
                    break
                chunk = os.read(p.stdout.fileno(), 65536)
                if not chunk:
                    break
                buf += chunk
                while True:
                    s = buf.find(b"\xff\xd8")
                    if s < 0:
                        buf = buf[-2:]
                        break
                    e = buf.find(b"\xff\xd9", s + 2)
                    if e < 0:
                        buf = buf[s:]
                        break
                    frame = buf[s:e + 2]
                    buf = buf[e + 2:]
                    if len(frame) > 500:
                        with open(out + ".tmp", "wb") as f:
                            f.write(frame)
                        os.replace(out + ".tmp", out)
            p.wait()
            log(f"stream cam{idx+1} ended rc={p.returncode}")
        except Exception as e:
            log(f"stream cam{idx+1} err: {e}")
        time.sleep(2)

def placeholder(idx):
    out = os.path.join(FRAMES, f"cam{idx+1}.jpg")
    ph = os.path.join(FRAMES, f"ph{idx+1}.jpg")
    if os.path.exists(ph):
        try:
            with open(ph, "rb") as f: data = f.read()
            with open(out, "wb") as f: f.write(data)
        except Exception:
            pass

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        p = self.path.split("?")[0]
        if p in ("/", "/widget.html", "/index.html"):
            cells = "".join(
                f'<div class="cell"><img data-n="cam{i+1}" src="/frame/cam{i+1}.jpg">'
                f'<span class="tag">{name}</span></div>'
                for i, (name, _) in enumerate(CAMS))
            html = WIDGET_HTML.replace("__SHOLAT__", SHOLAT_URL).replace("__CELLS__", cells)
            self._send(200, html.encode(), "text/html; charset=utf-8")
        elif p.startswith("/frame/"):
            f = os.path.join(FRAMES, os.path.basename(p))
            if os.path.exists(f):
                with open(f, "rb") as fh: self._send(200, fh.read(), "image/jpeg")
            else:
                self._send(404, b"no frame", "text/plain")
        elif p == "/health":
            self._send(200, b"ok", "text/plain")
        else:
            self._send(404, b"nf", "text/plain")

class TS(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

if __name__ == "__main__":
    os.makedirs(FRAMES, exist_ok=True)
    for i, (name, urls) in enumerate(CAMS):
        if urls:
            threading.Thread(target=streamer, args=(i, urls), daemon=True).start()
        else:
            placeholder(i)
    with TS(("0.0.0.0", PORT), H) as httpd:
        log(f"cctv-mosaic v3 on :{PORT}")
        httpd.serve_forever()
