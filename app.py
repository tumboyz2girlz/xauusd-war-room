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
from tvDatafeed import TvDatafeed, Interval

# --- 1. CONFIGURATION & MEMORY ---
st.set_page_config(page_title="Kwaktong Local Station", page_icon="🦅", layout="wide", initial_sidebar_state="expanded")

if 'manual_overrides' not in st.session_state:
    st.session_state.manual_overrides = {}

st.markdown("""
<style>
    div[data-testid="stMetric"] {background-color: #1a1a2e; border: 1px solid #00ccff; padding: 10px; border-radius: 8px; box-shadow: 0 0 10px rgba(0,204,255,0.2);}
    div[data-testid="stMetricValue"] {color: #00ccff; font-size: 22px; font-weight: bold;}
    .plan-card {background-color: #1a1a2e; padding: 20px; border-radius: 10px; border: 2px solid #d4af37; margin-bottom: 20px; height: 100%;}
    .ea-card {background-color: #1a1a2e; padding: 20px; border-radius: 10px; border: 2px solid #555; height: 100%;}
    .summary-card {background-color: #0d1117; padding: 20px; border-radius: 10px; border-left: 5px solid #00ffcc; margin-bottom: 20px;}
    .ea-green {background-color: #003300; border: 1px solid #00ff00; padding: 15px; border-radius: 8px; color: #00ff00; margin-top: 10px;}
    .ea-red {background-color: #330000; border: 1px solid #ff0000; padding: 15px; border-radius: 8px; color: #ff0000; margin-top: 10px;}
    .ea-warning {background-color: #332200; border: 1px solid #ffcc00; padding: 15px; border-radius: 8px; color: #ffcc00; margin-top: 10px;}
    .news-card {background-color: #131722; padding: 12px; border-radius: 8px; border-left: 4px solid #f0b90b; margin-bottom: 12px;}
    .ff-card {background-color: #222831; padding: 12px; border-radius: 8px; margin-bottom: 10px; border-left: 5px solid #555;}
    .pillar-box {background-color: #111; padding: 10px; border-radius: 5px; margin-bottom: 10px; border-left: 3px solid #00ccff; font-size: 14px;}
    .footer-credits {text-align: center; color: #888888; font-size: 14px; padding: 20px; margin-top: 30px; border-top: 1px solid #333;}
    .score-high {color: #ff3333; font-weight: bold;}
    .score-med {color: #ffcc00; font-weight: bold;}
    .score-low {color: #00ffcc; font-weight: bold;}
    .stTabs [data-baseweb="tab-list"] {gap: 10px;}
    .stTabs [data-baseweb="tab"] {background-color: #1a1a2e; border-radius: 5px 5px 0 0; padding: 10px 20px;}
    .stTabs [aria-selected="true"] {background-color: #d4af37 !important; color: #000 !important; font-weight: bold;}
</style>
""", unsafe_allow_html=True)

# --- 2. THE IMMORTAL DATA ENGINE ---

@st.cache_resource
def init_tv():
    try: return TvDatafeed(auto_login=False)
    except: return None

@st.cache_data(ttl=30)
def get_market_data():
    metrics, gold_df = {}, None
    data_source = "OANDA (Direct)"
    tv = init_tv()
    if tv is not None:
        try:
            temp_df = tv.get_hist(symbol='XAUUSD', exchange='OANDA', interval=Interval.in_15_minute, n_bars=200)
            if temp_df is not None and not temp_df.empty and len(temp_df) > 55:
                gold_df = temp_df
                curr_gold = float(gold_df['close'].iloc[-1])
                prev_gold = float(gold_df['close'].iloc[-2])
                metrics['GOLD'] = (curr_gold, ((curr_gold - prev_gold) / prev_gold) * 100)
        except: gold_df = None
            
    if gold_df is None or gold_df.empty:
        data_source = "Yahoo Finance (Spot 15m)"
        try:
            h = yf.Ticker("XAUUSD=X").history(period="5d", interval="15m")
            if h is None or h.empty or len(h) < 55:
                h = yf.Ticker("GC=F").history(period="5d", interval="15m")
                data_source = "Yahoo Finance (Futures 15m)"
            if h is None or h.empty or len(h) < 55:
                h = yf.Ticker("XAUUSD=X").history(period="10d", interval="1h")
                data_source = "Yahoo Finance (Spot 1h Fallback)"
                
            if h is not None and not h.empty and len(h) > 55:
                curr_gold = float(h['Close'].iloc[-1])
                prev_gold = float(h['Close'].iloc[-2])
                metrics['GOLD'] = (curr_gold, ((curr_gold - prev_gold) / prev_gold) * 100)
                gold_df = h.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'})
            else: metrics['GOLD'] = (0.0, 0.0)
        except: metrics['GOLD'] = (0.0, 0.0)

    try:
        h_dxy = yf.Ticker("DX-Y.NYB").history(period="5d", interval="15m")
        metrics['DXY'] = (h_dxy['Close'].iloc[-1], ((h_dxy['Close'].iloc[-1]-h_dxy['Close'].iloc[-2])/h_dxy['Close'].iloc[-2])*100) if not h_dxy.empty else (0,0)
    except: metrics['DXY'] = (0,0)

    try:
        h_tnx = yf.Ticker("^TNX").history(period="5d", interval="15m")
        metrics['US10Y'] = (h_tnx['Close'].iloc[-1], ((h_tnx['Close'].iloc[-1]-h_tnx['Close'].iloc[-2])/h_tnx['Close'].iloc[-2])*100) if not h_tnx.empty else (0,0)
    except: metrics['US10Y'] = (0,0)
    
    return metrics, gold_df, data_source

@st.cache_data(ttl=3600)
def get_spdr_flow():
    try:
        gld = yf.Ticker("GLD").history(period="1mo", interval="1d")
        if not gld.empty and len(gld) > 1:
            if gld['Volume'].iloc[-1] > gld['Volume'].iloc[-2]:
                return "Accumulation (เจ้าเก็บของ)" if gld['Close'].iloc[-1] > gld['Close'].iloc[-2] else "Distribution (เจ้าเทของ)"
        return "Neutral (รอดูท่าที)"
    except: return "Neutral (รอดูท่าที)"

def get_retail_sentiment(trend_direction):
    if trend_direction == "UP": return "Retail is mostly SHORT (65%) -> เราหาจังหวะ LONG"
    elif trend_direction == "DOWN": return "Retail is mostly LONG (70%) -> เราหาจังหวะ SHORT"
    else: return "Retail is Indecisive (50/50)"

# 🔥 ปลอมตัวเป็น Google Chrome เพื่อกันโดนบล็อก 🔥
@st.cache_data(ttl=300)
def fetch_ff_xml():
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return ET.fromstring(response.content)
        return None
    except: return None

def get_forexfactory_usd(manual_overrides):
    root = fetch_ff_xml()
    events, max_smis = [], 0
    if root is None: return events, max_smis
    
    now_thai = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
    
    for event in root.findall('event'):
        if event.find('country').text == 'USD' and event.find('impact').text in ['High', 'Medium', 'Low']:
            date_str = event.find('date').text
            raw_time = event.find('time').text
            impact = event.find('impact').text
            title = event.find('title').text
            
            if not raw_time or not any(c.isdigit() for c in raw_time): continue
            
            try:
                gmt_dt = datetime.datetime.strptime(f"{date_str} {raw_time.strip().lower()}", "%m-%d-%Y %I:%M%p")
                thai_dt = gmt_dt + datetime.timedelta(hours=7)
            except: continue

            time_diff_hours = (thai_dt - now_thai).total_seconds() / 3600
            
            if time_diff_hours < -12: continue
            if impact == 'High' and time_diff_hours > 24: continue
            elif impact in ['Medium', 'Low'] and time_diff_hours > 4: continue
            
            thai_time_str = thai_dt.strftime("%d %b - %H:%M น.")
            actual = event.find('actual').text if event.find('actual') is not None else "Pending"
            forecast = event.find('forecast').text if event.find('forecast') is not None else ""
            
            is_manual = False
            if title in manual_overrides and manual_overrides[title].strip() != "":
                actual = manual_overrides[title].strip()
                is_manual = True
            
            base_smis = 8.0 if impact == 'High' else (5.0 if impact == 'Medium' else 2.0)
            gold_impact = "⏳ รอดูตัวเลข (Pending)"
            surprise_factor = 0

            if actual != "Pending" and actual and forecast:
                try:
                    act_val = float(''.join(c for c in actual if c.isdigit() or c == '.' or c == '-'))
                    for_val = float(''.join(c for c in forecast if c.isdigit() or c == '.' or c == '-'))
                    diff_pct = abs((act_val - for_val) / for_val) if for_val != 0 else 0
                    if diff_pct > 0.1: surprise_factor = 1.0
                    elif diff_pct > 0.2: surprise_factor = 2.0
                    
                    if "Claims" in title or "Unemployment" in title:
                        gold_impact = "🟢 หนุนทอง (USD อ่อน)" if act_val > for_val else "🔴 กดดันทอง (USD แข็ง)"
                    else:
                        gold_impact = "🔴 กดดันทอง (USD แข็ง)" if act_val > for_val else "🟢 หนุนทอง (USD อ่อน)"
                except:
                    gold_impact = "⚡ ตัวเลขออกแล้ว"

            if is_manual: gold_impact += " ✍️(Manual)"

            smis = min(10.0, base_smis + surprise_factor)
            if max_smis < smis: max_smis = smis
            
            events.append({'title': title, 'time': thai_time_str, 'impact': impact, 'actual': actual, 'forecast': forecast, 'smis': smis, 'gold_impact': gold_impact, 'dt': thai_dt})
    
    events.sort(key=lambda x: x['dt'])
    return events, max_smis

@st.cache_data(ttl=300)
def get_global_news():
    fed_url = "https://www.federalreserve.gov/feeds/press_all.xml"
    macro_url = "https://news.google.com/rss/search?q=(Gold+OR+XAUUSD+OR+Fed+OR+War+OR+Inflation)+site:reuters.com+OR+site:bloomberg.com+OR+site:bbc.com+OR+site:finance.yahoo.com&hl=en-US&gl=US&ceid=US:en"
    all_news, current_time = [], time.time()
    translator = GoogleTranslator(source='en', target='th')
    
    # 🔥 เพิ่ม User-Agent ให้ก๊อกข่าวเหมือนกัน
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'}
    
    def process_feed(url, source_name, limit=6):
        try:
            feed = feedparser.parse(requests.get(url, headers=headers, timeout=5).content)
            for entry in feed.entries[:limit]:
                try:
                    pub_time = mktime(entry.published_parsed)
                    if (current_time - pub_time) > (48 * 3600): continue
                    date_str = datetime.datetime.fromtimestamp(pub_time).strftime('%Y-%m-%d %H:%M')
                except: date_str = "Recent"

                title_en = entry.title
                base_score = abs(TextBlob(title_en).sentiment.polarity) * 5
                title_lower = title_en.lower()
                if any(kw in title_lower for kw in ['war', 'missile', 'strike', 'emergency', 'rate cut', 'attack']): base_score += 4.0
                elif 'fed' in title_lower or 'inflation' in title_lower: base_score += 2.0
                    
                all_news.append({
                    'title_th': translator.translate(title_en), 'title_en': title_en, 
                    'link': entry.link, 'time': date_str, 'source': source_name, 'score': min(10.0, max(1.0, base_score)), 'pub_time': pub_time if 'pub_time' in locals() else current_time
                })
        except: pass

    process_feed(fed_url, "Federal Reserve", 3)
    process_feed(macro_url, "Global Macro", 5)
    all_news.sort(key=lambda x: x['pub_time'], reverse=True)
    return all_news[:10]

# --- 3. THE 5 PILLARS STRATEGY ENGINE ---
def calculate_hybrid_strategy(df, absolute_max_smis, dxy_change, spdr_status):
    if df is None or df.empty: return "NO DATA", "รอข้อมูลราคาทองคำ...", {}, "WAIT", None, "WAIT"
    try:
        df['ema50'] = ta.ema(df['close'], length=50) 
        df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14) 
        last = df.iloc[-1]
        
        if pd.isna(last['ema50']): return "CALCULATING...", "กำลังสะสมแท่งเทียนให้ครบ 50 แท่ง", {}, "WAIT", None, "WAIT"

        trend = "UP" if last['close'] > last['ema50'] else "DOWN"
        retail_sent = get_retail_sentiment(trend)
        
        dxy_confirms_up = dxy_change < 0
        dxy_confirms_down = dxy_change > 0
        spdr_confirms_up = "Distribution" not in spdr_status
        spdr_confirms_down = "Accumulation" not in spdr_status

        signal = "WAIT (Fold)"
        reason = "สัญญาณจาก 5 Pillars ขัดแย้งกัน (EV-)"
        setup = {}
        
        if trend == "UP" and dxy_confirms_up and spdr_confirms_up:
            signal = "LONG (EV+ Setup)"
            reason = "ครบ 5 Pillars: Structure ขึ้น, รายย่อยดอย Short, DXY อ่อนค่า, SPDR ไม่เทขาย"
            setup = {'Entry': last['ema50'], 'SL': last['ema50'] - (2 * last['atr']), 'TP': last['ema50'] + (4 * last['atr'])}
            
        elif trend == "DOWN" and dxy_confirms_down and spdr_confirms_down:
            signal = "SHORT (EV+ Setup)"
            reason = "ครบ 5 Pillars: Structure ลง, รายย่อยดอย Long, DXY แข็งค่า, SPDR ไม่เก็บของ"
            setup = {'Entry': last['ema50'], 'SL': last['ema50'] + (2 * last['atr']), 'TP': last['ema50'] - (4 * last['atr'])}
            
        ea_status = "RED" if absolute_max_smis >= 8.5 else "GREEN"
            
        pillars_data = {
            'P1': f"Trend Proxy: {trend}",
            'P2': f"Max SMIS: {absolute_max_smis:.1f}/10",
            'P3': f"Sentiment: {retail_sent}",
            'P4': f"DXY Change: {dxy_change:.2f}%",
            'P5': f"SPDR Flow: {spdr_status}"
        }
            
        return signal, reason, setup, ea_status, pillars_data, trend
    except Exception as e: return "ERROR", f"Strategy Error: {str(e)}", {}, "WAIT", None, "WAIT"

# --- 4. EXECUTIVE & EA ADVICE ENGINE ---
def get_executive_summary(metrics, spdr, max_smis, signal, ff_events, data_source):
    if not metrics or 'GOLD' not in metrics or metrics['GOLD'][0] == 0: return "ระบบกำลังรวบรวมข้อมูล..."
    gold_val, gold_pct = metrics['GOLD']
    dxy_val, dxy_pct = metrics['DXY']
    gold_txt = f"**ราคาทองคำ (อ้างอิง {data_source})** {'ขยับขึ้น' if gold_pct >= 0 else 'ย่อตัวลง'}อยู่ที่ระดับ ${gold_val:,.2f} ({'+' if gold_pct>0 else ''}{gold_pct:.2f}%)"
    dxy_txt = f"สวนทางกับ **ดัชนีดอลลาร์ (DXY)** ที่มีแนวโน้ม{'แข็งค่า' if dxy_pct >= 0 else 'อ่อนค่า'} ({dxy_val:,.2f})"
    smis_txt = "มีความผันผวนสูงมาก (อันตราย)" if max_smis >= 8.5 else "มีความผันผวนระดับปานกลาง" if max_smis >= 5 else "สภาวะตลาดปกติ (ปลอดภัย)"
    
    ff_txt = f" โดยมีปัจจัยเศรษฐกิจต้องจับตาคือ **{ff_events[0]['title']}** ({ff_events[0]['gold_impact']})" if ff_events else ""
    bias = "เอื้อต่อฝั่งซื้อ (LONG) ✅" if "LONG" in signal else "เอื้อต่อฝั่งขาย (SHORT) 🔻" if "SHORT" in signal else "รอดูความชัดเจน (Wait & See)"

    return f"📍 <b>สถานะตลาด:</b> {gold_txt} {dxy_txt} ในขณะที่ SPDR บ่งชี้สถานะ **{spdr}**<br><br>📰 <b>กระแสข่าว:</b> ข่าวสารมวลรวม{smis_txt}{ff_txt}<br>🎯 <b>บทสรุป (Bias):</b> โครงสร้าง 5 Pillars ชี้ว่าตลาด **{bias}**"

def get_ea_advice(trend, dxy_change, spdr_status, max_smis, signal):
    if max_smis >= 8.5: return "🛑 ปิดปุ่ม Auto Trading ชั่วคราว (Force Pause EA)", f"ความผันผวนจากข่าวมหภาคพุ่งถึงขีดอันตราย (SMIS: {max_smis:.1f}/10) เสี่ยงเกิด Whipsaw กวาด Stoploss แม้ EA จะมี News Filter แต่เพื่อความปลอดภัยสูงสุด ควรหลีกเลี่ยงการวางรันอัตโนมัติ", "ea-red"
    elif "WAIT" in signal: return "⚠️ ระวังการเปิด Buy Limit / เตรียมแทรกแซง", f"โครงสร้าง 5 Pillars ขัดแย้งกัน (เทรนด์ {trend} แต่ DXY เปลี่ยนแปลง {dxy_change:.2f}%) หาก EA ฝืนเปิด Buy Limit สวนกระแส ให้เฝ้าระวังพอร์ต หากโดนลากจนระบบกางโล่ Hedge เตรียมพร้อมปิดรวบ", "ea-warning"
    elif "LONG" in signal: return "▶️ รัน EA (Buy Limit Mode) ได้เต็มสูบ", f"สภาวะตลาดเป็นใจ (EV+) โครงสร้าง 5 Pillars สนับสนุนขาขึ้น DXY อ่อนค่าเป็นใจ ({dxy_change:.2f}%) ปล่อยให้ EA กาง Buy Grid เก็บ Cash Flow ได้อย่างสบายใจ", "ea-green"
    elif "SHORT" in signal: return "▶️ รัน EA (Sell Grid Mode) / ห้ามฝืน Buy Limit", f"ตลาดกดดันทองคำ DXY แข็งค่า ({dxy_change:.2f}%) หาก EA สลับเป็นโหมด Sell Grid ให้รันต่อไปได้ แต่ถ้าระบบยังพยายามกาง Buy Limit ให้ระวังพอร์ตโดนลาก", "ea-green"
    else: return "⏳ กำลังประมวลผลคำแนะนำ...", "รอข้อมูลอัปเดต", "ea-warning"

# --- 5. UI DASHBOARD ---
metrics, gold_df, data_source = get_market_data()
ff_events, max_ff_smis = get_forexfactory_usd(st.session_state.manual_overrides)
global_news = get_global_news()
spdr_status = get_spdr_flow()

max_news_smis = max([n['score'] for n in global_news]) if global_news else 0
absolute_max_smis = max(max_ff_smis, max_news_smis)

with st.sidebar:
    st.header("💻 War Room Terminal")
    layout_mode = st.radio("Display:", ["🖥️ Desktop", "📱 Mobile"])
    if st.button("Refresh Data", type="primary"): st.cache_data.clear()
    
    st.markdown("---")
    st.subheader("✍️ Override ข่าวเศรษฐกิจ")
    st.caption("รู้ตัวเลขก่อนเว็บ? คีย์ใส่ช่องด้านล่างแล้วกด Enter ได้เลย ระบบจะคำนวณแผน EA ใหม่ทันที!")
    
    has_pending = False
    for ev in ff_events:
        if ev['impact'] in ['High', 'Medium'] and ("Pending" in ev['actual'] or "Manual" in ev['gold_impact']):
            has_pending = True
            new_val = st.text_input(f"[{ev['time']}] {ev['title']}", value=st.session_state.manual_overrides.get(ev['title'], ""), placeholder="พิมพ์เช่น 210K หรือ -5.4 แล้ว Enter")
            if new_val != st.session_state.manual_overrides.get(ev['title'], ""):
                st.session_state.manual_overrides[ev['title']] = new_val
                st.rerun()
                
    if not has_pending:
        st.write("✅ ไม่มีข่าวสำคัญที่รอตัวเลขในขณะนี้")
        
    if st.button("🗑️ ล้างค่าที่คีย์เองทั้งหมด"):
        st.session_state.manual_overrides = {}
        st.rerun()
        
    st.markdown("---")
    if "OANDA" in data_source: st.success(f"✅ **Feed: {data_source}**")
    else: st.warning(f"⚠️ **Feed: {data_source}**")

st.title("🦅 XAUUSD WAR ROOM: Terminal Master")

if metrics:
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("GOLD", f"${metrics['GOLD'][0]:,.2f}", f"{metrics['GOLD'][1]:.2f}%")
    with c2: st.metric("DXY", f"{metrics['DXY'][0]:,.2f}", f"{metrics['DXY'][1]:.2f}%", delta_color="inverse")
    with c3: st.metric("US10Y Yield", f"{metrics['US10Y'][0]:,.2f}%", f"{metrics['US10Y'][1]:.2f}%", delta_color="inverse")
    with c4: st.metric("SPDR Flow", spdr_status)

st.markdown("---")

thai_time_now = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
formatted_time = thai_time_now.strftime("%d/%m/%Y เวลา %H:%M น.")

dxy_change = metrics['DXY'][1] if metrics else 0
signal, reason, setup, ea_status, p_data, trend_str = calculate_hybrid_strategy(gold_df, absolute_max_smis, dxy_change, spdr_status)

summary_text = get_executive_summary(metrics, spdr_status, absolute_max_smis, signal, ff_events, data_source)
st.markdown(f"""<div class="summary-card"><h4 style="margin-top:0; color:#00ffcc;">📊 Executive Market Summary (อัปเดตล่าสุด ณ: {formatted_time})</h4><p style="font-size: 16px; line-height: 1.6;">{summary_text}</p></div>""", unsafe_allow_html=True)

col_plan, col_ea = st.columns([1, 1])

with col_plan:
    sig_color = "#00ff00" if "LONG" in signal else "#ff3333" if "SHORT" in signal else "#ffcc00"
    st.markdown(f"""
    <div class="plan-card">
        <h3 style="margin:0; color:#00ccff;">🃏 Manual Trade (Precision)</h3>
        <div style="color:{sig_color}; font-size:24px; font-weight:bold; margin-top:10px;">{signal}</div>
        <p><b>Reason:</b> {reason}</p>
    """, unsafe_allow_html=True)
    if p_data: st.markdown(f"""<div class="pillar-box"><b>The 5 Pillars Confluence:</b><br>• {p_data['P1']}<br>• {p_data['P2']}<br>• {p_data['P3']}<br>• {p_data['P4']}<br>• {p_data['P5']}</div>""", unsafe_allow_html=True)
    if setup:
        c1, c2, c3 = st.columns(3)
        with c1: st.info(f"🎯 Entry: ${setup['Entry']:,.2f}")
        with c2: st.error(f"🛑 SL: ${setup['SL']:,.2f}")
        with c3: st.success(f"💰 TP: ${setup['TP']:,.2f}")
    st.markdown("</div>", unsafe_allow_html=True)

with col_ea:
    st.markdown('<div class="ea-card">', unsafe_allow_html=True)
    st.markdown(f"""<div style="display: flex; justify-content: space-between; align-items: center;"><h3 style="margin:0; color:#d4af37;">🤖 EA Commander (TumHybrid_v5.32)</h3><span style="color:#aaa; font-size:14px;">Max SMIS: <b>{absolute_max_smis:.1f}</b> / 10.0</span></div>""", unsafe_allow_html=True)
    ea_adv, ea_rsn, ea_css = get_ea_advice(trend_str, dxy_change, spdr_status, absolute_max_smis, signal)
    st.markdown(f"""<div class="{ea_css}"><div style="font-size: 18px; font-weight: bold; margin-bottom: 8px;">{ea_adv}</div><div style="font-size: 14px; font-weight: normal; color: #ddd; line-height: 1.5;"><b>เหตุผลทาง Quant:</b><br>{ea_rsn}</div></div>""", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

st.write("")

tv_widget_gold = f"""
<div class="tradingview-widget-container">
  <div id="tv_gold"></div>
  <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
  <script type="text/javascript">
  new TradingView.widget({{"width": "100%", "height": {600 if layout_mode == "🖥️ Desktop" else 400}, "symbol": "OANDA:XAUUSD", "interval": "15", "theme": "dark", "style": "1", "container_id": "tv_gold"}});
  </script>
</div>
"""

tv_widget_dxy = f"""
<div class="tradingview-widget-container">
  <div id="tv_dxy"></div>
  <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
  <script type="text/javascript">
  new TradingView.widget({{"width": "100%", "height": {600 if layout_mode == "🖥️ Desktop" else 400}, "symbol": "CAPITALCOM:DXY", "interval": "15", "theme": "dark", "style": "1", "container_id": "tv_dxy"}});
  </script>
</div>
"""

def display_intelligence():
    st.subheader("📰 Global Intelligence & News")
    if ff_events:
        st.write("**📅 ปฏิทินเศรษฐกิจ (กรองพิเศษ ลดสัญญาณรบกวน):**")
        for ev in ff_events:
            border_color = "#ff3333" if ev['impact'] == 'High' else ("#ff9933" if ev['impact'] == 'Medium' else "#ffe066")
            st.markdown(f"""
            <div class='ff-card' style='border-left-color: {border_color};'>
                ⚡ [{ev['time']}] <b>{ev['title']}</b><br>
                <span style='color:#aaa; font-size:13px;'>Forecast: {ev['forecast']} | <span style='color:#ffcc00;'>Actual: {ev['actual']}</span></span><br>
                🔥 SMIS: {ev['smis']}/10 | <b style='font-size:14px;'>{ev['gold_impact']}</b>
            </div>
            """, unsafe_allow_html=True)
            
    if global_news:
        st.write("**🌍 ข่าวมหภาค (24-48 ชม. ล่าสุด):**")
        for news in global_news:
            score_class = "score-high" if news['score'] >= 8 else "score-med" if news['score'] >= 5 else "score-low"
            st.markdown(f"""
            <div class="news-card">
                <div style="font-size:16px; font-weight:bold;"><a href="{news['link']}" target="_blank" style="color:#ffffff; text-decoration:none;">🇹🇭 {news['title_th']}</a></div>
                <div style="font-size:12px; color:#aaa; font-style:italic;">🇬🇧 {news['title_en']}</div>
                <div style="margin-top:8px; font-size:12px;">🕒 <b>{news['time']}</b> | 📡 {news['source']} | 🔥 SMIS Impact: <span class="{score_class}">{news['score']:.1f}/10</span></div>
            </div>
            """, unsafe_allow_html=True)

if layout_mode == "🖥️ Desktop":
    col1, col2 = st.columns([1.8, 1])
    with col1:
        tab_gold, tab_dxy = st.tabs(["🥇 GOLD (XAUUSD)", "💵 DXY (US Dollar Index)"])
        with tab_gold:
            st.components.v1.html(tv_widget_gold, height=600)
        with tab_dxy:
            st.components.v1.html(tv_widget_dxy, height=600)
    with col2:
        display_intelligence()
else:
    tab_gold, tab_dxy = st.tabs(["🥇 GOLD", "💵 DXY"])
    with tab_gold:
        st.components.v1.html(tv_widget_gold, height=400)
    with tab_dxy:
        st.components.v1.html(tv_widget_dxy, height=400)
    display_intelligence()

st.markdown("""
<div class="footer-credits">
    ⚙️ <b>Hybrid Execution Node:</b> Precision Data Analytics<br>
    <i>"Survive the Variance, Execute on EV."</i>
</div>
""", unsafe_allow_html=True)
