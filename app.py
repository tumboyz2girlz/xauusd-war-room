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

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Kwaktong War Room v11.8", page_icon="🦅", layout="wide", initial_sidebar_state="expanded")
st_autorefresh(interval=60000, limit=None, key="warroom_refresher")

if 'manual_overrides' not in st.session_state: st.session_state.manual_overrides = {}
if 'last_logged_setup' not in st.session_state: st.session_state.last_logged_setup = ""
if 'pending_trades' not in st.session_state: st.session_state.pending_trades = []

FIREBASE_URL = "https://kwaktong-warroom-default-rtdb.asia-southeast1.firebasedatabase.app/market_data.json"
GOOGLE_SHEET_API_URL = "https://script.google.com/macros/s/AKfycby1vkYO6JiJfPc6sqiCUEJerfzLCv5LxhU7j16S9FYRpPqxXIUiZY8Ifb0YKiCQ7aj3_g/exec"

st.markdown("""
<style>
    div[data-testid="stMetric"] {
        background-color: #1a1a2e; 
        border: 1px solid #00ccff; 
        padding: 15px !important; 
        border-radius: 8px; 
        box-shadow: 0 0 10px rgba(0,204,255,0.2);
        text-align: left; 
        height: 120px !important;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    div[data-testid="stMetricValue"] {color: #00ccff; font-size: 24px; font-weight: bold; margin-top: 5px;}
    .plan-card {background-color: #1a1a2e; padding: 20px; border-radius: 10px; border: 2px solid #00ccff; margin-bottom: 10px;}
    .allin-card {background-color: #2b0000; padding: 20px; border-radius: 10px; border: 2px solid #ffcc00; margin-bottom: 10px;}
    .ea-card {background-color: #111; padding: 20px; border-radius: 10px; border: 2px dashed #ffcc00; margin-bottom: 25px; text-align: center;}
    .exec-summary {background-color: #131722; padding: 15px; border-radius: 8px; border-left: 5px solid #d4af37; margin-bottom: 15px;}
    .ff-card {background-color: #222831; padding: 12px; border-radius: 8px; margin-bottom: 10px; border-left: 5px solid #555;}
    .news-card {background-color: #131722; padding: 12px; border-radius: 8px; border-left: 4px solid #f0b90b; margin-bottom: 12px;}
    h2.title-header {text-align: center; margin-bottom: 20px; font-weight: bold;}
    .stTabs [data-baseweb="tab"] {background-color: #1a1a2e; border-radius: 5px 5px 0 0;}
    .stTabs [aria-selected="true"] {background-color: #d4af37 !important; color: #000 !important; font-weight: bold;}
</style>
""", unsafe_allow_html=True)

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
                curr_gold, prev_gold = float(df_xau['close'].iloc[-1]), float(df_xau['close'].iloc[-2])
                metrics['GOLD'] = (curr_gold, ((curr_gold - prev_gold) / prev_gold) * 100)
                df_m15 = df_xau
            if 'XAUUSD_H1' in data:
                df_h1 = pd.DataFrame(data['XAUUSD_H1'])
                df_h1.rename(columns={'o':'open', 'h':'high', 'l':'low', 'c':'close', 't':'time'}, inplace=True)
                df_h4 = df_h1
            if 'DXY' in data:
                df_dxy = pd.DataFrame(data['DXY'])
                curr_dxy, prev_dxy = float(df_dxy['c'].iloc[-1]), float(df_dxy['c'].iloc[-2])
                metrics['DXY'] = (curr_dxy, ((curr_dxy - prev_dxy) / prev_dxy) * 100)
            if 'NEWS' in data:
                now_thai = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
                for ev in data['NEWS']:
                    event_dt = datetime.datetime.fromtimestamp(ev['time_sec']) 
                    time_diff_hours = (event_dt - now_thai).total_seconds() / 3600
                    mt5_news.append({'source': 'MT5', 'title': ev['title'], 'time': event_dt.strftime("%H:%M"), 'impact': ev['impact'], 'actual': st.session_state.manual_overrides.get(ev['title'], ev['actual']), 'forecast': ev['forecast'], 'direction': ev.get('direction', ''), 'dt': event_dt, 'time_diff_hours': time_diff_hours})
    except: pass

    if df_m15 is None:
        h_m15 = yf.Ticker("XAUUSD=X").history(period="5d", interval="15m")
        df_m15 = h_m15.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close'}) if not h_m15.empty else None
    if df_h4 is None:
        h_h1 = yf.Ticker("XAUUSD=X").history(period="1mo", interval="1h")
        df_h4 = h_h1.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close'}) if not h_h1.empty else None
    try:
        h_gcf = yf.Ticker("GC=F").history(period="5d", interval="15m")
        if not h_gcf.empty and len(h_gcf) >= 2: metrics['GC_F'] = (h_gcf['Close'].iloc[-1], ((h_gcf['Close'].iloc[-1]-h_gcf['Close'].iloc[-2])/h_gcf['Close'].iloc[-2])*100)
    except: pass
    try:
        h_tnx = yf.Ticker("^TNX").history(period="5d", interval="15m")
        if not h_tnx.empty and len(h_tnx) >= 2: metrics['US10Y'] = (h_tnx['Close'].iloc[-1], ((h_tnx['Close'].iloc[-1]-h_tnx['Close'].iloc[-2])/h_tnx['Close'].iloc[-2])*100)
    except: pass
    
    return metrics, df_m15, df_h4, mt5_news

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
                ff_news.append({'source': 'FF', 'title': title, 'time': thai_dt.strftime("%H:%M"), 'impact': impact, 'actual': st.session_state.manual_overrides.get(title, event.find('actual').text if event.find('actual') is not None else "Pending"), 'forecast': event.find('forecast').text if event.find('forecast') is not None else "", 'direction': '', 'dt': thai_dt, 'time_diff_hours': time_diff_hours})
        return ff_news
    except: return []

def merge_news_sources(mt5_list, ff_list):
    merged = mt5_list + [f for f in ff_list if not any(abs((f['dt']-m['dt']).total_seconds())<=3600 for m in mt5_list)]
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
                date_str = datetime.datetime.fromtimestamp(pub_time).strftime('%d %b %Y | %H:%M น.')
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

                news_list.append({'title_en': entry.title, 'title_th': translator.translate(entry.title), 'link': entry.link, 'time': date_str, 'score': final_score, 'direction': direction})
        except: pass
        return news_list
    return fetch_rss("(Fed OR Powell OR Treasury)"), fetch_rss("(War OR Missile OR Israel OR Russia)")

# --- 4. CORE AI (NORMAL MODE + 5 PILLARS INTEGRATED) ---
def calculate_normal_setup(df_m15, df_h4, final_news_list, sentiment, metrics):
    if df_m15 is None or df_h4 is None: return "WAIT", "No Data", {}, False
    
    df_h4['ema50'] = ta.ema(df_h4['close'], length=50)
    df_m15['ema50'] = ta.ema(df_m15['close'], length=50)
    df_m15['atr'] = ta.atr(df_m15['high'], df_m15['low'], df_m15['close'], length=14)
    df_m15['rsi'] = ta.rsi(df_m15['close'], length=14)
    macd = ta.macd(df_m15['close'], fast=12, slow=26, signal=9)
    df_m15 = pd.concat([df_m15, macd], axis=1)

    trend_h4 = "UP" if df_h4.iloc[-2]['close'] > df_h4.iloc[-2]['ema50'] else "DOWN"
    trend_m15 = "UP" if df_m15.iloc[-2]['close'] > df_m15.iloc[-2]['ema50'] else "DOWN"
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

# --- 5. AI 10-STRIKE ALL-IN PROTOCOL ---
def detect_choch_and_sweep(df):
    recent = df.tail(20).reset_index(drop=True)
    if len(recent) < 20: return False, "", 0, 0
    lowest_low = recent['low'].iloc[0:15].min()
    highest_high = recent['high'].iloc[0:15].max()
    current_close = recent['close'].iloc[-1]
    
    if recent['low'].iloc[-5:-1].min() < lowest_low and current_close > recent['high'].iloc[-5:-1].max(): return True, "LONG", recent['low'].iloc[-5:-1].min(), current_close
    if recent['high'].iloc[-5:-1].max() > highest_high and current_close < recent['low'].iloc[-5:-1].min(): return True, "SHORT", recent['high'].iloc[-5:-1].max(), current_close
    return False, "", 0, 0

def calculate_all_in_setup(df_m15, next_red_news, metrics, sentiment):
    if df_m15 is None: return "WAIT", "No Data", {}, "🔴"
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
        # 🟢 ส่งข้อมูล Sweep Price ออกไปด้วย เพื่อใช้วาดกราฟ 🟢
        return "ALL-IN LONG 🚀", f"Confluence 100%! ตั้ง Buy Limit ดักรอย่อ", {'Entry': f"${entry:.2f}", 'SL': f"${sl:.2f}", 'TP': f"${entry + ((entry - sl) * 2):.2f}", 'Sweep': f"${sweep_price:.2f}"}, "🟢"
        
    elif direction == "SHORT":
        if dxy_trend < 0: return "WAIT", "DXY ยังอ่อนค่า (ขัดแย้ง)", {}, "🟢"
        if gcf_trend > 0: return "WAIT", "GC=F Premium ไม่หนุนขาลง", {}, "🟢"
        if sentiment['long'] < 75.0: return "WAIT", f"รายย่อยยัง Buy ไม่พอ ({sentiment['long']}%)", {}, "🟢"
        entry = current_price + 1.0 
        sl = min(sweep_price + 0.5, entry + 3.0) 
        # 🟢 ส่งข้อมูล Sweep Price ออกไปด้วย เพื่อใช้วาดกราฟ 🟢
        return "ALL-IN SHORT 🚀", f"Confluence 100%! ตั้ง Sell Limit ดักรอเด้ง", {'Entry': f"${entry:.2f}", 'SL': f"${sl:.2f}", 'TP': f"${entry - ((sl - entry) * 2):.2f}", 'Sweep': f"${sweep_price:.2f}"}, "🟢"

    return "WAIT", "รอ...", {}, light

# --- 6. AUTO-LOGGER ---
def log_new_trade(setup_type, sig, setup_data, reason_text):
    if "ใส่_URL" in GOOGLE_SHEET_API_URL: return
    try:
        trade_id = f"TRD-{int(time.time())}"
        now_str = (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")
        clean_reason = re.sub('<[^<]+>', '', reason_text).strip()
        payload = {"action": "log", "id": trade_id, "timestamp": now_str, "setup_type": setup_type, "signal": sig, "entry": setup_data.get('Entry', ''), "sl": setup_data.get('SL', ''), "tp": setup_data.get('TP', ''), "reason": clean_reason}
        requests.post(GOOGLE_SHEET_API_URL, json=payload, timeout=3)
        st.session_state.pending_trades.append(payload)
    except: pass

def check_pending_trades(current_high, current_low):
    if "ใส่_URL" in GOOGLE_SHEET_API_URL: return
    trades_to_remove = []
    for trade in st.session_state.pending_trades:
        try:
            sl_price, tp_price = float(re.sub(r'[^\d.]', '', trade['sl'])), float(re.sub(r'[^\d.]', '', trade['tp']))
            result = None
            if "LONG" in trade['signal']: result = "LOSS ❌" if current_low <= sl_price else ("WIN 🎯" if current_high >= tp_price else None)
            elif "SHORT" in trade['signal']: result = "LOSS ❌" if current_high >= sl_price else ("WIN 🎯" if current_low <= tp_price else None)
            if result:
                requests.post(GOOGLE_SHEET_API_URL, json={"action": "update", "id": trade['id'], "result": result}, timeout=3)
                trades_to_remove.append(trade)
        except: continue
    for t in trades_to_remove: st.session_state.pending_trades.remove(t)

# --- 7. EXECUTIVE SUMMARY ---
def generate_exec_summary(df_h4, metrics, next_red_news, sentiment):
    if df_h4 is None: return "กำลังรวบรวมข้อมูล..."
    trend = "ขาขึ้น 🟢" if df_h4.iloc[-2]['close'] > ta.ema(df_h4['close'], length=50).iloc[-2] else "ขาลง 🔴"
    dxy_status = "อ่อนค่า (หนุนทอง)" if metrics['DXY'][1] < 0 else "แข็งค่า (กดดันทอง)"
    summary = f"**📊 Overall Market Bias:** ขณะนี้ทองคำอยู่ในโครงสร้างเทรนด์ **{trend}** (H4) "
    summary += f"ดอลลาร์ (DXY) กำลัง **{dxy_status}** และรายย่อยเทน้ำหนักไปฝั่ง **{'Short' if sentiment['short'] > 50 else 'Long'}** "
    if next_red_news: summary += f"<br>⚠️ **News Alert:** ระวังความผันผวนจากข่าว **{next_red_news['title']}** ในอีก {next_red_news['hours']:.1f} ชั่วโมง"
    else: summary += "<br>✅ **News Alert:** ไม่มีข่าวกล่องแดงกวนใจ สามารถรันเทรนด์ Grid ได้ตามปกติ"
    return summary

# --- 8. SMART VISUALIZER (วาด SMC Label) 🟢 ---
def plot_setup_chart(df, setup_dict, mode="Normal"):
    if df is None or df.empty or not setup_dict: return None
    df_plot = df.tail(100).copy()
    df_plot['datetime'] = pd.to_datetime(df_plot['time'], unit='s')
    fig = go.Figure(data=[go.Candlestick(x=df_plot['datetime'], open=df_plot['open'], high=df_plot['high'], low=df_plot['low'], close=df_plot['close'], increasing_line_color='#00ff00', decreasing_line_color='#ff3333')])
    
    def get_prices(t): return [float(x) for x in re.findall(r'\d+\.\d+', str(t).replace(',', ''))]
    
    sl = get_prices(setup_dict.get('SL', ''))
    tp = get_prices(setup_dict.get('TP', ''))
    entry = get_prices(setup_dict.get('Entry', ''))
    sweep = get_prices(setup_dict.get('Sweep', '')) # ดึงค่า Sweep/CHoCH
    
    # 🟢 อ่านเงื่อนไขเพื่อตั้งชื่อป้ายกำกับให้ฉลาดขึ้น 🟢
    entry_text = str(setup_dict.get('Entry', ''))
    label_text = "🎯 Entry"
    if "FVG" in entry_text: label_text = "🎯 FVG Zone"
    elif "EMA" in entry_text: label_text = "🎯 EMA Base"
    
    line_color = "#ffcc00" if mode == "All-In" else "#00ccff"
    
    if sl: fig.add_hline(y=sl[0], line_dash="dash", line_color="#ff4444", annotation_text="🛑 SL", annotation_position="bottom right", annotation_font_color="#ff4444")
    if tp: fig.add_hline(y=tp[0], line_dash="dash", line_color="#00ff00", annotation_text="💰 TP", annotation_position="top right", annotation_font_color="#00ff00")
    
    # 🟢 วาดเส้นบอก CHoCH / Liquidity Sweep (ถ้ามี) 🟢
    if sweep: fig.add_hline(y=sweep[0], line_dash="dot", line_color="#ff00ff", annotation_text="⚡ CHoCH / Sweep", annotation_position="left", annotation_font_color="#ff00ff")
    
    # 🟢 วาดกล่อง FVG หรือเส้น EMA พร้อมป้ายกำกับที่ฉลาดขึ้น 🟢
    if entry:
        if len(entry) >= 2: fig.add_hrect(y0=min(entry), y1=max(entry), fillcolor=f"rgba({'255, 204, 0' if mode=='All-In' else '0, 204, 255'}, 0.2)", line_width=1, annotation_text=label_text, annotation_position="top right")
        else: fig.add_hline(y=entry[0], line_dash="dash", line_color=line_color, annotation_text=label_text, annotation_position="top right", annotation_font_color=line_color)
        
    fig.update_layout(template='plotly_dark', margin=dict(l=10, r=50, t=10, b=10), height=350, xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    return fig

# --- UI MAIN ---
metrics, df_m15, df_h4, mt5_news = get_market_data()
ff_raw_news = get_forexfactory_usd()
final_news_list, next_red_news = merge_news_sources(mt5_news, ff_raw_news)
sentiment = get_retail_sentiment()
pol_news, war_news = get_categorized_news() 

if df_m15 is not None: check_pending_trades(float(df_m15.iloc[-1]['high']), float(df_m15.iloc[-1]['low']))

sig_norm, reason_norm, setup_norm, is_flash_crash = calculate_normal_setup(df_m15, df_h4, final_news_list, sentiment, metrics)
sig_allin, reason_allin, setup_allin, light = calculate_all_in_setup(df_m15, next_red_news, metrics, sentiment)

with st.sidebar:
    st.header("💻 War Room Terminal")
    layout_mode = st.radio("Display:", ["🖥️ Desktop", "📱 Mobile"])
    if st.button("Refresh Data", type="primary"): st.cache_data.clear()
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

st.title("🦅 XAUUSD WAR ROOM: Institutional Master Node v11.8")

c1, c2, c3, c4, c5, c6 = st.columns((1,1,1,1,1,1))
with c1: st.metric("XAUUSD", f"${metrics['GOLD'][0]:,.2f}", f"{metrics['GOLD'][1]:.2f}%")
with c2: st.metric("GC=F", f"${metrics['GC_F'][0]:,.2f}", f"{metrics['GC_F'][1]:.2f}%")
with c3: st.metric("DXY", f"{metrics['DXY'][0]:,.2f}", f"{metrics['DXY'][1]:.2f}%", delta_color="inverse")
with c4: st.metric("US10Y", f"{metrics['US10Y'][0]:,.2f}", f"{metrics['US10Y'][1]:.2f}%", delta_color="inverse")
with c5: st.metric("SPDR Flow", get_spdr_flow())
with c6: st.metric("Retail Senti.", f"S:{sentiment['short']}%", f"L:{sentiment['long']}%", delta_color="off")

st.markdown(f"<div class='exec-summary'>{generate_exec_summary(df_h4, metrics, next_red_news, sentiment)}</div>", unsafe_allow_html=True)

ea_status_html = ""
if is_flash_crash: ea_status_html = "<div style='color:#ff3333; font-size:18px; font-weight:bold; margin-top:10px;'>🚨 EMERGENCY: ปิดการทำงาน Grid ทันที! เข้าโหมด Anti-Dump / Hard Cut</div>"
elif "WAIT" in sig_norm or "PENDING" in sig_norm: ea_status_html = "<div style='color:#ffcc00; font-size:18px; font-weight:bold; margin-top:10px;'>⚠️ EA STANDBY: เข้าสู่โหมด Gold Down Pause หรือรอเข้าเทรดแบบ Limit</div>"
else: ea_status_html = "<div style='color:#00ff00; font-size:18px; font-weight:bold; margin-top:10px;'>▶️ EA RUNNING: กางระบบ Grid Buy/Sell ได้ตามปกติ</div>"

st.markdown(f"""
<div class="ea-card">
    <h3 style="margin:0; color:#d4af37;">🤖 EA Commander Sync (The Defender)</h3>
    {ea_status_html}
</div>
""", unsafe_allow_html=True)

col_allin, col_normal = st.columns(2)

with col_allin:
    st.markdown("<h2 class='title-header' style='color: #ffcc00;'>🎯 10-Strike All-In Protocol</h2>", unsafe_allow_html=True)
    if "ALL-IN" in sig_allin:
        curr_sig = f"ALLIN_{setup_allin.get('Entry','')}"
        if curr_sig != st.session_state.last_logged_setup:
            log_new_trade("All-In Setup", sig_allin, setup_allin, reason_allin)
            st.session_state.last_logged_setup = curr_sig
            
    st.markdown(f"""
    <div class="allin-card">
        <h3 style="margin:0; color:#ffcc00;">{light} All-In Commander</h3>
        <div style="color:{'#ffcc00' if 'WAIT' in sig_allin else '#00ff00'}; font-size:24px; font-weight:bold; margin-top:10px;">{sig_allin}</div>
        <div style="font-size:14px; margin-top:10px; color:#fff;"><b>Logic:</b> {reason_allin}</div>
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
    
    if setup_allin and df_m15 is not None: st.plotly_chart(plot_setup_chart(df_m15, setup_allin, mode="All-In"), use_container_width=True)
    else: st.markdown("<div style='background-color:#1a1a2e; padding:40px; text-align:center; border-radius:10px; border: 1px dashed #ff3333; height: 350px; display: flex; align-items: center; justify-content: center;'>📡 กำลังรอพายุสภาพคล่อง และการเกิด CHoCH...</div>", unsafe_allow_html=True)

with col_normal:
    st.markdown("<h2 class='title-header' style='color: #00ccff;'>🃏 Normal Trade Mode</h2>", unsafe_allow_html=True)
    if "WAIT" not in sig_norm and setup_norm:
        curr_sig = f"NORM_{setup_norm.get('Entry','')}"
        if curr_sig != st.session_state.last_logged_setup:
            log_new_trade("Normal Setup", sig_norm, setup_norm, reason_norm)
            st.session_state.last_logged_setup = curr_sig
            
    st.markdown(f"""
    <div class="plan-card">
        <h3 style="margin:0; color:#00ccff;">🃏 Daily Institutional Setup</h3>
        <div style="color:{'#ff00ff' if is_flash_crash else ('#ffcc00' if 'WAIT' in sig_norm else '#00ff00')}; font-size:24px; font-weight:bold; margin-top:10px;">{sig_norm}</div>
        <div style="font-size:14px; margin-top:10px; color:#fff;"><b>Logic:</b> {reason_norm}</div>
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

    if setup_norm and df_m15 is not None: st.plotly_chart(plot_setup_chart(df_m15, setup_norm, mode="Normal"), use_container_width=True)
    else: st.markdown("<div style='background-color:#1a1a2e; padding:40px; text-align:center; border-radius:10px; border: 1px dashed #00ccff; height: 350px; display: flex; align-items: center; justify-content: center;'>📡 กำลังสแกนหา Setup ปกติ...</div>", unsafe_allow_html=True)

st.write("---")

def display_intelligence():
    st.subheader("📰 Global Intelligence Hub")
    tab_eco, tab_pol, tab_war = st.tabs(["📅 ข่าวเศรษฐกิจ (Merged Data)", "🏛️ การเมือง & Fed", "⚔️ สงคราม"])
    
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

tv_gold = f"""<div class="tradingview-widget-container"><div id="tv_gold"></div><script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script><script type="text/javascript">new TradingView.widget({{"width": "100%", "height": {600 if layout_mode == "🖥️ Desktop" else 400}, "symbol": "OANDA:XAUUSD", "interval": "15", "theme": "dark", "style": "1", "container_id": "tv_gold"}});</script></div>"""
tv_dxy = f"""<div class="tradingview-widget-container"><div id="tv_dxy"></div><script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script><script type="text/javascript">new TradingView.widget({{"width": "100%", "height": {600 if layout_mode == "🖥️ Desktop" else 400}, "symbol": "CAPITALCOM:DXY", "interval": "15", "theme": "dark", "style": "1", "container_id": "tv_dxy"}});</script></div>"""

if layout_mode == "🖥️ Desktop":
    col_chart_bot, col_news_bot = st.columns([1.8, 1])
    with col_chart_bot:
        tab_chart_gold, tab_chart_dxy = st.tabs(["🥇 XAUUSD", "💵 DXY"])
        with tab_chart_gold: st.components.v1.html(tv_gold, height=600)
        with tab_chart_dxy: st.components.v1.html(tv_dxy, height=600)
    with col_news_bot: display_intelligence()
else:
    tab_chart_gold, tab_chart_dxy = st.tabs(["🥇 XAUUSD", "💵 DXY"])
    with tab_chart_gold: st.components.v1.html(tv_gold, height=400)
    with tab_chart_dxy: st.components.v1.html(tv_dxy, height=400)
    display_intelligence()
