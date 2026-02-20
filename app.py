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

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Kwaktong War Room", page_icon="🦅", layout="wide", initial_sidebar_state="expanded")

if 'manual_overrides' not in st.session_state:
    st.session_state.manual_overrides = {}

FIREBASE_URL = "https://kwaktong-warroom-default-rtdb.asia-southeast1.firebasedatabase.app/market_data.json"

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
    .score-low {color: #00ffcc; font-weight: bold;}
    .stTabs [data-baseweb="tab-list"] {gap: 10px;}
    .stTabs [data-baseweb="tab"] {background-color: #1a1a2e; border-radius: 5px 5px 0 0; padding: 10px 20px;}
    .stTabs [aria-selected="true"] {background-color: #d4af37 !important; color: #000 !important; font-weight: bold;}
</style>
""", unsafe_allow_html=True)

# --- 2. DATA ENGINE (Full MT5 Extraction) ---
@st.cache_data(ttl=30)
def get_market_data():
    metrics = {'GOLD': (0.0, 0.0), 'DXY': (0.0, 0.0), 'US10Y': (0.0, 0.0)}
    df_m15, df_h4 = None, None
    data_source = "Yahoo Finance (Fallback Mode)"
    
    try:
        res = requests.get(FIREBASE_URL, timeout=5)
        if res.status_code == 200 and res.json() is not None:
            data = res.json()
            
            # ดึง M15
            if 'XAUUSD' in data:
                df_xau = pd.DataFrame(data['XAUUSD'])
                df_xau.rename(columns={'o':'open', 'h':'high', 'l':'low', 'c':'close', 't':'time'}, inplace=True)
                curr_gold, prev_gold = float(df_xau['close'].iloc[-1]), float(df_xau['close'].iloc[-2])
                metrics['GOLD'] = (curr_gold, ((curr_gold - prev_gold) / prev_gold) * 100)
                df_m15 = df_xau
                data_source = "MT5 Direct Connection ⚡"
            
            # ดึง H1 (อัปเกรดใหม่)
            if 'XAUUSD_H1' in data:
                df_h1 = pd.DataFrame(data['XAUUSD_H1'])
                df_h1.rename(columns={'o':'open', 'h':'high', 'l':'low', 'c':'close', 't':'time'}, inplace=True)
                df_h4 = df_h1

            if 'DXY' in data:
                df_dxy = pd.DataFrame(data['DXY'])
                curr_dxy, prev_dxy = float(df_dxy['c'].iloc[-1]), float(df_dxy['c'].iloc[-2])
                metrics['DXY'] = (curr_dxy, ((curr_dxy - prev_dxy) / prev_dxy) * 100)
    except Exception as e: pass

    # ถ้าพลาดให้กลับไปพึ่ง Yahoo
    if df_m15 is None:
        try:
            h_m15 = yf.Ticker("XAUUSD=X").history(period="5d", interval="15m")
            if not h_m15.empty and len(h_m15) >= 2:
                curr_gold, prev_gold = float(h_m15['Close'].iloc[-1]), float(h_m15['Close'].iloc[-2])
                metrics['GOLD'] = (curr_gold, ((curr_gold - prev_gold) / prev_gold) * 100)
                df_m15 = h_m15.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close'})
        except: pass

    if df_h4 is None:
        try:
            h_h1 = yf.Ticker("XAUUSD=X").history(period="1mo", interval="1h")
            if not h_h1.empty: df_h4 = h_h1.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close'})
        except: pass
    
    if metrics['DXY'][0] == 0.0:
        try:
            h_dxy = yf.Ticker("DX-Y.NYB").history(period="5d", interval="15m")
            if not h_dxy.empty and len(h_dxy) >= 2: metrics['DXY'] = (h_dxy['Close'].iloc[-1], ((h_dxy['Close'].iloc[-1]-h_dxy['Close'].iloc[-2])/h_dxy['Close'].iloc[-2])*100)
        except: pass

    try:
        h_tnx = yf.Ticker("^TNX").history(period="5d", interval="15m")
        if not h_tnx.empty and len(h_tnx) >= 2: metrics['US10Y'] = (h_tnx['Close'].iloc[-1], ((h_tnx['Close'].iloc[-1]-h_tnx['Close'].iloc[-2])/h_tnx['Close'].iloc[-2])*100)
    except: pass
    
    return metrics, df_m15, df_h4, data_source

@st.cache_data(ttl=3600)
def get_spdr_flow(): return "Neutral (รอดูท่าที)"

# --- 3. NEWS & TIME ENGINE ---
def get_trading_session():
    now_utc = datetime.datetime.utcnow()
    hour_utc = now_utc.hour
    if 0 <= hour_utc < 7: return "🇯🇵 Asian Session", "สภาพคล่องต่ำ (Low Volatility) - เน้นเก็บกำไรสั้น", "#334455"
    elif 7 <= hour_utc < 13: return "🇬🇧 London Session", "สภาพคล่องปานกลางถึงสูง - กราฟเริ่มเลือกทาง", "#554433"
    else: return "🇺🇸 New York Session", "สภาพคล่องสูงสุด (High Volatility) - ระวังสวิงแรง / รันเทรนด์ได้", "#224422"

@st.cache_data(ttl=300)
def get_forexfactory_usd(manual_overrides):
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
    headers = {'User-Agent': 'Mozilla/5.0'}
    events, max_smis, next_red_news = [], 0, None
    now_thai = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
    try:
        root = ET.fromstring(requests.get(url, headers=headers, timeout=10).content)
        for event in root.findall('event'):
            if event.find('country').text == 'USD' and event.find('impact').text in ['High', 'Medium']:
                date_str, raw_time = event.find('date').text, event.find('time').text
                impact, title = event.find('impact').text, event.find('title').text
                if not raw_time or not any(c.isdigit() for c in raw_time): continue
                try: gmt_dt = datetime.datetime.strptime(f"{date_str} {raw_time.strip().lower()}", "%m-%d-%Y %I:%M%p")
                except: continue
                thai_dt = gmt_dt + datetime.timedelta(hours=7)
                time_diff_hours = (thai_dt - now_thai).total_seconds() / 3600
                if time_diff_hours < -12 or (impact == 'High' and time_diff_hours > 24) or (impact == 'Medium' and time_diff_hours > 4): continue
                if impact == 'High' and 0 < time_diff_hours <= 3:
                    if next_red_news is None or time_diff_hours < next_red_news['hours']:
                        next_red_news = {'title': title, 'hours': time_diff_hours, 'time': thai_dt.strftime("%H:%M น.")}
                actual = manual_overrides.get(title, event.find('actual').text if event.find('actual') is not None else "Pending")
                forecast = event.find('forecast').text if event.find('forecast') is not None else ""
                smis = 8.0 if impact == 'High' else 5.0
                if max_smis < smis: max_smis = smis
                events.append({'title': title, 'time': thai_dt.strftime("%d %b - %H:%M น."), 'impact': impact, 'actual': actual, 'forecast': forecast, 'smis': smis, 'dt': thai_dt})
        events.sort(key=lambda x: x['dt'])
        return events, max_smis, next_red_news
    except: return [], 0, None

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
                try:
                    pub_time = mktime(entry.published_parsed)
                    date_str = datetime.datetime.fromtimestamp(pub_time).strftime('%d %b %H:%M')
                except: date_str = "Recent"
                title_en = entry.title
                base_score = abs(TextBlob(title_en).sentiment.polarity) * 5
                title_lower = title_en.lower()
                if any(kw in title_lower for kw in ['war', 'missile', 'strike', 'emergency', 'attack']): base_score += 4.0
                elif 'fed' in title_lower or 'inflation' in title_lower or 'rate' in title_lower: base_score += 2.0
                final_score = min(10.0, max(1.0, base_score))
                news_list.append({'title_en': title_en, 'title_th': translator.translate(title_en), 'link': entry.link, 'time': date_str, 'score': final_score})
        except: pass
        return news_list
    pol_news = fetch_rss("(Fed OR Powell OR Trump OR Biden OR US Election OR Treasury)")
    war_news = fetch_rss("(War OR Missile OR Strike OR Iran OR Israel OR Russia OR Ukraine OR Geopolitics)")
    return pol_news, war_news

# --- 4. DUAL-TIMEFRAME STRATEGY ---
def calculate_institutional_setup(df_m15, df_h4, dxy_change):
    if df_m15 is None or df_h4 is None or len(df_m15) < 55 or len(df_h4) < 55: 
        return "WAIT", "รอข้อมูลราคาทองคำจากเซิร์ฟเวอร์ (กำลังซิงค์...)", {}, "UNKNOWN"
    
    df_h4['ema50'] = ta.ema(df_h4['close'], length=50)
    h4_closed = df_h4.iloc[-2]
    trend_h4 = "UP" if h4_closed['close'] > h4_closed['ema50'] else "DOWN"

    df_m15['ema50'] = ta.ema(df_m15['close'], length=50)
    df_m15['atr'] = ta.atr(df_m15['high'], df_m15['low'], df_m15['close'], length=14)
    m15_closed = df_m15.iloc[-2]
    trend_m15 = "UP" if m15_closed['close'] > m15_closed['ema50'] else "DOWN"
    
    atr_val = m15_closed['atr']
    ema_val = m15_closed['ema50']

    signal, reason, setup = "WAIT (Fold)", f"H1/H4 Trend ({trend_h4}) ไม่ตรงกับ M15 ({trend_m15}) หรือ DXY ขัดแย้ง", {}

    if trend_h4 == "UP" and trend_m15 == "UP" and dxy_change <= 0:
        signal = "LONG (Dual-TF Aligned)"
        reason = "โครงสร้างสถาบัน: เทรนด์ใหญ่(H1) ขึ้น + ย่อย(M15) ขึ้น + DXY อ่อนค่า เอื้อต่อการยิงโซน Buy"
        setup = {'Entry': f"${ema_val - (0.5*atr_val):.2f} ถึง ${ema_val + (0.5*atr_val):.2f}", 'SL': f"${ema_val - (2*atr_val):.2f} (เด็ดขาด)", 'TP': f"${ema_val + (2*atr_val):.2f} ถึง ${ema_val + (4*atr_val):.2f}"}
    elif trend_h4 == "DOWN" and trend_m15 == "DOWN" and dxy_change >= 0:
        signal = "SHORT (Dual-TF Aligned)"
        reason = "โครงสร้างสถาบัน: เทรนด์ใหญ่(H1) ลง + ย่อย(M15) ลง + DXY แข็งค่า เอื้อต่อการยิงโซน Sell"
        setup = {'Entry': f"${ema_val - (0.5*atr_val):.2f} ถึง ${ema_val + (0.5*atr_val):.2f}", 'SL': f"${ema_val + (2*atr_val):.2f} (เด็ดขาด)", 'TP': f"${ema_val - (2*atr_val):.2f} ถึง ${ema_val - (4*atr_val):.2f}"}
        
    return signal, reason, setup, trend_h4

# --- 5. UI DASHBOARD ---
metrics, df_m15, df_h4, data_source = get_market_data()
ff_events, max_ff_smis, next_red_news = get_forexfactory_usd(st.session_state.manual_overrides)
pol_news, war_news = get_categorized_news()
dxy_change = metrics['DXY'][1] if metrics else 0

with st.sidebar:
    st.header("💻 War Room Terminal")
    layout_mode = st.radio("Display:", ["🖥️ Desktop", "📱 Mobile"])
    if st.button("Refresh Data", type="primary"): st.cache_data.clear()
    
    st.markdown("---")
    if "MT5" in data_source: st.success(f"📡 **{data_source}**")
    else: st.warning(f"⚠️ **{data_source}**")
    st.markdown("---")

    st.subheader("✍️ Override ข่าวเศรษฐกิจ")
    has_pending = False
    for ev in ff_events:
        if ev['impact'] in ['High', 'Medium'] and "Pending" in ev['actual']:
            has_pending = True
            new_val = st.text_input(f"[{ev['time']}] {ev['title']}", value=st.session_state.manual_overrides.get(ev['title'], ""))
            if new_val != st.session_state.manual_overrides.get(ev['title'], ""):
                st.session_state.manual_overrides[ev['title']] = new_val
                st.rerun()
    if not has_pending: st.write("✅ ไม่มีข่าวรอตัวเลข")
    if st.button("🗑️ ล้างค่าคีย์เอง"):
        st.session_state.manual_overrides = {}
        st.rerun()

st.title("🦅 XAUUSD WAR ROOM: Institutional Edition")

if metrics and 'GOLD' in metrics:
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("GOLD", f"${metrics['GOLD'][0]:,.2f}", f"{metrics['GOLD'][1]:.2f}%")
    with c2: st.metric("DXY", f"{metrics['DXY'][0]:,.2f}", f"{metrics['DXY'][1]:.2f}%", delta_color="inverse")
    with c3: st.metric("US10Y Yield", f"{metrics['US10Y'][0]:,.2f}%", f"{metrics['US10Y'][1]:.2f}%", delta_color="inverse")
    with c4: st.metric("SPDR Flow", get_spdr_flow())

session_name, session_desc, session_color = get_trading_session()
st.markdown(f"<div class='session-badge' style='background-color:{session_color}; color:white;'>🗼 {session_name} : {session_desc}</div>", unsafe_allow_html=True)

if next_red_news:
    st.markdown(f"""
    <div class="alert-card">
        <h4 style="margin:0; color:#ff3333;">⚠️ QUANT ALERT: ระวังพายุข่าวมหภาค!</h4>
        <p style="margin:5px 0 0 0; color:#fff;">อีกประมาณ <b>{next_red_news['hours']:.1f} ชั่วโมง</b> ({next_red_news['time']}) จะมีข่าวกล่องแดง <b>{next_red_news['title']}</b><br>
        <i>คำแนะนำ: หากเข้าเทรดตอนนี้ ควรพิจารณาลดระยะ TP สั้นลง หรือเคลียร์พอร์ต/ลดหลอดก่อนข่าวออก เพื่อป้องกันการสะบัดตัวรุนแรง (Whipsaw)</i></p>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

signal, reason, setup, trend_h4 = calculate_institutional_setup(df_m15, df_h4, dxy_change)

col_plan, col_ea = st.columns([1, 1])

with col_plan:
    sig_color = "#00ff00" if "LONG" in signal else "#ff3333" if "SHORT" in signal else "#ffcc00"
    st.markdown(f"""
    <div class="plan-card">
        <h3 style="margin:0; color:#00ccff;">🃏 Institutional Manual Trade</h3>
        <div style="color:{sig_color}; font-size:24px; font-weight:bold; margin-top:10px;">{signal}</div>
        <p><b>Logic:</b> {reason}</p>
    """, unsafe_allow_html=True)
    if setup:
        st.markdown(f"""
        <div style="background-color:#111; padding:15px; border-radius:8px; border: 1px solid #444;">
            <div style="color:#00ccff; font-weight:bold; margin-bottom:5px;">🎯 Dynamic Zones (อ้างอิงราคาจริงจาก MT5 ของท่าน):</div>
            <div style="margin-bottom:5px;">📍 <b>Entry Zone:</b> กระจายไม้ในโซน {setup['Entry']}</div>
            <div style="margin-bottom:5px; color:#ff4444;">🛑 <b>Stoploss:</b> ยอมแพ้เด็ดขาดที่ {setup['SL']}</div>
            <div style="color:#00ff00;">💰 <b>TP Zone:</b> รินขายทำกำไรในโซน {setup['TP']}</div>
            <div style="margin-top:10px; font-size:12px; color:#aaa;">*ขนาด Lot ให้อ้างอิงตามระยะ SL และความเสี่ยงที่รับได้ของพอร์ตตัวเอง</div>
        </div>
        """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

with col_ea:
    st.markdown('<div class="ea-card">', unsafe_allow_html=True)
    st.markdown(f"""<h3 style="margin:0; color:#d4af37;">🤖 EA Commander (TumHybrid_v5.32)</h3>""", unsafe_allow_html=True)
    if max_ff_smis >= 8.5 or next_red_news:
        st.markdown(f"""<div class="ea-red"><div style="font-size: 18px; font-weight: bold;">🛑 พิจารณาปิด Auto Trading (Force Pause EA)</div><div style="font-size: 14px; margin-top:5px;">ความผันผวนจากข่าวสูง/ใกล้เวลาข่าวออก เสี่ยงเกิด Whipsaw กวาด Grid</div></div>""", unsafe_allow_html=True)
    elif "WAIT" in signal:
        st.markdown(f"""<div class="ea-warning"><div style="font-size: 18px; font-weight: bold;">⚠️ ระวังการกาง Grid / เตรียมแทรกแซง</div><div style="font-size: 14px; margin-top:5px;">เทรนด์ใหญ่และย่อยขัดแย้งกัน หาก EA ฝืนกาง Grid ให้เฝ้าระวังพอร์ตโดนลาก</div></div>""", unsafe_allow_html=True)
    elif "LONG" in signal:
        st.markdown(f"""<div class="ea-green"><div style="font-size: 18px; font-weight: bold;">▶️ รัน EA (Buy Limit Mode) ได้เต็มสูบ</div><div style="font-size: 14px; margin-top:5px;">โครงสร้าง H4 และ M15 สนับสนุนขาขึ้น DXY อ่อนค่า ปล่อยให้ EA กาง Buy Grid เก็บ Cash Flow ได้อย่างปลอดภัย</div></div>""", unsafe_allow_html=True)
    elif "SHORT" in signal:
        st.markdown(f"""<div class="ea-green"><div style="font-size: 18px; font-weight: bold;">▶️ รัน EA (Sell Grid Mode) / ห้ามฝืน Buy Limit</div><div style="font-size: 14px; margin-top:5px;">โครงสร้าง H4 และ M15 สนับสนุนขาลง DXY แข็งค่า หาก EA พยายามกาง Buy ให้แทรกแซงปิดมือทันที</div></div>""", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

st.write("")

tv_gold = f"""<div class="tradingview-widget-container"><div id="tv_gold"></div><script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script><script type="text/javascript">new TradingView.widget({{"width": "100%", "height": {600 if layout_mode == "🖥️ Desktop" else 400}, "symbol": "OANDA:XAUUSD", "interval": "15", "theme": "dark", "style": "1", "container_id": "tv_gold"}});</script></div>"""
tv_dxy = f"""<div class="tradingview-widget-container"><div id="tv_dxy"></div><script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script><script type="text/javascript">new TradingView.widget({{"width": "100%", "height": {600 if layout_mode == "🖥️ Desktop" else 400}, "symbol": "CAPITALCOM:DXY", "interval": "15", "theme": "dark", "style": "1", "container_id": "tv_dxy"}});</script></div>"""

def display_intelligence():
    st.subheader("📰 Global Intelligence Hub")
    tab_eco, tab_pol, tab_war = st.tabs(["📅 ข่าวเศรษฐกิจ", "🏛️ การเมือง & Fed", "⚔️ สงคราม"])
    
    with tab_eco:
        if ff_events:
            for ev in ff_events:
                border_color = "#ff3333" if ev['impact'] == 'High' else "#ff9933"
                st.markdown(f"<div class='ff-card' style='border-left-color: {border_color};'>⚡ [{ev['time']}] <b>{ev['title']}</b><br><span style='color:#aaa; font-size:13px;'>Forecast: {ev['forecast']} | <span style='color:#ffcc00;'>Actual: {ev['actual']}</span></span><br>🔥 SMIS: {ev['smis']}/10</div>", unsafe_allow_html=True)
        else: st.write("ไม่มีข่าวเศรษฐกิจสำคัญในช่วงนี้")
            
    with tab_pol:
        if pol_news:
            for news in pol_news:
                score_class = "score-high" if news['score'] >= 8 else "score-med" if news['score'] >= 5 else "score-low"
                st.markdown(f"<div class='news-card'><div style='font-size:15px; font-weight:bold;'><a href='{news['link']}' target='_blank' style='color:#ffffff; text-decoration:none;'>🇺🇸 {news['title_th']}</a></div><div style='font-size:12px; color:#aaa; font-style:italic;'>{news['title_en']}</div><div style='margin-top:5px; font-size:11px; color:#00ccff;'>🕒 {news['time']} | 🔥 SMIS Impact: <span class='{score_class}'>{news['score']:.1f}/10</span></div></div>", unsafe_allow_html=True)
        else: st.write("กำลังรวบรวมข่าวการเมือง...")
            
    with tab_war:
        if war_news:
            for news in war_news:
                score_class = "score-high" if news['score'] >= 8 else "score-med" if news['score'] >= 5 else "score-low"
                st.markdown(f"<div class='news-card' style='border-left-color: #ff3333;'><div style='font-size:15px; font-weight:bold;'><a href='{news['link']}' target='_blank' style='color:#ffffff; text-decoration:none;'>⚠️ {news['title_th']}</a></div><div style='font-size:12px; color:#aaa; font-style:italic;'>{news['title_en']}</div><div style='margin-top:5px; font-size:11px; color:#00ccff;'>🕒 {news['time']} | 🔥 SMIS Impact: <span class='{score_class}'>{news['score']:.1f}/10</span></div></div>", unsafe_allow_html=True)
        else: st.write("กำลังรวบรวมข่าวภูมิรัฐศาสตร์...")

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

st.markdown("<div class='footer-credits'>⚙️ <b>Institutional Master Node:</b> Powered by MT5 Firebase Bridge</div>", unsafe_allow_html=True)
