# -*- coding: utf-8 -*-

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import requests
import time
import json
import threading
from datetime import datetime, timedelta
import re
import sqlite3
import random
import string
import urllib3
import os
import sys
import html
from urllib.parse import quote
from contextlib import contextmanager

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================================
# DATABASE CLASS
# ============================================================
class Database:
    def __init__(self, db_file='turbo_bot.db'):
        self.db_file = db_file

    @contextmanager
    def get_connection(self, max_retries=5, retry_delay=0.1):
        conn = None
        for attempt in range(max_retries):
            try:
                conn = sqlite3.connect(self.db_file, timeout=20.0)
                conn.row_factory = sqlite3.Row
                yield conn
                conn.commit()
                conn.close()
                return
            except sqlite3.OperationalError as e:
                if conn:
                    try:
                        conn.rollback()
                        conn.close()
                    except:
                        pass
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                raise
            except Exception:
                if conn:
                    try:
                        conn.rollback()
                        conn.close()
                    except:
                        pass
                raise

    def execute(self, query, params=(), commit=True, fetch_one=False, fetch_all=False):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            if commit:
                conn.commit()
            if fetch_one:
                return cursor.fetchone()
            if fetch_all:
                return cursor.fetchall()
            return cursor

db = Database()

# ============================================================
# CONFIGURATION
# ============================================================
DEFAULT_API_KEY = "IeCCL2LYEBd6eo2wyDYEwXAcGRoEEHa8"
DEFAULT_BASE_URL = "https://bilaisms.shop/stubs/handler_api.php"

BOT_TOKEN = "8872193187:AAE29lM9fdZSPmIUjV9EJ_wueUlEgcw_uC8"

ADMIN_ID = 8309654045
DEPOSIT_ADMIN_ID = 8309654045
ADMINS = [ADMIN_ID, DEPOSIT_ADMIN_ID]

SUPPORT_USERNAME = "Managerphantom"
UPI_ID = "paytm.s1dw5n0@pty"

# ===== AUTO PAYMENT GATEWAY (defaults — changeable from admin panel) =====
PAYMENT_API_KEY = "PAYBDCFCFF18A7CBB5AAC519374"
PAYMENT_API_URL = "https://vcapi.vcstore.site/payment_api.php"
PAYMENT_MERCHANT_NAME = "VC Payment Gateway"

bot = telebot.TeleBot(BOT_TOKEN)

# Simple spinner animation frames
LOADING_FRAMES = ["◐", "◓", "◑", "◒"]
LOADING_MSG = "⏳ <b>Processing... Please wait.</b>"

user_temp_data = {}
services_cache = {}
countries_cache = {}
servers_cache = {}
user_sessions = {}
pending_channel_input = {}
order_timers = {}
api_cache = None
deposit_issue_temp = {}  # store user's deposit issue data

# ============================================================
# DATABASE INITIALIZATION
# ============================================================
def init_db():
    try:
        with db.get_connection() as conn:
            c = conn.cursor()
            # Users table (extended)
            c.execute('''CREATE TABLE IF NOT EXISTS users
                         (user_id INTEGER PRIMARY KEY,
                          username TEXT,
                          first_name TEXT,
                          last_name TEXT,
                          balance REAL DEFAULT 0,
                          joined_date TEXT,
                          total_orders INTEGER DEFAULT 0,
                          successful_orders INTEGER DEFAULT 0,
                          total_spent REAL DEFAULT 0,
                          is_admin INTEGER DEFAULT 0,
                          rejections INTEGER DEFAULT 0,
                          is_banned INTEGER DEFAULT 0,
                          total_gateway_fees REAL DEFAULT 0,
                          referral_code TEXT UNIQUE,
                          referred_by INTEGER,
                          total_referrals INTEGER DEFAULT 0,
                          total_commission REAL DEFAULT 0)''')
            c.execute('''CREATE TABLE IF NOT EXISTS orders
                         (order_id TEXT PRIMARY KEY,
                          user_id INTEGER,
                          service_code TEXT,
                          service_name TEXT,
                          phone_number TEXT,
                          price REAL,
                          status TEXT,
                          order_date TEXT,
                          completion_date TEXT,
                          cancel_time TEXT,
                          expires_at TEXT,
                          otps_received INTEGER DEFAULT 0)''')
            c.execute('''CREATE TABLE IF NOT EXISTS transactions
                         (txn_id TEXT PRIMARY KEY,
                          user_id INTEGER,
                          amount REAL,
                          gateway_fee REAL DEFAULT 0,
                          type TEXT,
                          status TEXT,
                          utr_number TEXT,
                          screenshot TEXT,
                          order_id TEXT,
                          admin_note TEXT,
                          created_date TEXT,
                          processed_date TEXT)''')
            c.execute('''CREATE TABLE IF NOT EXISTS promoCodes
                         (code TEXT PRIMARY KEY,
                          amount REAL,
                          uses_left INTEGER,
                          max_uses INTEGER,
                          created_by INTEGER,
                          created_date TEXT,
                          expiry_date TEXT)''')
            c.execute('''CREATE TABLE IF NOT EXISTS pending_transactions
                         (txn_id TEXT PRIMARY KEY,
                          user_id INTEGER,
                          amount REAL,
                          gateway_fee REAL DEFAULT 0,
                          utr_number TEXT,
                          screenshot TEXT,
                          order_id TEXT,
                          created_date TEXT)''')
            c.execute('''CREATE TABLE IF NOT EXISTS force_join_channels
                         (channel_id TEXT PRIMARY KEY,
                          channel_type TEXT,
                          channel_link TEXT,
                          channel_name TEXT,
                          added_by INTEGER,
                          added_date TEXT)''')
            c.execute('''CREATE TABLE IF NOT EXISTS referral_commissions
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          referrer_id INTEGER,
                          referred_id INTEGER,
                          amount REAL,
                          deposit_id TEXT,
                          created_date TEXT)''')
            c.execute('''CREATE TABLE IF NOT EXISTS service_prices
                         (service_code TEXT PRIMARY KEY,
                          api_price REAL,
                          sell_price REAL,
                          updated_by INTEGER,
                          updated_date TEXT)''')
            c.execute('''CREATE TABLE IF NOT EXISTS bug_reports
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          user_id INTEGER,
                          text TEXT,
                          media_type TEXT,
                          media_id TEXT,
                          status TEXT DEFAULT 'pending',
                          created_date TEXT)''')
            c.execute('''CREATE TABLE IF NOT EXISTS feedback
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          user_id INTEGER,
                          text TEXT,
                          created_date TEXT)''')
            c.execute('''CREATE TABLE IF NOT EXISTS settings
                         (key TEXT PRIMARY KEY,
                          value TEXT)''')
            c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('maintenance', 'false')")
            c.execute('''CREATE TABLE IF NOT EXISTS api_settings
                         (id INTEGER PRIMARY KEY CHECK (id=1),
                          api_key TEXT,
                          base_url TEXT,
                          updated_at TEXT)''')
            c.execute("INSERT OR IGNORE INTO api_settings (id, api_key, base_url, updated_at) VALUES (1, ?, ?, ?)",
                      (DEFAULT_API_KEY, DEFAULT_BASE_URL, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

            # === FIX: Custom servers table with auto-migration ===
            try:
                # Check if table exists and has server_id column
                c.execute("SELECT server_id FROM custom_servers LIMIT 1")
            except sqlite3.OperationalError:
                # If table is missing or doesn't have server_id, fix it
                print("⚠️ Fixing custom_servers table schema...")
                c.execute("DROP TABLE IF EXISTS custom_servers")
                c.execute('''CREATE TABLE custom_servers
                             (server_id TEXT PRIMARY KEY,
                              server_name TEXT,
                              added_by INTEGER,
                              added_date TEXT)''')

            # === NEW: gateway settings defaults ===
            for k, v in [('gateway_api_key', PAYMENT_API_KEY),
                         ('gateway_api_url', PAYMENT_API_URL),
                         ('gateway_merchant', PAYMENT_MERCHANT_NAME)]:
                c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

            # Ensure admin exists and has admin flag
            c.execute("SELECT * FROM users WHERE user_id = ?", (ADMIN_ID,))
            if not c.fetchone():
                ref_code = generate_referral_code(ADMIN_ID)
                c.execute("INSERT INTO users (user_id, username, first_name, joined_date, is_admin, balance, referral_code) VALUES (?, ?, ?, ?, ?, ?, ?)",
                          (ADMIN_ID, "admin", "Admin", datetime.now().strftime("%Y-%m-%d"), 1, 1000, ref_code))
            else:
                c.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (ADMIN_ID,))
            conn.commit()

            # Add otps_received column to orders if missing
            try:
                c.execute("ALTER TABLE orders ADD COLUMN otps_received INTEGER DEFAULT 0")
            except:
                pass

            print("✅ Database initialized.")
    except Exception as e:
        print(f"❌ init_db error: {e}")

def generate_referral_code(user_id):
    return f"REF{user_id}{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}"

# ============================================================
# HELPER FUNCTIONS
# ============================================================
def get_user(user_id):
    return db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,), fetch_one=True)

def create_user_if_not_exists(user_id, username, first_name, last_name):
    with db.get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        if not c.fetchone():
            ref_code = generate_referral_code(user_id)
            c.execute("INSERT INTO users (user_id, username, first_name, last_name, joined_date, referral_code) VALUES (?, ?, ?, ?, ?, ?)",
                      (user_id, username, first_name, last_name, datetime.now().strftime("%Y-%m-%d"), ref_code))
            conn.commit()
            return True
    return False

def get_user_balance(user_id):
    row = db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,), fetch_one=True)
    return float(row[0]) if row and row[0] is not None else 0.0

def update_user_balance(user_id, amount, add=True):
    with db.get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        current = float(row[0]) if row and row[0] is not None else 0.0
        new_bal = current + amount if add else current - amount
        if new_bal < 0:
            new_bal = 0
        c.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_bal, user_id))
        conn.commit()
        return new_bal

def is_admin(user_id):
    if user_id == ADMIN_ID:
        db.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (user_id,))
        return True
    row = db.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,), fetch_one=True)
    return row and row[0] == 1

def get_admins():
    return db.execute("SELECT user_id, username, first_name FROM users WHERE is_admin = 1", fetch_all=True)

def add_admin(user_id):
    db.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (user_id,))

def remove_admin(user_id):
    if user_id == ADMIN_ID:
        return False
    db.execute("UPDATE users SET is_admin = 0 WHERE user_id = ?", (user_id,))
    return True

def is_user_banned(user_id):
    row = db.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,), fetch_one=True)
    return row and row[0] == 1

def ban_user(user_id):
    db.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,))

def unban_user(user_id):
    db.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (user_id,))

def get_referral_code(user_id):
    row = db.execute("SELECT referral_code FROM users WHERE user_id = ?", (user_id,), fetch_one=True)
    return row[0] if row else None

def get_user_by_referral_code(code):
    row = db.execute("SELECT user_id FROM users WHERE referral_code = ?", (code,), fetch_one=True)
    return row[0] if row else None

def set_referred_by(user_id, referrer_id):
    db.execute("UPDATE users SET referred_by = ? WHERE user_id = ?", (referrer_id, user_id))

def add_commission(referrer_id, referred_id, amount, deposit_id):
    db.execute("INSERT INTO referral_commissions (referrer_id, referred_id, amount, deposit_id, created_date) VALUES (?, ?, ?, ?, ?)",
               (referrer_id, referred_id, amount, deposit_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    update_user_balance(referrer_id, amount, add=True)
    db.execute("UPDATE users SET total_commission = total_commission + ? WHERE user_id = ?", (amount, referrer_id))
    db.execute("UPDATE users SET total_referrals = total_referrals + 1 WHERE user_id = ?", (referrer_id,))

def get_maintenance_mode():
    row = db.execute("SELECT value FROM settings WHERE key = 'maintenance'", fetch_one=True)
    return row and row[0] == 'true'

def set_maintenance_mode(state):
    db.execute("UPDATE settings SET value = ? WHERE key = 'maintenance'", ('true' if state else 'false',))

def get_api_settings():
    global api_cache
    if api_cache:
        return api_cache
    row = db.execute("SELECT api_key, base_url FROM api_settings WHERE id = 1", fetch_one=True)
    if row:
        api_cache = (row[0], row[1])
        return api_cache
    return (DEFAULT_API_KEY, DEFAULT_BASE_URL)

def set_api_settings(api_key, base_url):
    global api_cache
    db.execute("UPDATE api_settings SET api_key = ?, base_url = ?, updated_at = ? WHERE id = 1",
               (api_key, base_url, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    api_cache = (api_key, base_url)
    return True

# ===== NEW: Gateway settings helpers =====
def get_gateway_settings():
    keys = {r[0]: r[1] for r in db.execute(
        "SELECT key, value FROM settings WHERE key IN ('gateway_api_key','gateway_api_url','gateway_merchant')",
        fetch_all=True)}
    return (
        keys.get('gateway_api_key', PAYMENT_API_KEY),
        keys.get('gateway_api_url', PAYMENT_API_URL),
        keys.get('gateway_merchant', PAYMENT_MERCHANT_NAME)
    )

def set_gateway_settings(api_key=None, api_url=None, merchant=None):
    if api_key is not None:
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('gateway_api_key', ?)", (api_key,))
    if api_url is not None:
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('gateway_api_url', ?)", (api_url,))
    if merchant is not None:
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('gateway_merchant', ?)", (merchant,))
    return True

# ===== NEW: Custom server helpers =====
def get_custom_servers():
    return db.execute("SELECT server_id, server_name FROM custom_servers", fetch_all=True)

def add_custom_server(server_id, server_name, admin_id):
    db.execute("INSERT OR REPLACE INTO custom_servers (server_id, server_name, added_by, added_date) VALUES (?, ?, ?, ?)",
               (server_id, server_name, admin_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

def remove_custom_server(server_id):
    db.execute("DELETE FROM custom_servers WHERE server_id = ?", (server_id,))

def get_service_price(service_code):
    row = db.execute("SELECT api_price, sell_price FROM service_prices WHERE service_code = ?", (service_code,), fetch_one=True)
    if row:
        return row[1] if row[1] is not None else row[0]
    services = get_services_list()
    if services and service_code in services:
        api_price = float(services[service_code].get('price', 10))
        db.execute("INSERT OR IGNORE INTO service_prices (service_code, api_price, sell_price, updated_by, updated_date) VALUES (?, ?, ?, ?, ?)",
                   (service_code, api_price, api_price, ADMIN_ID, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        return api_price
    return 10

def update_service_price(service_code, sell_price, admin_id):
    db.execute("UPDATE service_prices SET sell_price = ?, updated_by = ?, updated_date = ? WHERE service_code = ?",
               (sell_price, admin_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), service_code))

def get_all_service_prices():
    return db.execute("SELECT service_code, api_price, sell_price, updated_date FROM service_prices ORDER BY service_code", fetch_all=True)

def log_bug_report(user_id, text, media_type=None, media_id=None):
    db.execute("INSERT INTO bug_reports (user_id, text, media_type, media_id, created_date) VALUES (?, ?, ?, ?, ?)",
               (user_id, text, media_type, media_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

def get_all_bug_reports(status='pending'):
    return db.execute("SELECT * FROM bug_reports WHERE status = ? ORDER BY created_date DESC", (status,), fetch_all=True)

def resolve_bug_report(report_id):
    db.execute("UPDATE bug_reports SET status = 'resolved' WHERE id = ?", (report_id,))

def log_feedback(user_id, text):
    db.execute("INSERT INTO feedback (user_id, text, created_date) VALUES (?, ?, ?)",
               (user_id, text, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

def get_all_feedback():
    return db.execute("SELECT * FROM feedback ORDER BY created_date DESC", fetch_all=True)

def get_user_stats():
    total_users = db.execute("SELECT COUNT(*) FROM users", fetch_one=True)[0]
    total_balance = db.execute("SELECT SUM(balance) FROM users", fetch_one=True)[0] or 0
    total_revenue = db.execute("SELECT SUM(amount) FROM transactions WHERE type='deposit' AND status='completed'", fetch_one=True)[0] or 0
    total_orders = db.execute("SELECT COUNT(*) FROM orders WHERE status='completed'", fetch_one=True)[0]
    pending = db.execute("SELECT COUNT(*) FROM pending_transactions", fetch_one=True)[0]
    return total_users, total_balance, total_revenue, total_orders, pending

def get_top_referrers(limit=10):
    return db.execute("SELECT user_id, total_referrals, total_commission FROM users WHERE total_referrals > 0 ORDER BY total_referrals DESC LIMIT ?", (limit,), fetch_all=True)

def get_top_otp_buyers(limit=10):
    return db.execute("SELECT user_id, total_orders, total_spent FROM users WHERE total_orders > 0 ORDER BY total_orders DESC LIMIT ?", (limit,), fetch_all=True)

def get_top_depositors(limit=10):
    return db.execute("SELECT user_id, SUM(amount) as total_deposit FROM transactions WHERE type='deposit' AND status='completed' GROUP BY user_id ORDER BY total_deposit DESC LIMIT ?", (limit,), fetch_all=True)

def get_user_total_deposit(user_id):
    row = db.execute("SELECT SUM(amount) FROM transactions WHERE user_id = ? AND type='deposit' AND status='completed'", (user_id,), fetch_one=True)
    return row[0] if row and row[0] is not None else 0

# ============================================================
# API FUNCTIONS
# ============================================================
def api_request_json(params):
    api_key, base_url = get_api_settings()
    params['api_key'] = api_key
    try:
        resp = requests.get(base_url, params=params, timeout=30, verify=False)
        if resp.status_code == 429:
            retry = int(resp.headers.get('Retry-After', 5))
            time.sleep(retry)
            return api_request_json(params)
        text = resp.text.strip()
        if text.startswith('ACCESS_BALANCE:'):
            bal = text.replace('ACCESS_BALANCE:', '')
            try:
                return {"status": "OK", "balance": float(bal)}
            except:
                return {"status": "OK", "balance": 0}
        elif text.startswith('ACCESS_NUMBER:'):
            parts = text.split(':')
            if len(parts) >= 3:
                return {"status": "OK", "order_id": parts[1], "phone_number": parts[2]}
            else:
                return {"status": "ERROR", "message": "Invalid format"}
        elif text.startswith('STATUS_OK:'):
            sms = text.replace('STATUS_OK:', '')
            return {"status": "OK", "sms": sms}
        elif text == 'STATUS_WAIT_CODE':
            return {"status": "WAITING"}
        elif text == 'STATUS_CANCEL':
            return {"status": "CANCELLED"}
        elif text == 'ACCESS_ACTIVATION':
            return {"status": "COMPLETED"}
        elif text.startswith('EARLY_CANCEL_DENIED:'):
            sec = text.split(':')[1]
            return {"status": "ERROR", "message": f"Wait {sec} seconds"}
        elif text == 'NO_NUMBER':
            return {"status": "ERROR", "message": "No numbers"}
        elif text == 'NO_BALANCE':
            return {"status": "ERROR", "message": "Insufficient API balance"}
        elif text.startswith('BAD_SERVICE'):
            return {"status": "ERROR", "message": "Invalid service"}
        elif text.startswith('BAD_COUNTRY'):
            return {"status": "ERROR", "message": "Invalid country"}
        elif text.startswith('{'):
            try:
                return json.loads(text)
            except:
                return {"status": "UNKNOWN", "raw": text}
        else:
            return {"status": "UNKNOWN", "raw": text}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

def get_balance():
    r = api_request_json({'action': 'getBalance'})
    if r.get('status') == 'OK':
        return r.get('balance', 0)
    return 0

def get_countries():
    global countries_cache
    if countries_cache:
        return countries_cache
    r = api_request_json({'action': 'getCountries'})
    if isinstance(r, dict) and 'status' not in r:
        countries_cache = r
        return r
    return {}

def get_servers():
    global servers_cache
    if servers_cache:
        return servers_cache
    r = api_request_json({'action': 'getServers'})
    if isinstance(r, dict) and 'status' not in r:
        servers_cache = r
        return r
    return {}

def get_services_list(country_code='22', server=None):
    global services_cache
    key = f"{country_code}_{server}" if server else country_code
    if key in services_cache:
        return services_cache[key]
    params = {'action': 'getServices', 'country': country_code}
    if server:
        params['server'] = server
    r = api_request_json(params)
    if isinstance(r, dict) and 'status' not in r:
        services_cache[key] = r
        return r
    return {}

def get_number(service_code, country_code='22', server=None):
    params = {'action': 'getNumber', 'service': service_code, 'country': country_code}
    if server:
        params['server'] = server
    return api_request_json(params)

def get_activation_status(activation_id):
    return api_request_json({'action': 'getStatus', 'id': activation_id})

def set_activation_status(activation_id, status):
    return api_request_json({'action': 'setStatus', 'id': activation_id, 'status': status})

# ============================================================
# CLASSES
# ============================================================
class OTPSession:
    def __init__(self, user_id, service, service_name, order_id, activation_id, phone_number, price, country_code=None):
        self.user_id = user_id
        self.service = service
        self.service_name = service_name
        self.order_id = order_id
        self.activation_id = activation_id
        self.phone_number = phone_number
        self.price = price
        self.country_code = country_code
        self.status = "waiting"
        self.start_time = datetime.now()
        self.expires_at = datetime.now() + timedelta(minutes=20)
        self.monitoring = False
        self.otps_received = []
        self.cancel_allowed_from = datetime.now() + timedelta(minutes=2)

    def can_cancel(self):
        return datetime.now() >= self.cancel_allowed_from

    def get_remaining_time(self):
        rem = self.expires_at - datetime.now()
        if rem.total_seconds() <= 0:
            return "Expired"
        minutes = int(rem.total_seconds() // 60)
        seconds = int(rem.total_seconds() % 60)
        return f"{minutes:02d}:{seconds:02d}"

    def get_cancel_wait_time(self):
        if self.can_cancel():
            return 0
        rem = self.cancel_allowed_from - datetime.now()
        return int(rem.total_seconds())

# ============================================================
# LOADING ANIMATION
# ============================================================
def animate_loading(chat_id, msg_id, step, total, custom=None):
    try:
        frame = LOADING_FRAMES[step % len(LOADING_FRAMES)]
        progress = int((step / total) * 20) if total else 0
        bar = "█" * progress + "░" * (20 - progress)
        text = f"{frame} <b>Fetching number...</b>\n\n<code>{bar}</code> {step}/{total}\n\n⏳ Please wait..."
        bot.edit_message_text(text, chat_id, msg_id, parse_mode='HTML')
    except:
        pass

# ============================================================
# KEYBOARDS
# ============================================================
def main_menu_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("Get Number", callback_data="get_number", style="primary", icon_custom_emoji_id="5445146945024720188"),
        InlineKeyboardButton("My Profile", callback_data="profile", style="primary", icon_custom_emoji_id="5445372439397691719"),
        InlineKeyboardButton("Balance", callback_data="check_balance", style="success", icon_custom_emoji_id="5444960062407732826"),
        InlineKeyboardButton("Deposit", callback_data="deposit", style="success", icon_custom_emoji_id="5447453226498552490"),
        InlineKeyboardButton("Deposit Issue", callback_data="deposit_issue", style="danger", icon_custom_emoji_id="5447332224384925505"),
        InlineKeyboardButton("Promo Code", callback_data="claim_promo", style="success", icon_custom_emoji_id="5444860552310457690"),
        InlineKeyboardButton("Referral", callback_data="referral", style="primary", icon_custom_emoji_id="5445371412900508977"),
        InlineKeyboardButton("Feedback", callback_data="feedback", style="primary", icon_custom_emoji_id="5445059250382469069"),
        InlineKeyboardButton("Report Bug", callback_data="report_bug", style="danger", icon_custom_emoji_id="5447611706496808621"),
        InlineKeyboardButton("Support", callback_data="support", style="primary", icon_custom_emoji_id="5445046442789999895")
    )
    return kb

def admin_panel_keyboard():
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton("📊 STATS", callback_data="admin_stats"),
        InlineKeyboardButton("👥 USERS", callback_data="admin_users"),
        InlineKeyboardButton("🤖 ALL BOTS", callback_data="admin_bots")
    )
    kb.add(
        InlineKeyboardButton("💳 PAYMENTS", callback_data="admin_payments"),
        InlineKeyboardButton("📢 BROADCAST", callback_data="admin_broadcast"),
        InlineKeyboardButton("⚙️ SETTINGS", callback_data="admin_settings")
    )
    kb.add(
        InlineKeyboardButton("👤 MANAGE USER", callback_data="admin_manage_user"),
        InlineKeyboardButton("🔐 ADMINS", callback_data="admin_manage_admins"),
        InlineKeyboardButton("💾 BACKUP", callback_data="admin_backup")
    )
    kb.add(
        InlineKeyboardButton("🚫 BAN/UNBAN", callback_data="admin_ban"),
        InlineKeyboardButton("🎁 GIVE PLAN", callback_data="admin_give_plan"),
        InlineKeyboardButton("🎫 COUPONS", callback_data="admin_coupons")
    )
    kb.add(
        InlineKeyboardButton("🎟️ TICKETS", callback_data="admin_tickets"),
        InlineKeyboardButton("🔧 MAINTENANCE", callback_data="admin_maintenance"),
        InlineKeyboardButton("💰 SERVICE PRICES", callback_data="admin_service_prices")
    )
    kb.add(
        InlineKeyboardButton("🏆 LEADERBOARD", callback_data="admin_leaderboard"),
        InlineKeyboardButton("📋 REFERRALS", callback_data="admin_referrals"),
        InlineKeyboardButton("📊 USER STATS", callback_data="admin_user_stats")
    )
    kb.add(
        InlineKeyboardButton("🔍 SEARCH SERVICE", callback_data="admin_search_service"),
        InlineKeyboardButton("🏠 FORCE JOIN", callback_data="admin_force_join"),
        InlineKeyboardButton("📝 FEEDBACK", callback_data="admin_feedback")
    )
    kb.add(InlineKeyboardButton("🔙 MAIN MENU", callback_data="main_menu"))
    return kb

# ===== NEW Keyboards =====
def settings_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🔑 OTP API Key", callback_data="set_otp_key"),
        InlineKeyboardButton("🌐 OTP Base URL", callback_data="set_otp_url"),
        InlineKeyboardButton("💳 Gateway API Key", callback_data="set_gw_key"),
        InlineKeyboardButton("🔗 Gateway URL", callback_data="set_gw_url"),
        InlineKeyboardButton("🏪 Merchant Name", callback_data="set_gw_merchant"),
        InlineKeyboardButton("🖥️ Servers", callback_data="set_servers"),
        InlineKeyboardButton("👁️ View All Settings", callback_data="set_view"),
        InlineKeyboardButton("🔙 Back", callback_data="admin_panel")
    )
    return kb

def servers_settings_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("➕ Add Server", callback_data="srv_add"),
        InlineKeyboardButton("🗑️ Remove Server", callback_data="srv_remove_menu"),
        InlineKeyboardButton("📋 List Servers", callback_data="srv_list"),
        InlineKeyboardButton("🔙 Back", callback_data="admin_settings")
    )
    return kb

def backup_keyboard():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("📥 Export Database", callback_data="backup_db"),
        InlineKeyboardButton("📊 Export Users CSV", callback_data="backup_users_csv"),
        InlineKeyboardButton("📊 Export Orders CSV", callback_data="backup_orders_csv"),
        InlineKeyboardButton("📊 Export Transactions CSV", callback_data="backup_txn_csv"),
        InlineKeyboardButton("🔙 Back", callback_data="admin_panel")
    )
    return kb

def manage_admins_keyboard():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("📋 List Admins", callback_data="adm_list"),
        InlineKeyboardButton("➕ Add Admin", callback_data="adm_add"),
        InlineKeyboardButton("➖ Remove Admin", callback_data="adm_remove"),
        InlineKeyboardButton("🔙 Back", callback_data="admin_panel")
    )
    return kb

def manage_user_keyboard(user_id, is_banned=False, is_admin_flag=False):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("➕ Add Balance", callback_data=f"mu_addbal_{user_id}"),
        InlineKeyboardButton("➖ Remove Balance", callback_data=f"mu_rmbal_{user_id}")
    )
    kb.add(
        InlineKeyboardButton("✅ Unban" if is_banned else "🚫 Ban", callback_data=f"mu_toggleban_{user_id}"),
        InlineKeyboardButton("➖ Remove Admin" if is_admin_flag else "👑 Make Admin", callback_data=f"mu_toggleadmin_{user_id}")
    )
    kb.add(
        InlineKeyboardButton("📦 View Orders", callback_data=f"mu_orders_{user_id}"),
        InlineKeyboardButton("💸 View TXNs", callback_data=f"mu_txns_{user_id}")
    )
    kb.add(
        InlineKeyboardButton("🔄 Refresh", callback_data=f"mu_view_{user_id}"),
        InlineKeyboardButton("🔙 Back", callback_data="admin_manage_user")
    )
    return kb

def create_force_join_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("➕ Add Channel", callback_data="add_channel"),
        InlineKeyboardButton("📋 Channel List", callback_data="channel_list"),
        InlineKeyboardButton("🗑 Remove Channel", callback_data="remove_channel_menu"),
        InlineKeyboardButton("🔙 Back", callback_data="admin_panel")
    )
    return kb

def profile_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("Recent Orders", callback_data="recent_orders", style="primary", icon_custom_emoji_id="5884479287171485878"),
        InlineKeyboardButton("Transactions", callback_data="recent_transactions", style="primary", icon_custom_emoji_id="6237887278098684962"),
        InlineKeyboardButton("Referral", callback_data="referral", style="success", icon_custom_emoji_id="6052886672834566125"),
        InlineKeyboardButton("Main Menu", callback_data="main_menu", style="danger", icon_custom_emoji_id="5253997076169115797")
    )
    return kb

def referral_keyboard():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("My Referrals", callback_data="my_referrals", style="success", icon_custom_emoji_id="5445371412900508977"),
        InlineKeyboardButton("Back", callback_data="profile", style="danger", icon_custom_emoji_id="5253997076169115797")
    )
    return kb

def services_keyboard(services, country_code='22'):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🔍 Search Service", callback_data="search_service"))
    kb.add(InlineKeyboardButton("🌍 Change Country", callback_data="select_country"))
    count = 0
    for code, info in list(services.items())[:50]:
        name = info.get('name', code.upper())[:30]
        price = get_service_price(code)
        kb.add(InlineKeyboardButton(f"📱 {name} - ₹{price}", callback_data=f"select_service_{code}|{price}|{country_code}"))
        count += 1
    if count >= 50:
        kb.add(InlineKeyboardButton("📄 Next ➡️", callback_data=f"next_page_1_{country_code}"))
    kb.add(InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_services_{country_code}"))
    kb.add(InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
    return kb

def country_keyboard(countries):
    kb = InlineKeyboardMarkup(row_width=2)
    for code, name in list(countries.items())[:20]:
        kb.add(InlineKeyboardButton(f"🌍 {name}", callback_data=f"select_country_{code}"))
    kb.add(InlineKeyboardButton("🔙 Back", callback_data="get_number"))
    return kb

def order_management_keyboard(activation_id, otp_count=0, session=None):
    kb = InlineKeyboardMarkup(row_width=2)
    if session:
        remaining = session.get_remaining_time()
        cancel_wait = session.get_cancel_wait_time()
        kb.add(InlineKeyboardButton(f"⏱️ {remaining}", callback_data="dummy"))
        if otp_count == 0:
            kb.add(InlineKeyboardButton("🔄 Get OTP", callback_data=f"check_otp_{activation_id}"))
        else:
            kb.add(InlineKeyboardButton(f"📱 Get OTP ({otp_count} received)", callback_data=f"check_otp_{activation_id}"))
        if session.can_cancel():
            kb.add(InlineKeyboardButton("❌ Cancel Order", callback_data=f"cancel_{activation_id}"))
        else:
            kb.add(InlineKeyboardButton(f"⏳ Cancel in {cancel_wait}s", callback_data="cancel_not_allowed"))
    else:
        kb.add(InlineKeyboardButton("🔄 Get OTP", callback_data=f"check_otp_{activation_id}"))
        kb.add(InlineKeyboardButton("❌ Cancel Order", callback_data=f"cancel_{activation_id}"))
    kb.add(InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
    return kb

def deposit_keyboard(order_id, amount):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("I Have Paid", callback_data=f"check_payment_{order_id}", style="success", icon_custom_emoji_id="5447242579827523388"),
    )
    return kb

def force_join_keyboard_user(link, cid):
    kb = InlineKeyboardMarkup(row_width=1)
    if link and link.startswith('http'):
        kb.add(InlineKeyboardButton("Join Channel", url=link, style="primary", icon_custom_emoji_id="6052886672834566125"))
    elif link:
        kb.add(InlineKeyboardButton("Join Channel", url=f"https://t.me/{link.replace('@', '')}", style="primary", icon_custom_emoji_id="6052886672834566125"))
    else:
        kb.add(InlineKeyboardButton("Join Channel", url=f"https://t.me/c/{str(cid).replace('-100', '')}", style="primary", icon_custom_emoji_id="6052886672834566125"))
    kb.add(InlineKeyboardButton("I've Joined", callback_data="check_joined", style="success", icon_custom_emoji_id="5208727996315220567"))
    return kb

def confirmation_keyboard(service_code, service_name, price, country_code, server=None):
    kb = InlineKeyboardMarkup(row_width=2)
    server_param = f"|{server}" if server else ""
    kb.add(
        InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_{service_code}|{country_code}{server_param}"),
        InlineKeyboardButton("❌ Cancel", callback_data="main_menu")
    )
    return kb

# ============================================================
# BOT MESSAGE HANDLERS
# ============================================================
@bot.message_handler(commands=['start'])
def start_handler(message):
    if is_user_banned(message.chat.id):
        bot.reply_to(message, "🚫 <b>You are banned!</b> Contact @NikunjBro", parse_mode='HTML')
        return

    if get_maintenance_mode() and not is_admin(message.chat.id):
        bot.reply_to(message, "🔧 <b>Bot is under maintenance. Please wait.</b>", parse_mode='HTML')
        return

    args = message.text.split()
    ref_code = None
    if len(args) > 1 and args[1].startswith('ref_'):
        ref_code = args[1][4:]

    created = create_user_if_not_exists(message.chat.id, message.from_user.username, message.from_user.first_name, message.from_user.last_name)

    if created:
        admin_msg = (f"👤 <b>New User!</b>\n"
                     f"🆔 ID: <code>{message.chat.id}</code>\n"
                     f"👤 @{html.escape(str(message.from_user.username)) if message.from_user.username else 'No username'}\n"
                     f"📛 {html.escape(str(message.from_user.first_name)) if message.from_user.first_name else 'N/A'} {html.escape(str(message.from_user.last_name)) if message.from_user.last_name else ''}\n"
                     f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        try:
            bot.send_message(ADMIN_ID, admin_msg, parse_mode='HTML')
        except:
            pass

        if ref_code:
            referrer_id = get_user_by_referral_code(ref_code)
            if referrer_id and referrer_id != message.chat.id:
                set_referred_by(message.chat.id, referrer_id)
                bot.send_message(referrer_id, f"🎉 <b>New referral!</b> @{html.escape(str(message.from_user.username))} joined using your link.", parse_mode='HTML')

    joined, link, cid = check_force_join(message.chat.id)
    if not joined:
        bot.reply_to(message, '<tg-emoji emoji-id="6267039884016358504">⚠️</tg-emoji> <b>Please join our channel first!</b>', reply_markup=force_join_keyboard_user(link, cid), parse_mode='HTML')
        return

    user = get_user(message.chat.id)
    bal = user[4] if user else 0
    welcome = (f'<tg-emoji emoji-id="6053229398339884957">🌟</tg-emoji> <b>Welcome {html.escape(str(message.from_user.first_name))}!</b> <tg-emoji emoji-id="6053229398339884957">🌟</tg-emoji>\n\n'
               "━━━━━━━━━━━━━━━━━━━━━━━\n"
               f'<tg-emoji emoji-id="5816492162488995555">💸</tg-emoji> <b>Buy virtual numbers for OTP verification!</b>\n'
               f'<tg-emoji emoji-id="6267068789146260253">💰</tg-emoji> <b>Balance:</b> <code>₹{bal:.2f}</code>\n'
               f'<tg-emoji emoji-id="6338935574967098253">📱</tg-emoji> Click <b>Get Number</b> to start.\n'
               "━━━━━━━━━━━━━━━━━━━━━━━\n"
               f'<tg-emoji emoji-id="6052886672834566125">🔗</tg-emoji> <b>Referral link:</b>\n'
               f"<code>https://t.me/{bot.get_me().username}?start=ref_{get_referral_code(message.chat.id)}</code>\n"
               "Share and earn <b>5% commission</b>!\n"
               "━━━━━━━━━━━━━━━━━━━━━━━\n"
               f'<tg-emoji emoji-id="6338946058982267602">📞</tg-emoji> Need help? @{SUPPORT_USERNAME}')
    bot.reply_to(message, welcome, reply_markup=main_menu_keyboard(), parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if is_user_banned(call.message.chat.id):
        bot.answer_callback_query(call.id, "You are banned!", show_alert=True)
        return

    if get_maintenance_mode() and not is_admin(call.message.chat.id) and call.data not in ("main_menu", "check_joined"):
        bot.answer_callback_query(call.id, "Bot is under maintenance!", show_alert=True)
        return

    if not is_admin(call.message.chat.id) and call.data not in ("check_joined", "main_menu"):
        joined, link, cid = check_force_join(call.message.chat.id)
        if not joined:
            bot.answer_callback_query(call.id, "Join channel first!", show_alert=True)
            return

    try:
        if call.data == "main_menu":
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.send_message(call.message.chat.id, "🏠 <b>Main Menu</b>", reply_markup=main_menu_keyboard(), parse_mode='HTML')
        elif call.data == "profile":
            show_profile(call.message)
        elif call.data == "check_balance":
            show_balance(call.message)
        elif call.data == "deposit":
            ask_deposit_amount(call.message)
        elif call.data == "deposit_issue":
            handle_deposit_issue(call.message)
        elif call.data == "claim_promo":
            bot.delete_message(call.message.chat.id, call.message.message_id)
            msg = bot.send_message(call.message.chat.id, '<tg-emoji emoji-id="6239894475229895983">🎁</tg-emoji> <b>Enter Promo Code</b>', parse_mode='HTML')
            bot.register_next_step_handler(msg, process_promo_claim)
        elif call.data == "feedback":
            bot.delete_message(call.message.chat.id, call.message.message_id)
            msg = bot.send_message(call.message.chat.id, '<tg-emoji emoji-id="5258500400918587241">📝</tg-emoji> <b>Send your feedback:</b>', parse_mode='HTML')
            bot.register_next_step_handler(msg, receive_feedback)
        elif call.data == "support":
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.send_message(call.message.chat.id, f'<tg-emoji emoji-id="6278418184391367936">📞</tg-emoji> <b>Support</b>\nContact @{SUPPORT_USERNAME}', reply_markup=main_menu_keyboard(), parse_mode='HTML')
        elif call.data == "referral":
            show_referral_info(call.message)
        elif call.data == "my_referrals":
            show_my_referrals(call.message)
        elif call.data == "report_bug":
            bot.delete_message(call.message.chat.id, call.message.message_id)
            msg = bot.send_message(call.message.chat.id, '<tg-emoji emoji-id="5368487491097601104">🐞</tg-emoji> <b>Report a Bug</b>\n\nSend description (text/photo/video).\n\nSend /cancel to cancel.', parse_mode='HTML')
            bot.register_next_step_handler(msg, receive_bug_report)
        elif call.data == "cancel_not_allowed":
            sess = user_sessions.get(call.message.chat.id)
            if sess:
                wait = sess.get_cancel_wait_time()
                bot.answer_callback_query(call.id, f"⏳ Please wait {wait} seconds!", show_alert=True)
            else:
                bot.answer_callback_query(call.id, "Cannot cancel yet", show_alert=True)

        elif call.data == "dummy":
            bot.answer_callback_query(call.id, "⏱️ Time remaining", show_alert=False)

        # === Get Number ===
        elif call.data == "get_number":
            cc = '22'
            user_temp_data.setdefault(call.message.chat.id, {})['selected_country'] = cc
            services = get_services_list(cc)
            if services:
                bot.delete_message(call.message.chat.id, call.message.message_id)
                bot.send_message(call.message.chat.id, "📱 <b>Available Services</b>", reply_markup=services_keyboard(services, cc), parse_mode='HTML')
            else:
                kb = InlineKeyboardMarkup(row_width=1)
                kb.add(InlineKeyboardButton("Select Country", callback_data="select_country", style="primary", icon_custom_emoji_id="5224450179368767019"))
                kb.add(InlineKeyboardButton("Retry", callback_data="get_number", style="success", icon_custom_emoji_id="5386367538735104399"))
                kb.add(InlineKeyboardButton("Main Menu", callback_data="main_menu", style="danger", icon_custom_emoji_id="5253997076169115797"))
                bot.edit_message_text('<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> No services. Select country or retry.', call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode='HTML')

        elif call.data == "select_country":
            countries = get_countries()
            if countries:
                bot.delete_message(call.message.chat.id, call.message.message_id)
                bot.send_message(call.message.chat.id, "🌍 <b>Select Country</b>", reply_markup=country_keyboard(countries), parse_mode='HTML')
            else:
                bot.answer_callback_query(call.id, "No countries!", show_alert=True)

        elif call.data.startswith("select_country_"):
            cc = call.data.split("_")[2]
            user_temp_data.setdefault(call.message.chat.id, {})['selected_country'] = cc
            services = get_services_list(cc)
            if services:
                bot.edit_message_text(f"🌍 <b>Services for {cc}</b>", call.message.chat.id, call.message.message_id,
                                      reply_markup=services_keyboard(services, cc), parse_mode='HTML')
            else:
                kb = InlineKeyboardMarkup(row_width=1)
                kb.add(InlineKeyboardButton("🔄 Try Again", callback_data="select_country"))
                kb.add(InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
                bot.edit_message_text(f"❌ <b>No services for {cc}</b>", call.message.chat.id, call.message.message_id,
                                      reply_markup=kb, parse_mode='HTML')

        elif call.data.startswith("refresh_services_"):
            cc = call.data.split("_")[2]
            services_cache.clear()
            services = get_services_list(cc)
            if services:
                bot.edit_message_text("✅ <b>Services Refreshed!</b>", call.message.chat.id, call.message.message_id,
                                      reply_markup=services_keyboard(services, cc), parse_mode='HTML')
            else:
                bot.edit_message_text("❌ <b>No services.</b>", call.message.chat.id, call.message.message_id,
                                      reply_markup=services_keyboard({}, cc), parse_mode='HTML')

        elif call.data == "search_service":
            bot.delete_message(call.message.chat.id, call.message.message_id)
            msg = bot.send_message(call.message.chat.id, "🔍 <b>Send service name:</b>", parse_mode='HTML')
            bot.register_next_step_handler(msg, search_service)

        # Pagination
        elif call.data.startswith("next_page_"):
            parts = call.data.split("_")
            page = int(parts[2])
            cc = parts[3] if len(parts) > 3 else '22'
            services = get_services_list(cc)
            if services:
                items = list(services.items())
                per = 20
                start = page * per
                end = start + per
                if start < len(items):
                    kb = InlineKeyboardMarkup(row_width=1)
                    kb.add(InlineKeyboardButton("🔍 Search", callback_data="search_service"))
                    kb.add(InlineKeyboardButton("🌍 Change Country", callback_data="select_country"))
                    for code, info in items[start:end]:
                        name = info.get('name', code.upper())[:30]
                        price = get_service_price(code)
                        kb.add(InlineKeyboardButton(f"📱 {name} - ₹{price}", callback_data=f"select_service_{code}|{price}|{cc}"))
                    nav = []
                    if page > 0:
                        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"prev_page_{page}_{cc}"))
                    if end < len(items):
                        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"next_page_{page+1}_{cc}"))
                    if nav:
                        kb.add(*nav)
                    kb.add(InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_services_{cc}"))
                    kb.add(InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
                    bot.edit_message_text(f"📱 <b>Services - Page {page+1}</b>", call.message.chat.id, call.message.message_id,
                                          reply_markup=kb, parse_mode='HTML')
        elif call.data.startswith("prev_page_"):
            parts = call.data.split("_")
            page = int(parts[2])
            cc = parts[3] if len(parts) > 3 else '22'
            services = get_services_list(cc)
            if services:
                items = list(services.items())
                per = 20
                prev = page - 1
                start = prev * per
                end = start + per
                kb = InlineKeyboardMarkup(row_width=1)
                kb.add(InlineKeyboardButton("🔍 Search", callback_data="search_service"))
                kb.add(InlineKeyboardButton("🌍 Change Country", callback_data="select_country"))
                for code, info in items[start:end]:
                    name = info.get('name', code.upper())[:30]
                    price = get_service_price(code)
                    kb.add(InlineKeyboardButton(f"📱 {name} - ₹{price}", callback_data=f"select_service_{code}|{price}|{cc}"))
                nav = []
                if prev > 0:
                    nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"prev_page_{prev}_{cc}"))
                if end < len(items):
                    nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"next_page_{prev+1}_{cc}"))
                if nav:
                    kb.add(*nav)
                kb.add(InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_services_{cc}"))
                kb.add(InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
                bot.edit_message_text(f"📱 <b>Services - Page {prev+1}</b>", call.message.chat.id, call.message.message_id,
                                      reply_markup=kb, parse_mode='HTML')

        # Select service
        elif call.data.startswith("select_service_"):
            parts = call.data.split("|")
            service_code = parts[0].replace("select_service_", "")
            price = float(parts[1]) if len(parts) > 1 else 10
            country_code = parts[2] if len(parts) > 2 else '22'
            services = get_services_list(country_code)
            service_name = services.get(service_code, {}).get('name', service_code.upper())
            bal = get_user_balance(call.message.chat.id)
            if bal < price:
                bot.answer_callback_query(call.id, f"Insufficient! Have ₹{bal}, need ₹{price}", show_alert=True)
                bot.edit_message_text(f"❌ <b>Insufficient Balance!</b>\n💰 Balance: <code>₹{bal:.2f}</code>\n💸 Required: <code>₹{price}</code>",
                                      call.message.chat.id, call.message.message_id,
                                      reply_markup=main_menu_keyboard(), parse_mode='HTML')
                return
            user_temp_data.setdefault(call.message.chat.id, {})['pending_service'] = {
                'code': service_code, 'name': service_name, 'price': price, 'country': country_code
            }
            bot.edit_message_text(f"📱 <b>Confirm Purchase</b>\n\nService: <b>{html.escape(service_name)}</b>\n💰 Price: <code>₹{price}</code>\n🌍 Country: <code>{country_code}</code>\n\nProceed?",
                                  call.message.chat.id, call.message.message_id,
                                  reply_markup=confirmation_keyboard(service_code, service_name, price, country_code),
                                  parse_mode='HTML')

        elif call.data.startswith("confirm_"):
            parts = call.data.split("|")
            service_code = parts[0].replace("confirm_", "")
            country_code = parts[1] if len(parts) > 1 else '22'
            server = parts[2] if len(parts) > 2 else None
            pending = user_temp_data.get(call.message.chat.id, {}).get('pending_service')
            if pending:
                proc_msg = bot.send_message(call.message.chat.id, LOADING_MSG)
                request_number(call.message, service_code, country_code, server, pending['price'], proc_msg)
            else:
                bot.answer_callback_query(call.id, "Session expired. Please select service again.", show_alert=True)

        elif call.data.startswith("check_otp_"):
            aid = call.data.split("_")[2]
            check_and_show_otp(call.message, aid)
        elif call.data.startswith("cancel_"):
            aid = call.data.split("_")[1]
            cancel_specific_order(call, aid)  # Pass 'call' object

        elif call.data == "recent_orders":
            show_recent_orders(call.message)
        elif call.data == "recent_transactions":
            show_recent_transactions(call.message)

        # ===== ADMIN PANEL =====
        elif call.data == "admin_panel":
            if not is_admin(call.message.chat.id):
                bot.answer_callback_query(call.id, "Unauthorized!", show_alert=True)
                return
            bot.delete_message(call.message.chat.id, call.message.message_id)
            show_admin_panel(call.message)

        elif call.data == "admin_stats":
            if not is_admin(call.message.chat.id): return
            show_admin_stats(call.message)

        elif call.data == "admin_users":
            if not is_admin(call.message.chat.id): return
            show_user_list(call.message)

        elif call.data == "admin_bots":
            if not is_admin(call.message.chat.id): return
            show_all_bots(call.message)

        elif call.data == "admin_payments":
            if not is_admin(call.message.chat.id): return
            show_pending_deposits(call.message)

        elif call.data == "admin_broadcast":
            if not is_admin(call.message.chat.id): return
            msg = bot.send_message(call.message.chat.id, "📢 <b>Send broadcast message:</b>", parse_mode='HTML')
            bot.register_next_step_handler(msg, broadcast_message)

        elif call.data == "admin_ban":
            if not is_admin(call.message.chat.id): return
            show_ban_menu(call.message)

        elif call.data == "admin_give_plan":
            if not is_admin(call.message.chat.id): return
            msg = bot.send_message(call.message.chat.id, "🎁 <b>Give Plan</b>\nSend: <code>user_id amount</code>", parse_mode='HTML')
            bot.register_next_step_handler(msg, give_plan)

        elif call.data == "admin_approve_pay":
            if not is_admin(call.message.chat.id): return
            show_pending_deposits(call.message)

        elif call.data == "admin_coupons":
            if not is_admin(call.message.chat.id): return
            generate_promo_code(call.message)

        elif call.data == "admin_tickets":
            if not is_admin(call.message.chat.id): return
            show_bug_reports(call.message)

        elif call.data == "admin_maintenance":
            if not is_admin(call.message.chat.id): return
            toggle_maintenance(call.message)

        elif call.data == "admin_service_prices":
            if not is_admin(call.message.chat.id): return
            show_service_prices(call.message)

        elif call.data == "admin_leaderboard":
            if not is_admin(call.message.chat.id): return
            show_leaderboard(call.message)

        elif call.data == "admin_add_admin":
            if not is_admin(call.message.chat.id): return
            msg = bot.send_message(call.message.chat.id, "➕ <b>Add Admin</b>\nSend user ID:", parse_mode='HTML')
            bot.register_next_step_handler(msg, add_admin_by_id)

        elif call.data == "admin_admin_list":
            if not is_admin(call.message.chat.id): return
            show_admin_list(call.message)

        elif call.data == "admin_referrals":
            if not is_admin(call.message.chat.id): return
            show_referral_stats(call.message)

        elif call.data == "admin_user_stats":
            if not is_admin(call.message.chat.id): return
            show_user_stats(call.message)

        elif call.data == "admin_search_service":
            if not is_admin(call.message.chat.id): return
            msg = bot.send_message(call.message.chat.id, "🔍 <b>Search Service</b>\nSend service code or name:", parse_mode='HTML')
            bot.register_next_step_handler(msg, admin_search_service)

        elif call.data == "admin_force_join":
            if not is_admin(call.message.chat.id): return
            show_force_join_menu(call.message)

        elif call.data == "admin_feedback":
            if not is_admin(call.message.chat.id): return
            show_feedback(call.message)

        # ===== SETTINGS =====
        elif call.data == "admin_settings":
            if not is_admin(call.message.chat.id): return
            show_settings_panel(call.message)

        elif call.data == "set_otp_key":
            if not is_admin(call.message.chat.id): return
            msg = bot.send_message(call.message.chat.id, "🔑 <b>Send new OTP API Key:</b>", parse_mode='HTML')
            bot.register_next_step_handler(msg, save_otp_key)

        elif call.data == "set_otp_url":
            if not is_admin(call.message.chat.id): return
            msg = bot.send_message(call.message.chat.id, "🌐 <b>Send new OTP Base URL:</b>\nExample: <code>https://example.com/stubs/handler_api.php</code>", parse_mode='HTML')
            bot.register_next_step_handler(msg, save_otp_url)

        elif call.data == "set_gw_key":
            if not is_admin(call.message.chat.id): return
            msg = bot.send_message(call.message.chat.id, "💳 <b>Send new Gateway API Key:</b>", parse_mode='HTML')
            bot.register_next_step_handler(msg, save_gw_key)

        elif call.data == "set_gw_url":
            if not is_admin(call.message.chat.id): return
            msg = bot.send_message(call.message.chat.id, "🔗 <b>Send new Gateway URL:</b>", parse_mode='HTML')
            bot.register_next_step_handler(msg, save_gw_url)

        elif call.data == "set_gw_merchant":
            if not is_admin(call.message.chat.id): return
            msg = bot.send_message(call.message.chat.id, "🏪 <b>Send new Merchant Name:</b>", parse_mode='HTML')
            bot.register_next_step_handler(msg, save_gw_merchant)

        elif call.data == "set_view":
            if not is_admin(call.message.chat.id): return
            show_all_settings(call.message)

        elif call.data == "set_servers":
            if not is_admin(call.message.chat.id): return
            bot.edit_message_text("🖥️ <b>Server Settings</b>", call.message.chat.id, call.message.message_id,
                                  reply_markup=servers_settings_keyboard(), parse_mode='HTML')

        elif call.data == "srv_add":
            if not is_admin(call.message.chat.id): return
            msg = bot.send_message(call.message.chat.id, "➕ <b>Add Server</b>\nSend: <code>server_id,server_name</code>\nExample: <code>srv1, US Server</code>", parse_mode='HTML')
            bot.register_next_step_handler(msg, save_new_server)

        elif call.data == "srv_remove_menu":
            if not is_admin(call.message.chat.id): return
            msg = bot.send_message(call.message.chat.id, "🗑️ <b>Remove Server</b>\nSend server ID:", parse_mode='HTML')
            bot.register_next_step_handler(msg, remove_server_cb)

        elif call.data == "srv_list":
            if not is_admin(call.message.chat.id): return
            show_servers_list(call.message)

        # ===== MANAGE USER =====
        elif call.data == "admin_manage_user":
            if not is_admin(call.message.chat.id): return
            bot.delete_message(call.message.chat.id, call.message.message_id)
            msg = bot.send_message(call.message.chat.id, "👤 <b>Manage User</b>\n\nSend User ID to view:", parse_mode='HTML')
            bot.register_next_step_handler(msg, view_user_cb)

        elif call.data.startswith("mu_view_"):
            if not is_admin(call.message.chat.id): return
            uid = int(call.data.split("_")[2])
            show_user_detail(call.message, uid)

        elif call.data.startswith("mu_addbal_"):
            if not is_admin(call.message.chat.id): return
            uid = int(call.data.split("_")[2])
            msg = bot.send_message(call.message.chat.id, f"➕ <b>Add Balance to</b> <code>{uid}</code>\nSend amount:", parse_mode='HTML')
            bot.register_next_step_handler(msg, lambda m: do_add_balance(m, uid))

        elif call.data.startswith("mu_rmbal_"):
            if not is_admin(call.message.chat.id): return
            uid = int(call.data.split("_")[2])
            msg = bot.send_message(call.message.chat.id, f"➖ <b>Remove Balance from</b> <code>{uid}</code>\nSend amount:", parse_mode='HTML')
            bot.register_next_step_handler(msg, lambda m: do_remove_balance(m, uid))

        elif call.data.startswith("mu_toggleban_"):
            if not is_admin(call.message.chat.id): return
            uid = int(call.data.split("_")[2])
            row = db.execute("SELECT is_banned FROM users WHERE user_id = ?", (uid,), fetch_one=True)
            if row and row[0] == 1:
                unban_user(uid); bot.answer_callback_query(call.id, "✅ Unbanned")
            else:
                ban_user(uid); bot.answer_callback_query(call.id, "🚫 Banned")
            show_user_detail(call.message, uid)

        elif call.data.startswith("mu_toggleadmin_"):
            if not is_admin(call.message.chat.id): return
            uid = int(call.data.split("_")[2])
            if uid == ADMIN_ID:
                bot.answer_callback_query(call.id, "Can't change super admin!", show_alert=True); return
            row = db.execute("SELECT is_admin FROM users WHERE user_id = ?", (uid,), fetch_one=True)
            if row and row[0] == 1:
                remove_admin(uid); bot.answer_callback_query(call.id, "➖ Admin removed")
            else:
                add_admin(uid); bot.answer_callback_query(call.id, "👑 Admin added")
            show_user_detail(call.message, uid)

        elif call.data.startswith("mu_orders_"):
            if not is_admin(call.message.chat.id): return
            uid = int(call.data.split("_")[2])
            rows = db.execute("SELECT order_date, service_name, phone_number, price, status FROM orders WHERE user_id = ? ORDER BY order_date DESC LIMIT 15", (uid,), fetch_all=True)
            txt = f"📦 <b>Orders for</b> <code>{uid}</code>\n\n" + ("\n".join([f"{r[0]} | {html.escape(str(r[1]))} | ₹{r[3]} | {r[4]}" for r in rows]) if rows else "No orders.")
            bot.send_message(call.message.chat.id, txt[:4000], parse_mode='HTML')

        elif call.data.startswith("mu_txns_"):
            if not is_admin(call.message.chat.id): return
            uid = int(call.data.split("_")[2])
            rows = db.execute("SELECT created_date, amount, type, status FROM transactions WHERE user_id = ? ORDER BY created_date DESC LIMIT 15", (uid,), fetch_all=True)
            txt = f"💸 <b>Transactions for</b> <code>{uid}</code>\n\n" + ("\n".join([f"{r[0]} | ₹{r[1]} | {html.escape(str(r[2]))} | {r[3]}" for r in rows]) if rows else "No transactions.")
            bot.send_message(call.message.chat.id, txt[:4000], parse_mode='HTML')

        # ===== MANAGE ADMINS =====
        elif call.data == "admin_manage_admins":
            if not is_admin(call.message.chat.id): return
            bot.edit_message_text("🔐 <b>Admin Management</b>", call.message.chat.id, call.message.message_id,
                                  reply_markup=manage_admins_keyboard(), parse_mode='HTML')

        elif call.data == "adm_list":
            if not is_admin(call.message.chat.id): return
            admins = get_admins()
            txt = "📋 <b>All Admins</b>\n\n"
            for a in admins:
                tag = "👑 SUPER ADMIN" if a[0] == ADMIN_ID else "🛡️ Admin"
                txt += f"{tag}\n🆔 <code>{a[0]}</code> | @{html.escape(str(a[1])) if a[1] else 'None'} | {html.escape(str(a[2]))}\n\n"
            bot.send_message(call.message.chat.id, txt, parse_mode='HTML')

        elif call.data == "adm_add":
            if not is_admin(call.message.chat.id): return
            msg = bot.send_message(call.message.chat.id, "➕ <b>Add Admin</b>\nSend user ID:", parse_mode='HTML')
            bot.register_next_step_handler(msg, add_admin_by_id)

        elif call.data == "adm_remove":
            if not is_admin(call.message.chat.id): return
            msg = bot.send_message(call.message.chat.id, "➖ <b>Remove Admin</b>\nSend user ID:", parse_mode='HTML')
            bot.register_next_step_handler(msg, remove_admin_by_id)

        # ===== BACKUP =====
        elif call.data == "admin_backup":
            if not is_admin(call.message.chat.id): return
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.send_message(call.message.chat.id, "💾 <b>Backup & Export</b>\n\nChoose option:", reply_markup=backup_keyboard(), parse_mode='HTML')

        elif call.data == "backup_db":
            if not is_admin(call.message.chat.id): return
            export_db_file(call.message)

        elif call.data == "backup_users_csv":
            if not is_admin(call.message.chat.id): return
            export_csv(call.message, "users",
                       "SELECT user_id, username, first_name, balance, total_orders, total_spent, is_banned, is_admin, joined_date FROM users")

        elif call.data == "backup_orders_csv":
            if not is_admin(call.message.chat.id): return
            export_csv(call.message, "orders", "SELECT * FROM orders")

        elif call.data == "backup_txn_csv":
            if not is_admin(call.message.chat.id): return
            export_csv(call.message, "transactions", "SELECT * FROM transactions")

        # Force join callbacks
        elif call.data == "add_channel":
            if not is_admin(call.message.chat.id): return
            pending_channel_input[call.message.chat.id] = {'action': 'add_channel'}
            msg = bot.send_message(call.message.chat.id, "➕ <b>Add Channel</b>\nSend: <code>link,channel_id,channel_name</code>\nExample:\n<code>https://t.me/+-5SOU6Rf5BE3YTI0, -1003990564330, Main Channel</code>", parse_mode='HTML')
            bot.register_next_step_handler(msg, process_add_channel)

        elif call.data == "channel_list":
            if not is_admin(call.message.chat.id): return
            show_channel_list(call.message)

        elif call.data == "remove_channel_menu":
            if not is_admin(call.message.chat.id): return
            msg = bot.send_message(call.message.chat.id, "🗑 <b>Remove Channel</b>\nSend channel ID or link:", parse_mode='HTML')
            bot.register_next_step_handler(msg, remove_channel_admin)

        # ===== CHECK JOINED =====
        elif call.data == "check_joined":
            joined, link, cid = check_force_join(call.message.chat.id)
            if joined:
                bot.delete_message(call.message.chat.id, call.message.message_id)
                bot.send_message(call.message.chat.id, "✅ <b>Thanks for joining!</b>", reply_markup=main_menu_keyboard(), parse_mode='HTML')
            else:
                bot.edit_message_text('<tg-emoji emoji-id="6267039884016358504">⚠️</tg-emoji> <b>Please join our channel first!</b>', call.message.chat.id, call.message.message_id,
                                      reply_markup=force_join_keyboard_user(link, cid), parse_mode='HTML')

        # ===== CHECK PAYMENT (AUTO GATEWAY) =====
        elif call.data.startswith("check_payment_"):
            oid = call.data.split("_", 2)[2]
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass
            verify_gateway_payment(call.message.chat.id, oid)

        # ===== DEPOSIT ISSUE APPROVE / REJECT =====
        elif call.data.startswith("approve_deposit_issue_"):
            if not is_admin(call.message.chat.id): return
            uid = int(call.data.split("_")[3])
            issue_data = deposit_issue_temp.pop(uid, None)
            if not issue_data:
                bot.send_message(call.message.chat.id, "❌ No pending deposit issue for this user.")
                return
            amount = issue_data.get('amount', 0)
            new_bal = update_user_balance(uid, amount, add=True)
            try:
                bot.send_message(uid, f"✅ <b>Deposit Added!</b>\n\n💰 ₹{amount} has been added to your wallet.\n💳 New balance: ₹{new_bal:.2f}\n\n🙏 <b>Sorry for the inconvenience.</b>", parse_mode='HTML')
            except:
                pass
            bot.send_message(call.message.chat.id, f"✅ Added ₹{amount} to user <code>{uid}</code>. New balance: ₹{new_bal:.2f}", parse_mode='HTML')

        elif call.data.startswith("reject_deposit_issue_"):
            if not is_admin(call.message.chat.id): return
            uid = int(call.data.split("_")[3])
            deposit_issue_temp.pop(uid, None)
            try:
                bot.send_message(uid, "❌ Your deposit issue request was rejected. Please contact support.", parse_mode='HTML')
            except:
                pass
            bot.send_message(call.message.chat.id, f"❌ Rejected deposit issue for user <code>{uid}</code>.", parse_mode='HTML')

        # Resolve bug
        elif call.data.startswith("resolve_bug_"):
            if not is_admin(call.message.chat.id): return
            rid = int(call.data.split("_")[2])
            resolve_bug_report(rid)
            bot.answer_callback_query(call.id, "Report resolved!")
            bot.edit_message_text("✅ Resolved", call.message.chat.id, call.message.message_id)

        # Ban/Unban actions
        elif call.data.startswith("admin_ban_user_"):
            if not is_admin(call.message.chat.id): return
            uid = int(call.data.split("_")[3])
            ban_user(uid)
            bot.answer_callback_query(call.id, f"User {uid} banned!")
            bot.edit_message_text(f"✅ User {uid} banned.", call.message.chat.id, call.message.message_id)
        elif call.data.startswith("admin_unban_user_"):
            if not is_admin(call.message.chat.id): return
            uid = int(call.data.split("_")[3])
            unban_user(uid)
            bot.answer_callback_query(call.id, f"User {uid} unbanned!")
            bot.edit_message_text(f"✅ User {uid} unbanned.", call.message.chat.id, call.message.message_id)

        bot.answer_callback_query(call.id)
    except Exception as e:
        print(f"Callback error: {e}")
        import traceback; traceback.print_exc()
        try:
            bot.answer_callback_query(call.id, "❌ Something went wrong, please try again.", show_alert=True)
        except:
            pass

# ============================================================
# ADMIN PANEL UI
# ============================================================
def show_admin_panel(message):
    total_users, total_balance, total_revenue, total_orders, pending = get_user_stats()
    text = (f"<pre>\nADMIN PANEL\nRESTRICTED AREA\n\nADMIN PANEL\n- Users: {total_users}\n- Bots: 1\n- Running: 1\n- Revenue: ₹{total_revenue:.2f}\n- Pending: {pending}\n\nPremium Hosting Bot v1.0\n</pre>")
    bot.send_message(message.chat.id, text, reply_markup=admin_panel_keyboard(), parse_mode='HTML')

def show_admin_stats(message):
    total_users, total_balance, total_revenue, total_orders, pending = get_user_stats()
    text = (f"📊 <b>STATS</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 Users: <code>{total_users}</code>\n"
            f"💰 Total Balance: <code>₹{total_balance:.2f}</code>\n"
            f"💵 Revenue: <code>₹{total_revenue:.2f}</code>\n"
            f"📦 Orders: <code>{total_orders}</code>\n"
            f"⏳ Pending Deposits: <code>{pending}</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━")
    bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=admin_panel_keyboard())

# ============================================================
# SETTINGS PANEL
# ============================================================
def show_settings_panel(message):
    otp_key, otp_url = get_api_settings()
    gw_key, gw_url, gw_merchant = get_gateway_settings()
    txt = (f"⚙️ <b>Bot Settings</b>\n"
           "━━━━━━━━━━━━━━━━━━━━━\n"
           f"🔑 <b>OTP API Key:</b> <code>{otp_key[:15]}...</code>\n"
           f"🌐 <b>OTP URL:</b> <code>{otp_url}</code>\n"
           f"💳 <b>Gateway Key:</b> <code>{gw_key[:15]}...</code>\n"
           f"🔗 <b>Gateway URL:</b> <code>{gw_url}</code>\n"
           f"🏪 <b>Merchant:</b> <code>{gw_merchant}</code>\n"
           "━━━━━━━━━━━━━━━━━━━━━\n"
           "Tap any option to change.")
    bot.send_message(message.chat.id, txt, reply_markup=settings_keyboard(), parse_mode='HTML')

def save_otp_key(message):
    if not is_admin(message.chat.id): return
    new_key = message.text.strip()
    _, url = get_api_settings()
    set_api_settings(new_key, url)
    bot.send_message(message.chat.id, f"✅ OTP API Key updated!", reply_markup=settings_keyboard())

def save_otp_url(message):
    if not is_admin(message.chat.id): return
    new_url = message.text.strip()
    key, _ = get_api_settings()
    set_api_settings(key, new_url)
    bot.send_message(message.chat.id, f"✅ OTP Base URL updated!\n<code>{new_url}</code>", reply_markup=settings_keyboard(), parse_mode='HTML')

def save_gw_key(message):
    if not is_admin(message.chat.id): return
    set_gateway_settings(api_key=message.text.strip())
    bot.send_message(message.chat.id, "✅ Gateway API Key updated!", reply_markup=settings_keyboard())

def save_gw_url(message):
    if not is_admin(message.chat.id): return
    set_gateway_settings(api_url=message.text.strip())
    bot.send_message(message.chat.id, "✅ Gateway URL updated!", reply_markup=settings_keyboard())

def save_gw_merchant(message):
    if not is_admin(message.chat.id): return
    set_gateway_settings(merchant=message.text.strip())
    bot.send_message(message.chat.id, "✅ Merchant name updated!", reply_markup=settings_keyboard())

def show_all_settings(message):
    otp_key, otp_url = get_api_settings()
    gw_key, gw_url, gw_merchant = get_gateway_settings()
    txt = (f"👁️ <b>All Settings</b>\n\n"
           f"<b>OTP API:</b>\n🔑 Key: <code>{otp_key}</code>\n🌐 URL: <code>{otp_url}</code>\n\n"
           f"<b>Gateway:</b>\n💳 Key: <code>{gw_key}</code>\n🔗 URL: <code>{gw_url}</code>\n🏪 Merchant: <code>{gw_merchant}</code>")
    bot.send_message(message.chat.id, txt[:4000], parse_mode='HTML')

def save_new_server(message):
    if not is_admin(message.chat.id): return
    try:
        parts = message.text.split(',')
        sid = parts[0].strip()
        sname = parts[1].strip() if len(parts) > 1 else sid
        add_custom_server(sid, sname, message.chat.id)
        bot.send_message(message.chat.id, f"✅ Server <code>{html.escape(sid)}</code> added!", reply_markup=servers_settings_keyboard(), parse_mode='HTML')
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Error: {e}", reply_markup=servers_settings_keyboard())

def remove_server_cb(message):
    if not is_admin(message.chat.id): return
    sid = message.text.strip()
    remove_custom_server(sid)
    bot.send_message(message.chat.id, f"✅ Server <code>{html.escape(sid)}</code> removed!", reply_markup=servers_settings_keyboard(), parse_mode='HTML')

def show_servers_list(message):
    rows = get_custom_servers()
    api_servers = get_servers()
    txt = "🖥️ <b>Servers</b>\n\n<b>Custom Servers:</b>\n"
    if rows:
        for r in rows:
            txt += f"• <code>{html.escape(str(r[0]))}</code> - {html.escape(str(r[1]))}\n"
    else:
        txt += "<i>none</i>\n"
    txt += "\n<b>API Servers:</b>\n"
    if api_servers:
        for k, v in list(api_servers.items())[:15]:
            txt += f"• <code>{html.escape(str(k))}</code> - {html.escape(str(v)) if isinstance(v, str) else 'OK'}\n"
    else:
        txt += "<i>none</i>\n"
    bot.send_message(message.chat.id, txt, reply_markup=servers_settings_keyboard(), parse_mode='HTML')

# ============================================================
# MANAGE USER
# ============================================================
def view_user_cb(message):
    if not is_admin(message.chat.id): return
    try:
        uid = int(message.text.strip())
    except:
        bot.send_message(message.chat.id, "❌ Invalid user ID.", reply_markup=admin_panel_keyboard()); return
    show_user_detail(message, uid)

def show_user_detail(message, uid):
    u = get_user(uid)
    if not u:
        bot.send_message(message.chat.id, f"❌ User <code>{uid}</code> not found.", reply_markup=admin_panel_keyboard(), parse_mode='HTML'); return
    bal = float(u[4] or 0)
    is_banned_flag = u[11] if len(u) > 11 else 0
    is_admin_flag = u[9] if len(u) > 9 else 0
    total_dep = get_user_total_deposit(uid)
    txt = (f"👤 <b>User Details</b>\n"
           "━━━━━━━━━━━━━━━━━━━━━\n"
           f"🆔 ID: <code>{u[0]}</code>\n"
           f"👤 Username: @{html.escape(str(u[1])) if u[1] else 'None'}\n"
           f"📛 Name: {html.escape(str(u[2])) if u[2] else ''} {html.escape(str(u[3])) if u[3] else ''}\n"
           f"💰 Balance: <code>₹{bal:.2f}</code>\n"
           f"💳 Total Deposit: <code>₹{total_dep:.2f}</code>\n"
           f"📦 Orders: <code>{u[6] or 0}</code> | ✅ <code>{u[7] or 0}</code>\n"
           f"💸 Spent: <code>₹{float(u[8] or 0):.2f}</code>\n"
           f"📅 Joined: <code>{u[5]}</code>\n"
           f"🚫 Banned: <code>{'YES' if is_banned_flag else 'NO'}</code>\n"
           f"👑 Admin: <code>{'YES' if is_admin_flag else 'NO'}</code>\n"
           "━━━━━━━━━━━━━━━━━━━━━")
    bot.send_message(message.chat.id, txt, reply_markup=manage_user_keyboard(uid, is_banned_flag, is_admin_flag), parse_mode='HTML')

def do_add_balance(message, uid):
    if not is_admin(message.chat.id): return
    try:
        amt = float(message.text.strip())
        if amt <= 0: raise ValueError
        new_bal = update_user_balance(uid, amt, add=True)
        txn_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
        db.execute("INSERT INTO transactions (txn_id, user_id, amount, type, status, admin_note, created_date, processed_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                   (txn_id, uid, amt, "admin_credit", "completed", f"by {message.chat.id}",
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        bot.send_message(message.chat.id, f"✅ Added ₹{amt} to <code>{uid}</code>\n💰 New: <code>₹{new_bal:.2f}</code>", reply_markup=admin_panel_keyboard(), parse_mode='HTML')
        try:
            bot.send_message(uid, f"🎁 Admin added ₹{amt} to your balance!\n💰 New balance: ₹{new_bal:.2f}", parse_mode='HTML')
        except: pass
    except:
        bot.send_message(message.chat.id, "❌ Invalid amount.", reply_markup=admin_panel_keyboard())

def do_remove_balance(message, uid):
    if not is_admin(message.chat.id): return
    try:
        amt = float(message.text.strip())
        if amt <= 0: raise ValueError
        new_bal = update_user_balance(uid, amt, add=False)
        txn_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
        db.execute("INSERT INTO transactions (txn_id, user_id, amount, type, status, admin_note, created_date, processed_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                   (txn_id, uid, amt, "admin_debit", "completed", f"by {message.chat.id}",
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        bot.send_message(message.chat.id, f"✅ Removed ₹{amt} from <code>{uid}</code>\n💰 New: <code>₹{new_bal:.2f}</code>", reply_markup=admin_panel_keyboard(), parse_mode='HTML')
    except:
        bot.send_message(message.chat.id, "❌ Invalid amount.", reply_markup=admin_panel_keyboard())

def remove_admin_by_id(message):
    if not is_admin(message.chat.id): return
    try:
        uid = int(message.text.strip())
        if remove_admin(uid):
            bot.send_message(message.chat.id, f"✅ Admin removed: <code>{uid}</code>", reply_markup=manage_admins_keyboard(), parse_mode='HTML')
        else:
            bot.send_message(message.chat.id, "❌ Cannot remove super admin.", reply_markup=manage_admins_keyboard())
    except:
        bot.send_message(message.chat.id, "❌ Invalid ID.", reply_markup=manage_admins_keyboard())

# ============================================================
# BACKUP / EXPORT
# ============================================================
def export_db_file(message):
    try:
        if os.path.exists(db.db_file):
            with open(db.db_file, 'rb') as f:
                bot.send_document(message.chat.id, f, caption=f"💾 <b>Database Backup</b>\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", parse_mode='HTML')
        else:
            bot.send_message(message.chat.id, "❌ DB file not found.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Export error: {e}")

def export_csv(message, name, query):
    try:
        import csv, io
        rows = db.execute(query, fetch_all=True)
        if not rows:
            bot.send_message(message.chat.id, "📭 No data."); return
        cols = rows[0].keys()
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(cols)
        for r in rows:
            writer.writerow([r[c] for c in cols])
        bio = io.BytesIO(buf.getvalue().encode('utf-8'))
        bio.name = f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        bot.send_document(message.chat.id, bio, caption=f"📊 {name.upper()} Export")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ CSV export error: {e}")

# ============================================================
# USER FUNCTIONS
# ============================================================
def show_profile(message):
    user = get_user(message.chat.id)
    if not user:
        return
    bal = float(user[4]) if user[4] is not None else 0
    joined = user[5]
    total_orders = user[6] if user[6] is not None else 0
    successful = user[7] if user[7] is not None else 0
    spent = float(user[8]) if user[8] is not None else 0
    rej = user[10] if len(user) > 10 else 0
    refs = user[14] if len(user) > 14 else 0
    comm = float(user[15]) if len(user) > 15 else 0
    total_deposit = get_user_total_deposit(message.chat.id)
    rate = (successful / total_orders * 100) if total_orders > 0 else 0
    text = (f'<tg-emoji emoji-id="6032693626394382504">👤</tg-emoji> <b>My Profile</b>\n'
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f'<tg-emoji emoji-id="5447311106030726740">🆔</tg-emoji> ID: <code>{message.chat.id}</code>\n'
            f'<tg-emoji emoji-id="6267068789146260253">💰</tg-emoji> Balance: <code>₹{bal:.2f}</code>\n'
            f'<tg-emoji emoji-id="5447453226498552490">💳</tg-emoji> Total Deposit: <code>₹{total_deposit:.2f}</code>\n'
            f'<tg-emoji emoji-id="6053240981866683172">📅</tg-emoji> Joined: <code>{joined}</code>\n'
            f'<tg-emoji emoji-id="6267039884016358504">⚠️</tg-emoji> Rejections: <code>{rej}/5</code>\n\n'
            f'<tg-emoji emoji-id="6062124099516243830">📊</tg-emoji> <b>Stats:</b>\n'
            f'<tg-emoji emoji-id="5884479287171485878">📦</tg-emoji> Orders: <code>{total_orders}</code>\n'
            f'<tg-emoji emoji-id="5208748315805499400">✅</tg-emoji> Success: <code>{successful}</code>\n'
            f'<tg-emoji emoji-id="6237887278098684962">💸</tg-emoji> Spent: <code>₹{spent:.2f}</code>\n'
            f'<tg-emoji emoji-id="6125218994455582617">🎯</tg-emoji> Rate: <code>{rate:.1f}%</code>\n\n'
            f'<tg-emoji emoji-id="6052886672834566125">🔗</tg-emoji> <b>Referrals:</b>\n'
            f'<tg-emoji emoji-id="6032594876506312598">👥</tg-emoji> Total Referrals: <code>{refs}</code>\n'
            f'<tg-emoji emoji-id="5879991085001871624">💵</tg-emoji> Commission Earned: <code>₹{comm:.2f}</code>')
    bot.send_message(message.chat.id, text, reply_markup=profile_keyboard(), parse_mode='HTML')

def show_balance(message):
    bal = get_user_balance(message.chat.id)
    text = (f'<tg-emoji emoji-id="6267068789146260253">💰</tg-emoji> <b>Your Balance</b>\n\n'
            f'<tg-emoji emoji-id="6053104294532487625">💵</tg-emoji> Available: <code>₹{bal:.2f}</code>\n\n'
            f'<tg-emoji emoji-id="5816492162488995555">📱</tg-emoji> Minimum: ₹10')
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("Deposit", callback_data="deposit", style="success", icon_custom_emoji_id="5816492162488995555"),
        InlineKeyboardButton("Main Menu", callback_data="main_menu", style="danger", icon_custom_emoji_id="5253997076169115797")
    )
    bot.send_message(message.chat.id, text, reply_markup=kb, parse_mode='HTML')

def show_recent_orders(message):
    rows = db.execute("SELECT order_date, service_name, phone_number, price, status FROM orders WHERE user_id = ? ORDER BY order_date DESC LIMIT 10",
                      (message.chat.id,), fetch_all=True)
    if not rows:
        resp = "📦 <b>No orders</b>"
    else:
        resp = "📦 <b>Recent Orders</b>\n\n"
        for r in rows:
            emoji = "✅" if r[4] == "completed" else "⏳" if r[4] == "active" else "❌"
            resp += f"{emoji} 📅 <code>{r[0]}</code>\n🛠 <b>{html.escape(str(r[1]))}</b>\n📞 <code>{html.escape(str(r[2]))}</code>\n💰 <code>₹{r[3]}</code>\n\n---\n\n"
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Back", callback_data="profile"), InlineKeyboardButton("🏠 Home", callback_data="main_menu"))
    bot.send_message(message.chat.id, resp, reply_markup=kb, parse_mode='HTML')

def show_recent_transactions(message):
    rows = db.execute("SELECT created_date, amount, type, status FROM transactions WHERE user_id = ? ORDER BY created_date DESC LIMIT 10",
                      (message.chat.id,), fetch_all=True)
    if not rows:
        resp = "💸 <b>No transactions</b>"
    else:
        resp = "💸 <b>Recent Transactions</b>\n\n"
        for r in rows:
            emoji = "✅" if r[3] == "completed" else "⏳" if r[3] == "pending" else "❌"
            resp += f"{emoji} 📅 <code>{r[0]}</code>\n💰 <code>₹{r[1]}</code>\n📝 <b>{html.escape(str(r[2]))}</b>\n\n---\n\n"
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Back", callback_data="profile"), InlineKeyboardButton("🏠 Home", callback_data="main_menu"))
    bot.send_message(message.chat.id, resp, reply_markup=kb, parse_mode='HTML')

# ============================================================
# REFERRAL
# ============================================================
def show_referral_info(message):
    user = get_user(message.chat.id)
    if not user:
        return
    ref_code = user[13] if len(user) > 13 else None
    refs = user[14] if len(user) > 14 else 0
    comm = float(user[15]) if len(user) > 15 else 0
    link = f"https://t.me/{bot.get_me().username}?start=ref_{ref_code}"
    text = (f'<tg-emoji emoji-id="6052886672834566125">🔗</tg-emoji> <b>Referral Program</b>\n\nEarn <b>5% commission</b> on every deposit made by your referred friends!\n\n'
            f"Your referral link:\n<code>{link}</code>\n\nShare this link with friends.\n\n"
            f'<tg-emoji emoji-id="6032594876506312598">👥</tg-emoji> Total Referrals: <code>{refs}</code>\n'
            f'<tg-emoji emoji-id="6267068789146260253">💰</tg-emoji> Commission Earned: <code>₹{comm:.2f}</code>\n\nTap below to see details.')
    bot.send_message(message.chat.id, text, reply_markup=referral_keyboard(), parse_mode='HTML')

def show_my_referrals(message):
    rows = db.execute("SELECT referred_id, amount, created_date FROM referral_commissions WHERE referrer_id = ? ORDER BY created_date DESC LIMIT 20",
                      (message.chat.id,), fetch_all=True)
    if not rows:
        text = "📋 <b>You haven't referred anyone yet.</b>"
    else:
        text = "📋 <b>Your Referrals</b>\n\n"
        total_comm = 0
        for r in rows:
            ref_id, amt, date = r
            total_comm += amt
            text += f"👤 User <code>{ref_id}</code> earned you <code>₹{amt:.2f}</code> on <code>{date}</code>\n"
        text += f"\n💰 Total Commission: <code>₹{total_comm:.2f}</code>"
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Back", callback_data="referral"))
    bot.send_message(message.chat.id, text, reply_markup=kb, parse_mode='HTML')

# ============================================================
# BUG REPORT
# ============================================================
def receive_bug_report(message):
    if message.text and message.text.lower() == '/cancel':
        bot.send_message(message.chat.id, "❌ Report cancelled.", reply_markup=main_menu_keyboard())
        return
    user_id = message.chat.id
    text = message.text or ""
    media_type = None
    media_id = None
    if message.photo:
        media_type = "photo"
        media_id = message.photo[-1].file_id
    elif message.video:
        media_type = "video"
        media_id = message.video.file_id
    elif message.document:
        media_type = "document"
        media_id = message.document.file_id

    log_bug_report(user_id, text, media_type, media_id)

    for admin in get_admins():
        try:
            admin_msg = f"🐞 <b>New Bug Report</b>\n\nFrom: @{html.escape(str(message.from_user.username))} (<code>{user_id}</code>)\nText: {html.escape(text) if text else 'None'}\nMedia: {media_type if media_type else 'None'}"
            if media_id:
                if media_type == "photo":
                    bot.send_photo(admin[0], media_id, caption=admin_msg, parse_mode='HTML')
                elif media_type == "video":
                    bot.send_video(admin[0], media_id, caption=admin_msg, parse_mode='HTML')
                else:
                    bot.send_document(admin[0], media_id, caption=admin_msg, parse_mode='HTML')
            else:
                bot.send_message(admin[0], admin_msg, parse_mode='HTML')
        except:
            pass
    bot.send_message(user_id, '<tg-emoji emoji-id="5208788125857366775">✅</tg-emoji> Bug report submitted!', reply_markup=main_menu_keyboard(), parse_mode='HTML')

def show_bug_reports(message):
    reports = get_all_bug_reports('pending')
    if not reports:
        bot.send_message(message.chat.id, "📭 No pending bug reports.", reply_markup=admin_panel_keyboard())
        return
    for r in reports:
        rid, uid, text, mtype, mid, status, date = r
        user = get_user(uid)
        uname = user[1] if user else "Unknown"
        txt = f"🆔 Report #{rid}\nFrom: @{html.escape(str(uname))} (<code>{uid}</code>)\nDate: <code>{date}</code>\nText: {html.escape(str(text)) if text else 'None'}\nMedia: {mtype if mtype else 'None'}"
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("✅ Resolve", callback_data=f"resolve_bug_{rid}"))
        if mid and mtype:
            if mtype == "photo":
                bot.send_photo(message.chat.id, mid, caption=txt, reply_markup=kb, parse_mode='HTML')
            elif mtype == "video":
                bot.send_video(message.chat.id, mid, caption=txt, reply_markup=kb, parse_mode='HTML')
            else:
                bot.send_document(message.chat.id, mid, caption=txt, reply_markup=kb, parse_mode='HTML')
        else:
            bot.send_message(message.chat.id, txt, reply_markup=kb, parse_mode='HTML')

# ============================================================
# FEEDBACK
# ============================================================
def receive_feedback(message):
    if message.text and message.text.lower() == '/cancel':
        bot.send_message(message.chat.id, "❌ Feedback cancelled.", reply_markup=main_menu_keyboard())
        return
    text = message.text
    log_feedback(message.chat.id, text)
    for admin in get_admins():
        try:
            bot.send_message(admin[0], f"📝 <b>New Feedback</b>\n\nFrom: @{html.escape(str(message.from_user.username))} (<code>{message.chat.id}</code>)\n\n{html.escape(text)}", parse_mode='HTML')
        except:
            pass
    bot.send_message(message.chat.id, '<tg-emoji emoji-id="5208674601281797706">✅</tg-emoji> Thank you for your feedback!', reply_markup=main_menu_keyboard(), parse_mode='HTML')

def show_feedback(message):
    feedbacks = get_all_feedback()
    if not feedbacks:
        bot.send_message(message.chat.id, "📭 No feedback yet.", reply_markup=admin_panel_keyboard())
        return
    txt = "📝 <b>All Feedback</b>\n\n"
    for f in feedbacks:
        uid, text, date = f[1], f[2], f[3]
        user = get_user(uid)
        uname = user[1] if user else "Unknown"
        txt += f"👤 @{html.escape(str(uname))} (<code>{uid}</code>)\n📅 {date}\n{html.escape(str(text))}\n\n---\n\n"
    bot.send_message(message.chat.id, txt, parse_mode='HTML', reply_markup=admin_panel_keyboard())

# ============================================================
# DEPOSIT ISSUE (customer service)
# ============================================================
def handle_deposit_issue(message):
    bot.delete_message(message.chat.id, message.message_id)
    msg = bot.send_message(message.chat.id, '<tg-emoji emoji-id="5445353829304387411">💳</tg-emoji> <b>Deposit Not Received</b>\n\nPlease send the <b>UTR number</b> and <b>payment screenshot</b>.\n\nSend the UTR first.', parse_mode='HTML')
    bot.register_next_step_handler(msg, deposit_issue_utr)

def deposit_issue_utr(message):
    if message.text and message.text.lower() == '/cancel':
        bot.send_message(message.chat.id, "❌ Cancelled.", reply_markup=main_menu_keyboard())
        return
    utr = message.text.strip()
    if not utr or not utr.isdigit() or len(utr) != 12:
        bot.send_message(message.chat.id, "❌ Invalid UTR! Send a 12-digit number.", reply_markup=main_menu_keyboard())
        return
    deposit_issue_temp[message.chat.id] = {'utr': utr, 'step': 'screenshot'}
    msg = bot.send_message(message.chat.id, '<tg-emoji emoji-id="5309875627187254382">📸</tg-emoji> Now send the <b>payment screenshot</b> (photo).', parse_mode='HTML')
    bot.register_next_step_handler(msg, deposit_issue_screenshot)

def deposit_issue_screenshot(message):
    if message.text and message.text.lower() == '/cancel':
        bot.send_message(message.chat.id, "❌ Cancelled.", reply_markup=main_menu_keyboard())
        deposit_issue_temp.pop(message.chat.id, None)
        return
    if not message.photo:
        bot.send_message(message.chat.id, "❌ Please send a photo screenshot.", reply_markup=main_menu_keyboard())
        return
    photo = message.photo[-1].file_id
    data = deposit_issue_temp.get(message.chat.id, {})
    data['screenshot'] = photo
    data['amount'] = 0
    deposit_issue_temp[message.chat.id] = data

    user = get_user(message.chat.id)
    username = user[1] if user else "Unknown"
    admin_msg = (f"💳 <b>Deposit Issue Report</b>\n\n"
                 f"👤 @{html.escape(str(username))} (<code>{message.chat.id}</code>)\n"
                 f"🔢 UTR: {html.escape(str(data.get('utr', 'N/A')))} \n"
                 f"📸 Screenshot attached.\n\n"
                 f"<b>Admin action:</b>\n"
                 f"Use the buttons below to add deposit manually.")
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Approve", callback_data=f"approve_deposit_issue_{message.chat.id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"reject_deposit_issue_{message.chat.id}")
    )
    for admin in get_admins():
        try:
            bot.send_photo(admin[0], photo, caption=admin_msg, reply_markup=kb, parse_mode='HTML')
        except:
            pass
    bot.send_message(message.chat.id, '<tg-emoji emoji-id="5444987348334965906">✅</tg-emoji> Deposit issue reported! Admin will review it shortly.', reply_markup=main_menu_keyboard(), parse_mode='HTML')

# ============================================================
# SERVICE PRICE MANAGEMENT
# ============================================================
def show_service_prices(message):
    rows = get_all_service_prices()
    if not rows:
        services = get_services_list()
        for code, info in services.items():
            api_price = float(info.get('price', 10))
            db.execute("INSERT OR IGNORE INTO service_prices (service_code, api_price, sell_price, updated_by, updated_date) VALUES (?, ?, ?, ?, ?)",
                       (code, api_price, api_price, ADMIN_ID, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        rows = get_all_service_prices()
    if not rows:
        bot.send_message(message.chat.id, "❌ No services found.", reply_markup=admin_panel_keyboard())
        return
    txt = "💰 <b>Service Prices</b>\n\n"
    for r in rows:
        scode, api, sell, updated = r
        txt += f"<code>{html.escape(str(scode))}</code> | API: ₹{api} | Sell: ₹{sell if sell is not None else api}\n"
    txt += "\nTo change a price, send:\n<code>/setprice service_code new_sell_price</code>"
    bot.send_message(message.chat.id, txt, parse_mode='HTML', reply_markup=admin_panel_keyboard())

@bot.message_handler(commands=['setprice'])
def set_price_command(message):
    if not is_admin(message.chat.id):
        bot.reply_to(message, "❌ Unauthorized!")
        return
    try:
        parts = message.text.split()
        if len(parts) < 3:
            bot.reply_to(message, "Usage: /setprice service_code new_price")
            return
        code = parts[1]
        price = float(parts[2])
        update_service_price(code, price, message.chat.id)
        bot.reply_to(message, f"✅ Price for <code>{html.escape(code)}</code> updated to ₹{price}", parse_mode='HTML')
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")

def admin_search_service(message):
    term = message.text.strip().lower()
    services = get_services_list()
    if not services:
        bot.send_message(message.chat.id, "❌ No services.", reply_markup=admin_panel_keyboard())
        return
    matches = {}
    for code, info in services.items():
        if term in code.lower() or term in info.get('name', '').lower():
            matches[code] = info
    if not matches:
        bot.send_message(message.chat.id, f"❌ No service found for '{html.escape(term)}'.", reply_markup=admin_panel_keyboard(), parse_mode='HTML')
        return
    txt = "🔍 <b>Search Results</b>\n\n"
    for code, info in matches.items():
        api_price = info.get('price', 'N/A')
        sell_price = get_service_price(code)
        txt += f"<code>{html.escape(str(code))}</code> - {html.escape(str(info.get('name', code)))}\nAPI: ₹{api_price} | Sell: ₹{sell_price}\nTo change: <code>/setprice {html.escape(str(code))} new_price</code>\n\n"
    bot.send_message(message.chat.id, txt, parse_mode='HTML', reply_markup=admin_panel_keyboard())

# ============================================================
# MAINTENANCE
# ============================================================
def toggle_maintenance(message):
    current = get_maintenance_mode()
    new_state = not current
    set_maintenance_mode(new_state)
    status = "ON" if new_state else "OFF"
    bot.send_message(message.chat.id, f"🔧 Maintenance mode is now <b>{status}</b>.", parse_mode='HTML', reply_markup=admin_panel_keyboard())
    if not new_state:
        users = db.execute("SELECT user_id FROM users", fetch_all=True)
        for u in users:
            try:
                bot.send_message(u[0], "✅ <b>Bot is back online!</b> You can now use all features.\n\n📱 Click 'Get Number' to start.", parse_mode='HTML')
            except:
                pass

# ============================================================
# DEPOSIT FLOW (AUTO PAYMENT GATEWAY)
# ============================================================

EMO_CARD      = "6019224342666157570"
EMO_MONEY     = "5990147899403539264"
EMO_RUPEE     = "6053104294532487625"
EMO_PIN       = "6264537399846507987"
EMO_PENCIL    = "6228510501203088015"
EMO_POINTDOWN = "6147439566107186310"
EMO_STEP1     = "6129873970205302255"
EMO_STEP2     = "6122695903032645231"
EMO_STEP3     = "6136461792907370226"
EMO_SUCCESS   = "5208748315805499400"
EMO_BALANCE   = "6062124099516243830"
EMO_FAIL      = "6118672807166482201"
EMO_STATUS    = "6116236950824293871"

def e(emoji_id, char):
    return f'<tg-emoji emoji-id="{emoji_id}">{char}</tg-emoji>'

def _strip_html(text):
    return re.sub(r'<[^>]+>', '', text)

def safe_send_html(chat_id, text, reply_markup=None):
    try:
        return bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode='HTML')
    except Exception as ex:
        print(f"[deposit] HTML send failed, falling back to plain text: {ex}")
        try:
            return bot.send_message(chat_id, _strip_html(text), reply_markup=reply_markup)
        except Exception as ex2:
            print(f"[deposit] plain-text send also failed: {ex2}")
            return None

def safe_send_photo_html(chat_id, photo, caption, reply_markup=None):
    try:
        return bot.send_photo(chat_id, photo, caption=caption, reply_markup=reply_markup, parse_mode='HTML')
    except Exception as ex:
        print(f"[deposit] photo+HTML send failed, retrying without emoji tags: {ex}")
        try:
            return bot.send_photo(chat_id, photo, caption=_strip_html(caption), reply_markup=reply_markup)
        except Exception as ex2:
            print(f"[deposit] photo send failed entirely, falling back to text message: {ex2}")
            return safe_send_html(chat_id, caption, reply_markup)

def ask_deposit_amount(message):
    text = (
        "╔══════════════════╗\n"
        f"   {e(EMO_CARD,'💳')} DEPOSIT   \n"
        "╚══════════════════╝\n\n"
        f"{e(EMO_MONEY,'💰')} Enter amount {e(EMO_RUPEE,'💸')}\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"{e(EMO_PIN,'📌')} Min: ₹10\n"
        f"{e(EMO_PIN,'📌')} Max: ₹10,000\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        f"{e(EMO_PENCIL,'✏️')} Example: 100, 250, 500\n\n"
        f"{e(EMO_POINTDOWN,'👇')} Send amount:"
    )
    msg = safe_send_html(message.chat.id, text)
    if msg is None:
        return
    bot.register_next_step_handler(msg, process_deposit_amount_input)

def process_deposit_amount_input(message):
    try:
        amt = float(message.text.strip())
    except:
        bot.send_message(message.chat.id, "❌ Invalid amount!", reply_markup=main_menu_keyboard())
        return
    if amt < 10:
        bot.send_message(message.chat.id, "❌ Minimum ₹10!", reply_markup=main_menu_keyboard())
        return
    if amt > 10000:
        bot.send_message(message.chat.id, "❌ Maximum ₹10,000!", reply_markup=main_menu_keyboard())
        return

    oid = generate_order_id()
    user_temp_data.setdefault(message.chat.id, {})['pay_amount'] = amt
    user_temp_data[message.chat.id]['deposit_order_id'] = oid

    # Use current merchant name from settings
    _, _, merchant_name = get_gateway_settings()

    upi = (
        "upi://pay?pa=" + quote(UPI_ID) +
        "&pn=" + quote(merchant_name) +
        "&tid=" + oid +
        "&tr=" + oid +
        "&tn=VC Payment" +
        "&am=" + str(int(amt)) +
        "&cu=INR"
    )
    qr_url = "https://quickchart.io/qr?text=" + quote(upi, safe="")

    text = (
        "╔════════════════════╗\n"
        f"   {e(EMO_CARD,'💳')} DEPOSIT PAYMENT\n"
        "╚════════════════════╝\n\n"
        f"<b>Order ID:</b> <code>{oid}</code>\n"
        f"<b>Amount:</b> ₹{int(amt)}\n"
        f"<b>Range:</b> ₹10 - ₹10,000\n\n"
        "<b>Steps:</b>\n"
        f"{e(EMO_STEP1,'1️⃣')} Scan QR in any UPI app\n"
        f"{e(EMO_STEP2,'2️⃣')} Complete payment\n"
        f"{e(EMO_STEP3,'3️⃣')} Click I Have Paid"
    )
    safe_send_photo_html(message.chat.id, qr_url, text, reply_markup=deposit_keyboard(oid, amt))

def generate_order_id():
    return "ORD" + str(int(datetime.now().timestamp() * 1000))

def verify_gateway_payment(chat_id, order_id):
    try:
        amt = user_temp_data.get(chat_id, {}).get('pay_amount', 0)
        if not amt:
            row = db.execute("SELECT amount FROM transactions WHERE order_id = ?", (order_id,), fetch_one=True)
            amt = row[0] if row else 0

        result = call_payment_gateway(order_id, amt)

        if result.get('ok') and result.get('success'):
            credit_gateway_deposit(chat_id, order_id, amt)
        else:
            text = (
                f"{e(EMO_FAIL,'❌')} Payment Not Found\n\n"
                f"{e(EMO_PENCIL,'🆔')} Order ID: <code>{order_id}</code>\n"
                f"{e(EMO_STATUS,'📌')} Status: Payment Not Received\n\n"
                f"Please Complete Your Payment And Try Again {e(EMO_SUCCESS,'✅')}"
            )
            safe_send_html(chat_id, text, reply_markup=deposit_keyboard(order_id, amt))
    except Exception as ex:
        print(f"[deposit] verify_gateway_payment error: {ex}")
        try:
            bot.send_message(chat_id, "❌ Something went wrong while checking payment. Please try again.", reply_markup=main_menu_keyboard())
        except:
            pass

def call_payment_gateway(order_id, amount):
    """Uses gateway settings from DB — changeable from admin panel."""
    try:
        api_key, api_url, _ = get_gateway_settings()
        url = (
            f"{api_url}?api_key={quote(api_key)}"
            f"&order_id={quote(order_id)}"
            f"&amount={quote(str(amount))}"
        )
        resp = requests.get(url, timeout=15)
        try:
            data = resp.json()
        except Exception:
            data = {}
        status_val = str(data.get("status", "")).lower()
        is_success = status_val in ("success", "paid", "completed", "true", "1") or data.get("success") is True
        return {"ok": True, "success": is_success, "raw": data}
    except Exception as ex:
        return {"ok": False, "success": False, "error": str(ex)}

def credit_gateway_deposit(chat_id, order_id, amount):
    existing = db.execute("SELECT txn_id FROM transactions WHERE order_id = ?", (order_id,), fetch_one=True)
    if existing:
        return

    txn_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with db.get_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, chat_id))
            c.execute("SELECT balance FROM users WHERE user_id = ?", (chat_id,))
            new_bal = c.fetchone()[0]
            c.execute("INSERT INTO transactions (txn_id, user_id, amount, gateway_fee, type, status, order_id, created_date, processed_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      (txn_id, chat_id, amount, 0, "deposit", "completed", order_id, now, now))

            c.execute("SELECT referred_by FROM users WHERE user_id = ?", (chat_id,))
            ref_row = c.fetchone()
            if ref_row and ref_row[0]:
                referrer_id = ref_row[0]
                commission = amount * 0.05
                if commission > 0:
                    c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (commission, referrer_id))
                    c.execute("UPDATE users SET total_commission = total_commission + ? WHERE user_id = ?", (commission, referrer_id))
                    c.execute("UPDATE users SET total_referrals = total_referrals + 1 WHERE user_id = ?", (referrer_id,))
                    c.execute("INSERT INTO referral_commissions (referrer_id, referred_id, amount, deposit_id, created_date) VALUES (?, ?, ?, ?, ?)",
                              (referrer_id, chat_id, commission, order_id, now))
                    try:
                        bot.send_message(referrer_id, f"🎉 <b>Referral Commission!</b>\n\nYour referred user deposited ₹{amount:.2f}.\nYou earned ₹{commission:.2f} (5%).", parse_mode='HTML')
                    except:
                        pass
            conn.commit()
    except Exception as ex:
        bot.send_message(chat_id, f"❌ Error crediting deposit: {ex}")
        return

    user_temp_data.get(chat_id, {}).pop('pay_amount', None)
    user_temp_data.get(chat_id, {}).pop('deposit_order_id', None)

    user_text = (
        f"{e(EMO_SUCCESS,'🎉')} Payment Successful\n\n"
        f"{e(EMO_PENCIL,'🆔')} Order ID: <code>{order_id}</code>\n"
        f"{e(EMO_MONEY,'💰')} Added: ₹{amount:.2f}\n"
        f"{e(EMO_BALANCE,'📈')} New Balance: ₹{new_bal:.2f}"
    )
    safe_send_html(chat_id, user_text, reply_markup=main_menu_keyboard())

    u = get_user(chat_id)
    username = u[1] if u and len(u) > 1 else None
    first_name = u[2] if u and len(u) > 2 else None
    try:
        tg_user = bot.get_chat(chat_id)
        username = tg_user.username or username
        first_name = tg_user.first_name or first_name
    except:
        pass

    admin_text = (
        "🟢 <b>New Successful Payment</b>\n\n"
        f"👤 Name: <b>{html.escape(str(first_name)) if first_name else 'N/A'}</b>\n"
        f"🔖 Username: @{html.escape(str(username)) if username else 'N/A'}\n"
        f"😎 User ID: <code>{chat_id}</code>\n"
        f"🆔 Order ID: <code>{order_id}</code>\n"
        f"💰 Amount: ₹{amount:.2f}\n"
        f"📈 New Balance: ₹{new_bal:.2f}"
    )
    notify_ids = set(ADMINS)
    for a in get_admins():
        notify_ids.add(a[0])
    for admin_id in notify_ids:
        safe_send_html(admin_id, admin_text)

# ============================================================
# PROMO CODES
# ============================================================
def generate_promo_code(message):
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    msg = bot.send_message(message.chat.id, "💰 <b>Enter Promo Amount:</b>", parse_mode='HTML')
    bot.register_next_step_handler(msg, lambda m: process_promo_amount(m, code))

def process_promo_amount(message, code):
    try:
        amt = float(message.text.strip())
        msg = bot.send_message(message.chat.id, "📊 <b>Enter Max Uses:</b>", parse_mode='HTML')
        bot.register_next_step_handler(msg, lambda m: process_promo_uses(m, code, amt))
    except:
        bot.send_message(message.chat.id, "❌ Invalid amount!", reply_markup=admin_panel_keyboard())

def process_promo_uses(message, code, amount):
    try:
        uses = int(message.text.strip())
        db.execute("INSERT INTO promoCodes (code, amount, uses_left, max_uses, created_by, created_date) VALUES (?, ?, ?, ?, ?, ?)",
                   (code, amount, uses, uses, message.chat.id, datetime.now().strftime("%Y-%m-%d")))
        bot.send_message(message.chat.id, f"✅ <b>Promo Code Generated!</b>\n\n🎫 <code>{code}</code>\n💰 ₹{amount}\n📊 {uses} uses",
                         reply_markup=admin_panel_keyboard(), parse_mode='HTML')
    except:
        bot.send_message(message.chat.id, "❌ Invalid uses!", reply_markup=admin_panel_keyboard())

def process_promo_claim(message):
    code = message.text.strip().upper()
    try:
        with db.get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT amount, uses_left FROM promoCodes WHERE code = ? AND (expiry_date IS NULL OR expiry_date > date('now'))", (code,))
            row = c.fetchone()
            if not row:
                bot.send_message(message.chat.id, "❌ Invalid promo code!", reply_markup=main_menu_keyboard())
                return
            amt, left = row
            if left <= 0:
                bot.send_message(message.chat.id, "❌ Promo expired!", reply_markup=main_menu_keyboard())
                return
            c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amt, message.chat.id))
            c.execute("SELECT balance FROM users WHERE user_id = ?", (message.chat.id,))
            new_bal = c.fetchone()[0]
            c.execute("UPDATE promoCodes SET uses_left = uses_left - 1 WHERE code = ?", (code,))
            txn_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
            c.execute("INSERT INTO transactions (txn_id, user_id, amount, type, status, created_date) VALUES (?, ?, ?, ?, ?, ?)",
                      (txn_id, message.chat.id, amt, "promo", "completed", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
        text = (f'<tg-emoji emoji-id="5447242579827523388">🎉</tg-emoji> Promo Redeemed!\n\n'
                f'<tg-emoji emoji-id="6240085923397114865">💰</tg-emoji> ₹{amt:.1f} added!\n'
                f'<tg-emoji emoji-id="5445353829304387411">💳</tg-emoji> New balance: ₹{new_bal:.2f}')
        bot.send_message(message.chat.id, text, reply_markup=main_menu_keyboard(), parse_mode='HTML')
    except Exception as e:
        print(e)
        bot.send_message(message.chat.id, "❌ Error claiming promo!", reply_markup=main_menu_keyboard())

# ============================================================
# ORDER PROCESSING
# ============================================================
def request_number(message, service_code, country_code, server, price, proc_msg=None):
    try:
        if proc_msg is None:
            proc_msg = bot.send_message(message.chat.id, LOADING_MSG)

        bal = get_user_balance(message.chat.id)
        if bal < price:
            bot.edit_message_text(f"❌ <b>Insufficient Balance!</b>\n\n💰 Balance: <code>₹{bal:.2f}</code>\n💸 Required: <code>₹{price}</code>",
                                  message.chat.id, proc_msg.message_id,
                                  reply_markup=main_menu_keyboard(), parse_mode='HTML')
            return

        for step in range(5):
            animate_loading(message.chat.id, proc_msg.message_id, step+1, 5)
            time.sleep(1.2)

        result = None
        if server:
            result = get_number(service_code, country_code, server)
        else:
            # Try custom servers first (from admin panel), then API servers
            custom = get_custom_servers()
            all_servers = [r[0] for r in custom] if custom else []
            api_servers = get_servers()
            if api_servers:
                all_servers += list(api_servers.keys())

            for srv in all_servers:
                result = get_number(service_code, country_code, srv)
                if result and result.get('status') == 'OK':
                    server = srv
                    break
            if not result or result.get('status') != 'OK':
                result = get_number(service_code, country_code)

        if result and result.get('status') == 'OK':
            services = get_services_list(country_code, server)
            service_name = services.get(service_code, {}).get('name', service_code.upper()) if services else service_code.upper()
            phone = result.get('phone_number', 'N/A')
            activation_id = result.get('order_id', 'N/A')

            new_bal = update_user_balance(message.chat.id, price, add=False)
            expires_at = (datetime.now() + timedelta(minutes=20)).strftime("%Y-%m-%d %H:%M:%S")
            db.execute("INSERT INTO orders (order_id, user_id, service_code, service_name, phone_number, price, status, order_date, expires_at, otps_received) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (activation_id, message.chat.id, service_code, service_name, phone, price, "active",
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"), expires_at, 0))
            db.execute("UPDATE users SET total_orders = total_orders + 1, total_spent = total_spent + ? WHERE user_id = ?",
                       (price, message.chat.id))

            session = OTPSession(message.chat.id, service_code, service_name, activation_id, activation_id, phone, price, country_code)
            user_sessions[message.chat.id] = session
            server_info = f" (Server: {html.escape(str(server))})" if server else ""
            display_phone = f"+{phone}" if phone != "N/A" else phone
            rem = session.get_remaining_time()
            
            response = (f"✅ <b>Number Received!</b>{server_info}\n\n"
                        f"📞 <b>Number:</b> <code>{html.escape(display_phone)}</code>\n"
                        f"🛠 <b>Service:</b> <i>{html.escape(service_name)}</i>\n"
                        f"💰 <b>Price:</b> <code>₹{price}</code>\n"
                        f"💳 <b>Balance:</b> <code>₹{new_bal:.2f}</code>\n\n"
                        f"⏱ <b>Time Remaining:</b> <code>{rem}</code>\n"
                        f"⏳ <i>Cancel available after 2 minutes.</i>")
            
            bot.edit_message_text(response, message.chat.id, proc_msg.message_id,
                                  reply_markup=order_management_keyboard(session.activation_id, 0, session),
                                  parse_mode='HTML')
            start_monitoring(session)
            start_expiry_timer(session)

            user = get_user(message.chat.id)
            username = user[1] if user else "Unknown"
            admin_notif = (f"📱 <b>OTP Purchase Alert</b>\n\n"
                           f"👤 @{html.escape(str(username))} (<code>{message.chat.id}</code>)\n"
                           f"🛠 Service: <i>{html.escape(service_name)}</i>\n"
                           f"📞 Number: <code>{html.escape(phone)}</code>\n"
                           f"💰 Price: <code>₹{price}</code>\n"
                           f"🆔 Order: <code>{html.escape(str(activation_id))}</code>")
            for admin in get_admins():
                try:
                    bot.send_message(admin[0], admin_notif, parse_mode='HTML')
                except:
                    pass
        else:
            err = html.escape(str(result.get('message', result.get('raw', 'No numbers'))) if result else 'No result')
            help_text = f"❌ <b>Failed to get number</b>\n\n<b>Error:</b> {err}\n\nTry different service or country."
            bot.edit_message_text(help_text, message.chat.id, proc_msg.message_id,
                                  reply_markup=main_menu_keyboard(), parse_mode='HTML')
    except Exception as e:
        import traceback
        traceback.print_exc()
        err_msg = html.escape(str(e))
        try:
            bot.edit_message_text(f"❌ <b>Error:</b> {err_msg}\n\nTry again.",
                                  message.chat.id, proc_msg.message_id,
                                  reply_markup=main_menu_keyboard(), parse_mode='HTML')
        except:
            try:
                bot.send_message(message.chat.id, f"❌ <b>Error:</b> {err_msg}\n\nTry again.", reply_markup=main_menu_keyboard(), parse_mode='HTML')
            except:
                pass

def start_monitoring(session):
    if session.monitoring:
        return
    session.monitoring = True

    def monitor():
        waited = 0
        while waited < 300:
            if session.user_id not in user_sessions:
                break
            if datetime.now() > session.expires_at:
                break
            res = get_activation_status(session.activation_id)
            if res.get('status') == 'OK' and res.get('sms'):
                sms = res['sms']
                match = re.search(r'\b\d{4,8}\b', sms)
                if match:
                    code = match.group()
                    if code not in session.otps_received:
                        session.otps_received.append(code)
                        cnt = len(session.otps_received)
                        db.execute("UPDATE orders SET otps_received = ? WHERE order_id = ?", (cnt, session.activation_id))
                        rem = session.get_remaining_time()
                        try:
                            bot.send_message(session.user_id,
                                f"🎉 <b>New OTP!</b> (#{cnt})\n\n🔐 <b>Code:</b> <code>{code}</code>\n⏱ <b>Time Left:</b> <code>{rem}</code>",
                                reply_markup=order_management_keyboard(session.activation_id, cnt, session),
                                parse_mode='HTML')
                        except:
                            pass
                break
            time.sleep(10)
            waited += 10
    threading.Thread(target=monitor, daemon=True).start()

def start_expiry_timer(session):
    def expire():
        time.sleep(20 * 60)
        if session.user_id in user_sessions:
            cur = user_sessions.get(session.user_id)
            if cur and cur.order_id == session.order_id:
                otps = db.execute("SELECT otps_received FROM orders WHERE order_id = ?", (session.activation_id,), fetch_one=True)
                otp_count = otps[0] if otps else 0
                if otp_count == 0:
                    new_bal = refund_user(session.user_id, session.price, session.order_id)
                    db.execute("UPDATE orders SET status = 'expired' WHERE order_id = ?", (session.activation_id,))
                    if session.user_id in user_sessions:
                        del user_sessions[session.user_id]
                    try:
                        bot.send_message(session.user_id,
                            f"⏰ <b>Order Expired!</b>\n\n20 minutes passed.\n💰 ₹{session.price} refunded.\n💳 New balance: ₹{new_bal:.2f}",
                            reply_markup=main_menu_keyboard(), parse_mode='HTML')
                    except:
                        pass
                else:
                    db.execute("UPDATE orders SET status = 'expired' WHERE order_id = ?", (session.activation_id,))
                    if session.user_id in user_sessions:
                        del user_sessions[session.user_id]
                    try:
                        bot.send_message(session.user_id,
                            f"⏰ <b>Order Expired!</b>\n\n20 minutes passed.\nOTP already received, no refund.",
                            reply_markup=main_menu_keyboard(), parse_mode='HTML')
                    except:
                        pass
    threading.Thread(target=expire, daemon=True).start()

def cancel_specific_order(call, activation_id):
    message = call.message
    session = user_sessions.get(message.chat.id)
    if session and not session.can_cancel():
        wait = session.get_cancel_wait_time()
        bot.answer_callback_query(call.id, f"⏳ Please wait {wait} seconds!", show_alert=True)
        return

    otps = db.execute("SELECT otps_received FROM orders WHERE order_id = ?", (activation_id,), fetch_one=True)
    otp_count = otps[0] if otps else 0

    res = set_activation_status(activation_id, 8)
    if res.get('status') == 'CANCELLED' or 'STATUS_CANCEL' in str(res):
        if session:
            if otp_count == 0:
                new_bal = refund_user(message.chat.id, session.price, activation_id)
                msg = f"✅ <b>Order Cancelled!</b>\n\n💰 ₹{session.price} refunded.\n💳 New balance: ₹{new_bal:.2f}"
            else:
                msg = f"✅ <b>Order Cancelled!</b>\n\n⚠️ OTP already received, no refund."
            db.execute("UPDATE orders SET status = 'cancelled' WHERE order_id = ?", (activation_id,))
            if message.chat.id in user_sessions:
                del user_sessions[message.chat.id]
            bot.send_message(message.chat.id, msg, reply_markup=main_menu_keyboard(), parse_mode='HTML')
        else:
            bot.send_message(message.chat.id, "✅ <b>Order Cancelled!</b>", reply_markup=main_menu_keyboard(), parse_mode='HTML')
    else:
        bot.send_message(message.chat.id, "❌ Cannot cancel.", reply_markup=main_menu_keyboard())

def check_and_show_otp(message, activation_id):
    session = user_sessions.get(message.chat.id)
    res = get_activation_status(activation_id)
    time_display = f"\n⏱ <b>Time Left:</b> <code>{session.get_remaining_time()}</code>" if session else ""
    if res.get('status') == 'OK' and res.get('sms'):
        sms = res['sms']
        match = re.search(r'\b\d{4,8}\b', sms)
        if match:
            code = match.group()
            if session and code not in session.otps_received:
                session.otps_received.append(code)
                cnt = len(session.otps_received)
                db.execute("UPDATE orders SET otps_received = ? WHERE order_id = ?", (cnt, activation_id))
                response = f"✅ <b>OTP Received!</b> (#{cnt})\n\n🔐 <b>Code:</b> <code>{code}</code>{time_display}"
                bot.send_message(message.chat.id, response, reply_markup=order_management_keyboard(activation_id, cnt, session), parse_mode='HTML')
            else:
                cnt = len(session.otps_received) if session else 0
                bot.send_message(message.chat.id, f"⚠️ OTP already received. Total: {cnt}{time_display}", reply_markup=order_management_keyboard(activation_id, cnt, session), parse_mode='HTML')
        else:
            cnt = len(session.otps_received) if session else 0
            bot.send_message(message.chat.id, f"📨 <b>SMS Received!</b>\n\nMessage: <code>{html.escape(str(sms[:200]))}</code>{time_display}", reply_markup=order_management_keyboard(activation_id, cnt, session), parse_mode='HTML')
    elif res.get('status') == 'WAITING':
        cnt = len(session.otps_received) if session else 0
        bot.send_message(message.chat.id, f"⏳ <b>No OTP yet</b> ({cnt} received){time_display}\n\nWait 3-5 seconds.", reply_markup=order_management_keyboard(activation_id, cnt, session), parse_mode='HTML')
    else:
        cnt = len(session.otps_received) if session else 0
        bot.send_message(message.chat.id, f"⏳ Checking... ({cnt} received){time_display}", reply_markup=order_management_keyboard(activation_id, cnt, session), parse_mode='HTML')

def refund_user(user_id, amount, order_id):
    new_bal = update_user_balance(user_id, amount, add=True)
    txn_id = f"REF{datetime.now().strftime('%y%m%d%H%M%S')}{random.randint(1000,9999)}"
    db.execute("INSERT INTO transactions (txn_id, user_id, amount, type, status, order_id, created_date, processed_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
               (txn_id, user_id, amount, "refund", "completed", order_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    return new_bal

# ============================================================
# ADMIN USER MANAGEMENT
# ============================================================
def show_user_list(message):
    users = db.execute("SELECT user_id, username, first_name, balance, total_orders, total_spent, is_banned FROM users ORDER BY joined_date DESC", fetch_all=True)
    if not users:
        bot.send_message(message.chat.id, "📋 No users.", reply_markup=admin_panel_keyboard())
        return
    txt = "👥 <b>User List</b>\n\n"
    for u in users:
        uid, uname, fname, bal, orders, spent, banned = u
        txt += f"🆔 <code>{uid}</code> | @{html.escape(str(uname)) if uname else 'None'} | {html.escape(str(fname)) if fname else 'N/A'}\n"
        txt += f"💰 <code>₹{bal:.2f}</code> | 📦 <code>{orders}</code> | 💸 <code>₹{spent:.2f}</code> | {'🚫 Banned' if banned else '✅ Active'}\n\n"
    bot.send_message(message.chat.id, txt[:4000], parse_mode='HTML', reply_markup=admin_panel_keyboard())

def show_all_bots(message):
    rows = db.execute("SELECT order_id, user_id, service_name, phone_number, status, order_date FROM orders WHERE status='active' ORDER BY order_date DESC", fetch_all=True)
    if not rows:
        txt = "🤖 No active bots."
    else:
        txt = "🤖 <b>Active Orders</b>\n\n"
        for r in rows:
            oid, uid, sname, phone, status, date = r
            txt += f"🆔 <code>{oid}</code>\n👤 User: <code>{uid}</code>\n🛠 Service: <i>{html.escape(str(sname))}</i>\n📞 <code>{html.escape(str(phone))}</code>\n⏳ Status: <code>{status}</code>\n📅 <code>{date}</code>\n\n"
    bot.send_message(message.chat.id, txt, parse_mode='HTML', reply_markup=admin_panel_keyboard())

def show_pending_deposits(message):
    rows = db.execute("SELECT * FROM pending_transactions ORDER BY created_date DESC", fetch_all=True)
    if not rows:
        bot.send_message(message.chat.id, "📭 No pending deposits.", reply_markup=admin_panel_keyboard())
        return
    for r in rows:
        txn_id, uid, amount, fee, utr, screenshot, oid, date = r
        text = f"📝 <b>Pending Deposit</b>\n🆔 Order: <code>{oid}</code>\n👤 User: <code>{uid}</code>\n💰 <code>₹{amount}</code>\n💸 Gateway: <code>₹{fee if fee else 0}</code>\n🔢 UTR: <code>{utr}</code>"
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(InlineKeyboardButton("✅ Approve", callback_data=f"approve_txn_{txn_id}"),
               InlineKeyboardButton("❌ Reject", callback_data=f"reject_txn_{txn_id}"))
        bot.send_message(message.chat.id, text, reply_markup=kb, parse_mode='HTML')
        time.sleep(0.5)

def show_ban_menu(message):
    users = db.execute("SELECT user_id, username, first_name, is_banned FROM users ORDER BY user_id", fetch_all=True)
    if not users:
        bot.send_message(message.chat.id, "📋 No users.", reply_markup=admin_panel_keyboard())
        return
    kb = InlineKeyboardMarkup(row_width=2)
    for u in users[:50]:
        uid, uname, fname, banned = u
        label = f"{'🚫' if banned else '✅'} {uname if uname else uid} ({uid})"
        cb = f"admin_{'unban' if banned else 'ban'}_user_{uid}"
        kb.add(InlineKeyboardButton(label, callback_data=cb))
    kb.add(InlineKeyboardButton("🔙 Back", callback_data="admin_panel"))
    bot.send_message(message.chat.id, "🚫 <b>Ban/Unban Users</b>\n\nTap a user to toggle ban.", reply_markup=kb, parse_mode='HTML')

def add_admin_by_id(message):
    try:
        uid = int(message.text.strip())
        add_admin(uid)
        bot.send_message(message.chat.id, f"✅ User <code>{uid}</code> is now an admin.", parse_mode='HTML', reply_markup=admin_panel_keyboard())
    except:
        bot.send_message(message.chat.id, "❌ Invalid user ID.", reply_markup=admin_panel_keyboard())

def show_admin_list(message):
    admins = get_admins()
    if not admins:
        txt = "📋 No admins."
    else:
        txt = "📋 <b>Admin List</b>\n\n"
        for a in admins:
            uid, uname, fname = a
            txt += f"🆔 <code>{uid}</code> | @{html.escape(str(uname)) if uname else 'None'} | {html.escape(str(fname))}\n"
    bot.send_message(message.chat.id, txt, parse_mode='HTML', reply_markup=admin_panel_keyboard())

# ============================================================
# LEADERBOARD
# ============================================================
def show_leaderboard(message):
    txt = "🏆 <b>Leaderboard</b>\n\n"
    txt += "👥 <b>Top Referrers</b>\n"
    top_ref = get_top_referrers(5)
    if top_ref:
        for idx, (uid, refs, comm) in enumerate(top_ref, 1):
            user = get_user(uid)
            uname = user[1] if user else "Unknown"
            txt += f"{idx}. @{html.escape(str(uname))} - {refs} referrals (₹{comm:.2f})\n"
    else:
        txt += "No referrals yet.\n"

    txt += "\n📱 <b>Top OTP Buyers</b>\n"
    top_otp = get_top_otp_buyers(5)
    if top_otp:
        for idx, (uid, orders, spent) in enumerate(top_otp, 1):
            user = get_user(uid)
            uname = user[1] if user else "Unknown"
            txt += f"{idx}. @{html.escape(str(uname))} - {orders} OTPs (₹{spent:.2f})\n"
    else:
        txt += "No OTP purchases yet.\n"

    txt += "\n💰 <b>Top Depositors</b>\n"
    top_dep = get_top_depositors(5)
    if top_dep:
        for idx, (uid, total) in enumerate(top_dep, 1):
            user = get_user(uid)
            uname = user[1] if user else "Unknown"
            txt += f"{idx}. @{html.escape(str(uname))} - ₹{total:.2f}\n"
    else:
        txt += "No deposits yet.\n"

    bot.send_message(message.chat.id, txt, parse_mode='HTML', reply_markup=admin_panel_keyboard())

def show_referral_stats(message):
    total_refs = db.execute("SELECT SUM(total_referrals) FROM users", fetch_one=True)[0] or 0
    total_comm = db.execute("SELECT SUM(total_commission) FROM users", fetch_one=True)[0] or 0
    txt = f"📊 <b>Referral Stats</b>\n\nTotal Referrals: {total_refs}\nTotal Commission Paid: ₹{total_comm:.2f}\n\nTop referrers shown in leaderboard."
    bot.send_message(message.chat.id, txt, parse_mode='HTML', reply_markup=admin_panel_keyboard())

def show_user_stats(message):
    total_users, total_balance, total_revenue, total_orders, pending = get_user_stats()
    txt = (f"📊 <b>User Stats</b>\n"
           "━━━━━━━━━━━━━━━━━━━━━\n"
           f"👥 Total Users: <code>{total_users}</code>\n"
           f"💰 Total Balance: <code>₹{total_balance:.2f}</code>\n"
           f"💵 Total Revenue: <code>₹{total_revenue:.2f}</code>\n"
           f"📦 Total Orders: <code>{total_orders}</code>\n"
           f"⏳ Pending Deposits: <code>{pending}</code>\n"
           "━━━━━━━━━━━━━━━━━━━━━")
    bot.send_message(message.chat.id, txt, parse_mode='HTML', reply_markup=admin_panel_keyboard())

# ============================================================
# GIVE PLAN
# ============================================================
def give_plan(message):
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Invalid! Use: <code>user_id amount</code>", parse_mode='HTML')
            return
        uid = int(parts[0])
        amt = float(parts[1])
        new_bal = update_user_balance(uid, amt, add=True)
        bot.send_message(message.chat.id, f"✅ Added ₹{amt} to <code>{uid}</code>\n💳 New balance: ₹{new_bal:.2f}", parse_mode='HTML', reply_markup=admin_panel_keyboard())
        try:
            bot.send_message(uid, f"🎁 You received a gift of ₹{amt}!\n💳 New balance: ₹{new_bal:.2f}", parse_mode='HTML')
        except:
            pass
    except:
        bot.send_message(message.chat.id, "❌ Invalid format. Use: <code>user_id amount</code>", reply_markup=admin_panel_keyboard())

# ============================================================
# BROADCAST
# ============================================================
def broadcast_message(message):
    txt = message.text
    users = db.execute("SELECT user_id FROM users", fetch_all=True)
    ok, fail = 0, 0
    status = bot.send_message(message.chat.id, f"📢 Broadcasting to {len(users)} users...")
    for u in users:
        try:
            bot.send_message(u[0], f"📢 <b>Announcement</b>\n\n{html.escape(txt)}", parse_mode='HTML')
            ok += 1
            time.sleep(0.05)
        except:
            fail += 1
    bot.edit_message_text(f"✅ Broadcast Complete!\n\n✅ Success: {ok}\n❌ Failed: {fail}", message.chat.id, status.message_id)
    show_admin_panel(message)

# ============================================================
# FORCE JOIN
# ============================================================
def check_force_join(user_id):
    channels = db.execute("SELECT channel_id, channel_type, channel_link FROM force_join_channels", fetch_all=True)
    if not channels:
        return True, None, None
    for ch in channels:
        cid, ctype, clink = ch
        try:
            if ctype in ("public_link", "public"):
                if clink:
                    username = clink.replace('https://t.me/', '').replace('@', '').split('/')[0]
                    member = bot.get_chat_member(f"@{username}", user_id)
                else:
                    member = bot.get_chat_member(int(cid), user_id)
            else:
                member = bot.get_chat_member(int(cid), user_id)
            if member.status in ('left', 'kicked'):
                return False, clink, cid
        except:
            return False, clink, cid
    return True, None, None

def show_force_join_menu(message):
    kb = create_force_join_keyboard()
    bot.send_message(message.chat.id, "🏠 <b>Force Join Channels</b>\n\nAdd or remove channels that users must join.", reply_markup=kb, parse_mode='HTML')

def process_add_channel(message):
    details = message.text.strip()
    parts = details.split(',')
    if len(parts) < 3:
        bot.send_message(message.chat.id, "❌ Invalid format! Use: <code>link,channel_id,channel_name</code>", parse_mode='HTML')
        return
    link = parts[0].strip() or None
    cid = parts[1].strip() or None
    name = parts[2].strip()
    if link and (link.startswith('http') or link.startswith('@') or not link.startswith('-')):
        ctype = "public_link"
        if link.startswith('@'):
            link = link[1:]
        elif link.startswith('https://t.me/'):
            link = link.replace('https://t.me/', '')
        store_id = link
    else:
        ctype = "private_id"
        store_id = cid
    if not store_id:
        bot.send_message(message.chat.id, "❌ Invalid channel ID!", reply_markup=create_force_join_keyboard())
        return
    try:
        db.execute("INSERT INTO force_join_channels (channel_id, channel_type, channel_link, channel_name, added_by, added_date) VALUES (?, ?, ?, ?, ?, ?)",
                   (store_id, ctype, link if link else cid, name, message.chat.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        bot.send_message(message.chat.id, f"✅ <b>Channel added!</b>\n\n📌 {html.escape(name)}\n🔗 {html.escape(str(link)) if link else 'Private'}\n🆔 {html.escape(str(store_id))}", reply_markup=create_force_join_keyboard(), parse_mode='HTML')
    except sqlite3.IntegrityError:
        bot.send_message(message.chat.id, "❌ Channel already exists!", reply_markup=create_force_join_keyboard())
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Error: {e}", reply_markup=create_force_join_keyboard())
    if message.chat.id in pending_channel_input:
        del pending_channel_input[message.chat.id]

def show_channel_list(message):
    rows = db.execute("SELECT channel_id, channel_type, channel_link, channel_name FROM force_join_channels", fetch_all=True)
    if not rows:
        bot.send_message(message.chat.id, "📭 No channels configured.", reply_markup=create_force_join_keyboard())
        return
    txt = "🏠 <b>Force Join Channels</b>\n\n"
    for r in rows:
        cid, ctype, clink, cname = r
        txt += f"📌 <b>{html.escape(str(cname))}</b>\n🔗 Link: <code>{html.escape(str(clink)) if clink else 'Private'}</code>\n🆔 ID: <code>{html.escape(str(cid))}</code>\n📝 Type: {ctype}\n\n"
    bot.send_message(message.chat.id, txt, reply_markup=create_force_join_keyboard(), parse_mode='HTML')

def remove_channel_admin(message):
    ident = message.text.strip()
    db.execute("DELETE FROM force_join_channels WHERE channel_id = ? OR channel_link = ?", (ident, ident))
    bot.send_message(message.chat.id, "✅ Channel removed!", reply_markup=create_force_join_keyboard())

# ============================================================
# SEARCH SERVICE (user)
# ============================================================
def search_service(message):
    term = message.text.strip().lower()
    cc = user_temp_data.get(message.chat.id, {}).get('selected_country', '22')
    services = get_services_list(cc)
    if not services:
        bot.send_message(message.chat.id, "❌ No services.", reply_markup=main_menu_keyboard())
        return
    matches = {}
    for code, info in services.items():
        name = info.get('name', '').lower()
        if term in name or term in code.lower():
            matches[code] = info
    if not matches:
        bot.send_message(message.chat.id, f"❌ No services found for '{html.escape(term)}'.", reply_markup=services_keyboard(services, cc), parse_mode='HTML')
        return
    kb = InlineKeyboardMarkup(row_width=1)
    for code, info in list(matches.items())[:20]:
        name = info.get('name', code.upper())[:30]
        price = get_service_price(code)
        kb.add(InlineKeyboardButton(f"📱 {name} - ₹{price}", callback_data=f"select_service_{code}|{price}|{cc}"))
    kb.add(InlineKeyboardButton("🔍 New Search", callback_data="search_service"))
    kb.add(InlineKeyboardButton("📱 All Services", callback_data="get_number"))
    kb.add(InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu"))
    bot.send_message(message.chat.id, f"🔍 <b>Results for '{html.escape(term)}'</b>\n\nFound {len(matches)} services:", reply_markup=kb, parse_mode='HTML')

# ============================================================
# COMMAND HANDLERS
# ============================================================
@bot.message_handler(commands=['admin'])
def admin_command(message):
    if is_admin(message.chat.id):
        show_admin_panel(message)
    else:
        bot.reply_to(message, "❌ Unauthorized!")

@bot.message_handler(commands=['addadmin'])
def add_admin_command(message):
    if message.chat.id != ADMIN_ID:
        bot.reply_to(message, "❌ Only main admin can add admins.")
        return
    try:
        uid = int(message.text.split()[1])
        add_admin(uid)
        bot.reply_to(message, f"✅ Admin added: {uid}")
    except:
        bot.reply_to(message, "Usage: /addadmin user_id")

@bot.message_handler(commands=['removeadmin'])
def remove_admin_command(message):
    if message.chat.id != ADMIN_ID:
        bot.reply_to(message, "❌ Only main admin can remove admins.")
        return
    try:
        uid = int(message.text.split()[1])
        if remove_admin(uid):
            bot.reply_to(message, f"✅ Admin removed: {uid}")
        else:
            bot.reply_to(message, "❌ Cannot remove main admin.")
    except:
        bot.reply_to(message, "Usage: /removeadmin user_id")

@bot.message_handler(commands=['balance'])
def balance_command(message):
    bal = get_user_balance(message.chat.id)
    bot.reply_to(message, f"💰 <b>Your Balance:</b> ₹{bal:.2f}", parse_mode='HTML')

# ============================================================
# MAIN
# ============================================================
if __name__ == '__main__':
    print("=" * 60)
    print("💰 Turbo OTP Bot - Premium Version")
    print("🤖 With Referral System & Advanced Admin Panel")
    print("=" * 60)
    print(f"Bot Token: {BOT_TOKEN[:20]}...")
    print(f"Main Admin: {ADMIN_ID}")
    print(f"Support: @{SUPPORT_USERNAME}")
    print("=" * 60)

    print("\n📡 Initializing database...")
    init_db()

    print("\n📡 Testing API...")
    test_bal = get_balance()
    if test_bal is not None:
        print(f"✅ API Connected! Balance: ₹{test_bal}")
    else:
        print("⚠️ API Issue")

    print("\n" + "=" * 60)
    print("🚀 Bot running! Ctrl+C to stop")
    print("Features: Referral (5%), Maintenance, Bug Reports, Service Price Management, Leaderboard, Live OTP Monitoring, Deposit Issue, Feedback")
    print("NEW: Settings Panel (API/Gateway/Server), Manage User, Manage Admins, Backup/Export")
    print("=" * 60 + "\n")

    while True:
        try:
            bot.infinity_polling(timeout=60, interval=1)
        except (ConnectionError, requests.exceptions.ConnectionError) as e:
            print(f"Connection error: {e}")
            time.sleep(5)
        except KeyboardInterrupt:
            print("\n👋 Bot stopped.")
            break
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(5)