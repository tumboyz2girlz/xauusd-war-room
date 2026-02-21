import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import feedparser
import requests
from textblob import TextBlob
from deep_translator import GoogleTranslator
import xml.etree.ElementTree as ET
import datetime
import time
from time import mktime
from streamlit_autorefresh import st_autorefresh
import re

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Kwaktong War Room v10.4", page_icon="🦅", layout="wide", initial_sidebar_state="expanded")
st_autorefresh(interval=60000, limit=None, key="warroom_refresher")

if 'manual_overrides' not in st.session_state:
    st.session_state.manual_overrides = {}
if 'last_logged_setup' not in st.session_state:
    st.session_state.last_logged_setup = ""
if 'pending_trades' not in st.session_state:
    st.session_state.pending_trades = []

FIREBASE_URL = "https://kwaktong-warroom-default-rtdb.asia-southeast1.firebasedatabase.app/market_data.json"
GOOGLE_SHEET_API_URL = "YOUR_GOOGLE_SHEET_URL_HERE"

st.markdown("""
<style>
    div[data-testid="stMetric"] {background-color: #1a1a2e; border: 1px solid #00ccff; padding: 10px; border-radius: 8px; box-shadow: 0 0 10px rgba(0,204,255,0.2);}
    div[data-testid="stMetricValue"] {color: #00ccff; font-size: 22px; font-weight: bold;}
    .plan-card {background-color: #1a1a2e; padding: 20px; border-radius: 10px; border: 2px solid #d4af37; margin-bottom: 20px; height: 100%;}
    .ea-card {background-color: #1a1a2e; padding: 20px; border-radius: 10px; border: 2px solid #555; height: 100%;}
    .alert-card {background-color: #330000; padding: 15px; border-radius: 8px; border-left: 5px solid #ff0000; margin-bottom: 20px;}
    .session-badge {display: inline-block; padding: 5px 10px; border-radius: 5px; font-weight: bold; margin-bottom: 15px;}
    .ff-card {background-color: #222831; padding: 12px; border-radius: 8px; margin-bottom: 10px; border-left: 5px solid #555;}
    .news-card {background-color: #131722; padding: 12px; border-radius: 8px; border-left: 4px solid #f0b90b; margin-bottom: 12px;}
    .score-high {color: #ff3333; font-weight: bold;}
    .score-med {color: #ffcc00; font-weight: bold;}
    .stTabs [data-baseweb="tab"] {background-color: #1a1a2e; border-radius: 5px 5px 0 0;}
    .stTabs [aria-selected="true"] {background-color: #d4af37 !important; color: #000 !important; font-weight: bold;}
</style>
""", unsafe_allow_html=True)

# --- 2. DATA ENGINE (Prices + MT5 News) ---
@st.cache_data(ttl=30)
def get_market_data():
    metrics = {'GOLD': (0.0, 0.0), 'GC_F': (0.0, 0.0), 'DXY': (0.0, 0.0), 'US10Y': (0.0, 0.0)}
    df_m15, df_h4 = None, None
    mt5_news = []
    data_source = "Yahoo Finance (Fallback Mode)"
    
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
                data_source = "MT5 Direct Connection ⚡"
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
                    impact = ev['impact']
                    title = ev['title']
                    actual_val = st.session_state.manual_overrides.get(title, ev['actual'])

                    mt5_news.append({
                        'source': 'MT5', 'title': title,
                        'time': event_dt.strftime("%d %b - %H:%M น."),
                        'impact': impact, 'actual': actual_val, 'forecast': ev['forecast'],
                        'direction': ev.get('direction', ''), 'dt': event_dt, 'time_diff_hours': time_diff_hours
                    })
    except: pass

    if df_m15 is None:
        try:
            h_m15 = yf.Ticker("XAUUSD=X").history(period="5d", interval="15m")
            if not h_m15.empty: df_m15 = h_m15.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close'})
        except: pass
    if df_h4 is None:
        try:
            h_h1 = yf.Ticker("XAUUSD=X").history(period="1mo", interval="1h")
            if not h_h1.empty: df_h4 = h_h1.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close'})
        except: pass
    try:
        h_gcf = yf.Ticker("GC=F").history(period="5d", interval="15m")
        if not h_gcf.empty and len(h_gcf) >= 2: metrics['GC_F'] = (h_gcf['Close'].iloc[-1], ((h_gcf['Close'].iloc[-1]-h_gcf['Close'].iloc[-2])/h_gcf['Close'].iloc[-2])*100)
    except: pass
    try:
        h_tnx = yf.Ticker("^TNX").history(period="5d", interval="15m")
        if not h_tnx.empty and len(h_tnx) >= 2: metrics['US10Y'] = (h_tnx['Close'].iloc[-1], ((h_tnx['Close'].iloc[-1]-h_tnx['Close'].iloc[-2])/h_tnx['Close'].iloc[-2])*100)
    except: pass
    
    return metrics, df_m15, df_h4, mt5_news, data_source

# --- 3. FOREXFACTORY FETCH ---
@st.cache_data(ttl=900)
def fetch_ff_xml():
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
    try: return requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10).content
    except: return None

def get_forexfactory_usd(manual_overrides):
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
                
                if time_diff_hours < -12.0 or (impact == 'High' and time_diff_hours > 24) or (impact == 'Medium' and time_diff_hours > 4): continue
                
                actual = manual_overrides.get(title, event.find('actual').text if event.find('actual') is not None else "Pending")
                forecast = event.find('forecast').text if event.find('forecast') is not None else ""
                
                ff_news.append({
                    'source': 'FF', 'title': title, 'time': thai_dt.strftime("%d %b - %H:%M น."),
                    'impact': impact, 'actual': actual, 'forecast': forecast,
                    'direction': '', 'dt': thai_dt, 'time_diff_hours': time_diff_hours
                })
        return ff_news
    except: return []

# --- 4. DATA AGGREGATION ---
def extract_keywords(title):
    words = set(re.findall(r'\b[a-z]{3,}\b', title.lower()))
    stopwords = {'the', 'and', 'for', 'core', 'rate', 'index', 'sales', 'month', 'year', 'flash', 'final'}
    return words - stopwords

def merge_news_sources(mt5_list, ff_list):
    merged = []
    mt5_matched_indices = set()

    for ff in ff_list:
        is_matched = False
        ff_kw = extract_keywords(ff['title'])
        for i, mt5 in enumerate(mt5_list):
            if i in mt5_matched_indices: continue
            time_diff_sec = abs((ff['dt'] - mt5['dt']).total_seconds())
            if time_diff_sec <= 3600 and ff['impact'] == mt5['impact']:
                mt5_kw = extract_keywords(mt5['title'])
                if len(ff_kw.intersection(mt5_kw)) > 0:
                    is_matched = True
                    if mt5 not in merged: merged.append(mt5)
                    mt5_matched_indices.add(i)
                    break
        if not is_matched: merged.append(ff)

    for i, mt5 in enumerate(mt5_list):
        if i not in mt5_matched_indices and mt5 not in merged:
            merged.append(mt5)

    merged.sort(key=lambda x: x['dt'])
    max_smis = 0
    next_red_news = None
    for ev in merged:
        smis = 8.0 if ev['impact'] == 'High' else 5.0
        if max_smis < smis: max_smis = smis
        if ev['impact'] == 'High' and 0 < ev['time_diff_hours'] <= 3:
            if next_red_news is None or ev['time_diff_hours'] < next_red_news['hours']:
                next_red_news = {'title': ev['title'], 'hours': ev['time_diff_hours'], 'time': ev['dt'].strftime("%H:%M น.")}
    return merged, max_smis, next_red_news

# --- 5. 🤖 AI HEADLINE ANALYZER ---
@st.cache_data(ttl=900) 
def get_categorized_news():
    translator = GoogleTranslator(source='en', target='th')
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    def fetch_rss(query):
        url = f"https://news.google.com/rss/search?q={query}+when:24h&hl=en-US&gl=US&ceid=US:en"
        news_list = []
        try:
            feed = feedparser.parse(requests.get(url, headers=headers, timeout=5).content)
            for entry in feed.entries[:5]: 
                pub_time = mktime(entry.published_parsed)
                date_str = datetime.datetime.fromtimestamp(pub_time).strftime('%d %b %H:%M')
                title_en = entry.title
                title_lower = title_en.lower()
                
                polarity = TextBlob(title_en).sentiment.polarity
                base_score = abs(polarity) * 5
                if any(kw in title_lower for kw in ['war', 'missile', 'strike', 'emergency', 'attack']): base_score += 4.0
                elif any(kw in title_lower for kw in ['fed', 'inflation', 'rate']): base_score += 2.0
                final_score = min(10.0, max(1.0, base_score))

                direction = "⚪ NEUTRAL"
                if any(w in title_lower for w in ['war', 'missile', 'strike', 'attack', 'escalat', 'tension', 'emergency', 'crisis', 'terror', 'bomb']):
                    direction = "🟢 GOLD UP (Safe Haven / Risk-Off)"
                elif any(w in title_lower for w in ['ceasefire', 'peace', 'truce', 'agreement', 'de-escalat']):
                    direction = "🔴 GOLD DOWN (Peace / Risk-On)"
                elif any(w in title_lower for w in ['rate hike', 'raise rate', 'strong', 'hawkish', 'inflation ris']):
                    direction = "🔴 GOLD DOWN (Hawkish / Strong USD)"
                elif any(w in title_lower for w in ['rate cut', 'cut rate', 'dovish', 'recession', 'weak', 'slowdown', 'pause']):
                    direction = "🟢 GOLD UP (Dovish / Weak Econ)"
                else:
                    if polarity <= -0.2: direction = "🟢 GOLD UP (Negative News/Panic)"
                    elif polarity >= 0.2: direction = "🔴 GOLD DOWN (Positive News/Calm)"

                news_list.append({
                    'title_en': title_en, 'title_th': translator.translate(title_en), 
                    'link': entry.link, 'time': date_str, 'score': final_score, 'direction': direction
                })
        except: pass
        return news_list
        
    return fetch_rss("(Fed OR Powell OR Trump OR Biden OR US Election OR Treasury)"), fetch_rss("(War OR Missile OR Strike OR Iran OR Israel OR Russia OR Ukraine OR Geopolitics)")

def get_trading_session():
    hour_utc = datetime.datetime.utcnow().hour
    if 0 <= hour_utc < 7: return "🇯🇵 Asian Session", "สภาพคล่องต่ำ (Low Volatility) - เน้นเก็บกำไรสั้น", "#334455"
    elif 7 <= hour_utc < 13: return "🇬🇧 London Session", "สภาพคล่องปานกลางถึงสูง - กราฟเริ่มเลือกทาง", "#554433"
    else: return "🇺🇸 New York Session", "สภาพคล่องสูงสุด (High Volatility) - ระวังสวิงแรง / รันเทรนด์ได้", "#224422"

@st.cache_data(ttl=3600)
def get_spdr_flow(): return "Neutral (รอดูท่าที)"

# --- 6. CORE AI ENGINE (SMC + Macro + Momentum Physics 🚀) ---
def calculate_institutional_setup(df_m15, df_h4, dxy_change, next_red_news, max_war_score, final_news_list):
    if df_m15 is None or df_h4 is None or len(df_m15) < 55 or len(df_h4) < 55: 
        return "WAIT", "รอข้อมูลราคาทองคำจากเซิร์ฟเวอร์", {}, "UNKNOWN", False
    
    df_h4['ema50'] = ta.ema(df_h4['close'], length=50)
    trend_h4 = "UP" if df_h4.iloc[-2]['close'] > df_h4.iloc[-2]['ema50'] else "DOWN"

    df_m15['ema50'] = ta.ema(df_m15['close'], length=50)
    df_m15['atr'] = ta.atr(df_m15['high'], df_m15['low'], df_m15['close'], length=14)
    
    # 🌟 เครื่องยนต์คำนวณ Momentum (RSI & MACD) 🌟
    df_m15['rsi'] = ta.rsi(df_m15['close'], length=14)
    macd = ta.macd(df_m15['close'], fast=12, slow=26, signal=9)
    df_m15 = pd.concat([df_m15, macd], axis=1)

    m15_current = df_m15.iloc[-1]
    trend_m15 = "UP" if df_m15.iloc[-2]['close'] > df_m15.iloc[-2]['ema50'] else "DOWN"
    
    atr_val = float(df_m15.iloc[-2]['atr'])
    ema_val = float(df_m15.iloc[-2]['ema50'])
    
    current_rsi = float(m15_current['rsi']) if not pd.isna(m15_current['rsi']) else 50.0
    current_macd_hist = float(m15_current['MACDh_12_26_9']) if 'MACDh_12_26_9' in m15_current and not pd.isna(m15_current['MACDh_12_26_9']) else 0.0

    # 🚨 Anti-Dump Sensor 🚨
    red_body_size = m15_current['open'] - m15_current['close']
    is_flash_crash = True if (red_body_size >= 15.0) and ((m15_current['close'] - m15_current['low']) <= 3.0) else False
    is_war_panic = True if max_war_score >= 8.0 else False

    recent_news_dir = ""
    for ev in final_news_list:
        if ev['source'] == 'MT5' and ev['direction'] and -2.0 <= ev['time_diff_hours'] <= 0:
            if "UP" in ev['direction']: recent_news_dir = "UP"
            elif "DOWN" in ev['direction']: recent_news_dir = "DOWN"
            break

    def get_smc_setup(df, trend_dir):
        df_recent = df.tail(40).reset_index(drop=True)
        atr_smc = df_recent['atr'].iloc[-1]
        if trend_dir == "UP":
            for i in range(len(df_recent)-1, 1, -1):
                if df_recent['low'].iloc[i] > df_recent['high'].iloc[i-2]:
                    return True, f"🧲 รอราคาย่อเข้า Demand FVG โซน ${df_recent['high'].iloc[i-2]:.2f} ถึง ${df_recent['low'].iloc[i]:.2f}", f"${df_recent['low'].iloc[i-2] - (atr_smc * 0.5):.2f}", f"${df_recent['high'].max():.2f}"
        else:
            for i in range(len(df_recent)-1, 1, -1):
                if df_recent['high'].iloc[i] < df_recent['low'].iloc[i-2]:
                    return True, f"🧲 รอราคาเด้งเข้า Supply FVG โซน ${df_recent['high'].iloc[i]:.2f} ถึง ${df_recent['low'].iloc[i-2]:.2f}", f"${df_recent['high'].iloc[i-2] + (atr_smc * 0.5):.2f}", f"${df_recent['low'].min():.2f}"
        return False, "", "", ""

    smc_found, smc_entry, smc_sl, smc_tp = get_smc_setup(df_m15, trend_m15)

    news_warning_msg = ""
    if next_red_news and next_red_news['hours'] <= 2.0:
        news_warning_msg = f"<div style='background-color:#332200; padding:10px; border-left: 4px solid #ffcc00; margin-top:10px; font-size:13px; color:#ffcc00;'>⚠️ <b>NEWS ALERT:</b> อีก <b>{next_red_news['hours']:.1f} ชม.</b> ข่าว <b>{next_red_news['title']}</b> จะออก</div>"

    signal, reason, setup = "WAIT (Fold)", f"H1/H4 Trend ({trend_h4}) ไม่ตรงกับ M15 ({trend_m15}) หรือ DXY ขัดแย้ง", {}

    if is_flash_crash:
        signal = "🚨 FLASH CRASH (SELL NOW!)"
        reason = f"เซ็นเซอร์พบการเทขายแดงเต็มแท่งดิ่งลงมา ${red_body_size:.2f} สั่งแทง SELL ตามน้ำ!"
        setup = {'Entry': f"กด Sell ทันที หรือรอเด้งโซน ${m15_current['close'] + (0.5*atr_val):.2f}", 'SL': f"${m15_current['open'] + (0.5*atr_val):.2f}", 'TP': f"${m15_current['close'] - (3*atr_val):.2f}"}
    
    elif trend_h4 == "UP" and trend_m15 == "UP":
        if recent_news_dir == "DOWN":
            signal, reason, setup = "WAIT (News Conflict ⚠️)", "โครงสร้างขาขึ้น แต่ข่าว MT5 ล่าสุดกดดันให้ทองลง (Conflict) ให้รอดูสถานการณ์", {}
        elif current_rsi > 70.0:  
            signal = "PENDING LONG (รอย่อตัว ⚠️)"
            reason = f"เทรนด์ขาขึ้น แต่ RSI ทะลุ {current_rsi:.1f} (Overbought) ห้ามไล่ราคา! ให้ตั้ง Buy Limit ดักรอที่โซน FVG/EMA ด้านล่าง"
            setup = {'Entry': smc_entry, 'SL': smc_sl, 'TP': smc_tp} if smc_found else {'Entry': f"${ema_val - (0.5*atr_val):.2f} ถึง ${ema_val + (0.5*atr_val):.2f} (EMA Base)", 'SL': f"${ema_val - (2*atr_val):.2f}", 'TP': f"${ema_val + (2*atr_val):.2f}"}
        else:
            signal = "STRONG LONG (War+Macro)" if is_war_panic else "LONG"
            reason = "สงครามหนุน+Macroเป็นใจ" if is_war_panic else "โครงสร้าง 5 Pillars สนับสนุนขาขึ้น"
            if current_macd_hist > 0: reason += " + 🚀 MACD มีแรงส่งขึ้น (Momentum หนุน)"
            else: reason += " + 🐌 แรงส่ง MACD เริ่มอ่อน ระวังการพักตัว"
            if recent_news_dir == "UP": reason += " + ข่าว MT5 หนุนทอง 🟢"
            setup = {'Entry': smc_entry, 'SL': smc_sl, 'TP': smc_tp} if smc_found else {'Entry': f"${ema_val - (0.5*atr_val):.2f} ถึง ${ema_val + (0.5*atr_val):.2f} (EMA Base)", 'SL': f"${ema_val - (2*atr_val):.2f}", 'TP': f"${ema_val + (2*atr_val):.2f}"}
    
    elif trend_h4 == "DOWN" and trend_m15 == "DOWN":
        if is_war_panic: 
            signal, reason, setup = "WAIT", "ห้าม Short สวนกระแสสงครามเด็ดขาด!", {}
        elif recent_news_dir == "UP":
            signal, reason, setup = "WAIT (News Conflict ⚠️)", "โครงสร้างขาลง แต่ข่าว MT5 ล่าสุดหนุนให้ทองขึ้น (Conflict) ให้รอดูสถานการณ์", {}
        elif current_rsi < 30.0: 
            signal = "PENDING SHORT (รอเด้ง ⚠️)"
            reason = f"เทรนด์ขาลง แต่ RSI ตกไปที่ {current_rsi:.1f} (Oversold) ห้ามกด Sell ก้นเหว! ให้ตั้ง Sell Limit ดักรอที่โซน FVG/EMA ด้านบน"
            setup = {'Entry': smc_entry, 'SL': smc_sl, 'TP': smc_tp} if smc_found else {'Entry': f"${ema_val - (0.5*atr_val):.2f} ถึง ${ema_val + (0.5*atr_val):.2f} (EMA Base)", 'SL': f"${ema_val + (2*atr_val):.2f}", 'TP': f"${ema_val - (2*atr_val):.2f}"}
        else:
            signal = "SHORT"
            reason = "โครงสร้าง 5 Pillars สนับสนุนขาลง"
            if current_macd_hist < 0: reason += " + 🚀 MACD มีแรงกดลง (Momentum หนุน)"
            else: reason += " + 🐌 แรงส่ง MACD ขาลงเริ่มพับ ระวังการเด้งสู้"
            if recent_news_dir == "DOWN": reason += " + ข่าว MT5 กดดันทอง 🔴"
            setup = {'Entry': smc_entry, 'SL': smc_sl, 'TP': smc_tp} if smc_found else {'Entry': f"${ema_val - (0.5*atr_val):.2f} ถึง ${ema_val + (0.5*atr_val):.2f} (EMA Base)", 'SL': f"${ema_val + (2*atr_val):.2f}", 'TP': f"${ema_val - (2*atr_val):.2f}"}
    
    reason += news_warning_msg
    return signal, reason, setup, trend_h4, is_flash_crash

# --- 7. AUTO-TRADING JOURNAL & TRACKER ---
def log_new_trade(sig, setup_data, reason_text):
    if "YOUR_GOOGLE_SHEET_URL_HERE" in GOOGLE_SHEET_API_URL: return
    try:
        trade_id = f"TRD-{int(time.time())}"
        now_str = (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")
        clean_reason = re.sub('<[^<]+>', '', reason_text).strip()
        payload = {
            "action": "log", "id": trade_id, "timestamp": now_str,
            "signal": sig, "entry": setup_data.get('Entry', ''),
            "sl": setup_data.get('SL', ''), "tp": setup_data.get('TP', ''),
            "reason": clean_reason
        }
        requests.post(GOOGLE_SHEET_API_URL, json=payload, timeout=3)
        st.session_state.pending_trades.append(payload)
    except: pass

def check_pending_trades(current_high, current_low):
    if "YOUR_GOOGLE_SHEET_URL_HERE" in GOOGLE_SHEET_API_URL: return
    trades_to_remove = []
    for trade in st.session_state.pending_trades:
        try:
            sl_price = float(re.sub(r'[^\d.]', '', trade['sl']))
            tp_price = float(re.sub(r'[^\d.]', '', trade['tp']))
        except: continue
        result = None
        if "LONG" in trade['signal']:
            if current_low <= sl_price: result = "LOSS ❌"
            elif current_high >= tp_price: result = "WIN 🎯"
        elif "SHORT" in trade['signal']:
            if current_high >= sl_price: result = "LOSS ❌"
            elif current_low <= tp_price: result = "WIN 🎯"
        if result:
            try:
                requests.post(GOOGLE_SHEET_API_URL, json={"action": "update", "id": trade['id'], "result": result}, timeout=3)
                trades_to_remove.append(trade)
            except: pass
    for t in trades_to_remove: st.session_state.pending_trades.remove(t)

# --- UI MAIN ---
metrics, df_m15, df_h4, mt5_news, data_source = get_market_data()
ff_raw_news = get_forexfactory_usd(st.session_state.manual_overrides)
final_news_list, max_ff_smis, next_red_news = merge_news_sources(mt5_news, ff_raw_news)
pol_news, war_news = get_categorized_news()
dxy_change = metrics['DXY'][1] if metrics else 0
max_war_score = max([n['score'] for n in war_news]) if war_news else 0.0
timestamp_str = (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime("%d %b %Y | %H:%M:%S น.")

with st.sidebar:
    st.header("💻 War Room Terminal")
    layout_mode = st.radio("Display:", ["🖥️ Desktop", "📱 Mobile"])
    if st.button("Refresh Data", type="primary"): st.cache_data.clear()
    
    st.success(f"📡 **{data_source}**")
    st.markdown("---")

    st.subheader("✍️ Override ข่าวเศรษฐกิจ")
    has_pending = False
    for i, ev in enumerate(final_news_list):
        if "Pending" in ev['actual'] and -12.0 <= ev.get('time_diff_hours', 0) <= 24.0:
            has_pending = True
            source_tag = "⚡" if ev['source'] == 'MT5' else "🌐"
            new_val = st.text_input(f"{source_tag} [{ev['time']}] {ev['title']}", value=st.session_state.manual_overrides.get(ev['title'], ""), key=f"override_{i}")
            if new_val != st.session_state.manual_overrides.get(ev['title'], ""):
                st.session_state.manual_overrides[ev['title']] = new_val
                st.rerun()
                
    if not has_pending: st.write("✅ ข้อมูลอัปเดตสมบูรณ์")

st.title("🦅 XAUUSD WAR ROOM: Institutional Master Node v10.4")

if metrics and 'GOLD' in metrics:
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: st.metric("XAUUSD (Spot)", f"${metrics['GOLD'][0]:,.2f}", f"{metrics['GOLD'][1]:.2f}%")
    with c2: st.metric("GC=F (Futures)", f"${metrics['GC_F'][0]:,.2f}", f"{metrics['GC_F'][1]:.2f}%")
    with c3: st.metric("DXY", f"{metrics['DXY'][0]:,.2f}", f"{metrics['DXY'][1]:.2f}%", delta_color="inverse")
    with c4: st.metric("US10Y Yield", f"{metrics['US10Y'][0]:,.2f}%", f"{metrics['US10Y'][1]:.2f}%", delta_color="inverse")
    with c5: st.metric("SPDR Flow", get_spdr_flow())

session_name, session_desc, session_color = get_trading_session()
st.markdown(f"<div class='session-badge' style='background-color:{session_color}; color:white;'>🗼 {session_name} : {session_desc}</div>", unsafe_allow_html=True)

signal, reason, setup, trend_h4, is_flash_crash = calculate_institutional_setup(df_m15, df_h4, dxy_change, next_red_news, max_war_score, final_news_list)

if df_m15 is not None:
    check_pending_trades(float(df_m15.iloc[-1]['high']), float(df_m15.iloc[-1]['low']))

if "WAIT" not in signal and setup:
    current_setup_signature = f"{signal}_{setup.get('Entry', '')}"
    if current_setup_signature != st.session_state.last_logged_setup:
        log_new_trade(signal, setup, reason)
        st.session_state.last_logged_setup = current_setup_signature

col_plan, col_ea = st.columns([1, 1])

with col_plan:
    sig_color = "#ff00ff" if is_flash_crash else ("#ffcc00" if "WAIT" in signal or "PENDING" in signal else ("#00ff00" if "LONG" in signal else "#ff3333"))
    st.markdown(f"""
    <div class="plan-card" style="{ 'border-color: #ff00ff;' if is_flash_crash else '' }">
        <h3 style="margin:0; color:#00ccff;">🃏 Institutional Manual Trade</h3>
        <div style="font-size:12px; color:#aaa; margin-top:5px;">🕒 ประมวลผลล่าสุด: {timestamp_str}</div>
        <div style="color:{sig_color}; font-size:24px; font-weight:bold; margin-top:10px;">{signal}</div>
        <div style="font-size:14px; margin-top:10px;"><b>Logic:</b> {reason}</div>
    """, unsafe_allow_html=True)
    if setup:
        st.markdown(f"""
        <div style="background-color:#111; padding:15px; border-radius:8px; border: 1px solid #444; margin-top: 15px;">
            <div style="color:#00ccff; font-weight:bold; margin-bottom:5px;">🎯 Dynamic Zones:</div>
            <div>📍 <b>Entry:</b> {setup['Entry']}</div>
            <div style="color:#ff4444;">🛑 <b>SL:</b> {setup['SL']}</div>
            <div style="color:#00ff00;">💰 <b>TP:</b> {setup['TP']}</div>
        </div>
        """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

with col_ea:
    st.markdown('<div class="ea-card">', unsafe_allow_html=True)
    st.markdown('<h3 style="margin:0; color:#d4af37;">🤖 EA Commander</h3>', unsafe_allow_html=True)
    if is_flash_crash:
        st.markdown("<div style='color:#ff3333; font-weight:bold; margin-top:10px;'>🚨 ปิด AUTO TRADING ทันที! วาฬทุบตลาด</div>", unsafe_allow_html=True)
    elif "WAIT" in signal or "PENDING" in signal:
        st.markdown("<div style='color:#ffcc00; font-weight:bold; margin-top:10px;'>⚠️ EA STANDBY: พักการเปิดไม้ใหม่ / กาง Limit รอ</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div style='color:#00ff00; font-weight:bold; margin-top:10px;'>▶️ EA RUNNING: กางระบบ Grid ได้ปกติ</div>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

st.write("---")

def display_intelligence():
    st.subheader("📰 Global Intelligence Hub")
    tab_eco, tab_pol, tab_war = st.tabs(["📅 ข่าวเศรษฐกิจ (Merged Data)", "🏛️ การเมือง & Fed", "⚔️ สงคราม"])
    
    with tab_eco:
        if final_news_list:
            for ev in final_news_list:
                border_color = "#ff3333" if ev['impact'] == 'High' else "#ff9933"
                source_icon = "⚡ MT5" if ev['source'] == 'MT5' else "🌐 FF"
                ai_text = f"<br><span style='color:#00ccff; font-size:13px;'><b>🤖 AI Analysis:</b> {ev['direction']}</span>" if ev['direction'] else ""
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
            st.markdown(f"<div class='news-card'><a href='{news['link']}' target='_blank' style='color:#fff;'>🇺🇸 {news['title_th']}</a><br><span style='font-size: 12px; color: #aaa;'><b>AI:</b> {news['direction']} | Impact: {news['score']:.1f}/10</span></div>", unsafe_allow_html=True)
    with tab_war:
        for news in war_news: 
            st.markdown(f"<div class='news-card' style='border-color:#ff3333;'><a href='{news['link']}' target='_blank' style='color:#fff;'>⚠️ {news['title_th']}</a><br><span style='font-size: 12px; color: #aaa;'><b>AI:</b> {news['direction']} | Impact: {news['score']:.1f}/10</span></div>", unsafe_allow_html=True)

# --- สร้าง Widget กราฟ TradingView ---
tv_gold = f"""<div class="tradingview-widget-container"><div id="tv_gold"></div><script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script><script type="text/javascript">new TradingView.widget({{"width": "100%", "height": {600 if layout_mode == "🖥️ Desktop" else 400}, "symbol": "OANDA:XAUUSD", "interval": "15", "theme": "dark", "style": "1", "container_id": "tv_gold"}});</script></div>"""
tv_dxy = f"""<div class="tradingview-widget-container"><div id="tv_dxy"></div><script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script><script type="text/javascript">new TradingView.widget({{"width": "100%", "height": {600 if layout_mode == "🖥️ Desktop" else 400}, "symbol": "CAPITALCOM:DXY", "interval": "15", "theme": "dark", "style": "1", "container_id": "tv_dxy"}});</script></div>"""

# --- จัด Layout กราฟ และ ข่าว ---
if layout_mode == "🖥️ Desktop":
    col1, col2 = st.columns([1.8, 1])
    with col1:
        tab_chart_gold, tab_chart_dxy = st.tabs(["🥇 XAUUSD", "💵 DXY"])
        with tab_chart_gold: st.components.v1.html(tv_gold, height=600)
        with tab_chart_dxy: st.components.v1.html(tv_dxy, height=600)
    with col2: display_intelligence()
else:
    tab_chart_gold, tab_chart_dxy = st.tabs(["🥇 XAUUSD", "💵 DXY"])
    with tab_chart_gold: st.components.v1.html(tv_gold, height=400)
    with tab_chart_dxy: st.components.v1.html(tv_dxy, height=400)
    display_intelligence()
