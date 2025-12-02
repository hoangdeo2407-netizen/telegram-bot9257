# bot.py
import os
import time
import json
import logging
import atexit
import signal
from datetime import datetime
from logging.handlers import RotatingFileHandler
import telebot
from openpyxl import Workbook

# -------------------------
# CẤU HÌNH
# -------------------------
TOKEN = os.environ.get("BOT_TOKEN", "8522802063:AAFKq4aI6DsBZiS_zVf0DzeMcnI1VmODC_Q")
bot = telebot.TeleBot(TOKEN)

DATA_FILE = "bot_data.json"
AUTOSAVE_INTERVAL = 60  # giây

TY_GIA = 28200  # tỷ giá USDT cố định
PHI = 0.02

# -------------------------
# LOGGER
# -------------------------
logger = logging.getLogger("telegram_bot")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

ch = logging.StreamHandler()
ch.setFormatter(formatter)
logger.addHandler(ch)

fh = RotatingFileHandler("bot.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
fh.setFormatter(formatter)
logger.addHandler(fh)

# -------------------------
# DATA (load / save)
# -------------------------
data = {}

def load_data():
    global data
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info("Đã load dữ liệu từ %s", DATA_FILE)
        except Exception as e:
            logger.exception("Không thể load dữ liệu: %s", e)
            data = {}
    else:
        data = {}
        logger.info("Chưa có file dữ liệu, tạo mới.")

def save_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("Đã lưu dữ liệu vào %s", DATA_FILE)
    except Exception as e:
        logger.exception("Lưu dữ liệu thất bại: %s", e)

def _on_exit():
    logger.info("Process kết thúc — lưu dữ liệu...")
    save_data()
atexit.register(_on_exit)

def _signal_handler(signum, frame):
    logger.info("Nhận signal %s — kết thúc.", signum)
    save_data()
    raise SystemExit()

for s in ("SIGINT", "SIGTERM"):
    if hasattr(signal, s):
        signal.signal(getattr(signal, s), _signal_handler)

# -------------------------
# TIỆN ÍCH
# -------------------------
def get_today():
    return datetime.now().strftime("%Y-%m-%d")

def format_money(n):
    try:
        return f"{int(n):,}"
    except:
        return str(n)

def safe_reply(chat_id, text):
    try:
        bot.send_message(chat_id, text)
    except Exception as e:
        logger.exception("Gửi tin nhắn thất bại: %s", e)

# -------------------------
# MESSAGE BUILD
# -------------------------
def build_message(today):
    naps = data.get(today, {}).get("nap", [])
    ruts = data.get(today, {}).get("rut", [])

    tong_nap = sum([x.get("amount", 0) for x in naps])
    tong_rut = sum([x.get("amount", 0) for x in ruts])

    phai_rut = int(tong_nap * (1 - PHI))
    usdt_phai_rut = phai_rut / TY_GIA if TY_GIA else 0
    usdt_rut = tong_rut / TY_GIA if TY_GIA else 0
    con_lai = phai_rut - tong_rut
    usdt_con_lai = con_lai / TY_GIA if TY_GIA else 0

    ds_nap = "\n".join([f"  {i.get('time')}    {format_money(i.get('amount', 0))}" for i in naps]) if naps else ""
    ds_rut = "\n".join([f"  {i.get('time')}    {format_money(i.get('amount', 0))}" for i in ruts]) if ruts else ""

    msg = f"""
📌 Thống kê tự động

📅 Ngày: {today}

🟢 Nạp ({len(naps)} lần):
{ds_nap}

🔴 Rút ({len(ruts)} lần):
{ds_rut}

━━━━━━━━━━━━━━━━━━

💰 Tổng nạp: {format_money(tong_nap)}
💸 Phí: {int(PHI * 100)}%
💱 Tỷ giá USDT: {TY_GIA}

📤 Tiền phải rút: {format_money(phai_rut)} | {usdt_phai_rut:.2f} USDT
📤 Tổng đã rút: {format_money(tong_rut)} | {usdt_rut:.2f} USDT
📥 Còn lại: {format_money(con_lai)} | {usdt_con_lai:.2f} USDT
"""
    return msg

# -------------------------
# HANDLERS
# -------------------------
@bot.message_handler(commands=["r3"])
def r3(message):
    today = get_today()
    if today not in data:
        data[today] = {"nap": [], "rut": []}
    bot.reply_to(message, build_message(today))

@bot.message_handler(commands=["excel"])
def export_excel(message):
    try:
        today = get_today()
        if today not in data or (not data[today]["nap"] and not data[today]["rut"]):
            bot.reply_to(message, "Chưa có dữ liệu hôm nay để xuất file.")
            return

        naps = data[today]["nap"]
        ruts = data[today]["rut"]

        wb = Workbook()
        ws = wb.active
        ws.title = "Thong Ke"
        ws.append(["Thời gian", "Loại", "Số tiền"])

        for item in naps:
            ws.append([item.get("time"), "Nạp", item.get("amount", 0)])
        for item in ruts:
            ws.append([item.get("time"), "Rút", item.get("amount", 0)])

        tong_nap = sum(x.get("amount", 0) for x in naps)
        tong_rut = sum(x.get("amount", 0) for x in ruts)
        con_lai = int(tong_nap * (1 - PHI)) - tong_rut

        ws.append([])
        ws.append(["Tổng nạp", tong_nap])
        ws.append(["Tổng rút", tong_rut])
        ws.append(["Còn lại", con_lai])

        filename = f"Bao_cao_{today}.xlsx"
        wb.save(filename)

        with open(filename, "rb") as f:
            bot.send_document(message.chat.id, f)
        try:
            os.remove(filename)
        except:
            logger.warning("Không xóa được file tạm %s", filename)
    except Exception as e:
        logger.exception("Handler /excel lỗi: %s", e)
        safe_reply(message.chat.id, "Có lỗi khi xuất file Excel.")

@bot.message_handler(commands=["reset"])
def reset_data(message):
    today = get_today()
    if today in data:
        data[today] = {"nap": [], "rut": []}
        bot.reply_to(message, f"Đã reset dữ liệu ngày {today}.")
    else:
        bot.reply_to(message, "Chưa có dữ liệu hôm nay để reset.")

@bot.message_handler(commands=["resetall"])
def reset_all(message):
    global data
    data = {}
    save_data()
    bot.reply_to(message, "Đã reset toàn bộ dữ liệu.")

# -------------------------
# HANDLER TIN NHẮN + / HƯỚNG DẪN
# -------------------------
@bot.message_handler(func=lambda m: isinstance(m.text, str))
def auto_add(message):
    text = message.text.strip()
    today = get_today()
    if today not in data:
        data[today] = {"nap": [], "rut": []}

    # Nạp: +300000
    if text.startswith("+"):
        try:
            amount = int(text[1:].replace(",", "").strip())
        except:
            safe_reply(message.chat.id, "Sai cú pháp. Ví dụ: +300000")
            return
        data[today]["nap"].append({"amount": amount, "time": datetime.now().strftime("%H:%M:%S")})
        bot.reply_to(message, build_message(today))
        return

    # Rút: -1500000
    if text.startswith("-"):
        try:
            amount = int(text[1:].replace(",", "").strip())
        except:
            safe_reply(message.chat.id, "Sai cú pháp. Ví dụ: -1500000")
            return
        data[today]["rut"].append({"amount": amount, "time": datetime.now().strftime("%H:%M:%S")})
        bot.reply_to(message, build_message(today))
        return

    # Nếu không hợp lệ
    safe_reply(message.chat.id, """Lệnh không hợp lệ!
Cú pháp hợp lệ:
+SỐ_TIỀN -> Nạp tiền
-SỐ_TIỀN -> Rút tiền
/r3 -> Xem thống kê
/excel -> Xuất file Excel
/reset -> Reset dữ liệu hôm nay
/resetall -> Reset toàn bộ dữ liệu
""")

# -------------------------
# AUTOSAVE THREAD
# -------------------------
def autosave_loop():
    last = time.time()
    while True:
        time.sleep(1)
        if time.time() - last >= AUTOSAVE_INTERVAL:
            save_data()
            last = time.time()

# -------------------------
# RUN BOT
# -------------------------
def run():
    load_data()
    import threading
    t = threading.Thread(target=autosave_loop, daemon=True)
    t.start()

    backoff = 1
    max_backoff = 300
    logger.info("Bắt đầu vòng lặp polling. TOKEN từ biến môi trường: %s", "có" if os.environ.get("BOT_TOKEN") else "không")
    while True:
        try:
            logger.info("Khởi chạy bot.polling()")
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            logger.exception("Polling lỗi: %s", e)
            wait = max_backoff if "429" in str(e) else backoff
            time.sleep(wait)
            backoff = min(backoff * 2, max_backoff)

if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        logger.info("Nhận Ctrl+C — dừng bot.")
        save_data()
    except SystemExit:
        logger.info("SystemExit — kết thúc.")
        save_data()
    except Exception:
        logger.exception("Lỗi không mong muốn, bot kết thúc.")
        save_data()
