import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import calendar

# --- PAGE CONFIG ---
st.set_page_config(page_title="Abra PHO | Vaccine Inventory", layout="wide", page_icon="💉")

# --- DATA PROCESSING ---
@st.cache_data
def load_and_prep_data():
    # To connect directly to your live Google Sheet later, you would use:
    # url = "https://docs.google.com/spreadsheets/d/1CYarF3POk_UYyXxff2jj-k803nfBA8nhghQ-9OAz0Y4/export?format=csv&gid=0"
    # df = pd.read_csv(url)
    # However, because your sheet is a pivot matrix, we use a flattened version of your exact data for the dashboard engine:
    
    data = [
        {"RHU": "PHO", "Vaccine": "BCG", "Lot": "373MA085", "Expiry": "1/26", "Qty": 77},
        {"RHU": "BANGUED", "Vaccine": "PENTAVALENT", "Lot": "28540140", "Expiry": "6/26", "Qty": 107},
        {"RHU": "BOLINEY", "Vaccine": "HEPA B", "Lot": "0333L010", "Expiry": "9/27", "Qty": 33},
        {"RHU": "BUCAY", "Vaccine": "BCG", "Lot": "373G0110", "Expiry": "4/26", "Qty": 40},
        {"RHU": "BUCAY", "Vaccine": "bOPV", "Lot": "E53014101", "Expiry": "7/27", "Qty": 37},
        {"RHU": "DANGLAS", "Vaccine": "BCG", "Lot": "373G0110", "Expiry": "4/26", "Qty": 20},
        {"RHU": "DOLORES", "Vaccine": "PENTAVALENT", "Lot": "12854X007B", "Expiry": "8/26", "Qty": 47},
        {"RHU": "LA PAZ", "Vaccine": "IPV", "Lot": "139E5V014", "Expiry": "11/26", "Qty": 215},
        {"RHU": "LAGANGILANG", "Vaccine": "BCG", "Lot": "373G0110", "Expiry": "4/26", "Qty": 90},
        {"RHU": "LICUAN-BAAY", "Vaccine": "PENTAVALENT", "Lot": "2854Z033", "Expiry": "3/27", "Qty": 31},
        {"RHU": "MANABO", "Vaccine": "HEPA B", "Lot": "0334L0058", "Expiry": "9/27", "Qty": 50},
        {"RHU": "MANABO", "Vaccine": "MR", "Lot": "0163W031", "Expiry": "11/26", "Qty": 60},
        {"RHU": "PIDIGAN", "Vaccine": "PENTAVALENT", "Lot": "12854X007B", "Expiry": "8/26", "Qty": 48},
        {"RHU": "SALLAPADAN", "Vaccine": "IPV", "Lot": "139E5V014", "Expiry": "11/26", "Qty": 30},
        {"RHU": "TAYUM", "Vaccine": "HEPA B", "Lot": "0334L0058", "Expiry": "9/27", "Qty": 55},
        {"RHU": "TUBO", "Vaccine": "BCG", "Lot": "373G0110", "Expiry": "4/26", "Qty": 60},
        {"RHU": "APH", "Vaccine": "HEPA B", "Lot": "0333L010", "Expiry": "9/27", "Qty": 15},
        {"RHU": "PHO", "Vaccine": "HPV", "Lot": "Y016840", "Expiry": "2/27", "Qty": 340},
        {"RHU": "PHO", "Vaccine": "TD", "Lot": "0222600124", "Expiry": "12/25", "Qty": 409},
    ]
    df = pd.DataFrame(data)
    
    # Convert MM/YY to actual end-of-month datetime for accurate math
    def parse_expiry(expiry_str):
        month, year = map(int, expiry_str.split('/'))
        year += 2000 # Convert 26 to 2026
        last_day = calendar.monthrange(year, month)[1]
        return pd.to_datetime(f"{year}-{month:02d}-{last_day}")
        
    df['Expiry Date'] = df['Expiry'].apply(parse_expiry)
    
    # Calculate days from today (Current system time is Feb 2026)
    today = pd.to_datetime("today")
    df['Days to Expiry'] = (df['Expiry Date'] - today).dt.days
    
    def get_status(days):
        if days < 0:
            return '🚨 EXPIRED'
        elif days <= 60:
            return '🔴 CRITICAL (< 2 Mos)'
        elif days <= 120:
            return '🟡 WARNING (2-4 Mos)'
        else:
            return '🟢 SAFE'
            
    df['Status'] = df['Days to Expiry'].apply(get_status)
    return df

df = load_and_prep_data()

# --- CSS STYLING ---
st.markdown("""
    <style>
    .main-header { color: #4cc9f0; font-weight: bold; margin-bottom: 0px; }
    .sub-header { color: #a9d6e5; margin-top: 0px; margin-bottom: 30px; font-style: italic; }
    div[data-testid="stMetricValue"] { color: #BC13FE !important; }
    </style>
""", unsafe_allow_html=True)

# --- DASHBOARD HEADER ---
st.markdown('<h1 class="main-header">🏥 PHO Abra: Vaccine Inventory Control</h1>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Live logistics tracking across all 27 Municipalities & Provincial Hubs</p>', unsafe_allow_html=True)

# --- TOP METRICS ---
col1, col2, col3, col4 = st.columns(4)
total_vax = df['Qty'].sum()
expired_vax = df[df['Status'] == '🚨 EXPIRED']['Qty'].sum()
critical_vax = df[df['Status'] == '🔴 CRITICAL (< 2 Mos)']['Qty'].sum()
active_rhus = df['RHU'].nunique()

col1.metric("Total Doses (Recorded)", f"{total_vax:,}")
col2.metric("Active Locations", f"{active_rhus} / 29")
col3.metric("🚨 Expired Doses (Do Not Use)", f"{expired_vax:,}")
col4.metric("🔴 Critical Stock (<60 Days)", f"{critical_vax:,}")

st.markdown("---")

# --- MAIN CONTENT TABS ---
tab1, tab2, tab3 = st.tabs(["⚠️ Expiry Radar", "🗺️ RHU Distribution", "📋 Raw Data Matrix"])

with tab1:
    st.subheader("Action Required: Expiring or Expired Batches")
    
    # Filter for anything not safe
    urgent_df = df[df['Status'] != '🟢 SAFE'].sort_values(by='Days to Expiry')
    
    def highlight_rows(row):
        if 'EXPIRED' in row['Status']:
            return ['background-color: rgba(255, 0, 0, 0.3); color: #ff4b4b; font-weight: bold;'] * len(row)
        elif 'CRITICAL' in row['Status']:
            return ['background-color: rgba(255, 100, 0, 0.2); color: #ff8c00;'] * len(row)
        elif 'WARNING' in row['Status']:
            return ['background-color: rgba(255, 200, 0, 0.1); color: #ffd700;'] * len(row)
        return [''] * len(row)

    styled_df = urgent_df[['RHU', 'Vaccine', 'Lot', 'Expiry Date', 'Days to Expiry', 'Qty', 'Status']].style.apply(highlight_rows, axis=1)
    
    st.dataframe(
        styled_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Expiry Date": st.column_config.DateColumn("Exact Expiry", format="MMM DD, YYYY")
        }
    )

with tab2:
    st.subheader("Vaccine Distribution by Municipality")
    
    c1, c2 = st.columns([2, 1])
    with c1:
        # Bar chart showing which RHUs have the most stock
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
        # Pie chart showing breakdown of vaccines
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
    st.subheader("Complete Inventory Log")
    
    # Filter tools for the raw data
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
