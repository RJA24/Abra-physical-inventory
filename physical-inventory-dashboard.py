import streamlit as st
import pandas as pd
import plotly.express as px
from streamlit_gsheets import GSheetsConnection
import calendar
import datetime
import smtplib
from email.mime.text import MIMEText

# --- PAGE CONFIG ---
st.set_page_config(page_title="Abra PHO | Vaccine Inventory", layout="wide", page_icon="💉")

# --- SECURE DATA CONNECTION & PARSING ---
@st.cache_data(ttl=300) 
def load_and_prep_data():
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        raw_df = conn.read(
            spreadsheet="https://docs.google.com/spreadsheets/d/1CYarF3POk_UYyXxff2jj-k803nfBA8nhghQ-9OAz0Y4",
            worksheet="PHYSICAL INVENTORY1",
            header=None,
            ttl=300
        )
    except Exception as e:
        st.error(f"🚨 Connection Failed: {e}")
        st.stop()
    
    # Metadata Parsing
    vaccines = pd.Series(raw_df.iloc[0, 2:]).ffill().values 
    lots = raw_df.iloc[2, 2:].values
    expiries = raw_df.iloc[3, 2:].values
    
    grid_df = raw_df.iloc[4:, 1:].copy()
    col_indices = list(range(len(vaccines)))
    grid_df.columns = ['RHU'] + col_indices
    grid_df = grid_df.dropna(subset=['RHU'])
    grid_df = grid_df[~grid_df['RHU'].astype(str).str.contains('TOTAL', case=False, na=False)]
    
    # Reshaping Data
    melted = grid_df.melt(id_vars=['RHU'], var_name='ColIndex', value_name='Qty')
    melted['Vaccine'] = [vaccines[i] for i in melted['ColIndex']]
    melted['Lot'] = [str(lots[i]) for i in melted['ColIndex']]
    melted['Expiry'] = [str(expiries[i]) for i in melted['ColIndex']]
    melted['Qty'] = pd.to_numeric(melted['Qty'], errors='coerce').fillna(0).astype(int)
    
    # Stockout Logic
    critical_vaxes = ['BCG', 'bOPV', 'PENTAVALENT', 'MR']
    crit_df = melted[melted['Vaccine'].isin(critical_vaxes)]
    rhu_vax_totals = crit_df.groupby(['RHU', 'Vaccine'])['Qty'].sum().reset_index()
    stockouts_df = rhu_vax_totals[rhu_vax_totals['Qty'] == 0].copy()
    
    # Expiry Logic
    clean_df = melted[melted['Qty'] > 0].copy()
    def parse_expiry(val):
        try:
            val_str = str(val).strip()
            if '/' in val_str:
                parts = val_str.split('/')
                if len(parts) == 2:
                    month, year = int(parts[0]), int(parts[1])
                    if year < 100: year += 2000
                    last_day = calendar.monthrange(year, month)[1]
                    return pd.to_datetime(f"{year}-{month:02d}-{last_day}")
            return pd.to_datetime(val)
        except: return pd.NaT 
            
    clean_df['Expiry Date'] = clean_df['Expiry'].apply(parse_expiry)
    clean_df['Expiry Date'] = pd.to_datetime(clean_df['Expiry Date'], errors='coerce').dt.tz_localize(None)

    # --- LOCKING TO PHILIPPINE STANDARD TIME (UTC+8) ---
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    pst_now = utc_now + datetime.timedelta(hours=8)
    today = pd.Timestamp(pst_now).normalize().tz_localize(None)
    
    clean_df['Days to Expiry'] = (clean_df['Expiry Date'] - today).dt.days
    
    def get_status(days):
        if pd.isna(days): return '⚪ UNKNOWN'
        elif days < 0: return '🚨 EXPIRED'
        elif days <= 60: return '🔴 CRITICAL (< 2 Mos)'
        elif days <= 120: return '🟡 WARNING (2-4 Mos)'
        else: return '🟢 SAFE'
            
    clean_df['Status'] = clean_df['Days to Expiry'].apply(get_status)
    load_time = pst_now.strftime("%I:%M %p")
    return clean_df, stockouts_df, load_time

# --- EMAIL ALERT FUNCTION ---
def send_executive_alert(urgent_df, stockouts_df):
    try:
        # Pulls secure credentials from Streamlit Secrets
        email_sender = st.secrets["email"]["sender"]
        email_password = st.secrets["email"]["password"]
        email_receiver = st.secrets["email"]["receiver"]
        
        pst_now = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)).strftime('%b %d, %Y')
        subject = f"🚨 URGENT: Abra PHO Logistics Alert - {pst_now}"
        
        body = f"Abra Provincial Health Office - Automated Logistics Report\nGenerated on: {pst_now}\n\n"
        
        if not stockouts_df.empty:
            body += "⚠️ CRITICAL ZERO-STOCK ALERTS (Primary Vaccines):\n"
            summary = stockouts_df.groupby('RHU')['Vaccine'].apply(lambda x: ', '.join(x)).reset_index()
            body += summary.to_string(index=False) + "\n\n"
            
        if not urgent_df.empty:
            body += "🚨 EXPIRING BATCHES ACTION REQUIRED:\n"
            body += urgent_df[['RHU', 'Vaccine', 'Lot', 'Days to Expiry', 'Qty']].to_string(index=False)
            
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = email_sender
        msg['To'] = email_receiver

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp_server:
            smtp_server.login(email_sender, email_password)
            smtp_server.sendmail(email_sender, email_receiver, msg.as_string())
            
        return True
    except Exception as e:
        st.error(f"Email failed to send. Error: {e}")
        return False

# --- INITIALIZE DATA ---
df_init, stockouts_init, last_sync = load_and_prep_data()
urgent_data = df_init[df_init['Status'] != '🟢 SAFE'].sort_values(by='Days to Expiry')

# --- SIDEBAR & GLOBAL FILTERS ---
with st.sidebar:
    st.title("🏥 Abra PHO")
    st.markdown("**Cold Chain Management System**")
    st.info(f"🕒 Last Sync (PST): {last_sync}")
    
    if st.button("🔄 Force Refresh Now"):
        st.cache_data.clear()
        st.rerun()
        
    st.markdown("---")
    st.subheader("Automated Reports")
    if st.button("📧 Send Alert to PHO Lead", type="primary"):
        with st.spinner("Transmitting logistics report..."):
            success = send_executive_alert(urgent_data, stockouts_init)
            if success:
                st.success("✅ Report successfully emailed!")
        
    st.markdown("---")
    st.subheader("Global Filters")
    global_rhu_filter = st.multiselect(
        "Filter by Municipality:",
        options=sorted(df_init['RHU'].unique()),
        help="Filters all charts and tables across the entire dashboard."
    )

# Apply Global Filter
df = df_init.copy()
stockouts = stockouts_init.copy()
if global_rhu_filter:
    df = df[df['RHU'].isin(global_rhu_filter)]
    stockouts = stockouts[stockouts['RHU'].isin(global_rhu_filter)]

# --- CSS STYLING ---
st.markdown("""
    <style>
    .main-header { color: #4cc9f0; font-weight: bold; margin-bottom: 0px; }
    .sub-header { color: #a9d6e5; margin-top: 0px; margin-bottom: 20px; font-style: italic; }
    div[data-testid="stMetricValue"] { color: #BC13FE !important; }
    </style>
""", unsafe_allow_html=True)

# --- HEADER ---
st.markdown('<h1 class="main-header">🏥 Abra: Physical Vaccine Inventory</h1>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Live Provincial Logistics Command Center</p>', unsafe_allow_html=True)

# --- TOP METRICS ---
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Active Doses", f"{df['Qty'].sum():,}")
col2.metric("Locations Reported", f"{df['RHU'].nunique()}")
col3.metric("🚨 Expired", f"{df[df['Status'] == '🚨 EXPIRED']['Qty'].sum():,}")
col4.metric("🔴 Critical (<60d)", f"{df[df['Status'] == '🔴 CRITICAL (< 2 Mos)']['Qty'].sum():,}")
col5.metric("⚠️ Stockout RHUs", len(stockouts['RHU'].unique()))

st.markdown("---")

# --- TABS ---
tab1, tab2, tab3, tab4, tab5 = st.tabs(["⚠️ Expiry Radar", "🗺️ Distribution", "📋 Raw Data Matrix", "🔍 Recall Trace", "🚨 Stockouts"])

with tab1:
    st.subheader("Action Required: Expiring or Expired Batches")
    urgent_df = df[df['Status'] != '🟢 SAFE'].sort_values(by='Days to Expiry')
    
    if not urgent_df.empty:
        c1, c2 = st.columns([1, 2])
        with c1:
            st.metric("Batches at Risk", len(urgent_df))
            csv = urgent_df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Export Urgent List", csv, "urgent_list.csv", "text/csv")
        with c2:
            fig_status = px.bar(urgent_df['Status'].value_counts().reset_index(), x='Status', y='count', 
                               color='Status', color_discrete_map={'🚨 EXPIRED': '#ff4b4b', '🔴 CRITICAL (< 2 Mos)': '#ff8c00', '🟡 WARNING (2-4 Mos)': '#ffd700'},
                               template='plotly_dark', height=200)
            st.plotly_chart(fig_status, use_container_width=True)

        st.dataframe(urgent_df[['RHU', 'Vaccine', 'Lot', 'Expiry Date', 'Qty', 'Status']], use_container_width=True, hide_index=True)
    else:
        st.success("✅ All stock is currently within safe expiry limits.")

with tab2:
    st.subheader("Inventory by Municipality")
    rhu_totals = df.groupby('RHU')['Qty'].sum().reset_index().sort_values(by='Qty', ascending=False)
    fig_rhu = px.bar(rhu_totals, x='RHU', y='Qty', color='Qty', color_continuous_scale='Purpor', template='plotly_dark')
    st.plotly_chart(fig_rhu, use_container_width=True)

with tab3:
    st.subheader("Searchable Data Grid")
    vax_filter = st.multiselect("Filter by Vaccine Type:", options=sorted(df['Vaccine'].unique()))
    grid_view = df.copy()
    if vax_filter: grid_view = grid_view[grid_view['Vaccine'].isin(vax_filter)]
    st.dataframe(grid_view[['RHU', 'Vaccine', 'Lot', 'Expiry', 'Qty', 'Status']], use_container_width=True, hide_index=True)

with tab4:
    st.subheader("🔍 Product Recall Search")
    search_lot = st.text_input("Enter Lot Number (e.g., 12854X007B):")
    if search_lot:
        res = df[df['Lot'].str.contains(search_lot, case=False, na=False)]
        if not res.empty:
            st.warning(f"Found {res['Qty'].sum()} doses of Lot {search_lot}")
            st.dataframe(res[['RHU', 'Vaccine', 'Qty', 'Status']], use_container_width=True, hide_index=True)
        else: st.success("No active doses found for this Lot.")

with tab5:
    st.subheader("🚨 Critical Stockouts")
    if not stockouts.empty:
        st.error(f"Alert: {len(stockouts['RHU'].unique())} municipalities are missing primary vaccine types.")
        summary = stockouts.groupby('RHU')['Vaccine'].apply(lambda x: ', '.join(x)).reset_index()
        summary.rename(columns={'Vaccine': 'Missing (Total Stock = 0)'}, inplace=True)
        st.dataframe(summary, use_container_width=True, hide_index=True)
    else: st.success("All RHUs have primary vaccine coverage.")
