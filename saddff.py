import os, json, time, hmac, hashlib, threading, asyncio
from datetime import datetime
from urllib.parse import parse_qsl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# روی Space از Secrets می‌خونه؛ برای تست لوکال مستقیم بنویس
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_ID  = int(os.environ.get("OWNER_ID", "0"))
APP_URL   = os.environ.get("APP_URL", "")   # مثل: https://username-tennis.hf.space

LOG_FILE, BEST_FILE = "events.jsonl", "best.json"
loop, bot_app, _seen = None, None, {}

GAME_HTML = r"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
*{margin:0;padding:0}
html,body{height:100%;overflow:hidden;background:#0c5c33;touch-action:none;
  user-select:none;-webkit-user-select:none;font-family:system-ui,'Segoe UI',Tahoma,sans-serif}
canvas{display:block}
</style>
</head>
<body>
<canvas id="c"></canvas>
<script>
var tg = window.Telegram && window.Telegram.WebApp;
if (tg) { tg.ready(); tg.expand(); }
var me = (tg && tg.initDataUnsafe && tg.initDataUnsafe.user) || null;
fetch('/log', {method:'POST', body:'init=' + encodeURIComponent(tg ? tg.initData : '')});

var cv = document.getElementById('c'), ctx = cv.getContext('2d');
var W = 0, H = 0;
function resize(){
  var d = window.devicePixelRatio || 1;
  W = innerWidth; H = innerHeight;
  cv.width = Math.round(W*d); cv.height = Math.round(H*d);
  cv.style.width = W+'px'; cv.style.height = H+'px';
  ctx.setTransform(d,0,0,d,0,0);
}
addEventListener('resize', resize); resize();

var WIN = 5, PW = 90, PH = 14, BR = 9;
var px = 0, ax = 0, bx = 0, by = 0, bvx = 0, bvy = 0;
var ps = 0, as = 0, hits = 0, bestRally = 0;
var mode = 'menu', frame = 0, tick = 0;
var myBest = +(localStorage.getItem('tb') || 0), top = [];

function buzz(k){ try{ if(tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred(k); }catch(e){} }

function serve(toDown){
  bx = W/2; by = H/2; hits = 0;
  var sp = Math.max(5, H/110), a = (Math.random()-.5)*.8;
  bvx = Math.sin(a)*sp*(Math.random()<.5?-1:1);
  bvy = Math.cos(a)*sp*(toDown?1:-1);
}
function startMatch(){
  PW = Math.min(W*.24, 110);
  ps = as = bestRally = 0; px = W/2; ax = W/2;
  serve(Math.random()<.5);
  mode = 'serve'; tick = 50;
}

var pressed = false;
addEventListener('pointerdown', function(e){
  pressed = true; px = e.clientX;
  if (mode === 'menu' || mode === 'over') startMatch();
});
addEventListener('pointermove', function(e){ if(pressed) px = e.clientX; });
addEventListener('pointerup', function(){ pressed = false; });
addEventListener('keydown', function(e){
  if(e.key==='ArrowLeft') px -= 34;
  if(e.key==='ArrowRight') px += 34;
});

function paddleBounce(isPlayer){
  var cx = isPlayer ? px : ax;
  var off = Math.max(-1, Math.min(1, (bx-cx)/(PW/2)));
  var sp = Math.min(Math.hypot(bvx,bvy)*1.06 + .15, Math.max(9, H/50));
  bvx = off*sp*.8;
  bvy = (isPlayer?-1:1)*sp*.62;
  hits++; if(hits > bestRally) bestRally = hits;
  buzz('light');
}
function end(){
  buzz('medium');
  if (ps >= WIN || as >= WIN){ mode = 'over'; submit(); }
  else { mode = 'serve'; tick = 45; serve(by > H); }
}
function step(){
  var pby = by;
  px = Math.max(PW/2, Math.min(W-PW/2, px));
  ax = Math.max(PW/2, Math.min(W-PW/2, ax));
  var wob = Math.sin(frame*.07)*PW*.4;
  var target = bvy < 0 ? bx + wob : W/2;           // AI موقع حمله دنبال توپ، وگرنه وسط
  var aisp = Math.max(4.5, H/120) + Math.min(hits*.3, 6);  // هر رالی سخت‌تر می‌شه
  ax += Math.max(-aisp, Math.min(aisp, target-ax));
  bx += bvx; by += bvy;
  if (bx < BR){ bx = BR; bvx = Math.abs(bvx); }
  if (bx > W-BR){ bx = W-BR; bvx = -Math.abs(bvx); }
  if (bvy>0 && pby+BR <= H-50 && by+BR >= H-50 && Math.abs(bx-px) <= PW/2+BR) paddleBounce(true);
  if (bvy<0 && pby-BR >= 36+PH && by-BR <= 36+PH && Math.abs(bx-ax) <= PW/2+BR) paddleBounce(false);
  if (by > H+40){ as++; end(); }
  else if (by < -40){ ps++; end(); }
}

function submit(){
  fetch('/score', {method:'POST', body:'init=' + encodeURIComponent(tg?tg.initData:'') +
    '&score=' + bestRally + '&won=' + (ps>as?1:0)});
  if (bestRally > myBest){ myBest = bestRally; localStorage.setItem('tb', myBest); }
  loadTop();
}
function loadTop(){
  fetch('/top').then(function(r){ return r.json(); })
    .then(function(j){ top = j; }).catch(function(){});
}
loadTop();

function rr(x,y,w,h,r){
  ctx.beginPath();
  if (ctx.roundRect) ctx.roundRect(x,y,w,h,r); else ctx.rect(x,y,w,h);
  ctx.fill();
}
function drawTop(y){
  if (!top.length) return;
  ctx.font = 'bold 18px system-ui'; ctx.fillStyle = '#ffe14d';
  ctx.fillText('🏆 رکوردی‌ها (طولانی‌ترین رالی)', W/2, y);
  ctx.fillStyle = '#fff'; ctx.font = '16px system-ui';
  for (var i=0; i<Math.min(5, top.length); i++)
    ctx.fillText((i+1)+'. '+top[i].name+' — '+top[i].best, W/2, y+28+i*24);
}
function draw(){
  ctx.fillStyle = '#0c5c33'; ctx.fillRect(0,0,W,H);
  ctx.fillStyle = '#106b3f'; ctx.fillRect(20,20,W-40,H-40);
  ctx.strokeStyle = 'rgba(255,255,255,.35)'; ctx.lineWidth = 2;
  ctx.strokeRect(20,20,W-40,H-40);
  ctx.setLineDash([12,10]);
  ctx.beginPath(); ctx.moveTo(0,H/2); ctx.lineTo(W,H/2); ctx.stroke();
  ctx.setLineDash([]);
  ctx.strokeStyle = 'rgba(255,255,255,.15)';
  ctx.beginPath(); ctx.moveTo(W/2,20); ctx.lineTo(W/2,H-20); ctx.stroke();

  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillStyle = 'rgba(255,255,255,.13)';
  ctx.font = 'bold '+Math.round(Math.min(W,H)/4)+'px system-ui';
  ctx.fillText(ps+'   '+as, W/2, H/2);

  ctx.fillStyle = '#fff';
  ctx.shadowColor = 'rgba(0,0,0,.45)'; ctx.shadowBlur = 6; ctx.shadowOffsetY = 2;
  rr(ax-PW/2, 36, PW, PH, 7);
  rr(px-PW/2, H-50, PW, PH, 7);
  ctx.shadowColor = 'transparent'; ctx.shadowBlur = 0; ctx.shadowOffsetY = 0;

  if (mode==='play' || mode==='serve'){
    ctx.fillStyle = '#e8ff4f';
    ctx.shadowColor = 'rgba(0,0,0,.35)'; ctx.shadowBlur = 8;
    ctx.beginPath(); ctx.arc(bx,by,BR,0,7); ctx.fill();
    ctx.shadowBlur = 0; ctx.shadowColor = 'transparent';
    ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.4;
    ctx.beginPath(); ctx.arc(bx,by,BR,.4,2.7); ctx.stroke();
    ctx.beginPath(); ctx.arc(bx,by,BR,3.5,5.8); ctx.stroke();
  }

  ctx.fillStyle = '#fff';
  if (mode==='menu'){
    ctx.font = 'bold '+Math.round(Math.min(W*.13,52))+'px system-ui';
    ctx.fillText('🎾 مینی‌تنیس', W/2, H/2-120);
    if (me && me.first_name){
      ctx.font = '20px system-ui'; ctx.fillStyle = '#ffe14d';
      ctx.fillText('سلام '+me.first_name+' 👋', W/2, H/2-72); ctx.fillStyle = '#fff';
    }
    ctx.font = '18px system-ui';
    ctx.fillText('انگشتت رو بکش تا راکت حرکت کنه', W/2, H/2-34);
    ctx.fillText('اولین نفری که ۵ امتیاز بگیره برنده‌ست', W/2, H/2-8);
    if (myBest){ ctx.fillStyle='#ffe14d'; ctx.fillText('رکورد رالی تو: '+myBest, W/2, H/2+26); ctx.fillStyle='#fff'; }
    drawTop(H/2+78);
    if (Math.floor(frame/30)%2){ ctx.font='bold 21px system-ui'; ctx.fillText('👆 لمس کن و شروع کن', W/2, H-80); }
  } else if (mode==='serve'){
    ctx.font = 'bold 22px system-ui'; ctx.fillText('آماده…', W/2, H/2-Math.round(H*.18));
    ctx.font = '15px system-ui'; ctx.fillText('رالی: '+hits, W/2, 70);
  } else if (mode==='play'){
    ctx.font = '15px system-ui'; ctx.fillText('رالی: '+hits, W/2, 70);
  } else if (mode==='over'){
    ctx.font = 'bold '+Math.round(Math.min(W*.1,42))+'px system-ui';
    ctx.fillText(ps>as?'🏆 بردی!':'😅 باختی!', W/2, H/2-160);
    ctx.font = '21px system-ui';
    ctx.fillText(ps+' : '+as+'   •   بهترین رالی: '+bestRally, W/2, H/2-112);
    drawTop(H/2-74);
    if (Math.floor(frame/30)%2){ ctx.font='bold 21px system-ui'; ctx.fillText('👆 بازی مجدد', W/2, H-80); }
  }
}
function loop(){
  frame++;
  if (mode==='serve' && --tick <= 0) mode = 'play';
  if (mode==='play') step();
  draw();
  requestAnimationFrame(loop);
}
loop();
</script>
</body>
</html>"""

# ---------- ابزارها ----------
def send_owner(text):
    """خبررسانی به خودت از داخل ترِد وب‌سرور"""
    if not (loop and bot_app and OWNER_ID): return
    try:
        asyncio.run_coroutine_threadsafe(
            bot_app.bot.send_message(OWNER_ID, text), loop).result(timeout=15)
    except Exception as e:
        print("notify err:", e)

def tg_user(init_data):
    """اعتبارسنجی initData مینی‌اپ با هش تلگرام → کاربر واقعی"""
    try:
        if not init_data: return None
        d = dict(parse_qsl(init_data, keep_blank_values=True))
        h = d.pop("hash", "")
        if BOT_TOKEN:
            s = "\n".join(f"{k}={v}" for k, v in sorted(d.items()))
            secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
            if hmac.new(secret, s.encode(), hashlib.sha256).hexdigest() != h:
                return None
        u = json.loads(d.get("user", "{}"))
        return u if u.get("id") else None
    except Exception:
        return None

def full_name(u):
    return (u.get("first_name", "") + " " + (u.get("last_name") or "")).strip()

def log_event(user, action, detail=""):
    rec = {"time": datetime.now().strftime("%Y-%m-%d %H:%M"),
           "action": action, "id": user.get("id"), "name": full_name(user),
           "username": user.get("username"), "detail": str(detail)[:100]}
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

def load_best():
    try:
        with open(BEST_FILE, encoding="utf-8") as f: return json.load(f)
    except Exception: return {}

def upd_best(user, score):
    b, k = load_best(), str(user["id"])
    prev = b.get(k, {}).get("best", 0)
    if score > prev:
        b[k] = {"name": full_name(user)[:16], "username": user.get("username"), "best": score}
        with open(BEST_FILE, "w", encoding="utf-8") as f:
            json.dump(b, f, ensure_ascii=False)
        if prev > 0 or score >= 4:
            un = f" @{user['username']}" if user.get("username") else ""
            send_owner(f"🏆 رکورد رالی: {full_name(user)}{un} — {score}")

# ---------- وب‌سرور ----------
class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/":
            self._send(200, GAME_HTML.encode())
        elif p == "/top":
            top = sorted(load_best().values(), key=lambda v: -v["best"])[:10]
            self._send(200, json.dumps(top, ensure_ascii=False).encode(),
                       "application/json")
        else:
            self._send(404, b"not found")

    def do_POST(self):
        p = self.path.split("?")[0]
        try:
            n = int(self.headers.get("Content-Length", 0))
            data = dict(parse_qsl(self.rfile.read(n).decode()))
        except Exception:
            data = {}
        user = tg_user(data.get("init", ""))
        if not user:
            self._send(403, b"invalid"); return
        if p == "/log":
            log_event(user, "open")
            uid, now = user["id"], time.time()
            if now - _seen.get(uid, 0) > 1800:    # هر نیم ساعت یه خبر، نه بیشتر
                _seen[uid] = now
                un = f"@{user['username']}" if user.get("username") else "—"
                send_owner(f"🎾 {full_name(user)} ({un}) بازی رو باز کرد!")
            self._send(200, b"ok")
        elif p == "/score":
            try: score = int(data.get("score", 0))
            except Exception: score = 0
            log_event(user, "game", f"score={score} won={data.get('won')}")
            upd_best(user, score)
            self._send(200, b"ok")
        else:
            self._send(404, b"not found")

    def log_message(self, *a): pass

# ---------- بات ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    log_event({"id": u.id, "first_name": u.first_name, "last_name": u.last_name,
               "username": u.username}, "bot_start")
    if OWNER_ID and u.id != OWNER_ID:
        try:
            await context.bot.send_message(
                OWNER_ID, f"🔔 /start: {u.full_name} | @{u.username or '—'} | {u.id}")
        except Exception: pass
    kb = None
    if APP_URL:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(
            "🎾 بزن بریم بازی!", web_app=WebAppInfo(url=APP_URL))]])
    await update.message.reply_text(
        "🎾 مینی‌تنیس\nانگشتت رو بکش تا راکت حرکت کنه — اولین نفری که ۵ امتیاز بگیره برنده‌ست!",
        reply_markup=kb)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    users, opens, games = set(), 0, 0
    try:
        with open(LOG_FILE, encoding="utf-8") as f:
            for line in f:
                try: rec = json.loads(line)
                except Exception: continue
                users.add(rec.get("id"))
                if rec.get("action") == "open": opens += 1
                if rec.get("action") == "game": games += 1
    except FileNotFoundError: pass
    msg = [f"👥 کاربر: {len(users)} | 🎮 بازکردن بازی: {opens} | بازی تموم‌شده: {games}", ""]
    for v in sorted(load_best().values(), key=lambda v: -v["best"])[:10]:
        un = f" @{v['username']}" if v.get("username") else ""
        msg.append(f"• {v['name']}{un} — رالی {v['best']}")
    await update.message.reply_text("\n".join(msg) if users else "هنوز هیچی!")

async def post_init(application):
    global loop, bot_app
    loop = asyncio.get_running_loop()
    bot_app = application

# ---------- اجرا ----------
def main():
    threading.Thread(target=lambda: ThreadingHTTPServer(
        ("0.0.0.0", int(os.environ.get("PORT", 7860))), Handler).serve_forever(),
        daemon=True).start()
    print("بازی روی پورت 7860 سرو می‌شه")
    if BOT_TOKEN:
        app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("stats", stats))
        print("بات روشن شد...")
        app.run_polling()
    else:
        import threading as t; t.Event().wait()

if __name__ == "__main__":
    main()
