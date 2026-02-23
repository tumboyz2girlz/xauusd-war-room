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

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Kwaktong War Room v12.12", page_icon="🦅", layout="wide", initial_sidebar_state="expanded")
st_autorefresh(interval=60000, limit=None, key="warroom_refresher")

if 'manual_overrides' not in st.session_state: st.session_state.manual_overrides = {}
if 'last_logged_setup' not in st.session_state: st.session_state.last_logged_setup = ""
if 'pending_trades' not in st.session_state: st.session_state.pending_trades = []
if 'log_history' not in st.session_state: st.session_state.log_history = {} 
if 'last_us_open_summary_date' not in st.session_state: st.session_state.last_us_open_summary_date = ""

# ⚠️ URL Firebase และ Google Sheet
FIREBASE_URL = "https://kwaktong-warroom-default-rtdb.asia-southeast1.firebasedatabase.app/market_data.json"
GOOGLE_SHEET_API_URL = "https://script.google.com/macros/s/AKfycby1vkYO6JiJfPc6sqiCUEJerfzLCv5LxhU7j16S9FYRpPqxXIUiZY8Ifb0YKiCQ7aj3_g/exec"

TELEGRAM_BOT_TOKEN = "8239625215:AAF7qUsz2O5mhINRhRYPTICljJsCErDDLD8"
TELEGRAM_CHAT_ID = "5638824802"

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
    h2.title-header {text-align: center; margin-bottom: 20px; font-weight: bold;}
    .stTabs [data-baseweb="tab"] {background-color: #1a1a2e; border-radius: 5px 5px 0 0;}
    .stTabs [aria-selected="true"] {background-color: #d4af37 !important; color: #000 !important; font-weight: bold;}
</style>
""", unsafe_allow_html=True)

def send_telegram_notify(msg, image_path=None):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return
    
    if image_path and os.path.exists(image_path):
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        data = {"chat_id": TELEGRAM_CHAT_ID, "caption": msg}
        with open(image_path, "rb") as image_file:
            files = {"photo": image_file}
            try: requests.post(url, data=data, files=files, timeout=10)
            except: pass
    else:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
        try: requests.post(url, json=data, timeout=5)
        except: pass

# --- 2. DATA ENGINE ---
@st.cache_data(ttl=30)
def get_market_data():
    metrics = {'GOLD': (0.0, 0.0), 'GC_F': (0.0, 0.0), 'DXY': (0.0, 0.0), 'US10Y': (0.0, 0.0)}
    df_m15, df_h4, mt5_news = None, None, []
    
    try:
        res = requests.get(FIREBASE_URL, timeout=5)
        if res.status_code == 200 and res.json() is not None:
            data = res.json()
            
            # XAUUSD M15
            if 'XAUUSD' in data:
                df_xau = pd.DataFrame(data['XAUUSD'])
                df_xau.rename(columns={'o':'open', 'h':'high', 'l':'low', 'c':'close', 't':'time'}, inplace=True)
                curr_gold, prev_gold = float(df_xau['close'].iloc[-1]), float(df_xau['close'].iloc[-2])
                metrics['GOLD'] = (curr_gold, ((curr_gold - prev_gold) / prev_gold) * 100)
                df_m15 = df_xau
                
            # XAUUSD H4
            if 'XAUUSD_H1' in data:
                df_h1 = pd.DataFrame(data['XAUUSD_H1'])
                df_h1.rename(columns={'o':'open', 'h':'high', 'l':'low', 'c':'close', 't':'time'}, inplace=True)
                df_h4 = df_h1
                
            # DXY จาก MT5 (ฉับไวที่สุด)
            if 'DXY' in data:
                df_dxy = pd.DataFrame(data['DXY'])
                df_dxy.rename(columns={'o':'open', 'h':'high', 'l':'low', 'c':'close', 't':'time'}, inplace=True)
                curr_dxy, prev_dxy = float(df_dxy['close'].iloc[-1]), float(df_dxy['close'].iloc[-2])
                metrics['DXY'] = (curr_dxy, ((curr_dxy - prev_dxy) / prev_dxy) * 100)
                
            # ข่าวจาก MT5
            if 'NEWS' in data:
                now_thai = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
                for ev in data['NEWS']:
                    event_dt = datetime.datetime.fromtimestamp(ev['time_sec']) 
                    time_diff_hours = (event_dt - now_thai).total_seconds() / 3600
                    mt5_news.append({
                        'source': 'MT5', 'title': ev['title'], 
                        'time': event_dt.strftime("%H:%M"), 'impact': ev['impact'], 
                        'actual': st.session_state.manual_overrides.get(ev['title'], ev['actual']), 
                        'forecast': ev['forecast'], 'direction': ev.get('direction', ''), 
                        'dt': event_dt, 'time_diff_hours': time_diff_hours
                    })
    except: pass

    # ดึงข้อมูลเพิ่มเติมจาก Yahoo Finance เป็น Confluence
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
    if weekday == 5 or weekday == 6:
        return True, "🛑 ตลาดปิดทำการ (Weekend)"
    if df_m15 is None or df_m15.empty:
        return True, "🛑 ไม่มีข้อมูลการเชื่อมต่อจาก MT5"
    last_candle_time = pd.to_datetime(df_m15['time'].iloc[-1], unit='s') + datetime.timedelta(hours=7)
    hours_diff = (now_thai - last_candle_time).total_seconds() / 3600
    if hours_diff > 2.0:
        return True, f"🛑 ตลาดเปิด แต่ MT5 ขาดการเชื่อมต่อ (ข้อมูลหยุดเดินมา {hours_diff:.1f} ชั่วโมง)"
    return False, "🟢 เชื่อมต่อ MT5 สำเร็จ (Market Open)"

def get_current_session():
    now_thai = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
    h = now_thai.hour
    sessions = []
    if 5 <= h < 14: sessions.append("🌏 Asia Session")
    if 14 <= h < 23: sessions.append("💶 Europe/London Session")
    if h >= 19 or h < 4: sessions.append("🗽 US/New York Session")
    if not sessions: return "🌙 Market Transition / Low Liquidity"
    return " | ".join(sessions)

# --- 3. FOREXFACTORY & SCRAPERS ---
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
                ff_news.append({
                    'source': 'FF', 'title': title, 'time': thai_dt.strftime("%H:%M"), 
                    'impact': impact, 'actual': st.session_state.manual_overrides.get(title, event.find('actual').text if event.find('actual') is not None else "Pending"), 
                    'forecast': event.find('forecast').text if event.find('forecast') is not None else "", 
                    'direction': '', 'dt': thai_dt, 'time_diff_hours': time_diff_hours
                })
        return ff_news
    except: return []

# 💡 การ Merge ข่าวที่ฉลาดขึ้น: ให้ MT5 เป็นใหญ่
def merge_news_sources(mt5_list, ff_list):
    merged = []
    # 1. เอา MT5 เป็นแกนหลัก (ความเร็วสูงสุด)
    for mt5_news in mt5_list:
        merged.append(mt5_news)
        
    # 2. เอา FF มาเสริมเฉพาะที่ MT5 ไม่มี
    for ff_news in ff_list:
        is_duplicate = False
        for m_news in merged:
            time_diff_sec = abs((ff_news['dt'] - m_news['dt']).total_seconds())
            ff_keyword = ff_news['title'].split()[0].lower()
            mt5_keyword = m_news['title'].split()[0].lower()
            
            if time_diff_sec <= 3600 and (ff_keyword in m_news['title'].lower() or mt5_keyword in ff_news['title'].lower()):
                is_duplicate = True
                break
                
        if not is_duplicate:
            merged.append(ff_news)

    merged.sort(key=lambda x: x['dt'])
    
    next_red_news = None
    for ev in merged:
        if ev['impact'] == 'High' and -0.5 <= ev['time_diff_hours'] <= 3:
            if next_red_news is None or ev['time_diff_hours'] < next_red_news['hours']:
                next_red_news = {'title': ev['title'], 'hours': ev['time_diff_hours'], 'time': ev['dt'].strftime("%H:%M น.")}
                
    return merged, next_red_news

@st.cache_data(ttl=600)
def get_retail_sentiment():
    try: return {"short": 78.5, "long": 21.5}
    except: return {"short": 50, "long": 50}

@st.cache_data(ttl=3600)
def get_spdr_flow(): return "Neutral" 

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
                elif any(kw in title_lower for kw in ['fed', 'inflation', 'rate']): base_score += 2.0
                final_score = min(10.0, max(1.0, base_score))
                
                direction = "⚪ NEUTRAL"
                if any(w in title_lower for w in ['war', 'missile', 'strike', 'attack', 'escalat']): direction = "🟢 GOLD UP (Safe Haven)"
                elif any(w in title_lower for w in ['ceasefire', 'peace']): direction = "🔴 GOLD DOWN (Risk-On)"
                elif any(w in title_lower for w in ['rate hike', 'hawkish']): direction = "🔴 GOLD DOWN (Strong USD)"
                elif any(w in title_lower for w in ['rate cut', 'dovish']): direction = "🟢 GOLD UP (Weak Econ)"
                else:
                    if polarity <= -0.2: direction = "🟢 GOLD UP (Negative/Panic)"
                    elif polarity >= 0.2: direction = "🔴 GOLD DOWN (Positive/Calm)"
                
                news_list.append({
                    'title_en': entry.title, 'title_th': translator.translate(entry.title), 
                    'link': entry.link, 'time': date_str, 'score': final_score, 'direction': direction
                })
        except: pass
        return news_list
    return fetch_rss("(Fed OR Powell OR Treasury)"), fetch_rss("(War OR Missile OR Israel OR Russia)")

@st.cache_data(ttl=300) 
def get_breaking_news():
    translator = GoogleTranslator(source='en', target='th')
    speed_news = []
    urls = [
        {"url": "https://www.forexlive.com/feed", "source": "ForexLive"},
        {"url": "https://www.fxstreet.com/rss", "source": "FXStreet"}
    ]
    for source in urls:
        try:
            feed = feedparser.parse(requests.get(source['url'], headers={'User-Agent': 'Mozilla/5.0'}, timeout=5).content)
            for entry in feed.entries[:5]:
                pub_time = mktime(entry.published_parsed)
                date_str = datetime.datetime.fromtimestamp(pub_time).strftime('%d %b | %H:%M น.')
                title_lower = entry.title.lower()
                polarity = TextBlob(entry.title).sentiment.polarity
                
                direction = "⚪ NEUTRAL"
                if any(w in title_lower for w in ['gold', 'xau']):
                    direction = "🟢 GOLD UP" if polarity > 0 else "🔴 GOLD DOWN"
                elif any(w in title_lower for w in ['usd', 'dollar', 'fed']):
                    direction = "🔴 GOLD DOWN (Strong USD)" if polarity > 0 else "🟢 GOLD UP (Weak USD)"
                
                base_score = abs(polarity) * 5
                if any(w in title_lower for w in ['urgent', 'breaking', 'alert', 'jump', 'drop', 'crash']): base_score += 5.0
                final_score = min(10.0, max(1.0, base_score))
                
                speed_news.append({
                    'title_en': entry.title, 'title_th': translator.translate(entry.title), 
                    'link': entry.link, 'time': date_str, 'score': final_score, 
                    'direction': direction, 'source': source['source'], 'timestamp': pub_time
                })
        except: pass
    speed_news.sort(key=lambda x: x['timestamp'], reverse=True)
    return speed_news[:10]

# --- 4. CORE AI ---
def calculate_normal_setup(df_m15, df_h4, final_news_list, sentiment, metrics, is_market_closed):
    if is_market_closed: 
        return "MARKET CLOSED 🛑", "ระบบหยุดการวิเคราะห์เนื่องจากตลาดปิด หรือขาดข้อมูลล่าสุดจาก MT5", {}, False
        
    df_h4['ema50'] = ta.ema(df_h4['close'], length=50)
    df_m15['ema50'] = ta.ema(df_m15['close'], length=50)
    df_m15['atr'] = ta.atr(df_m15['high'], df_m15['low'], df_m15['close'], length=14)
    df_m15['rsi'] = ta.rsi(df_m15['close'], length=14)
    macd = ta.macd(df_m15['close'], fast=12, slow=26, signal=9)
    df_m15 = pd.concat([df_m15, macd], axis=1)

    # 💡 อัปเกรด Logic หาเทรนด์: เช็คความชัน (Slope) 3 แท่งล่าสุด ป้องกัน Liquidity Sweep
    if df_h4.iloc[-2]['ema50'] > df_h4.iloc[-3]['ema50'] and df_h4.iloc[-3]['ema50'] > df_h4.iloc[-4]['ema50']:
        trend_h4 = "UP"
    elif df_h4.iloc[-2]['ema50'] < df_h4.iloc[-3]['ema50'] and df_h4.iloc[-3]['ema50'] < df_h4.iloc[-4]['ema50']:
        trend_h4 = "DOWN"
    else:
        trend_h4 = "SIDEWAY"

    if df_m15.iloc[-2]['ema50'] > df_m15.iloc[-3]['ema50'] and df_m15.iloc[-3]['ema50'] > df_m15.iloc[-4]['ema50']:
        trend_m15 = "UP"
    elif df_m15.iloc[-2]['ema50'] < df_m15.iloc[-3]['ema50'] and df_m15.iloc[-3]['ema50'] < df_m15.iloc[-4]['ema50']:
        trend_m15 = "DOWN"
    else:
        trend_m15 = "SIDEWAY"

    atr = float(df_m15.iloc[-2]['atr'])
    ema = float(df_m15.iloc[-2]['ema50'])
    rsi = float(df_m15.iloc[-1]['rsi'])
    macd_hist = float(df_m15['MACDh_12_26_9'].iloc[-1]) if 'MACDh_12_26_9' in df_m15 else 0.0

    current_m15 = df_m15.iloc[-1]
    red_body_size = current_m15['open'] - current_m15['close']
    is_flash_crash = True if (red_body_size >= 15.0) and ((current_m15['close'] - current_m15['low']) <= 3.0) else False

    def get_smc_setup(df, trend_dir):
        df_recent = df.tail(40).reset_index(drop=True)
        atr_smc = df_recent['atr'].iloc[-1]
        if trend_dir == "UP":
            for i in range(len(df_recent)-1, 1, -1):
                if df_recent['low'].iloc[i] > df_recent['high'].iloc[i-2]: return True, f"🧲 Demand FVG โซน ${df_recent['high'].iloc[i-2]:.2f} ถึง ${df_recent['low'].iloc[i]:.2f}", f"${df_recent['low'].iloc[i-2] - (atr_smc * 0.5):.2f}", f"${df_recent['high'].max():.2f}"
        else:
            for i in range(len(df_recent)-1, 1, -1):
                if df_recent['high'].iloc[i] < df_recent['low'].iloc[i-2]: return True, f"🧲 Supply FVG โซน ${df_recent['high'].iloc[i]:.2f} ถึง ${df_recent['low'].iloc[i-2]:.2f}", f"${df_recent['high'].iloc[i-2] + (atr_smc * 0.5):.2f}", f"${df_recent['low'].min():.2f}"
        return False, "", "", ""

    smc_found, smc_entry, smc_sl, smc_tp = get_smc_setup(df_m15, trend_m15)
    
    recent_news_dir = ""
    for ev in final_news_list:
        if ev['source'] == 'MT5' and ev['direction'] and -2.0 <= ev['time_diff_hours'] <= 0:
            if "UP" in ev['direction']: recent_news_dir = "UP"
            elif "DOWN" in ev['direction']: recent_news_dir = "DOWN"
            break

    retail_short = sentiment.get('short', 50)
    retail_long = sentiment.get('long', 50)
    dxy_trend = metrics['DXY'][1]

    if is_flash_crash:
        setup = {'Entry': f"กด Sell ทันที หรือรอเด้งโซน ${current_m15['close'] + (0.5*atr):.2f}", 'SL': f"${current_m15['open'] + (0.5*atr):.2f}", 'TP': f"${current_m15['close'] - (3*atr):.2f}"}
        return "🚨 FLASH CRASH (SELL NOW!)", f"ตรวจพบการเทขายแดงเต็มแท่งดิ่งลง ${red_body_size:.2f} สั่งแทง SELL ตามน้ำ!", setup, True

    elif trend_h4 == "UP" and trend_m15 == "UP":
        if recent_news_dir == "DOWN": return "WAIT (News Conflict ⚠️)", "เทรนด์ขาขึ้น แต่ข่าว MT5 ล่าสุดกดดันทองลง", {}, False
        elif rsi > 70: 
            setup = {'Entry': smc_entry, 'SL': smc_sl, 'TP': smc_tp} if smc_found else {'Entry': f"${ema-(0.5*atr):.2f} (EMA)", 'SL': f"${ema-(2*atr):.2f}", 'TP': f"${ema+(2*atr):.2f}"}
            return "PENDING LONG", f"RSI ทะลุ {rsi:.1f} (Overbought) ห้ามไล่ราคา! ให้ตั้ง Buy Limit รอย่อ", setup, False
        else:
            reason = "เทรนด์หลักขาขึ้น"
            reason += " + 🚀 MACD หนุน" if macd_hist > 0 else " + 🐌 MACD เริ่มอ่อนแรง"
            if retail_short > 60: reason += " + 🐑 รายย่อยฝืน Sell"
            elif retail_long > 70: reason += " + ⚠️ ระวังรายย่อยแห่ Buy ตาม"
            if dxy_trend < 0: reason += " + 💵 DXY อ่อนค่า"
            setup = {'Entry': smc_entry, 'SL': smc_sl, 'TP': smc_tp} if smc_found else {'Entry': f"${ema:.2f} (EMA)", 'SL': f"${ema-(2*atr):.2f}", 'TP': f"${ema+(2*atr):.2f}"}
            return "LONG", reason, setup, False

    elif trend_h4 == "DOWN" and trend_m15 == "DOWN":
        if recent_news_dir == "UP": return "WAIT (News Conflict ⚠️)", "เทรนด์ขาลง แต่ข่าว MT5 ล่าสุดหนุนทองขึ้น", {}, False
        elif rsi < 30: 
            setup = {'Entry': smc_entry, 'SL': smc_sl, 'TP': smc_tp} if smc_found else {'Entry': f"${ema+(0.5*atr):.2f} (EMA)", 'SL': f"${ema+(2*atr):.2f}", 'TP': f"${ema-(2*atr):.2f}"}
            return "PENDING SHORT", f"RSI ตกไปที่ {rsi:.1f} (Oversold) ห้ามกด Sell ก้นเหว! ตั้ง Sell Limit รอเด้ง", setup, False
        else:
            reason = "เทรนด์หลักขาลง"
            reason += " + 🚀 MACD หนุน" if macd_hist < 0 else " + 🐌 MACD เริ่มอ่อนแรง"
            if retail_long > 60: reason += " + 🐑 รายย่อยฝืน Buy"
            elif retail_short > 70: reason += " + ⚠️ ระวังรายย่อยแห่ Sell ตาม"
            if dxy_trend > 0: reason += " + 💵 DXY แข็งค่า"
            setup = {'Entry': smc_entry, 'SL': smc_sl, 'TP': smc_tp} if smc_found else {'Entry': f"${ema:.2f} (EMA)", 'SL': f"${ema+(2*atr):.2f}", 'TP': f"${ema-(2*atr):.2f}"}
            return "SHORT", reason, setup, False
            
    return "WAIT", "H1/H4 Trend ไม่ตรงกับ M15", {}, False

def detect_choch_and_sweep(df):
    recent = df.tail(20).reset_index(drop=True)
    if len(recent) < 20: return False, "", 0, 0
    lowest_low = recent['low'].iloc[0:15].min()
    highest_high = recent['high'].iloc[0:15].max()
    current_close = recent['close'].iloc[-1]
    if recent['low'].iloc[-5:-1].min() < lowest_low and current_close > recent['high'].iloc[-5:-1].max(): return True, "LONG", recent['low'].iloc[-5:-1].min(), current_close
    if recent['high'].iloc[-5:-1].max() > highest_high and current_close < recent['low'].iloc[-5:-1].min(): return True, "SHORT", recent['high'].iloc[-5:-1].max(), current_close
    return False, "", 0, 0

def calculate_all_in_setup(df_m15, next_red_news, metrics, sentiment, is_market_closed):
    if is_market_closed: return "MARKET CLOSED 🛑", "ระบบหยุดการวิเคราะห์เนื่องจากตลาดปิด", {}, "🔴"
    light = "🔴"
    if next_red_news:
        hrs = next_red_news['hours']
        if 0.25 <= hrs <= 0.5: light = "🟢" 
        elif -0.5 <= hrs < 0.25: return "WAIT", f"🔴 ห้ามเทรด! ข่าว {next_red_news['title']} เพิ่งออก/กำลังจะออก", {}, "🔴"
        else: return "WAIT", "🟡 รอพายุสภาพคล่อง (ข่าวกล่องแดง)", {}, "🟡"
    else: return "WAIT", "⚪ ไม่มีข่าวกล่องแดงในระยะนี้", {}, "⚪"
        
    found_sweep, direction, sweep_price, current_price = detect_choch_and_sweep(df_m15)
    if not found_sweep: return "WAIT", "🟢 ข่าวออกแล้ว แต่ยังไม่พบ CHoCH & Liquidity Sweep", {}, "🟢"
        
    dxy_trend, gcf_trend = metrics['DXY'][1], metrics['GC_F'][1]
    
    if direction == "LONG":
        if dxy_trend > 0: return "WAIT", "DXY ยังแข็งค่า (ขัดแย้ง)", {}, "🟢"
        if gcf_trend < 0: return "WAIT", "GC=F Premium ไม่หนุนขาขึ้น", {}, "🟢"
        if sentiment['short'] < 75.0: return "WAIT", f"รายย่อยยัง Short ไม่พอ ({sentiment['short']}%)", {}, "🟢"
        entry = current_price - 1.0 
        sl = max(sweep_price - 0.5, entry - 3.0) 
        return "ALL-IN LONG 🚀", f"Confluence 100%! ตั้ง Buy Limit ดักรอย่อ", {'Entry': f"${entry:.2f}", 'SL': f"${sl:.2f}", 'TP': f"${entry + ((entry - sl) * 2):.2f}", 'Sweep': f"${sweep_price:.2f}"}, "🟢"
        
    elif direction == "SHORT":
        if dxy_trend < 0: return "WAIT", "DXY ยังอ่อนค่า (ขัดแย้ง)", {}, "🟢"
        if gcf_trend > 0: return "WAIT", "GC=F Premium ไม่หนุนขาลง", {}, "🟢"
        if sentiment['long'] < 75.0: return "WAIT", f"รายย่อยยัง Buy ไม่พอ ({sentiment['long']}%)", {}, "🟢"
        entry = current_price + 1.0 
        sl = min(sweep_price + 0.5, entry + 3.0) 
        return "ALL-IN SHORT 🚀", f"Confluence 100%! ตั้ง Sell Limit ดักรอเด้ง", {'Entry': f"${entry:.2f}", 'SL': f"${sl:.2f}", 'TP': f"${entry - ((sl - entry) * 2):.2f}", 'Sweep': f"${sweep_price:.2f}"}, "🟢"

    return "WAIT", "รอ...", {}, light

# --- 6. AUTO-LOGGER & TELEGRAM NOTIFY ---
def extract_price(text, is_long=True, is_entry=False):
    prices = [float(x) for x in re.findall(r'\d+\.\d+', str(text).replace(',', ''))]
    if not prices: return 0.0
    if len(prices) == 1: return prices[0]
    if is_entry: return max(prices) if is_long else min(prices)
    return prices[0]

def log_new_trade(setup_type, sig, setup_data, reason_text, df_m15):
    if "ใส่_URL" in GOOGLE_SHEET_API_URL: return
    hist = st.session_state.log_history.get(setup_type)
    now = time.time()
    if hist and (now - hist['time'] < 3600) and hist['signal'] == sig: return

    st.session_state.log_history[setup_type] = {'time': now, 'signal': sig}
    try:
        trade_id = f"TRD-{int(time.time())}"
        thai_dt_str = (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime("%d %b %Y %H:%M")
        now_str = (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")
        clean_reason = re.sub('<[^<]+>', '', reason_text).strip()
        is_long = "LONG" in sig or "BUY" in sig
        entry_val = extract_price(setup_data.get('Entry', ''), is_long, True)
        sl_val = extract_price(setup_data.get('SL', ''))
        tp_val = extract_price(setup_data.get('TP', ''))
        is_market = "NOW" in sig 

        payload = {
            "action": "log", "id": trade_id, "timestamp": now_str, 
            "setup_type": setup_type, "signal": sig, 
            "entry": setup_data.get('Entry', ''), "sl": setup_data.get('SL', ''), 
            "tp": setup_data.get('TP', ''), "reason": clean_reason
        }
        
        internal_trade = payload.copy()
        internal_trade['activated'] = is_market 
        internal_trade['entry_val'] = entry_val
        internal_trade['sl_val'] = sl_val
        internal_trade['tp_val'] = tp_val
        internal_trade['display_time'] = thai_dt_str
        internal_trade['display_entry'] = setup_data.get('Entry', '')
        internal_trade['display_tp'] = setup_data.get('TP', '')
        internal_trade['display_sl'] = setup_data.get('SL', '')
        internal_trade['display_reason'] = clean_reason

        requests.post(GOOGLE_SHEET_API_URL, json=payload, timeout=3)
        st.session_state.pending_trades.append(internal_trade)
        
        img_path = "setup_chart.png"
        fig = plot_setup_chart(df_m15, setup_data, mode="All-In" if "All-In" in setup_type else "Normal")
        if fig:
            try: fig.write_image(img_path)
            except: img_path = None

        tg_msg = f"🎯 [NEW SETUP] {thai_dt_str}\n\n"
        tg_msg += f"Mode: {setup_type}\n"
        tg_msg += f"Signal: {sig}\n"
        tg_msg += f"Entry: {internal_trade['display_entry']}\n"
        tg_msg += f"Why?: {clean_reason}\n"
        tg_msg += f"Tp: {internal_trade['display_tp']}\n"
        tg_msg += f"Sl: {internal_trade['display_sl']}"
        send_telegram_notify(tg_msg, img_path)
        
    except Exception as e: print("Log Error:", e)

def check_pending_trades(current_high, current_low):
    if "ใส่_URL" in GOOGLE_SHEET_API_URL: return
    trades_to_remove = []
    for trade in st.session_state.pending_trades:
        entry_p = trade.get('entry_val', 0.0)
        sl_p = trade.get('sl_val', 0.0)
        tp_p = trade.get('tp_val', 0.0)
        if entry_p == 0.0 or sl_p == 0.0 or tp_p == 0.0: continue
        is_long = "LONG" in trade['signal'] or "BUY" in trade['signal']

        if not trade.get('activated', False):
            if is_long and current_low <= entry_p: trade['activated'] = True
            elif not is_long and current_high >= entry_p: trade['activated'] = True

        if trade.get('activated', False):
            result = None
            if is_long:
                if current_low <= sl_p: result = "LOSS ❌"
                elif current_high >= tp_p: result = "WIN 🎯"
            else:
                if current_high >= sl_p: result = "LOSS ❌"
                elif current_low <= tp_p: result = "WIN 🎯"
            if result:
                try: requests.post(GOOGLE_SHEET_API_URL, json={"action": "update", "id": trade['id'], "result": result}, timeout=3)
                except: pass
                
                tg_msg = f"🏁 [RESULT] {trade.get('display_time', '')}\n\n"
                tg_msg += f"Signal: {trade.get('signal', '')}\n"
                tg_msg += f"Entry: {trade.get('display_entry', '')}\n"
                tg_msg += f"Why?: {trade.get('display_reason', '')}\n"
                tg_msg += f"Tp: {trade.get('display_tp', '')}\n"
                tg_msg += f"Sl: {trade.get('display_sl', '')}\n\n"
                tg_msg += f"✨ Result: {result}"
                send_telegram_notify(tg_msg)
                trades_to_remove.append(trade)
                
    for t in trades_to_remove:
        if t in st.session_state.pending_trades: st.session_state.pending_trades.remove(t)

# --- 7. EXECUTIVE SUMMARY ---
def generate_exec_summary(df_h4, metrics, next_red_news, sentiment):
    if df_h4 is None: return "ข้อมูล Market ปิดทำการ ไม่สามารถประมวลผลเทรนด์ได้ในขณะนี้"
    
    # อัปเกรด Logic หาเทรนด์ H4
    if df_h4.iloc[-2]['ema50'] > df_h4.iloc[-3]['ema50'] and df_h4.iloc[-3]['ema50'] > df_h4.iloc[-4]['ema50']: trend = "ขาขึ้น 🟢"
    elif df_h4.iloc[-2]['ema50'] < df_h4.iloc[-3]['ema50'] and df_h4.iloc[-3]['ema50'] < df_h4.iloc[-4]['ema50']: trend = "ขาลง 🔴"
    else: trend = "ไซด์เวย์ ⚪"
    
    dxy_status = "อ่อนค่า (หนุนทอง)" if metrics['DXY'][1] < 0 else "แข็งค่า (กดดันทอง)"
    summary = f"**📊 Overall Market Bias:** ขณะนี้ทองคำอยู่ในโครงสร้างเทรนด์ **{trend}** (H4) "
    summary += f"ดอลลาร์ (DXY) กำลัง **{dxy_status}** และรายย่อยเทน้ำหนักไปฝั่ง **{'Short' if sentiment.get('short',50) > 50 else 'Long'}** "
    if next_red_news: summary += f"<br>⚠️ **News Alert:** ระวังความผันผวนจากข่าว **{next_red_news['title']}** ในอีก {next_red_news['hours']:.1f} ชั่วโมง"
    else: summary += "<br>✅ **News Alert:** ไม่มีข่าวกล่องแดงกวนใจ สามารถรันเทรนด์ Grid ได้ตามปกติ"
    return summary

def generate_telegram_us_briefing(df_h4, metrics, sentiment, final_news_list, war_news):
    now_thai = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
    trend = "ไม่สามารถวิเคราะห์ได้ (ไม่มีข้อมูล)"
    if df_h4 is not None: 
        if df_h4.iloc[-2]['ema50'] > df_h4.iloc[-3]['ema50'] and df_h4.iloc[-3]['ema50'] > df_h4.iloc[-4]['ema50']: trend = "ขาขึ้น 🟢"
        elif df_h4.iloc[-2]['ema50'] < df_h4.iloc[-3]['ema50'] and df_h4.iloc[-3]['ema50'] < df_h4.iloc[-4]['ema50']: trend = "ขาลง 🔴"
        else: trend = "ไซด์เวย์ ⚪"
    
    dxy_status = "อ่อนค่า 🟢" if metrics['DXY'][1] < 0 else "แข็งค่า 🔴"
    us10y_status = "ปรับตัวลง 🟢" if metrics['US10Y'][1] < 0 else "พุ่งขึ้น 🔴"
    gcf_status = "ซื้อเก็บ 🟢" if metrics['GC_F'][1] > 0 else "เทขาย 🔴"
    senti_status = "หนุนทองขึ้น 🟢" if sentiment.get('short',50) > 50 else "กดดันทองลง 🔴"
    
    today_news_str = ""
    for ev in final_news_list:
        if ev['dt'].date() == now_thai.date() and ev['impact'] == 'High':
            today_news_str += f"- {ev['time']} น. : {ev['title']}\n"
    if not today_news_str: today_news_str = "- ไม่มีข่าวกล่องแดงคืนนี้ ✅\n"
    
    geo_str = "- สงบสุข ไม่มีข่าวฉุกเฉิน ⚪"
    if war_news: geo_str = f"- {war_news[0]['title_th']} (Impact: {war_news[0]['score']:.1f}/10) {war_news[0]['direction']}"

    msg = f"🗽🇺🇸 US Session Briefing 🇺🇸🗽\n"
    msg += f"ประจำวันที่: {now_thai.strftime('%d %b %Y | 19:30 น.')}\n\n"
    msg += f"📊 [Technical]\n"
    msg += f"Trend H4: {trend}\n"
    msg += f"XAUUSD (Live): ${metrics['GOLD'][0]:.2f}\n\n"
    msg += f"💵 [Macro / 5 Pillars]\n"
    msg += f"DXY: {metrics['DXY'][0]:.2f} ({dxy_status})\n"
    msg += f"US10Y: {metrics['US10Y'][0]:.2f}% ({us10y_status})\n"
    msg += f"GC=F (Premium): {gcf_status}\n\n"
    msg += f"🐑 [Retail Sentiment]\n"
    msg += f"S:{sentiment.get('short',50)}% / L:{sentiment.get('long',50)}% ({senti_status})\n\n"
    msg += f"📅 [US Economic News Tonight]\n{today_news_str}\n"
    msg += f"⚠️ [Geo-Politics]\n{geo_str}\n\n"
    msg += f"🤖 AI Prediction: หากโครงสร้างไม่เปลี่ยน แนะนำให้หาจุดเข้าฝั่ง {trend.replace('🟢','').replace('🔴','').replace('⚪','').strip()}"
    return msg

# --- 8. VISUALIZER ---
def plot_setup_chart(df, setup_dict, mode="Normal"):
    if df is None or df.empty or not setup_dict: return None
    df_plot = df.tail(100).copy()
    df_plot['datetime'] = pd.to_datetime(df_plot['time'], unit='s')
    fig = go.Figure(data=[go.Candlestick(x=df_plot['datetime'], open=df_plot['open'], high=df_plot['high'], low=df_plot['low'], close=df_plot['close'], increasing_line_color='#00ff00', decreasing_line_color='#ff3333')])
    def get_prices(t): return [float(x) for x in re.findall(r'\d+\.\d+', str(t).replace(',', ''))]
    sl, tp, entry = get_prices(setup_dict.get('SL', '')), get_prices(setup_dict.get('TP', '')), get_prices(setup_dict.get('Entry', ''))
    sweep = get_prices(setup_dict.get('Sweep', '')) 
    
    entry_text = str(setup_dict.get('Entry', ''))
    label_text = "🎯 Entry"
    if "FVG" in entry_text: label_text = "🎯 FVG Zone"
    elif "EMA" in entry_text: label_text = "🎯 EMA Base"
    
    line_color = "#ffcc00" if mode == "All-In" else "#00ccff"
    
    if sl: fig.add_hline(y=sl[0], line_dash="dash", line_color="#ff4444", annotation_text="🛑 SL", annotation_position="bottom right", annotation_font_color="#ff4444")
    if tp: fig.add_hline(y=tp[0], line_dash="dash", line_color="#00ff00", annotation_text="💰 TP", annotation_position="top right", annotation_font_color="#00ff00")
    if sweep: fig.add_hline(y=sweep[0], line_dash="dot", line_color="#ff00ff", annotation_text="⚡ CHoCH / Sweep", annotation_position="left", annotation_font_color="#ff00ff")
    
    if entry:
        if len(entry) >= 2: fig.add_hrect(y0=min(entry), y1=max(entry), fillcolor=f"rgba({'255, 204, 0' if mode=='All-In' else '0, 204, 255'}, 0.2)", line_width=1, annotation_text=label_text, annotation_position="top right")
        else: fig.add_hline(y=entry[0], line_dash="dash", line_color=line_color, annotation_text=label_text, annotation_position="top right", annotation_font_color=line_color)
        
    fig.update_layout(template='plotly_dark', margin=dict(l=10, r=50, t=10, b=10), height=350, xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    return fig

def get_setup_time_html(setup_type, current_sig, base_color):
    hist = st.session_state.log_history.get(setup_type)
    if hist and hist['signal'] == current_sig:
        utc_dt = datetime.datetime.utcfromtimestamp(hist['time'])
        thai_dt = utc_dt + datetime.timedelta(hours=7)
        elapsed_mins = int((time.time() - hist['time']) / 60)
        is_stale = elapsed_mins >= 45
        warn_color = "#ff4444" if is_stale else base_color
        warn_icon = "⚠️" if is_stale else "🕒"
        warn_text = f" ({elapsed_mins} นาทีที่แล้ว - ระวัง! Setup เก่าอาจจบไปแล้ว)" if is_stale else f" ({elapsed_mins} นาทีที่แล้ว)"
        return f"<div style='font-size:13px; color:{warn_color}; margin-top:8px; padding-top:8px; border-top:1px dashed #444;'>{warn_icon} <b>Signal Time:</b> {thai_dt.strftime('%d %b %Y | %H:%M น.')} {warn_text}</div>"
    return ""

# --- UI MAIN ---
metrics, df_m15, df_h4, mt5_news = get_market_data()
is_market_closed, status_msg = check_market_status(df_m15)
current_session = get_current_session()

ff_raw_news = get_forexfactory_usd()
final_news_list, next_red_news = merge_news_sources(mt5_news, ff_raw_news)
sentiment = get_retail_sentiment()
pol_news, war_news = get_categorized_news() 
speed_news = get_breaking_news()

if not is_market_closed and df_m15 is not None: 
    check_pending_trades(float(df_m15.iloc[-1]['high']), float(df_m15.iloc[-1]['low']))

sig_norm, reason_norm, setup_norm, is_flash_crash = calculate_normal_setup(df_m15, df_h4, final_news_list, sentiment, metrics, is_market_closed)
sig_allin, reason_allin, setup_allin, light = calculate_all_in_setup(df_m15, next_red_news, metrics, sentiment, is_market_closed)

now_thai = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
current_date_str = now_thai.strftime("%Y-%m-%d")
if not is_market_closed and now_thai.hour == 19 and now_thai.minute >= 30 and st.session_state.last_us_open_summary_date != current_date_str:
    us_briefing_msg = generate_telegram_us_briefing(df_h4, metrics, sentiment, final_news_list, war_news)
    send_telegram_notify(us_briefing_msg)
    st.session_state.last_us_open_summary_date = current_date_str

with st.sidebar:
    st.header("💻 War Room Terminal")
    layout_mode = st.radio("Display:", ["🖥️ Desktop", "📱 Mobile"])
    if st.button("Refresh Data", type="primary"): st.cache_data.clear()
    
    st.markdown("---")
    st.markdown(f"**Status:** {status_msg}")
    st.markdown("---")
    
    st.subheader("✍️ Override ข่าวเศรษฐกิจ")
    has_pending = False
    for i, ev in enumerate(final_news_list):
        if "Pending" in ev['actual'] and -12.0 <= ev.get('time_diff_hours', 0) <= 24.0:
            has_pending = True
            source_tag = "⚡" if ev.get('source') == 'MT5' else "🌐"
            new_val = st.text_input(f"{source_tag} [{ev['time']}] {ev['title']}", value=st.session_state.manual_overrides.get(ev['title'], ""), key=f"override_{i}")
            if new_val != st.session_state.manual_overrides.get(ev['title'], ""):
                st.session_state.manual_overrides[ev['title']] = new_val
                st.rerun()
    if not has_pending: st.write("✅ ข้อมูลอัปเดตสมบูรณ์")

st.title("🦅 XAUUSD WAR Room: Institutional Master Node v12.12")

st.markdown(f"<div class='session-card'>📍 Active Market Killzone: {current_session}</div>", unsafe_allow_html=True)

c1, c2, c3, c4, c5, c6 = st.columns((1,1,1,1,1,1))
with c1: st.metric("XAUUSD", f"${metrics['GOLD'][0]:,.2f}", f"{metrics['GOLD'][1]:.2f}%")
with c2: st.metric("GC=F", f"${metrics['GC_F'][0]:,.2f}", f"{metrics['GC_F'][1]:.2f}%")
with c3: st.metric("DXY", f"{metrics['DXY'][0]:,.2f}", f"{metrics['DXY'][1]:.2f}%", delta_color="inverse")
with c4: st.metric("US10Y", f"{metrics['US10Y'][0]:,.2f}", f"{metrics['US10Y'][1]:.2f}%", delta_color="inverse")
with c5: st.metric("SPDR Flow", get_spdr_flow())
with c6: st.metric("Retail Senti.", f"S:{sentiment.get('short',50)}%", f"L:{sentiment.get('long',50)}%", delta_color="off")

if is_market_closed:
    st.markdown(f"<div style='text-align: center; color: #ff4444; font-size: 14px; margin-top: -5px; margin-bottom: 15px;'>{status_msg}</div>", unsafe_allow_html=True)
else:
    st.markdown(f"<div style='text-align: center; color: #00ff00; font-size: 14px; margin-top: -5px; margin-bottom: 15px;'>{status_msg}</div>", unsafe_allow_html=True)

st.markdown(f"<div class='exec-summary'>{generate_exec_summary(df_h4, metrics, next_red_news, sentiment)}</div>", unsafe_allow_html=True)

ea_status_html = ""
siren_html = ""

if "CLOSED" in sig_norm: 
    ea_status_html = "<div style='color:#888; font-size:18px; font-weight:bold; margin-top:10px;'>🛑 EA OFFLINE: ตลาดปิด หรือ ขาดการเชื่อมต่อจาก MT5</div>"
elif is_flash_crash: 
    ea_status_html = "<div style='color:#ff3333; font-size:18px; font-weight:bold; margin-top:10px;'>🚨 EMERGENCY: ปิดการทำงาน Grid ทันที! เข้าโหมด Anti-Dump / Hard Cut</div>"
    siren_html = """
    <audio id="siren_audio" autoplay loop><source src="https://actions.google.com/sounds/v1/alarms/air_raid_siren.ogg" type="audio/ogg"></audio>
    <script>var siren = document.getElementById("siren_audio"); siren.volume = 1.0; setTimeout(function(){ siren.pause(); }, 15000);</script>
    """
elif "WAIT" in sig_norm or "PENDING" in sig_norm: 
    ea_status_html = "<div style='color:#ffcc00; font-size:18px; font-weight:bold; margin-top:10px;'>⚠️ EA STANDBY: เข้าสู่โหมด Gold Down Pause หรือรอเข้าเทรดแบบ Limit</div>"
else: 
    ea_status_html = "<div style='color:#00ff00; font-size:18px; font-weight:bold; margin-top:10px;'>▶️ EA RUNNING: กางระบบ Grid Buy/Sell ได้ตามปกติ</div>"

st.markdown(f"""
<div class="ea-card">
    <h3 style="margin:0; color:#d4af37;">🤖 EA Commander Sync (The Defender)</h3>
    {ea_status_html}
</div>
""", unsafe_allow_html=True)

if siren_html: st.components.v1.html(siren_html, width=0, height=0)

col_allin, col_normal = st.columns(2)

with col_allin:
    st.markdown("<h2 class='title-header' style='color: #ffcc00;'>🎯 10-Strike All-In Protocol</h2>", unsafe_allow_html=True)
    time_html_allin = ""
    if "ALL-IN" in sig_allin: 
        log_new_trade("All-In Setup", sig_allin, setup_allin, reason_allin, df_m15)
        time_html_allin = get_setup_time_html("All-In Setup", sig_allin, "#ffcc00")
            
    st.markdown(f"""
    <div class="allin-card">
        <h3 style="margin:0; color:#ffcc00;">{light} All-In Commander</h3>
        <div style="color:{'#888' if 'CLOSED' in sig_allin else ('#ffcc00' if 'WAIT' in sig_allin else '#00ff00')}; font-size:24px; font-weight:bold; margin-top:10px;">{sig_allin}</div>
        <div style="font-size:14px; margin-top:10px; color:#fff;"><b>Logic:</b> {reason_allin}</div>
        {time_html_allin}
    """, unsafe_allow_html=True)
    if setup_allin:
        st.markdown(f"""
        <div style="background-color:#111; padding:15px; border-radius:8px; border: 1px solid #444; margin-top: 15px;">
            <div style="color:#ffcc00; font-weight:bold; margin-bottom:5px;">🎯 1:2 Geometry Setup:</div>
            <div>📍 <b>Entry:</b> {setup_allin['Entry']}</div>
            <div style="color:#ff4444;">🛑 <b>SL:</b> {setup_allin['SL']}</div>
            <div style="color:#00ff00;">💰 <b>TP:</b> {setup_allin['TP']}</div>
        </div>
        """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    
    if setup_allin and not is_market_closed and df_m15 is not None: st.plotly_chart(plot_setup_chart(df_m15, setup_allin, mode="All-In"), use_container_width=True)
    else: st.markdown("<div style='background-color:#1a1a2e; padding:40px; text-align:center; border-radius:10px; border: 1px dashed #ff3333; height: 350px; display: flex; align-items: center; justify-content: center;'>📡 ตลาดปิดทำการ หรือ EA ออฟไลน์...</div>" if "CLOSED" in sig_allin else "<div style='background-color:#1a1a2e; padding:40px; text-align:center; border-radius:10px; border: 1px dashed #ff3333; height: 350px; display: flex; align-items: center; justify-content: center;'>📡 กำลังรอพายุสภาพคล่อง และการเกิด CHoCH...</div>", unsafe_allow_html=True)

with col_normal:
    st.markdown("<h2 class='title-header' style='color: #00ccff;'>🃏 Normal Trade Mode</h2>", unsafe_allow_html=True)
    time_html_norm = ""
    if "WAIT" not in sig_norm and "CLOSED" not in sig_norm and setup_norm: 
        log_new_trade("Normal Setup", sig_norm, setup_norm, reason_norm, df_m15)
        time_html_norm = get_setup_time_html("Normal Setup", sig_norm, "#00ccff")
            
    st.markdown(f"""
    <div class="plan-card">
        <h3 style="margin:0; color:#00ccff;">🃏 Daily Institutional Setup</h3>
        <div style="color:{'#888' if 'CLOSED' in sig_norm else ('#ff00ff' if is_flash_crash else ('#ffcc00' if 'WAIT' in sig_norm else '#00ff00'))}; font-size:24px; font-weight:bold; margin-top:10px;">{sig_norm}</div>
        <div style="font-size:14px; margin-top:10px; color:#fff;"><b>Logic:</b> {reason_norm}</div>
        {time_html_norm}
    """, unsafe_allow_html=True)
    if setup_norm:
        st.markdown(f"""
        <div style="background-color:#111; padding:15px; border-radius:8px; border: 1px solid #444; margin-top: 15px;">
            <div style="color:#00ccff; font-weight:bold; margin-bottom:5px;">🎯 Dynamic Zones:</div>
            <div>📍 <b>Entry:</b> {setup_norm['Entry']}</div>
            <div style="color:#ff4444;">🛑 <b>SL:</b> {setup_norm['SL']}</div>
            <div style="color:#00ff00;">💰 <b>TP:</b> {setup_norm['TP']}</div>
        </div>
        """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    if setup_norm and not is_market_closed and df_m15 is not None: st.plotly_chart(plot_setup_chart(df_m15, setup_norm, mode="Normal"), use_container_width=True)
    else: st.markdown("<div style='background-color:#1a1a2e; padding:40px; text-align:center; border-radius:10px; border: 1px dashed #00ccff; height: 350px; display: flex; align-items: center; justify-content: center;'>📡 ตลาดปิดทำการ หรือ EA ออฟไลน์...</div>" if "CLOSED" in sig_norm else "<div style='background-color:#1a1a2e; padding:40px; text-align:center; border-radius:10px; border: 1px dashed #00ccff; height: 350px; display: flex; align-items: center; justify-content: center;'>📡 กำลังสแกนหา Setup ปกติ...</div>", unsafe_allow_html=True)

st.write("---")

def get_tv_html(symbol, height):
    return f"""
    <div class="tradingview-widget-container">
      <div id="tv_{symbol.replace(':','_')}"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({{
        "width": "100%", "height": {height}, "symbol": "{symbol}", "interval": "15",
        "theme": "dark", "style": "1", "container_id": "tv_{symbol.replace(':','_')}"
      }});
      </script>
    </div>
    """

def display_intelligence():
    st.subheader("📰 Global Intelligence Hub")
    tab_eco, tab_pol, tab_war, tab_speed = st.tabs(["📅 ข่าวเศรษฐกิจ (Merged Data)", "🏛️ การเมือง & Fed", "⚔️ สงคราม", "⚡ ข่าวด่วน (Breaking News)"])
    
    with tab_eco:
        if final_news_list:
            for ev in final_news_list:
                border_color = "#ff3333" if ev['impact'] == 'High' else "#ff9933"
                source_icon = "⚡ MT5" if ev.get('source') == 'MT5' else "🌐 FF"
                ai_text = f"<br><span style='color:#00ccff; font-size:13px;'><b>🤖 AI Analysis:</b> {ev.get('direction', '')}</span>" if ev.get('direction') else ""
                st.markdown(f"""
                <div class='ff-card' style='border-left-color: {border_color};'>
                    <div style='font-size:11px; color:#aaa; margin-bottom:3px;'>{source_icon} | {ev['time']}</div>
                    <div style='font-size:15px;'><b>{ev['title']}</b></div>
                    <div style='font-size:13px; color:#aaa;'>Forecast: {ev['forecast']} | <span style='color:#ffcc00;'>Actual: {ev['actual']}</span></div>
                    {ai_text}
                </div>
                """, unsafe_allow_html=True)
        else: st.write("ไม่มีข่าวเศรษฐกิจสำคัญในช่วงนี้")
            
    with tab_pol:
        for news in pol_news: 
            st.markdown(f"<div class='news-card'><a href='{news['link']}' target='_blank' style='color:#fff;'>🇺🇸 {news['title_th']}</a><br><span style='font-size:11px; color:#888;'>🕒 {news['time']}</span><br><span style='font-size: 12px; color: #aaa;'><b>AI:</b> {news['direction']} | SMIS Impact: {news['score']:.1f}/10</span></div>", unsafe_allow_html=True)
    with tab_war:
        for news in war_news: 
            st.markdown(f"<div class='news-card' style='border-color:#ff3333;'><a href='{news['link']}' target='_blank' style='color:#fff;'>⚠️ {news['title_th']}</a><br><span style='font-size:11px; color:#888;'>🕒 {news['time']}</span><br><span style='font-size: 12px; color: #aaa;'><b>AI:</b> {news['direction']} | SMIS Impact: {news['score']:.1f}/10</span></div>", unsafe_allow_html=True)
    with tab_speed:
        if speed_news:
            for news in speed_news:
                st.markdown(f"<div class='news-card' style='border-color:#00ccff;'><a href='{news['link']}' target='_blank' style='color:#fff;'>🔥 [{news['source']}] {news['title_th']}</a><br><span style='font-size:11px; color:#888;'>🕒 {news['time']}</span><br><span style='font-size: 12px; color: #aaa;'><b>AI:</b> {news['direction']} | SMIS Impact: {news['score']:.1f}/10</span></div>", unsafe_allow_html=True)
        else:
            st.write("กำลังสแกนหาข่าวด่วน...")

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
