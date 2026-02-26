import streamlit as st
import pandas as pd
import plotly.express as px
from streamlit_gsheets import GSheetsConnection
import calendar

# --- PAGE CONFIG ---
st.set_page_config(page_title="Abra PHO | Vaccine Inventory", layout="wide", page_icon="💉")

# --- SECURE DATA CONNECTION & PARSING ---
# Caches data for 60 seconds to protect API limits
@st.cache_data(ttl=60) 
def load_and_prep_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    raw_df = conn.read(
        spreadsheet="https://docs.google.com/spreadsheets/d/1CYarF3POk_UYyXxff2jj-k803nfBA8nhghQ-9OAz0Y4",
        worksheet="PHYSICAL INVENTORY1",
        header=None
    )
    
    # EXACT COORDINATES FROM DEBUG SCRIPT
    vaccines = pd.Series(raw_df.iloc[0, 2:]).ffill().values 
    lots = raw_df.iloc[2, 2:].values
    expiries = raw_df.iloc[3, 2:].values
    
    grid_df = raw_df.iloc[4:, 1:].copy()
    
    col_indices = list(range(len(vaccines)))
    grid_df.columns = ['RHU'] + col_indices
    
    grid_df = grid_df.dropna(subset=['RHU'])
    grid_df = grid_df[~grid_df['RHU'].astype(str).str.contains('TOTAL', case=False, na=False)]
    
    # MELT THE MATRIX
    melted = grid_df.melt(id_vars=['RHU'], var_name='ColIndex', value_name='Qty')
    
    # Map the metadata
    melted['Vaccine'] = [vaccines[i] for i in melted['ColIndex']]
    melted['Lot'] = [str(lots[i]) for i in melted['ColIndex']]
    melted['Expiry'] = [str(expiries[i]) for i in melted['ColIndex']]
    
    # Clean up the data & REMOVE DECIMALS
    melted['Qty'] = pd.to_numeric(melted['Qty'], errors='coerce').fillna(0)
    clean_df = melted[melted['Qty'] > 0].copy()
    clean_df['Qty'] = clean_df['Qty'].astype(int) # Forces whole numbers
    
    # BULLETPROOF DATE PARSING
    def parse_expiry(val):
        try:
            val_str = str(val).strip()
            if '/' in val_str:
                parts = val_str.split('/')
                if len(parts) == 2:
                    month, year = int(parts[0]), int(parts[1])
                    if year < 100:
                        year += 2000
                    last_day = calendar.monthrange(year, month)[1]
                    return pd.to_datetime(f"{year}-{month:02d}-{last_day}")
            return pd.to_datetime(val)
        except:
            return pd.NaT 
            
    clean_df['Expiry Date'] = clean_df['Expiry'].apply(parse_expiry)
    clean_df['Expiry Date'] = pd.to_datetime(clean_df['Expiry Date'], errors='coerce')
    
    today = pd.Timestamp.now().normalize()
    clean_df['Days to Expiry'] = (clean_df['Expiry Date'] - today).dt.days
    
    def get_status(days):
        if pd.isna(days):
            return '⚪ UNKNOWN'
        elif days < 0:
            return '🚨 EXPIRED'
        elif days <= 60:
            return '🔴 CRITICAL (< 2 Mos)'
        elif days <= 120:
            return '🟡 WARNING (2-4 Mos)'
        else:
            return '🟢 SAFE'
            
    clean_df['Status'] = clean_df['Days to Expiry'].apply(get_status)
    return clean_df

# Load the data
df = load_and_prep_data()

# --- CSS STYLING ---
st.markdown("""
    <style>
    .main-header { color: #4cc9f0; font-weight: bold; margin-bottom: 0px; }
    .sub-header { color: #a9d6e5; margin-top: 0px; margin-bottom: 15px; font-style: italic; }
    div[data-testid="stMetricValue"] { color: #BC13FE !important; }
    </style>
""", unsafe_allow_html=True)

# --- DASHBOARD HEADER ---
st.markdown('<h1 class="main-header">🏥 PHO Abra: Vaccine Inventory Control</h1>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Live logistics tracking across all 27 Municipalities & Provincial Hubs</p>', unsafe_allow_html=True)

# THE MANUAL REFRESH BUTTON
if st.button("🔄 Sync Live Data from Google Sheets"):
    st.cache_data.clear()
    st.rerun()

# --- TOP METRICS ---
col1, col2, col3, col4 = st.columns(4)
total_vax = df['Qty'].sum()
expired_vax = df[df['Status'] == '🚨 EXPIRED']['Qty'].sum()
critical_vax = df[df['Status'] == '🔴 CRITICAL (< 2 Mos)']['Qty'].sum()
active_rhus = df['RHU'].nunique()

col1.metric("Total Doses Active", f"{total_vax:,}")
col2.metric("Locations with Stock", f"{active_rhus} / 29")
col3.metric("🚨 Expired Doses", f"{expired_vax:,}")
col4.metric("🔴 Critical Stock (<60 Days)", f"{critical_vax:,}")

st.markdown("---")

# --- MAIN CONTENT TABS ---
tab1, tab2, tab3 = st.tabs(["⚠️ Expiry Radar", "🗺️ RHU Distribution", "📋 Raw Data Matrix"])

with tab1:
    st.subheader("Action Required: Expiring or Expired Batches")
    
    urgent_df = df[df['Status'] != '🟢 SAFE'].sort_values(by='Days to Expiry')
    
    def highlight_rows(row):
        if 'EXPIRED' in row['Status']:
            return ['background-color: rgba(255, 0, 0, 0.3); color: #ff4b4b; font-weight: bold;'] * len(row)
        elif 'CRITICAL' in row['Status']:
            return ['background-color: rgba(255, 100, 0, 0.2); color: #ff8c00;'] * len(row)
        elif 'WARNING' in row['Status']:
            return ['background-color: rgba(255, 200, 0, 0.1); color: #ffd700;'] * len(row)
        return [''] * len(row)

    if not urgent_df.empty:
        styled_df = urgent_df[['RHU', 'Vaccine', 'Lot', 'Expiry Date', 'Days to Expiry', 'Qty', 'Status']].style.apply(highlight_rows, axis=1)
        st.dataframe(
            styled_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Expiry Date": st.column_config.DateColumn("Exact Expiry", format="MMM DD, YYYY")
            }
        )
    else:
        st.success("All inventory is currently marked as Safe!")

with tab2:
    st.subheader("Vaccine Distribution by Municipality")
    
    c1, c2 = st.columns([2, 1])
    with c1:
        rhu_totals = df.groupby('RHU')['Qty'].sum().reset_index().sort_values(by='Qty', ascending=False)
        fig_rhu = px.bar(
            rhu_totals, 
            x='RHU', 
            y='Qty', 
            color='Qty',
            color_continuous_scale='Purpor',
            template='plotly_dark',
            title="Total Doses per Location"
        )
        st.plotly_chart(fig_rhu, use_container_width=True)
        
    with c2:
        vax_totals = df.groupby('Vaccine')['Qty'].sum().reset_index()
        fig_vax = px.pie(
            vax_totals, 
            names='Vaccine', 
            values='Qty', 
            hole=0.4,
            template='plotly_dark',
            title="Overall Vaccine Composition"
        )
        st.plotly_chart(fig_vax, use_container_width=True)

with tab3:
    st.subheader("Live Database Query")
    
    f_col1, f_col2 = st.columns(2)
    with f_col1:
        sel_rhu = st.multiselect("Filter by RHU:", options=sorted(df['RHU'].unique()))
    with f_col2:
        sel_vax = st.multiselect("Filter by Vaccine:", options=sorted(df['Vaccine'].unique()))
        
    filtered_raw = df
    if sel_rhu:
        filtered_raw = filtered_raw[filtered_raw['RHU'].isin(sel_rhu)]
    if sel_vax:
        filtered_raw = filtered_raw[filtered_raw['Vaccine'].isin(sel_vax)]
        
    st.dataframe(filtered_raw[['RHU', 'Vaccine', 'Lot', 'Expiry', 'Qty', 'Status']], use_container_width=True, hide_index=True)
