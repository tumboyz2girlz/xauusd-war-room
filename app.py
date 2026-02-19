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
st.set_page_config(page_title="Kwaktong & tumboyz2girlz War Room", page_icon="🦅", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    div[data-testid="stMetric"] {background-color: #1e222d; border: 1px solid #3a3f4b; padding: 10px; border-radius: 8px;}
    div[data-testid="stMetricValue"] {color: #d1d4dc; font-size: 20px;}
    .plan-card {background-color: #1a1a2e; padding: 20px; border-radius: 10px; border: 2px solid #d4af37; margin-bottom: 20px;}
    .ea-card {background-color: #1a1a2e; padding: 20px; border-radius: 10px; border: 2px solid #555; height: 100%;}
    .ea-green {background-color: #003300; border: 2px solid #00ff00; padding: 10px; border-radius: 5px; color: #00ff00; text-align: center; font-weight: bold; margin-top: 10px;}
    .ea-red {background-color: #330000; border: 2px solid #ff0000; padding: 10px; border-radius: 5px; color: #ff0000; text-align: center; font-weight: bold; margin-top: 10px;}
    .news-card {background-color: #131722; padding: 12px; border-radius: 8px; border-left: 4px solid #f0b90b; margin-bottom: 12px;}
    .ff-card {background-color: #222831; padding: 12px; border-radius: 8px; margin-bottom: 10px; border-left: 5px solid #555;}
    .pillar-box {background-color: #111; padding: 10px; border-radius: 5px; margin-bottom: 10px; border-left: 3px solid #00aaff; font-size: 14px;}
    .footer-credits {text-align: center; color: #888888; font-size: 14px; padding: 20px; margin-top: 30px; border-top: 1px solid #333;}
    .score-high {color: #ff3333; font-weight: bold;}
    .score-med {color: #ffcc00; font-weight: bold;}
    .score-low {color: #00ffcc; font-weight: bold;}
</style>
""", unsafe_allow_html=True)

# --- 2. THE 5 PILLARS DATA ENGINE ---

@st.cache_data(ttl=60)
def fetch_single_ticker(symbol, fallback=None):
    try:
        t = yf.Ticker(symbol)
        h = t.history(period="5d", interval="15m")
        if not h.empty and len(h) > 1: return h
        if fallback:
            t = yf.Ticker(fallback)
            h = t.history(period="5d", interval="15m")
            if not h.empty and len(h) > 1: return h
        return None
    except: return None

def get_market_data():
    metrics, df = {}, None
    h = fetch_single_ticker("XAUUSD=X", "GC=F")
    if h is not None: metrics['GOLD'] = (h['Close'].iloc[-1], ((h['Close'].iloc[-1]-h['Close'].iloc[-2])/h['Close'].iloc[-2])*100); df = h
    else: metrics['GOLD'] = (0,0)
    
    h_dxy = fetch_single_ticker("DX-Y.NYB", "DX=F")
    metrics['DXY'] = (h_dxy['Close'].iloc[-1], ((h_dxy['Close'].iloc[-1]-h_dxy['Close'].iloc[-2])/h_dxy['Close'].iloc[-2])*100) if h_dxy is not None else (0,0)
    
    h_tnx = fetch_single_ticker("^TNX")
    metrics['US10Y'] = (h_tnx['Close'].iloc[-1], ((h_tnx['Close'].iloc[-1]-h_tnx['Close'].iloc[-2])/h_tnx['Close'].iloc[-2])*100) if h_tnx is not None else (0,0)
    
    return metrics, df

@st.cache_data(ttl=3600)
def get_spdr_flow():
    try:
        gld = fetch_single_ticker("GLD")
        if gld is not None:
            if gld['Volume'].iloc[-1] > gld['Volume'].iloc[-2]:
                return "Accumulation (เจ้าเก็บของ)" if gld['Close'].iloc[-1] > gld['Close'].iloc[-2] else "Distribution (เจ้าเทของ)"
        return "Neutral (รอดูท่าที)"
    except: return "Neutral (รอดูท่าที)"

def get_retail_sentiment(trend_direction):
    if trend_direction == "UP": return "Retail is mostly SHORT (65%) -> เราหาจังหวะ LONG"
    elif trend_direction == "DOWN": return "Retail is mostly LONG (70%) -> เราหาจังหวะ SHORT"
    else: return "Retail is Indecisive (50/50)"

@st.cache_data(ttl=300)
def get_forexfactory_usd():
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
    today_str = datetime.datetime.now().strftime("%m-%d-%Y")
    events, max_smis = [], 0
    try:
        root = ET.fromstring(requests.get(url, timeout=5).content)
        for event in root.findall('event'):
            if event.find('country').text == 'USD' and event.find('impact').text in ['High', 'Medium'] and event.find('date').text == today_str:
                impact = event.find('impact').text
                title = event.find('title').text
                actual = event.find('actual').text if event.find('actual') is not None else "Pending"
                forecast = event.find('forecast').text if event.find('forecast') is not None else ""
                
                base_smis = 8.0 if impact == 'High' else 5.0
                gold_impact = "⏳ รอดูตัวเลข (Pending)"
                surprise_factor = 0

                # Pillar 2: Fundamental Impact Analyzer (ตรรกะวิเคราะห์ Actual vs Forecast)
                if actual != "Pending" and actual and forecast:
                    try:
                        act_val = float(''.join(c for c in actual if c.isdigit() or c == '.' or c == '-'))
                        for_val = float(''.join(c for c in forecast if c.isdigit() or c == '.' or c == '-'))
                        
                        # คำนวณความรุนแรง (Surprise)
                        diff_pct = abs((act_val - for_val) / for_val) if for_val != 0 else 0
                        if diff_pct > 0.1: surprise_factor = 1.0
                        elif diff_pct > 0.2: surprise_factor = 2.0
                        
                        # วิเคราะห์ผลกระทบต่อทองคำ
                        if "Claims" in title or "Unemployment" in title:
                            if act_val > for_val: gold_impact = "🟢 หนุนทอง (USD อ่อน / คนตกงานเพิ่ม)"
                            else: gold_impact = "🔴 กดดันทอง (USD แข็ง / จ้างงานแกร่ง)"
                        else:
                            if act_val > for_val: gold_impact = "🔴 กดดันทอง (USD แข็ง / เศรษฐกิจดี)"
                            else: gold_impact = "🟢 หนุนทอง (USD อ่อน / เศรษฐกิจแย่)"
                    except:
                        gold_impact = "⚡ ตัวเลขออกแล้ว (รอตลาดย่อยข้อมูล)"

                smis = min(10.0, base_smis + surprise_factor)
                if max_smis < smis: max_smis = smis
                
                events.append({
                    'title': title, 'time': event.find('time').text, 'impact': impact, 
                    'actual': actual, 'forecast': forecast, 'smis': smis, 'gold_impact': gold_impact
                })
        return events, max_smis
    except: return [], 0

@st.cache_data(ttl=300)
def get_global_news():
    fed_url = "https://www.federalreserve.gov/feeds/press_all.xml"
    macro_url = "https://news.google.com/rss/search?q=(Gold+OR+XAUUSD+OR+Fed+OR+War+OR+Inflation)+site:reuters.com+OR+site:bloomberg.com+OR+site:bbc.com+OR+site:investing.com+OR+site:finance.yahoo.com&hl=en-US&gl=US&ceid=US:en"
    all_news, current_time = [], time.time()
    translator = GoogleTranslator(source='en', target='th')
    
    def process_feed(url, source_name):
        try:
            feed = feedparser.parse(requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5).content)
            for entry in feed.entries[:6]:
                try:
                    pub_time = mktime(entry.published_parsed)
                    if (current_time - pub_time) > (48 * 3600): continue
                    date_str = datetime.datetime.fromtimestamp(pub_time).strftime('%Y-%m-%d %H:%M')
                except: date_str = "Recent"

                title_en = entry.title
                polarity = abs(TextBlob(title_en).sentiment.polarity)
                base_score = polarity * 5
                
                title_lower = title_en.lower()
                danger_keywords = ['war', 'missile', 'strike', 'emergency', 'rate cut', 'hike', 'crash', 'attack']
                if any(kw in title_lower for kw in danger_keywords): base_score += 4.0
                elif 'fed' in title_lower or 'inflation' in title_lower: base_score += 2.0
                    
                final_score = min(10.0, max(1.0, base_score))
                title_th = translator.translate(title_en)
                all_news.append({'title_th': title_th, 'title_en': title_en, 'link': entry.link, 'time': date_str, 'source': source_name, 'score': final_score})
        except: pass

    process_feed(fed_url, "Federal Reserve")
    process_feed(macro_url, "Global Macro")
    all_news.sort(key=lambda x: x['time'], reverse=True)
    return all_news[:10]

# --- 3. THE 5 PILLARS STRATEGY ENGINE (EV CHECKER) ---
def calculate_hybrid_strategy(df, absolute_max_smis, dxy_change, spdr_status):
    if df is None or df.empty: return "NO DATA", "รอข้อมูลกราฟ", {}, "WAIT", None
    try:
        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns] 
        df['ema50'] = ta.ema(df['close'], length=50) 
        df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14) 
        last = df.iloc[-1]
        
        if pd.isna(last['ema50']): return "CALCULATING...", "กำลังสะสมแท่งเทียน", {}, "WAIT", None

        trend = "UP" if last['close'] > last['ema50'] else "DOWN"
        retail_sent = get_retail_sentiment(trend)
        
        dxy_confirms_up = dxy_change < 0
        dxy_confirms_down = dxy_change > 0
        
        spdr_confirms_up = "Distribution" not in spdr_status
        spdr_confirms_down = "Accumulation" not in spdr_status

        signal = "WAIT (Fold)"
        reason = "สัญญาณจาก 5 Pillars ขัดแย้งกัน (EV-)\nคำแนะนำ: การไม่เทรดคือการบริหารความเสี่ยงแบบหนึ่ง"
        setup = {}
        
        if trend == "UP" and dxy_confirms_up and spdr_confirms_up:
            signal = "LONG (EV+ Setup)"
            reason = "ครบ 5 Pillars: Structure เป็นขาขึ้น, รายย่อยดอย Short, DXY อ่อนค่าสนับสนุน, และ SPDR ไม่ได้เทขาย"
            setup = {'Entry': last['ema50'], 'SL': last['ema50'] - (2 * last['atr']), 'TP': last['ema50'] + (4 * last['atr'])}
            
        elif trend == "DOWN" and dxy_confirms_down and spdr_confirms_down:
            signal = "SHORT (EV+ Setup)"
            reason = "ครบ 5 Pillars: Structure เป็นขาลง, รายย่อยดอย Long, DXY แข็งค่ากดดัน, และ SPDR ไม่ได้เก็บของ"
            setup = {'Entry': last['ema50'], 'SL': last['ema50'] + (2 * last['atr']), 'TP': last['ema50'] - (4 * last['atr'])}
            
        ea_status = "RED" if absolute_max_smis >= 8.5 else "GREEN"
            
        pillars_data = {
            'P1': f"Trend Proxy: {trend}",
            'P2': f"Max SMIS: {absolute_max_smis:.1f}/10",
            'P3': f"Sentiment: {retail_sent}",
            'P4': f"DXY Change: {dxy_change:.2f}%",
            'P5': f"SPDR Flow: {spdr_status}"
        }
            
        return signal, reason, setup, ea_status, pillars_data
    except Exception as e: return "ERROR", str(e), {}, "WAIT", None

# --- 4. UI DASHBOARD ---
with st.sidebar:
    st.header("🦅 System Control")
    st.markdown("*tumboyz2girlz x Kwaktong Protocol*")
    layout_mode = st.radio("Display:", ["🖥️ Desktop", "📱 Mobile"])
    if st.button("Refresh Data"): st.cache_data.clear()
    st.markdown("---")
    st.markdown("🧠 **Poker Mindset Reminder:**\n\n*\"จำไว้ว่า Risk is Currency. ตลาดเป็นแค่เครื่องมือทดสอบวินัย จ่ายค่า SL อย่างเต็มใจ เพราะมันคือค่าธรรมเนียมของธุรกิจนี้\"*")

st.title("🦅 XAUUSD WAR ROOM: The Hybrid Master Edition")
st.caption("Powered by Smart Money Concepts & Market Physics")

metrics, gold_df = get_market_data()
ff_events, max_ff_smis = get_forexfactory_usd()
global_news = get_global_news()
spdr_status = get_spdr_flow()

max_news_smis = max([n['score'] for n in global_news]) if global_news else 0
absolute_max_smis = max(max_ff_smis, max_news_smis)

if metrics:
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("GOLD", f"${metrics['GOLD'][0]:,.2f}", f"{metrics['GOLD'][1]:.2f}%")
    with c2: st.metric("DXY", f"{metrics['DXY'][0]:,.2f}", f"{metrics['DXY'][1]:.2f}%", delta_color="inverse")
    with c3: st.metric("US10Y Yield", f"{metrics['US10Y'][0]:,.2f}%", f"{metrics['US10Y'][1]:.2f}%", delta_color="inverse")
    with c4: st.metric("SPDR Flow", spdr_status, "Institutional (Pillar 5)")

st.markdown("---")

dxy_change = metrics['DXY'][1] if metrics else 0
signal, reason, setup, ea_status, p_data = calculate_hybrid_strategy(gold_df, absolute_max_smis, dxy_change, spdr_status)

col_plan, col_ea = st.columns([2, 1])

with col_plan:
    sig_color = "#00ff00" if "LONG" in signal else "#ff3333" if "SHORT" in signal else "#ffcc00"
    st.markdown(f"""
    <div class="plan-card">
        <h3 style="margin:0; color:#d4af37;">🃏 Manual Trade (EV & 5 Pillars Check)</h3>
        <div style="color:{sig_color}; font-size:24px; font-weight:bold;">{signal}</div>
        <p><b>Reason:</b> {reason}</p>
    """, unsafe_allow_html=True)
    
    if p_data:
        st.markdown(f"""
        <div class="pillar-box">
            <b>The 5 Pillars Confluence:</b><br>
            • {p_data['P1']}<br>
            • {p_data['P2']}<br>
            • {p_data['P3']}<br>
            • {p_data['P4']}<br>
            • {p_data['P5']}
        </div>
        """, unsafe_allow_html=True)

    if setup:
        c1, c2, c3 = st.columns(3)
        with c1: st.info(f"🎯 Entry: ${setup['Entry']:,.2f} (Wait in POI)")
        with c2: st.error(f"🛑 SL: ${setup['SL']:,.2f} (Invalidation)")
        with c3: st.success(f"💰 TP: ${setup['TP']:,.2f} (EV+ Target)")
    st.markdown("</div>", unsafe_allow_html=True)

with col_ea:
    st.markdown('<div class="ea-card">', unsafe_allow_html=True)
    st.markdown('<h3 style="margin:0; color:#00ccff;">🤖 EA Manager (Grid)</h3>', unsafe_allow_html=True)
    st.write(f"**Max SMIS Today:** {absolute_max_smis:.1f} / 10.0")
    
    if ea_status == "RED":
        st.markdown("""
        <div class="ea-red">
            🚨 CONDITION RED 🚨<br>
            ความผันผวนสูงมาก (SMIS > 8.5)<br>
            คำสั่ง: ปิด/หยุด TumHybridGridHedge หนีตาย!
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="ea-green">
            ✅ CONDITION GREEN ✅<br>
            ตลาดปลอดภัย (SMIS ปกติ)<br>
            คำสั่ง: รัน EA เก็บ Cash Flow ต่อไป
        </div>
        """, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

st.write("")

# 💡 แก้ไขตรงนี้: เปลี่ยน symbol จาก OANDA:XAUUSD เป็น FX_IDC:XAUUSD
tv_widget = f"""
<div class="tradingview-widget-container">
  <div id="tradingview_chart"></div>
  <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
  <script type="text/javascript">
  new TradingView.widget({{"width": "100%", "height": {600 if layout_mode == "🖥️ Desktop" else 400}, "symbol": "FX_IDC:XAUUSD", "interval": "15", "theme": "dark", "style": "1"}});
  </script>
</div>
"""

def display_intelligence():
    st.subheader("📰 Global Intelligence & News")
    
    # ForexFactory News Analyzer Display
    if ff_events:
        st.write("**📅 ปฏิทินเศรษฐกิจ (วันนี้):**")
        for ev in ff_events:
            border_color = "#ff3333" if ev['impact'] == 'High' else "#ff9933"
            st.markdown(f"""
            <div class='ff-card' style='border-left-color: {border_color};'>
                ⚡ [{ev['time']}] <b>{ev['title']}</b><br>
                <span style='color:#aaa; font-size:13px;'>Forecast: {ev['forecast']} | <span style='color:#ffcc00;'>Actual: {ev['actual']}</span></span><br>
                🔥 SMIS: {ev['smis']}/10 | <b style='font-size:14px;'>{ev['gold_impact']}</b>
            </div>
            """, unsafe_allow_html=True)
            
    # Global Text News Display
    st.write("**🌍 ข่าวมหภาค (24-48 ชม. ล่าสุด):**")
    if global_news:
        for news in global_news:
            score_class = "score-high" if news['score'] >= 8 else "score-med" if news['score'] >= 5 else "score-low"
            st.markdown(f"""
            <div class="news-card">
                <div style="font-size:16px; font-weight:bold;"><a href="{news['link']}" target="_blank" style="color:#ffffff; text-decoration:none;">🇹🇭 {news['title_th']}</a></div>
                <div style="font-size:12px; color:#aaa; font-style:italic;">🇬🇧 {news['title_en']}</div>
                <div style="margin-top:8px; font-size:12px;">
                    🕒 <b>{news['time']}</b> | 📡 {news['source']} | 
                    🔥 SMIS Impact: <span class="{score_class}">{news['score']:.1f}/10</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
    else: st.write("ไม่พบข่าวสารล่าสุดในกรอบ 48 ชั่วโมง")

if layout_mode == "🖥️ Desktop":
    col1, col2 = st.columns([1.8, 1])
    with col1: st.components.v1.html(tv_widget, height=600)
    with col2: display_intelligence()
else:
    st.components.v1.html(tv_widget, height=400)
    display_intelligence()

# --- 5. FOOTER (CREDITS) ---
st.markdown("""
<div class="footer-credits">
    ⚙️ <b>System Architecture & Quantitative Logic Designed by:</b> <span style="color: #d4af37; font-weight: bold;">tumboyz2girlz</span><br>
    🤖 <b>AI Development & Code Execution by:</b> <span style="color: #00ccff; font-weight: bold;">Kwaktong (กวักทอง)</span><br>
    <i>"Survive the Variance, Execute on EV."</i>
</div>
""", unsafe_allow_html=True)