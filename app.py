import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import feedparser
import requests
from bs4 import BeautifulSoup
from textblob import TextBlob
from deep_translator import GoogleTranslator
import xml.etree.ElementTree as ET
import datetime
import time
from time import mktime
from streamlit_autorefresh import st_autorefresh
import re
import plotly.graph_objects as go
import os
import io
import json

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Kwaktong War Room v12.36", page_icon="🦅", layout="wide", initial_sidebar_state="expanded")
st_autorefresh(interval=60000, limit=None, key="warroom_refresher")

if 'manual_overrides' not in st.session_state: st.session_state.manual_overrides = {}

FIREBASE_URL = "https://kwaktong-warroom-default-rtdb.asia-southeast1.firebasedatabase.app/market_data.json"
GOOGLE_SHEET_API_URL = "https://script.google.com/macros/s/AKfycby1vkYO6JiJfPc6sqiCUEJerfzLCv5LxhU7j16S9FYRpPqxXIUiZY8Ifb0YKiCQ7aj3_g/exec"
TELEGRAM_BOT_TOKEN = "8239625215:AAF7qUsz2O5mhINRhRYPTICljJsCErDDLD8"
TELEGRAM_CHAT_ID = "-5078466063"
SCORE_FILE = "daily_score.json"

st.markdown("""
<style>
    div[data-testid="stMetric"] {background-color: #1a1a2e; border: 1px solid #00ccff; padding: 15px !important; border-radius: 8px; box-shadow: 0 0 10px rgba(0,204,255,0.2); text-align: left; height: 120px !important; display: flex; flex-direction: column; justify-content: center;}
    div[data-testid="stMetricValue"] {color: #00ccff; font-size: 24px; font-weight: bold; margin-top: 5px;}
    .plan-card {background-color: #1a1a2e; padding: 20px; border-radius: 10px; border: 2px solid #00ccff; margin-bottom: 10px;}
    .allin-card {background-color: #2b0000; padding: 20px; border-radius: 10px; border: 2px solid #ffcc00; margin-bottom: 10px;}
    .ea-card {background-color: #111; padding: 20px; border-radius: 10px; border: 2px dashed #ffcc00; margin-bottom: 25px; text-align: center;}
    .exec-summary {background-color: #131722; padding: 15px; border-radius: 8px; border-left: 5px solid #d4af37; margin-bottom: 15px;}
    .ff-card {background-color: #222831; padding: 12px; border-radius: 8px; margin-bottom: 10px; border-left: 5px solid #555;}
    .news-card {background-color: #131722; padding: 12px; border-radius: 8px; border-left: 4px solid #f0b90b; margin-bottom: 12px;}
    .session-card {background-color: #1a1a2e; padding: 10px; border-radius: 8px; border: 1px solid #ff00ff; text-align: center; margin-bottom: 15px; font-weight: bold; color: #ff00ff;}
    .scoreboard {background-color: #1a1a2e; padding: 15px; border-radius: 8px; border: 2px solid #d4af37; text-align: center; margin-bottom: 25px;}
    h2.title-header {text-align: center; margin-bottom: 20px; font-weight: bold;}
    .stTabs [data-baseweb="tab"] {background-color: #1a1a2e; border-radius: 5px 5px 0 0;}
    .stTabs [aria-selected="true"] {background-color: #d4af37 !important; color: #000 !important; font-weight: bold;}
</style>
""", unsafe_allow_html=True)

def send_telegram_notify(msg, image_path=None):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return
    if image_path and os.path.exists(image_path):
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        with open(image_path, "rb") as image_file:
            try: requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "caption": msg}, files={"photo": image_file}, timeout=10)
            except: pass
    else:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        try: requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=5)
        except: pass

def interpret_spdr(val_str):
    if not val_str or str(val_str).strip().lower() == "neutral": return "รอดูท่าที ⚪"
    try:
        val = float(str(val_str).replace('+', '').replace(',', '').strip())
        if val > 0: return f"เจ้าเก็บของ 🟢 (+{val} ตัน)"
        elif val < 0: return f"เจ้าเทของ 🔴 ({val} ตัน)"
        else: return "รอดูท่าที ⚪ (0 ตัน)"
    except: return str(val_str)

def get_us_briefing_time():
    now_utc = datetime.datetime.utcnow()
    year = now_utc.year
    dst_start = datetime.datetime(year, 3, 8)
    dst_start += datetime.timedelta(days=(6 - dst_start.weekday()))
    dst_end = datetime.datetime(year, 11, 1)
    dst_end += datetime.timedelta(days=(6 - dst_end.weekday()))
    if dst_start <= now_utc < dst_end: return 19, 30
    else: return 20, 30 

@st.cache_data(ttl=14400)
def fetch_spdr_auto():
    try:
        url = "https://www.spdrgoldshares.com/assets/dynamic/GLD/GLD_US_archive_EN.csv"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            lines = res.text.split('\n')
            header_idx = -1
            for i, line in enumerate(lines[:30]):
                if "Date" in line and "Tonnes" in line:
                    header_idx = i
                    break
            if header_idx != -1:
                df = pd.read_csv(io.StringIO(res.text), skiprows=header_idx)
                df.dropna(subset=['Tonnes in the Trust'], inplace=True)
                if len(df) >= 2:
                    t1_str = str(df['Tonnes in the Trust'].iloc[-2]).replace(',', '')
                    t2_str = str(df['Tonnes in the Trust'].iloc[-1]).replace(',', '')
                    diff = float(t2_str) - float(t1_str)
                    sign = "+" if diff > 0 else ""
                    return f"{sign}{diff:.2f}"
    except Exception as e: pass
    return "Neutral"

auto_spdr_val = fetch_spdr_auto()
if 'spdr_manual' not in st.session_state or st.session_state.spdr_manual == "Neutral":
    st.session_state.spdr_manual = auto_spdr_val

# --- 📊 DAILY SCOREBOARD (LOCAL JSON) ---
def load_score():
    now_thai = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
    today_str = now_thai.strftime("%Y-%m-%d")
    default_score = {"date": today_str, "win": 0, "loss": 0, "be": 0, "pending": 0, "profit": 0.0}
    try:
        if os.path.exists(SCORE_FILE):
            with open(SCORE_FILE, "r") as f:
                data = json.load(f)
                if data.get("date") == today_str: return data
    except: pass
    return default_score

def save_score(data):
    try:
        with open(SCORE_FILE, "w") as f:
            json.dump(data, f)
    except: pass

def update_score(action, trade=None):
    score = load_score()
    if action == "pending":
        score["pending"] += 1
    elif action == "win" and trade:
        score["pending"] = max(0, score["pending"] - 1)
        score["win"] += 1
        score["profit"] += abs(trade['tp_val'] - trade['entry_val']) # TP - Entry x 1$
    elif action == "loss" and trade:
        score["pending"] = max(0, score["pending"] - 1)
        score["loss"] += 1
        score["profit"] -= abs(trade['entry_val'] - trade['sl_val_orig']) # Entry - SL_เดิม x 1$
    elif action == "be" and trade:
        score["pending"] = max(0, score["pending"] - 1)
        score["be"] += 1
        score["profit"] += 1.0 # บังหน้าทุน +1$
    elif action == "cancel":
        score["pending"] = max(0, score["pending"] - 1)
    save_score(score)

# --- 2. DATA ENGINE ---
@st.cache_data(ttl=30)
def get_market_data():
    metrics = {'GOLD': (0.0, 0.0), 'GC_F': (0.0, 0.0), 'DXY': (0.0, 0.0), 'US10Y': (0.0, 0.0)}
    df_m15, df_h4, mt5_news = None, None, []
    try:
        res = requests.get(FIREBASE_URL, timeout=5)
        if res.status_code == 200 and res.json() is not None:
            data = res.json()
            if 'XAUUSD' in data:
                df_xau = pd.DataFrame(data['XAUUSD'])
                df_xau.rename(columns={'o':'open', 'h':'high', 'l':'low', 'c':'close', 't':'time'}, inplace=True)
                for col in ['open', 'high', 'low', 'close']: df_xau[col] = pd.to_numeric(df_xau[col], errors='coerce')
                df_xau.dropna(inplace=True)
                curr_gold, prev_gold = float(df_xau['close'].iloc[-1]), float(df_xau['close'].iloc[-2])
                metrics['GOLD'] = (curr_gold, ((curr_gold - prev_gold) / prev_gold) * 100)
                df_m15 = df_xau
            if 'XAUUSD_H1' in data:
                df_h1 = pd.DataFrame(data['XAUUSD_H1'])
                df_h1.rename(columns={'o':'open', 'h':'high', 'l':'low', 'c':'close', 't':'time'}, inplace=True)
                for col in ['open', 'high', 'low', 'close']: df_h1[col] = pd.to_numeric(df_h1[col], errors='coerce')
                df_h1.dropna(inplace=True)
                df_h4 = df_h1
            if 'DXY' in data:
                df_dxy = pd.DataFrame(data['DXY'])
                df_dxy.rename(columns={'o':'open', 'h':'high', 'l':'low', 'c':'close', 't':'time'}, inplace=True)
                for col in ['open', 'high', 'low', 'close']: df_dxy[col] = pd.to_numeric(df_dxy[col], errors='coerce')
                df_dxy.dropna(inplace=True)
                curr_dxy, prev_dxy = float(df_dxy['close'].iloc[-1]), float(df_dxy['close'].iloc[-2])
                metrics['DXY'] = (curr_dxy, ((curr_dxy - prev_dxy) / prev_dxy) * 100)
            if 'NEWS' in data:
                now_thai = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
                for ev in data['NEWS']:
                    try: 
                        event_dt = datetime.datetime.utcfromtimestamp(float(ev['time_sec'])) + datetime.timedelta(hours=7)
                        time_diff_hours = (event_dt - now_thai).total_seconds() / 3600
                        time_str = event_dt.strftime("%d %b | %H:%M น.")
                        mt5_news.append({'source': 'MT5', 'title': ev['title'], 'time': time_str, 'impact': ev['impact'], 'actual': st.session_state.manual_overrides.get(ev['title'], ev['actual']), 'forecast': ev['forecast'], 'direction': ev.get('direction', ''), 'dt': event_dt, 'time_diff_hours': time_diff_hours})
                    except: pass
    except: pass
    try:
        h_gcf = yf.Ticker("GC=F").history(period="5d", interval="15m")
        if not h_gcf.empty and len(h_gcf) >= 2: metrics['GC_F'] = (h_gcf['Close'].iloc[-1], ((h_gcf['Close'].iloc[-1]-h_gcf['Close'].iloc[-2])/h_gcf['Close'].iloc[-2])*100)
    except: pass
    try:
        h_tnx = yf.Ticker("^TNX").history(period="5d", interval="15m")
        if not h_tnx.empty and len(h_tnx) >= 2: metrics['US10Y'] = (h_tnx['Close'].iloc[-1], ((h_tnx['Close'].iloc[-1]-h_tnx['Close'].iloc[-2])/h_tnx['Close'].iloc[-2])*100)
    except: pass
    return metrics, df_m15, df_h4, mt5_news

def check_market_status(df_m15):
    now_thai = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
    weekday = now_thai.weekday()
    if weekday == 5 or weekday == 6: return True, "🛑 ตลาดปิดทำการ (Weekend)"
    if df_m15 is None or df_m15.empty: return True, "🛑 ไม่มีข้อมูลการเชื่อมต่อจาก MT5"
    last_candle_time = pd.to_datetime(df_m15['time'].iloc[-1], unit='s') + datetime.timedelta(hours=7)
    hours_diff = (now_thai - last_candle_time).total_seconds() / 3600
    if hours_diff > 2.0: return True, f"🛑 ตลาดเปิด แต่ MT5 ขาดการเชื่อมต่อ ({hours_diff:.1f} ชม.)"
    return False, "🟢 เชื่อมต่อ MT5 สำเร็จ (Market Open)"

def get_current_session():
    now_thai = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
    h = now_thai.hour
    if 5 <= h < 14: return "🌏 Asia Session"
    if 14 <= h < 23: return "💶 Europe/London Session"
    if h >= 19 or h < 4: return "🗽 US/New York Session"
    return "🌙 Market Transition"

@st.cache_data(ttl=900)
def fetch_ff_xml():
    try: return requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.xml", headers={'User-Agent': 'Mozilla/5.0'}, timeout=10).content
    except: return None

def get_forexfactory_usd():
    xml_content = fetch_ff_xml()
    if not xml_content: return []
    ff_news = []
    now_thai = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
    try:
        root = ET.fromstring(xml_content)
        for event in root.findall('event'):
            if event.find('country').text == 'USD' and event.find('impact').text in ['High', 'Medium']:
                date_str, raw_time = event.find('date').text, event.find('time').text
                impact, title = event.find('impact').text, event.find('title').text
                if not raw_time or not any(c.isdigit() for c in raw_time): continue
                try: gmt_dt = datetime.datetime.strptime(f"{date_str} {raw_time.strip().lower()}", "%m-%d-%Y %I:%M%p")
                except: continue
                thai_dt = gmt_dt + datetime.timedelta(hours=7)
                time_diff_hours = (thai_dt - now_thai).total_seconds() / 3600
                if time_diff_hours < -12.0 or (impact == 'High' and time_diff_hours > 24): continue
                time_str = thai_dt.strftime("%d %b | %H:%M น.")
                ff_news.append({'source': 'FF', 'title': title, 'time': time_str, 'impact': impact, 'actual': st.session_state.manual_overrides.get(title, event.find('actual').text if event.find('actual') is not None else "Pending"), 'forecast': event.find('forecast').text if event.find('forecast') is not None else "", 'direction': '', 'dt': thai_dt, 'time_diff_hours': time_diff_hours})
        return ff_news
    except: return []

def merge_news_sources(mt5_list, ff_list):
    merged = []
    for mt5_news in mt5_list: merged.append(mt5_news)
    for ff_news in ff_list:
        is_duplicate = False
        for m_news in merged:
            time_diff_sec = abs((ff_news['dt'] - m_news['dt']).total_seconds())
            ff_kw, mt5_kw = ff_news['title'].split()[0].lower(), m_news['title'].split()[0].lower()
            if time_diff_sec <= 3600 and (ff_kw in m_news['title'].lower() or mt5_kw in ff_news['title'].lower()):
                is_duplicate = True; break
        if not is_duplicate: merged.append(ff_news)
    merged.sort(key=lambda x: x['dt'])
    next_red_news = None
    for ev in merged:
        if ev['impact'] == 'High' and -0.5 <= ev['time_diff_hours'] <= 6:
            if next_red_news is None or ev['time_diff_hours'] < next_red_news['hours']:
                next_red_news = {'title': ev['title'], 'hours': ev['time_diff_hours'], 'time': ev['dt'].strftime("%H:%M น.")}
    return merged, next_red_news

@st.cache_data(ttl=600)
def get_retail_sentiment():
    try: return {"short": 78.5, "long": 21.5}
    except: return {"short": 50, "long": 50}

@st.cache_data(ttl=900) 
def get_categorized_news():
    translator = GoogleTranslator(source='en', target='th')
    def fetch_rss(query):
        news_list = []
        try:
            feed = feedparser.parse(requests.get(f"https://news.google.com/rss/search?q={query}+when:24h&hl=en-US&gl=US&ceid=US:en", headers={'User-Agent': 'Mozilla/5.0'}, timeout=5).content)
            for entry in feed.entries[:5]: 
                pub_time = mktime(entry.published_parsed)
                date_str = datetime.datetime.fromtimestamp(pub_time).strftime('%d %b | %H:%M น.')
                title_lower = entry.title.lower()
                polarity = TextBlob(entry.title).sentiment.polarity
                base_score = abs(polarity) * 5
                if any(kw in title_lower for kw in ['war', 'missile', 'strike', 'emergency', 'attack']): base_score += 4.0
                elif any(kw in title_lower for kw in ['fed', 'inflation', 'rate', 'fomc', 'cpi']): base_score += 2.0
                final_score = min(10.0, max(1.0, base_score))
                direction = "⚪ NEUTRAL"
                if any(w in title_lower for w in ['war', 'missile', 'strike', 'attack', 'escalat', 'iran', 'houthi']): direction = "🟢 GOLD UP (Safe Haven)"
                elif any(w in title_lower for w in ['ceasefire', 'peace']): direction = "🔴 GOLD DOWN (Risk-On)"
                elif any(w in title_lower for w in ['rate hike', 'hawkish']): direction = "🔴 GOLD DOWN (Strong USD)"
                elif any(w in title_lower for w in ['rate cut', 'dovish']): direction = "🟢 GOLD UP (Weak Econ)"
                else:
                    if polarity <= -0.2: direction = "🟢 GOLD UP (Negative/Panic)"
                    elif polarity >= 0.2: direction = "🔴 GOLD DOWN (Positive/Calm)"
                news_list.append({'title_en': entry.title, 'title_th': translator.translate(entry.title), 'link': entry.link, 'time': date_str, 'score': final_score, 'direction': direction})
        except: pass
        return news_list
    return fetch_rss("(Fed OR Powell OR Treasury OR FOMC OR CPI)"), fetch_rss("(War OR Missile OR Israel OR Russia OR Iran OR USA OR Taiwan OR Houthi OR Strike)")

@st.cache_data(ttl=300) 
def get_breaking_news():
    translator = GoogleTranslator(source='en', target='th')
    speed_news = []
    urls = [{"url": "https://www.forexlive.com/feed", "source": "ForexLive"}, {"url": "https://www.fxstreet.com/rss", "source": "FXStreet"}]
    for source in urls:
        try:
            feed = feedparser.parse(requests.get(source['url'], headers={'User-Agent': 'Mozilla/5.0'}, timeout=5).content)
            for entry in feed.entries[:5]:
                pub_time = mktime(entry.published_parsed)
                date_str = datetime.datetime.fromtimestamp(pub_time).strftime('%d %b | %H:%M น.')
                title_lower = entry.title.lower()
                polarity = TextBlob(entry.title).sentiment.polarity
                direction = "⚪ NEUTRAL"
                if any(w in title_lower for w in ['gold', 'xau']): direction = "🟢 GOLD UP" if polarity > 0 else "🔴 GOLD DOWN"
                elif any(w in title_lower for w in ['usd', 'dollar', 'fed']): direction = "🔴 GOLD DOWN (Strong USD)" if polarity > 0 else "🟢 GOLD UP (Weak USD)"
                base_score = abs(polarity) * 5
                if any(w in title_lower for w in ['urgent', 'breaking', 'alert', 'jump', 'drop', 'crash']): base_score += 5.0
                speed_news.append({'title_en': entry.title, 'title_th': translator.translate(entry.title), 'link': entry.link, 'time': date_str, 'score': min(10.0, max(1.0, base_score)), 'direction': direction, 'source': source['source'], 'timestamp': pub_time})
        except: pass
    speed_news.sort(key=lambda x: x['timestamp'], reverse=True)
    return speed_news[:10]

def identify_trend(df):
    if df is None or df.empty or len(df) < 50: return "ไซด์เวย์ ⚪", "SIDEWAY"
    try:
        ema12 = ta.ema(df['close'], length=12)
        ema50 = ta.ema(df['close'], length=50)
        if ema12 is not None and ema50 is not None and not ema12.empty and not ema50.empty:
            curr_close = float(df['close'].iloc[-1])
            curr_ema12 = float(ema12.iloc[-1])
            curr_ema50 = float(ema50.iloc[-1])
            if pd.notna(curr_ema12) and pd.notna(curr_ema50):
                if curr_close > curr_ema50 and curr_ema12 > curr_ema50: return "ขาขึ้น 🟢", "UP"
                elif curr_close < curr_ema50 and curr_ema12 < curr_ema50: return "ขาลง 🔴", "DOWN"
    except: pass
    return "ไซด์เวย์ ⚪", "SIDEWAY"

def get_h4_zones(df_h4):
    demand_h4, supply_h4 = [], []
    if df_h4 is None or len(df_h4) < 20: return demand_h4, supply_h4
    df_recent = df_h4.tail(60).reset_index(drop=True)
    for i in range(len(df_recent)-1, 1, -1):
        try:
            if float(df_recent['low'].iloc[i]) > float(df_recent['high'].iloc[i-2]): 
                demand_h4.append((float(df_recent['high'].iloc[i-2]), float(df_recent['low'].iloc[i])))
            if float(df_recent['high'].iloc[i]) < float(df_recent['low'].iloc[i-2]): 
                supply_h4.append((float(df_recent['low'].iloc[i-2]), float(df_recent['high'].iloc[i])))
        except: continue
    return demand_h4, supply_h4

def detect_candlestick_reversal(df, direction):
    if len(df) < 3: return False, ""
    c1 = df.iloc[-1] 
    c2 = df.iloc[-2] 
    def get_props(c):
        body = abs(c['open'] - c['close'])
        high, low = c['high'], c['low']
        uw = high - max(c['open'], c['close']) 
        lw = min(c['open'], c['close']) - low  
        is_green = c['close'] > c['open']
        is_red = c['close'] < c['open']
        return body, uw, lw, is_green, is_red

    b1, uw1, lw1, g1, r1 = get_props(c1)
    b2, uw2, lw2, g2, r2 = get_props(c2)

    if direction == "UP": 
        if r2 and g1 and c1['close'] > c2['open'] and c1['open'] <= c2['close']: return True, "Bullish Engulfing (กลืนกินขาขึ้น)"
        if lw1 > (b1 * 2) and uw1 < b1 and lw1 > 1.0: return True, "Bullish Pinbar / Hammer (หางยาวแทงลง)"
        if lw2 > (b2 * 2) and uw2 < b2 and lw2 > 1.0 and g1: return True, "Confirmed Hammer (แฮมเมอร์ยืนยัน)"
    elif direction == "DOWN": 
        if g2 and r1 and c1['close'] < c2['open'] and c1['open'] >= c2['close']: return True, "Bearish Engulfing (กลืนกินขาลง)"
        if uw1 > (b1 * 2) and lw1 < b1 and uw1 > 1.0: return True, "Bearish Pinbar / Shooting Star (หางยาวแทงขึ้น)"
        if uw2 > (b2 * 2) and lw2 < b2 and uw2 > 1.0 and r1: return True, "Confirmed Shooting Star (ชูตติ้งสตาร์ยืนยัน)"
    return False, ""

def detect_choch_and_sweep(df):
    recent = df.tail(20).reset_index(drop=True)
    if len(recent) < 20: return False, "", 0, 0
    lowest_low, highest_high = recent['low'].iloc[0:15].min(), recent['high'].iloc[0:15].max()
    current_close = recent['close'].iloc[-1]
    if recent['low'].iloc[-5:-1].min() < lowest_low and current_close > recent['high'].iloc[-5:-1].max(): return True, "BUY", recent['low'].iloc[-5:-1].min(), current_close
    if recent['high'].iloc[-5:-1].max() > highest_high and current_close < recent['low'].iloc[-5:-1].min(): return True, "SELL", recent['high'].iloc[-5:-1].max(), current_close
    return False, "", 0, 0

# --- 🧠 GLOBAL MEMORY ---
@st.cache_resource
def get_global_memory():
    return {
        "active_trades": {"Normal Setup": None, "All-In Setup": None},
        "last_sent_entry": {"Normal Setup": "", "All-In Setup": ""}, 
        "last_us_briefing_date": "", 
        "sent_news_links": set(), 
        "sent_mt5_events": set()  
    }

def process_news_alerts(pol_news, war_news, speed_news, mt5_news):
    mem = get_global_memory()
    all_rss = pol_news + war_news + speed_news
    for n in all_rss:
        if n['score'] >= 6.0 and n['direction'] != "⚪ NEUTRAL" and n['link'] not in mem["sent_news_links"]:
            mem["sent_news_links"].add(n['link'])
            msg = f"📰 [BREAKING NEWS]\n\n🔥 หัวข้อ: {n['title_th']}\n({n['title_en']})\n\n🤖 AI วิเคราะห์: {n['direction']}\n📈 ระดับความรุนแรง: {n['score']:.1f}/10\n\n🔗 อ่านต่อ: {n['link']}"
            send_telegram_notify(msg)

    now = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
    for ev in mt5_news:
        if -0.5 <= ev['time_diff_hours'] <= 0.1 and ev['actual'] and "Pending" not in ev['actual']:
            event_id = f"{ev['title']}_{ev['dt'].strftime('%Y%m%d')}"
            if event_id not in mem["sent_mt5_events"]:
                mem["sent_mt5_events"].add(event_id)
                act_str = re.sub(r'[^\d.-]', '', ev['actual'])
                for_str = re.sub(r'[^\d.-]', '', ev['forecast'])
                impact_dir = "⚪ ตลาดกำลังย่อยข้อมูล (Neutral/Mixed)"
                try:
                    if act_str and for_str:
                        a_val, f_val = float(act_str), float(for_str)
                        if a_val > f_val: 
                            impact_dir = "🔴 ทองกดดันลง (ตัวเลขดีกว่าคาด = USD แข็ง)"
                            if "unemployment" in ev['title'].lower() or "claims" in ev['title'].lower():
                                impact_dir = "🟢 ทองหนุนขึ้น (คนตกงานพุ่ง = USD อ่อน)"
                        elif a_val < f_val:
                            impact_dir = "🟢 ทองหนุนขึ้น (ตัวเลขแย่กว่าคาด = USD อ่อน)"
                            if "unemployment" in ev['title'].lower() or "claims" in ev['title'].lower():
                                impact_dir = "🔴 ทองกดดันลง (คนตกงานลดลง = USD แข็ง)"
                except: pass
                msg = f"📅 [ECONOMIC DATA RELEASE]\nตัวเลขเศรษฐกิจประกาศแล้ว!\n\n📌 ข่าว: {ev['title']}\n\nประกาศ (Actual): {ev['actual']}\nคาดการณ์ (Forecast): {ev['forecast']}\n\n🤖 AI วิเคราะห์ผลกระทบ:\n👉 {impact_dir}"
                send_telegram_notify(msg)

def check_active_trades(current_high, current_low, current_close):
    if "ใส่_URL" in GOOGLE_SHEET_API_URL: return
    mem = get_global_memory()
    for mode in ["Normal Setup", "All-In Setup"]:
        trade = mem["active_trades"][mode]
        if trade is None: continue
        is_long = "BUY" in trade['signal']
        
        if not trade['activated']:
            if is_long and current_low <= trade['entry_val']: trade['activated'] = True
            elif not is_long and current_high >= trade['entry_val']: trade['activated'] = True
            
            if not trade['activated']:
                is_missed = False
                if is_long and current_high >= trade['tp_val']: is_missed = True
                elif not is_long and current_low <= trade['tp_val']: is_missed = True
                if is_missed:
                    send_telegram_notify(f"🚫 [CANCELLED] ตกรถ!\n\nMode: {mode}\nSignal: {trade['signal']}\n\nกราฟวิ่งไปชน TP ที่ {trade['display_tp']} เรียบร้อยแล้ว แต่ราคาไม่ได้ย้อนมารับออเดอร์ในโซน Entry ที่ตั้งไว้\n\n👉 ยกเลิก Setup นี้เพื่อหาจุดเข้าใหม่ครับ")
                    mem["last_sent_entry"][mode] = trade['display_entry'] 
                    mem["active_trades"][mode] = None
                    update_score("cancel") 
                    continue
                    
        if trade['activated']:
            result = None
            is_tp = False
            is_sl = False
            if is_long:
                if current_high >= trade['tp_val']: is_tp = True
                if current_low <= trade['sl_val']: is_sl = True
            else:
                if current_low <= trade['tp_val']: is_tp = True
                if current_high >= trade['sl_val']: is_sl = True
                
            if is_tp and is_sl:
                if is_long: result = "Win / TP ✅" if current_close >= trade['entry_val'] else ("Breakeven (เสมอตัว) 🛡️" if trade.get('is_breakeven') else "Lose / SL ❌")
                else: result = "Win / TP ✅" if current_close <= trade['entry_val'] else ("Breakeven (เสมอตัว) 🛡️" if trade.get('is_breakeven') else "Lose / SL ❌")
            elif is_tp: result = "Win / TP ✅"
            elif is_sl: result = "Breakeven (เสมอตัว) 🛡️" if trade.get('is_breakeven') else "Lose / SL ❌"
            
            if not result and not trade.get('is_breakeven', False):
                if is_long and current_high >= trade['mid_val']:
                    trade['is_breakeven'] = True
                    trade['sl_val'] = trade['entry_val'] + 1.0 
                    send_telegram_notify(f"🚨 [UPDATE: Risk Free] {mode}\n\n✨ ราคาวิ่งไป 50% ของเป้าหมาย TP แล้ว!\n👉 ระบบทำการขยับ SL มาบังหน้าทุนที่ ${trade['sl_val']:.2f}\n(หากราคาย้อนกลับ จะถือว่าเสมอตัว Breakeven 🛡️)")
                elif not is_long and current_low <= trade['mid_val']:
                    trade['is_breakeven'] = True
                    trade['sl_val'] = trade['entry_val'] - 1.0 
                    send_telegram_notify(f"🚨 [UPDATE: Risk Free] {mode}\n\n✨ ราคาวิ่งไป 50% ของเป้าหมาย TP แล้ว!\n👉 ระบบทำการขยับ SL มาบังหน้าทุนที่ ${trade['sl_val']:.2f}\n(หากราคาย้อนกลับ จะถือว่าเสมอตัว Breakeven 🛡️)")

            if result:
                try: requests.post(GOOGLE_SHEET_API_URL, json={"action": "update", "id": trade['id'], "result": result}, timeout=3)
                except: pass
                
                if "Win" in result: update_score("win", trade)
                elif "Lose" in result: update_score("loss", trade)
                elif "Breakeven" in result: update_score("be", trade)

                tg_msg = f"🏁 [RESULT] สรุปผล Setup!\n\nMode: {mode}\nSignal: {trade['signal']}\n\n📍 Entry: {trade['display_entry']}\n🛑 SL: {trade['display_sl']}\n💰 TP: {trade['display_tp']}\n"
                if trade['rr'] > 0: tg_msg += f"🧮 Risk:Reward: 1:{trade['rr']:.2f}\n\n❓ Why?:\n- {trade['display_reason']}\n\n🎲 Implied Win Rate: {trade['wr_pct']}%\n📈 Expected Value (EV): {trade['ev_r']:+.2f} R\n\n"
                tg_msg += f"⚡ **Result: {result}**"
                send_telegram_notify(tg_msg)
                
                mem["last_sent_entry"][mode] = trade['display_entry']
                mem["active_trades"][mode] = None 

# --- 4. CORE AI ---
def calculate_normal_setup(df_m15, df_h4, final_news_list, sentiment, metrics, is_market_closed, next_red_news, trend_m15_dir, trend_h4_dir):
    if is_market_closed or df_m15 is None or len(df_m15) < 50: return "MARKET CLOSED 🛑", "ระบบหยุดการวิเคราะห์เนื่องจากตลาดปิด", {}, False
    
    atr_val = 5.0
    try: 
        atr_series = ta.atr(df_m15['high'], df_m15['low'], df_m15['close'], length=14)
        if atr_series is not None and not atr_series.empty: atr_val = float(atr_series.iloc[-2])
    except: pass
    
    current_m15 = df_m15.iloc[-1]
    red_body_size = float(current_m15['open']) - float(current_m15['close'])
    is_flash_crash = True if (red_body_size >= 30.0) and ((float(current_m15['close']) - float(current_m15['low'])) <= 5.0) else False

    h4_demands, h4_supplies = get_h4_zones(df_h4)

    def get_smc_setup(df, trend_dir):
        df_recent = df.tail(40).reset_index(drop=True)
        current_close = float(df.iloc[-1]['close'])
        mtf_aligned = False
        has_candle, candle_name = detect_candlestick_reversal(df, trend_dir)
        if trend_dir == "UP": 
            for i in range(len(df_recent)-1, 1, -1):
                try:
                    if float(df_recent['low'].iloc[i]) > float(df_recent['high'].iloc[i-2]): 
                        entry_top = float(df_recent['low'].iloc[i])
                        entry_bot = float(df_recent['high'].iloc[i-2])
                        sl_val = entry_bot - (atr_val * 0.5)
                        tp_val = float(df_recent['high'].max())
                        for h4_bot, h4_top in h4_demands:
                            if max(entry_bot, h4_bot) <= min(entry_top, h4_top): mtf_aligned = True; break
                        if current_close > entry_top and (current_close - entry_top) < (atr_val * 2):
                            return True, f"🧲 โซน Demand FVG $ {entry_bot:.2f} - $ {entry_top:.2f}", f"$ {sl_val:.2f}", f"$ {tp_val:.2f}", mtf_aligned, has_candle, candle_name
                except: continue
        elif trend_dir == "DOWN": 
            for i in range(len(df_recent)-1, 1, -1):
                try:
                    if float(df_recent['high'].iloc[i]) < float(df_recent['low'].iloc[i-2]): 
                        entry_bot = float(df_recent['high'].iloc[i])
                        entry_top = float(df_recent['low'].iloc[i-2])
                        sl_val = entry_top + (atr_val * 0.5)
                        tp_val = float(df_recent['low'].min())
                        for h4_bot, h4_top in h4_supplies:
                            if max(entry_bot, h4_bot) <= min(entry_top, h4_top): mtf_aligned = True; break
                        if current_close < entry_bot and (entry_bot - current_close) < (atr_val * 2):
                            return True, f"🧲 โซน Supply FVG $ {entry_bot:.2f} - $ {entry_top:.2f}", f"$ {sl_val:.2f}", f"$ {tp_val:.2f}", mtf_aligned, has_candle, candle_name
                except: continue
        return False, "", "", "", False, False, ""

    smc_found, smc_entry, smc_sl, smc_tp, is_mtf_aligned, has_candle, candle_name = get_smc_setup(df_m15, trend_m15_dir)
    news_warning = ""
    is_news_danger = False
    if next_red_news:
        hrs = next_red_news['hours']
        if -0.5 <= hrs <= 0.5:
            is_news_danger = True
            news_warning = f"\n🚨 **DANGER (ระงับเทรด):** ข่าวสำคัญ '{next_red_news['title']}' กำลังจะประกาศ!"
        elif 0.5 < hrs <= 3.0:
            news_warning = f"\n⚠️ **WARNING (ลดความเสี่ยง):** ข่าว '{next_red_news['title']}' จะออกใน {hrs:.1f} ชม."

    if is_flash_crash:
        setup = {'Entry': f"กด Sell ทันที หรือรอเด้งโซน $ {(float(current_m15['close']) + (0.5*atr_val)):.2f}", 'SL': f"$ {(float(current_m15['open']) + (0.5*atr_val)):.2f}", 'TP': f"$ {(float(current_m15['close']) - (3*atr_val)):.2f}"}
        return "🚨 FLASH CRASH (SELL NOW!)", f"เกิดแรงเทขายผิดปกติระดับ 30$ สั่งแทง SELL ตามน้ำ!{news_warning}", setup, True

    if is_news_danger: return "WAIT (News Danger 🛑)", f"ระบบระงับการเข้าเทรดเพื่อหลีกเลี่ยงความผันผวนของข่าว{news_warning}", {}, False
    if not smc_found: return "WAIT", f"ยังไม่พบโซนย่อตัว (Pullback/FVG) ใน M15 รอราคาสร้างฐาน{news_warning}", {}, False
    
    spdr_val = 0.0
    try:
        spdr_str = st.session_state.spdr_manual.replace('+', '').replace(',', '').strip()
        if spdr_str.lower() != "neutral" and spdr_str != "": spdr_val = float(spdr_str)
    except: pass

    stars = 2 
    logic_details = [f"⭐ M15 พบจุดเข้า Buy on Dip / Sell on Rally (FVG)"]
    if trend_m15_dir == trend_h4_dir: stars += 1; logic_details.append("⭐ เทรนด์ H4 สนับสนุนทิศทาง M15")
    else: logic_details.append("➖ H4 ขัดแย้งกับ M15 (เป็นการเทรด Pullback สั้นๆ)")
    if is_mtf_aligned: stars += 1; logic_details.append("🔥 โซน FVG ซ้อนทับกับแนวรับ/ต้าน ของ H4 (High Probability!)")

    dxy_trend = metrics['DXY'][1]
    if (trend_m15_dir == "UP" and dxy_trend < 0) or (trend_m15_dir == "DOWN" and dxy_trend > 0):
        stars += 1; logic_details.append("⭐ ดัชนี DXY เคลื่อนไหวสนับสนุนทิศทางทองคำ")

    if (trend_m15_dir == "UP" and spdr_val > 0) or (trend_m15_dir == "DOWN" and spdr_val < 0):
        stars += 1; logic_details.append(f"⭐ SPDR Smart Money: สถาบันเก็บของสอดคล้องทิศทาง ({'+' if spdr_val>0 else ''}{spdr_val} ตัน)")

    if has_candle: stars += 1; logic_details.append(f"🔥 Price Action: พบแท่งเทียน '{candle_name}' ยืนยันในโซน")
    else: logic_details.append(f"⏳ Price Action: ราคายังไม่ทำรูปแบบแท่งเทียนกลับตัว (ควรระวังโซนทะลุ)")

    stars = min(5, stars)
    star_str = "⭐" * stars
    logic_str = "<br>".join(logic_details) + news_warning

    rsi_val = st.session_state.get('rsi', 50.0)
    if trend_m15_dir == "UP":
        if rsi_val > 70: return f"WAIT (Overbought)", f"RSI = {rsi_val:.1f} เข้าเขต Overbought ห้ามไล่ราคา! รอราคาย่อลงมาในโซน{news_warning}", {}, False
        return f"BUY {star_str}", logic_str, {'Entry': smc_entry, 'SL': smc_sl, 'TP': smc_tp}, False
    elif trend_m15_dir == "DOWN":
        if rsi_val < 30: return f"WAIT (Oversold)", f"RSI = {rsi_val:.1f} เข้าเขต Oversold ห้ามไล่ราคาขาย! รอราคาเด้งกลับ{news_warning}", {}, False
        return f"SELL {star_str}", logic_str, {'Entry': smc_entry, 'SL': smc_sl, 'TP': smc_tp}, False

    return "WAIT", "รอ...", {}, False

def calculate_all_in_setup(df_m15, next_red_news, metrics, sentiment, is_market_closed):
    if is_market_closed or df_m15 is None: return "MARKET CLOSED 🛑", "ระบบหยุดการวิเคราะห์เนื่องจากตลาดปิด", {}, "🔴"
    light = "🔴"
    if next_red_news:
        hrs = next_red_news['hours']
        if 0.25 <= hrs <= 0.5: light = "🟢" 
        elif -0.5 <= hrs < 0.25: return "WAIT", f"🔴 ห้ามเทรด! ข่าว {next_red_news['title']} เพิ่งออก/กำลังจะออก", {}, "🔴"
        else: return "WAIT", "🟡 รอพายุสภาพคล่อง (ข่าวกล่องแดง)", {}, "🟡"
    else: return "WAIT", "⚪ ไม่มีข่าวกล่องแดงในระยะนี้", {}, "⚪"
        
    found_sweep, direction, sweep_price, current_price = detect_choch_and_sweep(df_m15)
    if not found_sweep: return "WAIT", "🟢 ข่าวออกแล้ว แต่ยังไม่พบโครงสร้าง Liquidity Sweep", {}, "🟢"
    
    has_candle, candle_name = detect_candlestick_reversal(df_m15, direction)
    if not has_candle: return "WAIT", f"🟢 เกิดโครงสร้าง CHoCH แล้ว รอแท่งเทียนกลับตัว (Price Action) คอนเฟิร์มจุดเข้า", {}, "🟢"
        
    dxy_trend, gcf_trend = metrics['DXY'][1], metrics['GC_F'][1]
    if direction == "BUY":
        if dxy_trend > 0: return "WAIT", "DXY ยังแข็งค่า (ขัดแย้งกับสัญญาณ)", {}, "🟢"
        if gcf_trend < 0: return "WAIT", "GC=F Premium ไม่สนับสนุนทิศทาง", {}, "🟢"
        if sentiment['short'] < 75.0: return "WAIT", f"รายย่อยยังสะสมฝั่ง Short ไม่พอ ({sentiment['short']}%)", {}, "🟢"
        entry, sl = current_price - 1.0, max(sweep_price - 0.5, current_price - 4.0)
        return "ALL-IN BUY 🚀", f"Confluence ครบ 100% + พบแท่งเทียน '{candle_name}' ยืนยัน", {'Entry': f"🎯 โซน $ {(entry-1.0):.2f} - $ {entry:.2f}", 'SL': f"$ {sl:.2f}", 'TP': f"$ {(entry + ((entry - sl) * 2)):.2f}", 'Sweep': f"$ {sweep_price:.2f}"}, "🟢"
    elif direction == "SELL":
        if dxy_trend < 0: return "WAIT", "DXY ยังอ่อนค่า (ขัดแย้งกับสัญญาณ)", {}, "🟢"
        if gcf_trend > 0: return "WAIT", "GC=F Premium ไม่สนับสนุนทิศทาง", {}, "🟢"
        if sentiment['long'] < 75.0: return "WAIT", f"รายย่อยยังสะสมฝั่ง Buy ไม่พอ ({sentiment['long']}%)", {}, "🟢"
        entry, sl = current_price + 1.0, min(sweep_price + 0.5, current_price + 4.0)
        return "ALL-IN SELL 🚀", f"Confluence ครบ 100% + พบแท่งเทียน '{candle_name}' ยืนยัน", {'Entry': f"🎯 โซน $ {entry:.2f} - $ {(entry+1.0):.2f}", 'SL': f"$ {sl:.2f}", 'TP': f"$ {(entry - ((sl - entry) * 2)):.2f}", 'Sweep': f"$ {sweep_price:.2f}"}, "🟢"

    return "WAIT", "รอ...", {}, light

def get_ea_commander_status(trend_m15_str, trend_h4_str, is_flash_crash, rsi):
    if is_flash_crash: return "🚨 HARD CUT (ปิด EA ทันที!)", "ตรวจพบความผันผวนรุนแรง (High Variance) ปิด EA เพื่อรักษาเงินทุน ห้ามถัวเด็ดขาด!", "#ff3333"
    if rsi > 75 or rsi < 25: return "⚠️ PAUSE EA (ห้ามเปิดออเดอร์ใหม่)", "RSI เข้าเขตสุดโต่ง โอกาสโดนลากสูง พัก EA รอราคาเข้าโซนสมดุล", "#ffcc00"
    if trend_m15_str == "ไซด์เวย์ ⚪" and trend_h4_str == "ไซด์เวย์ ⚪": return "🟡 LOW RISK MODE (รันไซด์เวย์)", "ตลาดสะสมพลัง (Low Volatility) เหมาะกับการรัน Grid เก็บกรอบแคบ", "#f0b90b"
    if trend_m15_str != trend_h4_str: return "🟡 CAUTION (ลดความเสี่ยง)", "ไทม์เฟรมใหญ่และเล็กขัดแย้งกัน แนะนำปรับลดขนาด Lot Size ของ EA", "#ffcc00"
    return "🟢 TREND FOLLOWING (FULL GRID)", f"โครงสร้าง H4 และ M15 สอดคล้องกัน ({trend_m15_str}) กาง Grid ดักตามเทรนด์ได้เต็มกำลัง", "#00ff00"

def calculate_ev_stats(entry_str, sl_str, tp_str, stars):
    def get_num(s):
        nums = [float(x) for x in re.findall(r'\d+\.\d+', str(s).replace(',', ''))]
        return sum(nums)/len(nums) if nums else 0.0
    entry, sl, tp = get_num(entry_str), get_num(sl_str), get_num(tp_str)
    if entry == 0 or sl == 0 or tp == 0: return 0, 0, 0, 0, 0
    risk = abs(entry - sl)
    reward = abs(tp - entry)
    if risk == 0: risk = 0.001
    rr = reward / risk
    win_rates = {5: 0.80, 4: 0.65, 3: 0.50, 2: 0.35, 1: 0.20}
    wr = win_rates.get(stars, 0.50)
    ev_r = (wr * rr) - ((1 - wr) * 1)
    return risk, reward, rr, int(wr*100), ev_r

def log_new_trade(setup_type, sig, setup_data, reason_text, df_m15):
    if "ใส่_URL" in GOOGLE_SHEET_API_URL: return
    mem = get_global_memory()
    try:
        now = time.time()
        trade_id = f"TRD-{int(now)}"
        thai_dt_str = (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime("%d %b %Y | %H:%M น.")
        now_str = (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")
        clean_reason = re.sub('<[^<]+>', '\n- ', reason_text).strip()
        if clean_reason.startswith("- "): clean_reason = clean_reason[2:]

        is_long = "BUY" in sig
        stars_count = sig.count("⭐") if "⭐" in sig else 5 
        
        entry_str, sl_str, tp_str = setup_data.get('Entry', ''), setup_data.get('SL', ''), setup_data.get('TP', '')
        risk, reward, rr, wr_pct, ev_r = calculate_ev_stats(entry_str, sl_str, tp_str, stars_count)

        def extract_price(t, is_long, is_entry):
            p = [float(x) for x in re.findall(r'\d+\.\d+', str(t).replace(',', ''))]
            if not p: return 0.0
            if len(p) == 1: return p[0]
            if is_entry: return max(p) if is_long else min(p)
            return p[0]

        entry_val = extract_price(entry_str, is_long, True)
        sl_val = extract_price(sl_str, False, False)
        tp_val = extract_price(tp_str, False, False)
        is_market = "NOW" in sig 
        mid_val = entry_val + ((tp_val - entry_val) / 2) if entry_val > 0 else 0.0

        trade_dict = {
            "id": trade_id,
            "signal": sig,
            "display_entry": entry_str,
            "display_sl": sl_str,
            "display_tp": tp_str,
            "display_reason": clean_reason,
            "display_time": thai_dt_str,
            "rr": rr,
            "wr_pct": wr_pct,
            "ev_r": ev_r,
            "entry_val": entry_val,
            "sl_val": sl_val,
            "sl_val_orig": sl_val, 
            "tp_val": tp_val,
            "mid_val": mid_val, 
            "activated": is_market,
            "is_breakeven": False, 
            "timestamp_sec": now
        }
        mem["active_trades"][setup_type] = trade_dict
        update_score("pending") 

        payload = {"action": "log", "id": trade_id, "timestamp": now_str, "setup_type": setup_type, "signal": sig, "entry": entry_str, "sl": sl_str, "tp": tp_str, "reason": clean_reason}
        requests.post(GOOGLE_SHEET_API_URL, json=payload, timeout=3)
        
        img_path = "setup_chart.png"
        fig = plot_setup_chart(df_m15, setup_data, mode="All-In" if "All-In" in setup_type else "Normal")
        if fig:
            try: 
                fig.write_image(img_path)
                time.sleep(1) 
            except: img_path = None

        tg_msg = f"🎯 [NEW SETUP] แจ้งเตือนจุดเข้า!\n⏰ เวลาออก Setup: {thai_dt_str}\n\nMode: {setup_type}\nSignal: {sig}\n\n📍 Entry: {entry_str}\n"
        if risk > 0: tg_msg += f"🛑 SL: {sl_str} (Risk = ${risk:.2f})\n💰 TP: {tp_str} (Reward = ${reward:.2f})\n🧮 Risk:Reward: 1:{rr:.2f}\n\n"
        else: tg_msg += f"🛑 SL: {sl_str}\n💰 TP: {tp_str}\n\n"
            
        tg_msg += f"❓ Why?:\n- {clean_reason}\n\n"
        if risk > 0:
            ev_status = "Positive EV คุ้มค่าที่จะเสี่ยง! ✅" if ev_r > 0 else "Negative EV ความเสี่ยงสูง ⚠️"
            tg_msg += f"🎲 Implied Win Rate: {int(wr_pct)}% (ระดับ {stars_count} ดาว)\n📈 Expected Value (EV): {ev_r:+.2f} R ({ev_status})"

        send_telegram_notify(tg_msg, img_path)
    except: pass

def generate_exec_summary(trend_h4_str, trend_m15_str, metrics, next_red_news, sentiment):
    dxy_status = "อ่อนค่า (หนุนทอง)" if metrics['DXY'][1] < 0 else "แข็งค่า (กดดันทอง)"
    summary = f"**📊 Overall Market Bias:** กราฟใหญ่ (H4) อยู่ในเทรนด์ **{trend_h4_str}** | กราฟเล็ก (M15) กำลังทำโครงสร้าง **{trend_m15_str}**<br>"
    summary += f"ดอลลาร์ (DXY) กำลัง **{dxy_status}** และรายย่อยเทน้ำหนักไปฝั่ง **{'Short' if sentiment.get('short',50) > 50 else 'Long'}** "
    if next_red_news: summary += f"<br>⚠️ **News Alert:** ระวังความผันผวนจากข่าว **{next_red_news['title']}** ในอีก {next_red_news['hours']:.1f} ชั่วโมง"
    else: summary += "<br>✅ **News Alert:** ไม่มีข่าวกล่องแดงกวนใจ สามารถรันเทรนด์ได้ตามปกติ"
    return summary

def generate_telegram_us_briefing(trend_h4_str, trend_m15_str, metrics, sentiment, final_news_list, war_news, spdr_val):
    now_thai = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
    dxy_status = "อ่อนค่า 🟢" if metrics['DXY'][1] < 0 else "แข็งค่า 🔴"
    us10y_status = "ปรับตัวลง 🟢" if metrics['US10Y'][1] < 0 else "พุ่งขึ้น 🔴"
    gcf_status = "ซื้อเก็บ 🟢" if metrics['GC_F'][1] > 0 else "เทขาย 🔴"
    senti_status = "หนุนทองขึ้น 🟢" if sentiment.get('short',50) > 50 else "กดดันทองลง 🔴"
    today_news_str = "".join([f"- {ev['dt'].strftime('%H:%M น.')} : {ev['title']}\n" for ev in final_news_list if ev['dt'].date() == now_thai.date() and ev['impact'] == 'High']) or "- ไม่มีข่าวกล่องแดงคืนนี้ ✅\n"
    geo_str = f"- {war_news[0]['title_th']} (Impact: {war_news[0]['score']:.1f}/10) {war_news[0]['direction']}" if war_news else "- สงบสุข ไม่มีข่าวฉุกเฉิน ⚪"

    spdr_display = interpret_spdr(spdr_val)
    
    msg = f"🗽🇺🇸 US Session Briefing 🇺🇸🗽\nประจำวันที่: {now_thai.strftime('%d %b %Y | 19:30 น.')}\n\n📊 [Technical]\nTrend H4: {trend_h4_str}\nTrend M15 (ล่าสุด): {trend_m15_str}\nXAUUSD: ${metrics['GOLD'][0]:.2f}\n\n💵 [Macro / 5 Pillars]\nDXY: {metrics['DXY'][0]:.2f} ({dxy_status})\nUS10Y: {metrics['US10Y'][0]:.2f}% ({us10y_status})\nGC=F (Premium): {gcf_status}\nSPDR Fund: {spdr_display}\n\n🐑 [Retail Sentiment]\nS:{sentiment.get('short',50)}% / L:{sentiment.get('long',50)}% ({senti_status})\n\n📅 [US Economic News Tonight]\n{today_news_str}\n⚠️ [Geo-Politics]\n{geo_str}\n\n🤖 AI Prediction: โฟกัสจุดเข้าตามเทรนด์ M15 และคุม Position Size ตามหลัก Positive EV"
    return msg

def plot_setup_chart(df, setup_dict, mode="Normal"):
    if df is None or df.empty or not setup_dict: return None
    df_plot = df.tail(100).copy()
    df_plot['datetime'] = pd.to_datetime(df_plot['time'], unit='s')
    fig = go.Figure(data=[go.Candlestick(x=df_plot['datetime'], open=df_plot['open'], high=df_plot['high'], low=df_plot['low'], close=df_plot['close'], increasing_line_color='#00ff00', decreasing_line_color='#ff3333')])
    def get_prices(t): return [float(x) for x in re.findall(r'\d+\.\d+', str(t).replace(',', ''))]
    sl, tp, entry, sweep = get_prices(setup_dict.get('SL', '')), get_prices(setup_dict.get('TP', '')), get_prices(setup_dict.get('Entry', '')), get_prices(setup_dict.get('Sweep', '')) 
    entry_text = str(setup_dict.get('Entry', ''))
    label_text = "🎯 Entry Zone" if "โซน" in entry_text else "🎯 Entry"
    line_color = "#ffcc00" if mode == "All-In" else "#00ccff"
    
    if sl: fig.add_hline(y=sl[0], line_dash="dash", line_color="#ff4444", annotation_text="🛑 SL", annotation_position="bottom right", annotation_font_color="#ff4444")
    if tp: fig.add_hline(y=tp[0], line_dash="dash", line_color="#00ff00", annotation_text="💰 TP", annotation_position="top right", annotation_font_color="#00ff00")
    if sweep: fig.add_hline(y=sweep[0], line_dash="dot", line_color="#ff00ff", annotation_text="⚡ CHoCH / Sweep", annotation_position="left", annotation_font_color="#ff00ff")
    if entry:
        if len(entry) >= 2: fig.add_hrect(y0=min(entry), y1=max(entry), fillcolor=f"rgba({'255, 204, 0' if mode=='All-In' else '0, 204, 255'}, 0.2)", line_width=1, annotation_text=label_text, annotation_position="top right")
        else: fig.add_hline(y=entry[0], line_dash="dash", line_color=line_color, annotation_text=label_text, annotation_position="top right", annotation_font_color=line_color)
    fig.update_layout(template='plotly_dark', margin=dict(l=10, r=50, t=10, b=10), height=350, xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    return fig

# --- UI MAIN ---
metrics, df_m15, df_h4, mt5_news = get_market_data()
is_market_closed, status_msg = check_market_status(df_m15)
current_session = get_current_session()

ff_raw_news = get_forexfactory_usd()
final_news_list, next_red_news = merge_news_sources(mt5_news, ff_raw_news)
sentiment = get_retail_sentiment()
pol_news, war_news = get_categorized_news() 
speed_news = get_breaking_news()

mem = get_global_memory()

if not is_market_closed: process_news_alerts(pol_news, war_news, speed_news, mt5_news)
if not is_market_closed and df_m15 is not None: check_active_trades(float(df_m15.iloc[-1]['high']), float(df_m15.iloc[-1]['low']), float(df_m15.iloc[-1]['close']))

trend_h4_str, trend_h4_dir = identify_trend(df_h4)
trend_m15_str, trend_m15_dir = identify_trend(df_m15)

current_rsi = 50.0
try:
    if df_m15 is not None and len(df_m15) > 15:
        temp_rsi = ta.rsi(df_m15['close'], length=14)
        if temp_rsi is not None and not temp_rsi.empty:
            val = float(temp_rsi.iloc[-1])
            if pd.notna(val): current_rsi = val
except: pass
st.session_state.rsi = current_rsi 

# --- โหมด Normal Setup ---
sig_norm_raw, reason_norm_raw, setup_norm_raw, is_flash_crash = calculate_normal_setup(df_m15, df_h4, final_news_list, sentiment, metrics, is_market_closed, next_red_news, trend_m15_dir, trend_h4_dir)
time_html_norm = ""

if mem["active_trades"]["Normal Setup"] is not None:
    active_trade = mem["active_trades"]["Normal Setup"]
    sig_norm = f"⏳ TRACKING: {active_trade['signal']}"
    reason_norm = f"<b>[สถานะ: กำลังรันออเดอร์ รอชน TP/SL]</b><br>{active_trade['display_reason'].replace('- ', '• ')}"
    setup_norm = {'Entry': active_trade['display_entry'], 'SL': f"$ {active_trade['sl_val']:.2f} {'(บังทุนแล้ว 🛡️)' if active_trade.get('is_breakeven') else ''}", 'TP': active_trade['display_tp']}
    elapsed_mins = int((time.time() - active_trade["timestamp_sec"]) / 60)
    time_html_norm = f"<div style='font-size:13px; color:#00ccff; margin-top:8px; padding-top:8px; border-top:1px dashed #444;'>🕒 <b>เวลาออก Setup:</b> {active_trade['display_time']} (ผ่านมา {elapsed_mins} นาที)</div>"
else:
    if setup_norm_raw.get('Entry') != "" and setup_norm_raw.get('Entry') == mem["last_sent_entry"]["Normal Setup"]:
        sig_norm = "WAIT (Zone Traded 🛑)"
        reason_norm = "รอ... โซนราคานี้เพิ่งถูกเทรดจบไปแล้ว ระบบกำลังรอให้กราฟสร้าง FVG โซนใหม่"
        setup_norm = {}
    else:
        sig_norm, reason_norm, setup_norm = sig_norm_raw, reason_norm_raw, setup_norm_raw
        if "WAIT" not in sig_norm and "CLOSED" not in sig_norm and setup_norm:
            log_new_trade("Normal Setup", sig_norm, setup_norm, reason_norm, df_m15)
            new_trade = mem["active_trades"]["Normal Setup"]
            if new_trade:
                sig_norm = f"⏳ TRACKING: {new_trade['signal']}"
                reason_norm = f"<b>[สถานะ: กำลังรันออเดอร์ รอชน TP/SL]</b><br>{new_trade['display_reason'].replace('- ', '• ')}"
                elapsed_mins = int((time.time() - new_trade["timestamp_sec"]) / 60)
                time_html_norm = f"<div style='font-size:13px; color:#00ccff; margin-top:8px; padding-top:8px; border-top:1px dashed #444;'>🕒 <b>เวลาออก Setup:</b> {new_trade['display_time']} (ผ่านมา {elapsed_mins} นาที)</div>"

# --- โหมด All-In Setup ---
sig_allin_raw, reason_allin_raw, setup_allin_raw, light = calculate_all_in_setup(df_m15, next_red_news, metrics, sentiment, is_market_closed)
time_html_allin = ""

if mem["active_trades"]["All-In Setup"] is not None:
    active_allin = mem["active_trades"]["All-In Setup"]
    sig_allin = f"⏳ TRACKING: {active_allin['signal']}"
    reason_allin = f"<b>[สถานะ: กำลังรันออเดอร์ รอชน TP/SL]</b><br>{active_allin['display_reason'].replace('- ', '• ')}"
    setup_allin = {'Entry': active_allin['display_entry'], 'SL': f"$ {active_allin['sl_val']:.2f} {'(บังทุนแล้ว 🛡️)' if active_allin.get('is_breakeven') else ''}", 'TP': active_allin['display_tp']}
    elapsed_mins = int((time.time() - active_allin["timestamp_sec"]) / 60)
    time_html_allin = f"<div style='font-size:13px; color:#ffcc00; margin-top:8px; padding-top:8px; border-top:1px dashed #444;'>🕒 <b>เวลาออก Setup:</b> {active_allin['display_time']} (ผ่านมา {elapsed_mins} นาที)</div>"
else:
    if setup_allin_raw.get('Entry') != "" and setup_allin_raw.get('Entry') == mem["last_sent_entry"]["All-In Setup"]:
        sig_allin = "WAIT (Zone Traded 🛑)"
        reason_allin = "รอ... โซนราคานี้เพิ่งถูกเทรดจบไปแล้ว ระบบกำลังรอโครงสร้างใหม่"
        setup_allin = {}
    else:
        sig_allin, reason_allin, setup_allin = sig_allin_raw, reason_allin_raw, setup_allin_raw
        if "WAIT" not in sig_allin and "CLOSED" not in sig_allin and setup_allin:
            log_new_trade("All-In Setup", sig_allin, setup_allin, reason_allin, df_m15)
            new_allin = mem["active_trades"]["All-In Setup"]
            if new_allin:
                sig_allin = f"⏳ TRACKING: {new_allin['signal']}"
                reason_allin = f"<b>[สถานะ: กำลังรันออเดอร์ รอชน TP/SL]</b><br>{new_allin['display_reason'].replace('- ', '• ')}"
                elapsed_mins = int((time.time() - new_allin["timestamp_sec"]) / 60)
                time_html_allin = f"<div style='font-size:13px; color:#ffcc00; margin-top:8px; padding-top:8px; border-top:1px dashed #444;'>🕒 <b>เวลาออก Setup:</b> {new_allin['display_time']} (ผ่านมา {elapsed_mins} นาที)</div>"

# 💡 US Session Briefing 
now_thai = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
current_date_str = now_thai.strftime("%Y-%m-%d")
briefing_hour, briefing_minute = get_us_briefing_time()

if not is_market_closed and now_thai.hour == briefing_hour and now_thai.minute >= briefing_minute and mem["last_us_briefing_date"] != current_date_str:
    send_telegram_notify(generate_telegram_us_briefing(trend_h4_str, trend_m15_str, metrics, sentiment, final_news_list, war_news, st.session_state.spdr_manual))
    mem["last_us_briefing_date"] = current_date_str 

# --- ส่วน UI (The Psychology Layout) ---
st.title("🦅 XAUUSD WAR Room: Institutional Quant Setup (v12.36)")
st.markdown(f"<div class='session-card'>📍 Active Market Killzone: {current_session}</div>", unsafe_allow_html=True)

with st.sidebar:
    st.header("💻 War Room Terminal")
    layout_mode = st.radio("Display:", ["🖥️ Desktop", "📱 Mobile"])
    
    if st.button("🔄 Refresh & Clear Cache", type="primary"): 
        st.cache_data.clear()
        st.rerun()
    
    st.markdown("---")
    st.subheader("🏦 อัปเดตกองทุน SPDR")
    new_spdr = st.text_input("ระบุค่า SPDR ล่าสุด (เช่น +3.14 หรือ -1.5)", value=st.session_state.spdr_manual)
    if new_spdr != st.session_state.spdr_manual:
        st.session_state.spdr_manual = new_spdr
        st.rerun()
        
    st.markdown("---")
    st.subheader("✍️ Override ข่าวเศรษฐกิจ")
    has_pending = False
    for i, ev in enumerate(final_news_list):
        if "Pending" in ev['actual'] and -12.0 <= ev.get('time_diff_hours', 0) <= 24.0:
            has_pending = True
            source_tag = "⚡" if ev.get('source') == 'MT5' else "🌐"
            time_display = ev['dt'].strftime('%d %b | %H:%M น.')
            new_val = st.text_input(f"{source_tag} [{time_display}] {ev['title']}", value=st.session_state.manual_overrides.get(ev['title'], ""), key=f"override_{i}")
            if new_val != st.session_state.manual_overrides.get(ev['title'], ""):
                st.session_state.manual_overrides[ev['title']] = new_val
                st.rerun()
    if not has_pending: st.write("✅ ข้อมูลอัปเดตสมบูรณ์")

c1, c2, c3, c4, c5, c6 = st.columns((1,1,1,1,1,1))
with c1: st.metric("XAUUSD", f"${metrics['GOLD'][0]:,.2f}", f"{metrics['GOLD'][1]:.2f}%")
with c2: st.metric("GC=F", f"${metrics['GC_F'][0]:,.2f}", f"{metrics['GC_F'][1]:.2f}%")
with c3: st.metric("DXY", f"{metrics['DXY'][0]:,.2f}", f"{metrics['DXY'][1]:.2f}%", delta_color="inverse")
with c4: st.metric("US10Y", f"{metrics['US10Y'][0]:,.2f}", f"{metrics['US10Y'][1]:.2f}%", delta_color="inverse")
with c5: st.metric("SPDR Flow", interpret_spdr(st.session_state.spdr_manual))
with c6: st.metric("Retail Senti.", f"S:{sentiment.get('short',50)}%", f"L:{sentiment.get('long',50)}%", delta_color="off")

st.markdown(f"<div style='text-align: center; color: {'#ff4444' if is_market_closed else '#00ff00'}; font-size: 14px; margin-top: -5px; margin-bottom: 15px;'>{status_msg}</div>", unsafe_allow_html=True)

# 💡 ย้าย EA Commander มาอยู่ก่อน Scoreboard
st.markdown(f"<div class='exec-summary'>{generate_exec_summary(trend_h4_str, trend_m15_str, metrics, next_red_news, sentiment)}</div>", unsafe_allow_html=True)

if is_market_closed: 
    ea_cmd, ea_desc, ea_color = "🛑 EA OFFLINE", "ตลาดปิดทำการ หรือขาดการเชื่อมต่อจาก MT5", "#888"
else: 
    ea_cmd, ea_desc, ea_color = get_ea_commander_status(trend_m15_str, trend_h4_str, is_flash_crash, current_rsi)

st.markdown(f"""
<div class="ea-card" style="border-color: {ea_color};">
    <h3 style="margin:0; color:{ea_color};">🤖 EA Commander (Risk Management)</h3>
    <div style='color:{ea_color}; font-size:18px; font-weight:bold; margin-top:10px;'>{ea_cmd}</div>
    <div style='color:#fff; font-size:14px; margin-top:5px;'><b>คำแนะนำ:</b> {ea_desc}</div>
</div>
""", unsafe_allow_html=True)

# 💡 V12.36: ย้ายกระดานคะแนนมาอยู่ใต้ EA Commander
score = load_score() 
profit_color = "#00ff00" if score['profit'] >= 0 else "#ff3333"
profit_sign = "+" if score['profit'] >= 0 else "-"
st.markdown(f"""
<div class="scoreboard">
    <div style="color:#d4af37; font-size: 18px; margin-bottom: 5px;">📊 <b>Daily Performance (วันนี้)</b></div>
    <div style="font-size: 20px;">🟩 Win: {score['win']} &nbsp;|&nbsp; 🟥 Loss: {score['loss']} &nbsp;|&nbsp; 🛡️ BE: {score['be']} &nbsp;|&nbsp; ⏳ Pending: {score['pending']}</div>
    <div style="font-size: 24px; font-weight: bold; margin-top: 8px; color: {profit_color};">
        Fixlot 0.01 :: Net Profit: {profit_sign}${abs(score['profit']):.2f}
    </div>
</div>
""", unsafe_allow_html=True)

col_allin, col_normal = st.columns(2)

with col_allin:
    st.markdown("<h2 class='title-header' style='color: #ffcc00;'>🎯 10-Strike All-In Protocol</h2>", unsafe_allow_html=True)
    st.markdown(f"""
    <div class="allin-card">
        <h3 style="margin:0; color:#ffcc00;">{light} All-In Commander</h3>
        <div style="color:{'#888' if 'CLOSED' in sig_allin else ('#ffcc00' if 'WAIT' in sig_allin and 'TRACKING' not in sig_allin else '#00ff00')}; font-size:24px; font-weight:bold; margin-top:10px;">{sig_allin}</div>
        <div style="font-size:14px; margin-top:10px; color:#fff;"><b>Logic:</b><br>{reason_allin.replace('<br>', '<br>- ')}</div>
        {time_html_allin}
    """, unsafe_allow_html=True)
    if setup_allin:
        st.markdown(f"""<div style="background-color:#111; padding:15px; border-radius:8px; border: 1px solid #444; margin-top: 15px;"><div style="color:#ffcc00; font-weight:bold; margin-bottom:5px;">🎯 1:2 Geometry Setup:</div><div>📍 <b>Entry:</b> {setup_allin.get('Entry','')}</div><div style="color:#ff4444;">🛑 <b>SL:</b> {setup_allin.get('SL','')}</div><div style="color:#00ff00;">💰 <b>TP:</b> {setup_allin.get('TP','')}</div></div>""", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    
    if setup_allin and not is_market_closed and df_m15 is not None: 
        st.plotly_chart(plot_setup_chart(df_m15, setup_allin, mode="All-In"), use_container_width=True)
    else: 
        st.markdown("<div style='background-color:#1a1a2e; padding:40px; text-align:center; border-radius:10px; border: 1px dashed #ff3333; height: 350px; display: flex; align-items: center; justify-content: center;'>📡 กำลังรอพายุสภาพคล่อง...</div>", unsafe_allow_html=True)

with col_normal:
    st.markdown("<h2 class='title-header' style='color: #00ccff;'>⭐ 5-Star Trade Matrix</h2>", unsafe_allow_html=True)
    st.markdown(f"""
    <div class="plan-card">
        <h3 style="margin:0; color:#00ccff;">🃏 Daily Setup (Quant Mode)</h3>
        <div style="color:{'#ffcc00' if 'WAIT' in sig_norm and 'TRACKING' not in sig_norm else '#00ff00'}; font-size:24px; font-weight:bold; margin-top:10px;">{sig_norm}</div>
        <div style="font-size:14px; margin-top:10px; color:#fff;"><b>Score & Logic:</b><br>{reason_norm}</div>
        {time_html_norm}
    """, unsafe_allow_html=True)
    
    if setup_norm:
        st.markdown(f"""<div style="background-color:#111; padding:15px; border-radius:8px; border: 1px solid #444; margin-top: 15px;"><div style="color:#00ccff; font-weight:bold; margin-bottom:5px;">🎯 Dynamic Zones:</div><div>📍 <b>Entry:</b> {setup_norm.get('Entry','')}</div><div style="color:#ff4444;">🛑 <b>SL:</b> {setup_norm.get('SL','')}</div><div style="color:#00ff00;">💰 <b>TP:</b> {setup_norm.get('TP','')}</div></div>""", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    
    if setup_norm and not is_market_closed and df_m15 is not None: 
        st.plotly_chart(plot_setup_chart(df_m15, setup_norm, mode="Normal"), use_container_width=True)
    else: 
        st.markdown("<div style='background-color:#1a1a2e; padding:40px; text-align:center; border-radius:10px; border: 1px dashed #00ccff; height: 350px; display: flex; align-items: center; justify-content: center;'>📡 กำลังคำนวณ Probability Matrix...</div>", unsafe_allow_html=True)

st.write("---")

def get_tv_html(symbol, height): return f"""<div class="tradingview-widget-container"><div id="tv_{symbol.replace(':','_')}"></div><script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script><script type="text/javascript">new TradingView.widget({{"width": "100%", "height": {height}, "symbol": "{symbol}", "interval": "15", "theme": "dark", "style": "1", "container_id": "tv_{symbol.replace(':','_')}"}});</script></div>"""
def display_intelligence():
    st.subheader("📰 Global Intelligence Hub")
    tab_eco, tab_pol, tab_war, tab_speed = st.tabs(["📅 ข่าวเศรษฐกิจ", "🏛️ Fed", "⚔️ สงคราม", "⚡ ข่าวด่วน"])
    with tab_eco:
        if final_news_list:
            for ev in final_news_list: 
                time_display = ev['dt'].strftime('%d %b | %H:%M น.')
                st.markdown(f"<div class='ff-card' style='border-left-color: {'#ff3333' if ev['impact']=='High' else '#ff9933'};'><div style='font-size:11px; color:#aaa;'>{'⚡ MT5' if ev.get('source')=='MT5' else '🌐 FF'} | {time_display}</div><div style='font-size:15px;'><b>{ev['title']}</b></div><div style='font-size:13px; color:#aaa;'>Forecast: {ev['forecast']} | <span style='color:#ffcc00;'>Actual: {ev['actual']}</span></div></div>", unsafe_allow_html=True)
        else: st.write("ไม่มีข่าว")
    with tab_pol:
        for news in pol_news: st.markdown(f"<div class='news-card'><a href='{news['link']}' target='_blank' style='color:#fff;'>🇺🇸 {news['title_th']}</a><br><span style='font-size:11px; color:#888;'>🕒 {news['time']}</span><br><span style='font-size: 12px; color: #aaa;'><b>AI:</b> {news['direction']} | SMIS Impact: {news['score']:.1f}/10</span></div>", unsafe_allow_html=True)
    with tab_war:
        for news in war_news: st.markdown(f"<div class='news-card' style='border-color:#ff3333;'><a href='{news['link']}' target='_blank' style='color:#fff;'>⚠️ {news['title_th']}</a><br><span style='font-size:11px; color:#888;'>🕒 {news['time']}</span><br><span style='font-size: 12px; color: #aaa;'><b>AI:</b> {news['direction']} | SMIS Impact: {news['score']:.1f}/10</span></div>", unsafe_allow_html=True)
    with tab_speed:
        if speed_news:
            for news in speed_news: st.markdown(f"<div class='news-card' style='border-color:#00ccff;'><a href='{news['link']}' target='_blank' style='color:#fff;'>🔥 [{news['source']}] {news['title_th']}</a><br><span style='font-size:11px; color:#888;'>🕒 {news['time']}</span><br><span style='font-size: 12px; color: #aaa;'><b>AI:</b> {news['direction']} | SMIS Impact: {news['score']:.1f}/10</span></div>", unsafe_allow_html=True)
        else: st.write("กำลังสแกนหาข่าวด่วน...")

if layout_mode == "🖥️ Desktop":
    col_chart_bot, col_news_bot = st.columns([1.8, 1])
    with col_chart_bot:
        tab_chart_gold, tab_chart_dxy = st.tabs(["🥇 XAUUSD", "💵 DXY"])
        with tab_chart_gold: st.components.v1.html(get_tv_html("OANDA:XAUUSD", 600), height=600)
        with tab_chart_dxy: st.components.v1.html(get_tv_html("CAPITALCOM:DXY", 600), height=600)
    with col_news_bot: display_intelligence()
else:
    tab_chart_gold, tab_chart_dxy = st.tabs(["🥇 XAUUSD", "💵 DXY"])
    with tab_chart_gold: st.components.v1.html(get_tv_html("OANDA:XAUUSD", 400), height=400)
    with tab_chart_dxy: st.components.v1.html(get_tv_html("CAPITALCOM:DXY", 400), height=400)
    display_intelligence()

def handle_telegram_mentions(metrics, df_h4, df_m15, sentiment, final_news_list, war_news, setup_norm, trend_h4_str, trend_m15_str, spdr_val):
    last_update_id = st.session_state.get('last_tg_update_id', 0)
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    try:
        res = requests.get(url, params={"offset": last_update_id + 1, "timeout": 1}, timeout=5).json()
        if res.get("ok") and res.get("result"):
            for update in res["result"]:
                st.session_state.last_tg_update_id = update["update_id"]
                if "message" in update and "text" in update["message"]:
                    msg_text = update["message"]["text"]
                    if "@" in msg_text or msg_text.startswith("/"):
                        spdr_display = interpret_spdr(spdr_val)
                        if "/status" in msg_text or "ราคา" in msg_text: send_telegram_notify(f"🦅 กวักทองรายงานตัวครับ!\n\n🥇 Gold: ${metrics['GOLD'][0]:,.2f} ({metrics['GOLD'][1]:.2f}%)\n💵 DXY: {metrics['DXY'][0]:,.2f}\n🏦 SPDR: {spdr_display}\n🐑 Sentiment: S:{sentiment['short']}% | L:{sentiment['long']}%")
                        elif "/brief" in msg_text or "สรุป" in msg_text: send_telegram_notify(generate_telegram_us_briefing(trend_h4_str, trend_m15_str, metrics, sentiment, final_news_list, war_news, spdr_val))
                        elif "/chart" in msg_text or "กราฟ" in msg_text:
                            if setup_norm and isinstance(setup_norm, dict) and "Entry" in setup_norm:
                                msg = f"🎯 [Current Setup Focus]\n\n📍 Entry: {setup_norm.get('Entry')}\n🛑 SL: {setup_norm.get('SL')}\n💰 TP: {setup_norm.get('TP')}\n\n*(ระบบรันบน Cloud ปิดโหมดรูปภาพเพื่อความเสถียรครับ)*"
                                send_telegram_notify(msg)
                            else:
                                send_telegram_notify("📡 ตอนนี้ตลาดยังไม่มี Setup ที่ชัดเจนครับ แนะนำให้ WAIT ไปก่อน")
    except: pass

if not is_market_closed and df_m15 is not None: handle_telegram_mentions(metrics, df_h4, df_m15, sentiment, final_news_list, war_news, setup_norm, trend_h4_str, trend_m15_str, st.session_state.spdr_manual)
