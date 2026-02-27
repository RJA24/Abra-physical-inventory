import streamlit as st
import pandas as pd
import plotly.express as px
from streamlit_gsheets import GSheetsConnection
import calendar
import datetime

# --- PAGE CONFIG ---
st.set_page_config(page_title="Abra PHO | Vaccine Inventory", layout="wide", page_icon="💉")

# --- ABRA GEOSPATIAL DATA ---
ABRA_COORDS = {
    'BANGUED': [17.5958, 120.6186], 'BOLINEY': [17.3917, 120.8167], 'BUCAY': [17.5333, 120.7333],
    'BUCLOC': [17.4500, 120.8333], 'DAGUIOMAN': [17.4500, 120.9333], 'DANGLAS': [17.6333, 120.5833],
    'DOLORES': [17.6500, 120.6500], 'LA PAZ': [17.6667, 120.6333], 'LACUB': [17.6667, 120.9333],
    'LAGANGILANG': [17.6167, 120.7333], 'LAGAYAN': [17.7167, 120.6333], 'LANGIDEN': [17.5833, 120.5667],
    'LICUAN-BAAY': [17.5667, 120.8833], 'LUBA': [17.3167, 120.6833], 'MALIBCONG': [17.5667, 120.9833],
    'MANABO': [17.4333, 120.7000], 'PEÑARRUBIA': [17.5667, 120.6333], 'PIDIGAN': [17.5667, 120.5833],
    'PILAR': [17.4167, 120.6000], 'SALLAPADAN': [17.4500, 120.7667], 'SAN ISIDRO': [17.4667, 120.6000],
    'SAN JUAN': [17.6833, 120.6167], 'SAN QUINTIN': [17.5333, 120.5167], 'TAYUM': [17.6000, 120.6500],
    'TINEG': [17.7833, 120.9333], 'TUBO': [17.2333, 120.8000], 'VILLAVICIOSA': [17.4333, 120.6333]
}

# --- SECURE DATA CONNECTION & PARSING ---
@st.cache_data(ttl=300) 
def load_and_prep_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    try:
        raw_df = conn.read(
            spreadsheet="https://docs.google.com/spreadsheets/d/1CYarF3POk_UYyXxff2jj-k803nfBA8nhghQ-9OAz0Y4",
            worksheet="PHYSICAL INVENTORY1",
            header=None,
            ttl=300
        )
        
        try:
            history_df = conn.read(
                spreadsheet="https://docs.google.com/spreadsheets/d/1CYarF3POk_UYyXxff2jj-k803nfBA8nhghQ-9OAz0Y4",
                worksheet="HISTORY LOG",
                ttl=300
            )
        except:
            history_df = pd.DataFrame(columns=['Date', 'RHU', 'Vaccine', 'Qty'])

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
    
    melted['RHU_Clean'] = melted['RHU'].astype(str).str.strip().str.upper()
    
    # --- AUTOMATED 7-DAY HISTORICAL SNAPSHOT LOGIC ---
    if history_df.empty or 'Date' not in history_df.columns:
        history_df = pd.DataFrame(columns=['Date', 'RHU', 'Vaccine', 'Qty'])

    history_df['Date_Temp'] = pd.to_datetime(history_df['Date'], errors='coerce')
    last_snapshot_date = history_df['Date_Temp'].max()

    pst_now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)
    today_date = pd.Timestamp(pst_now).normalize().tz_localize(None)

    needs_update = False
    if pd.isna(last_snapshot_date):
        needs_update = True
    elif (today_date - last_snapshot_date).days >= 7:
        needs_update = True

    if needs_update:
        snap_df = melted.groupby(['RHU', 'Vaccine'])['Qty'].sum().reset_index()
        snap_df.insert(0, 'Date', pst_now.strftime('%Y-%m-%d'))

        history_df = history_df.drop(columns=['Date_Temp'])
        updated_history = pd.concat([history_df, snap_df], ignore_index=True)

        try:
            conn.update(worksheet="HISTORY LOG", data=updated_history)
            history_df = updated_history
        except Exception as e:
            print(f"Robot failed to write to History Log: {e}")
    else:
        history_df = history_df.drop(columns=['Date_Temp'])
        
    # --- END AUTOMATED SNAPSHOT ---

    # Stockout Logic (All Vaccines)
    rhu_vax_totals = melted.groupby(['RHU', 'RHU_Clean', 'Vaccine'])['Qty'].sum().reset_index()
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

    clean_df['Days to Expiry'] = (clean_df['Expiry Date'] - today_date).dt.days
    
    def get_status(days):
        if pd.isna(days): return '⚪ UNKNOWN'
        elif days < 0: return '🚨 EXPIRED'
        elif days <= 60: return '🔴 CRITICAL (< 2 Mos)'
        elif days <= 120: return '🟡 WARNING (2-4 Mos)'
        else: return '🟢 SAFE'
            
    clean_df['Status'] = clean_df['Days to Expiry'].apply(get_status)
    load_time = pst_now.strftime("%I:%M %p")
    
    # Need to return original melted df to Tab 2 for mapping zero quantities
    return clean_df, stockouts_df, history_df, load_time, melted

# --- INITIALIZE DATA ---
df_init, stockouts_init, history_init, last_sync, melted_init = load_and_prep_data()

# --- SIDEBAR & GLOBAL FILTERS ---
with st.sidebar:
    st.title("🏥 Abra PHO")
    st.markdown("**Cold Chain Management System**")
    st.info(f"🕒 Last Sync (PST): {last_sync}")
    
    if st.button("🔄 Force Refresh Now"):
        st.cache_data.clear()
        st.rerun()
        
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
melted_df = melted_init.copy()

if global_rhu_filter:
    df = df[df['RHU'].isin(global_rhu_filter)]
    stockouts = stockouts[stockouts['RHU'].isin(global_rhu_filter)]
    melted_df = melted_df[melted_df['RHU'].isin(global_rhu_filter)]

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
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "⚠️ Expiry Radar", 
    "🗺️ Interactive Heat Map", 
    "📋 Raw Data Matrix", 
    "🔍 Recall Trace", 
    "🚨 Smart Redistribution",
    "📈 Historical Trends"
])

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
    st.subheader("Geographical Distribution Map")
    st.write("Visualizing cold chain stock levels and health statuses across the Cordillera Administrative Region.")
    
    # 1. Vaccine Radar Filter
    map_vax = st.selectbox("🎯 Target Vaccine (Radar):", ["ALL VACCINES"] + sorted(melted_df['Vaccine'].unique()))
    
    # 2. Build Rich Map Data
    all_rhus = list(ABRA_COORDS.keys()) if not global_rhu_filter else [r.strip().upper() for r in global_rhu_filter]
    map_data = []
    
    for rhu in all_rhus:
        if rhu not in ABRA_COORDS: continue
        lat, lon = ABRA_COORDS[rhu]
        
        # Isolate Data
        r_df = df[df['RHU_Clean'] == rhu]
        r_stock = stockouts[stockouts['RHU_Clean'] == rhu]
        
        if map_vax != "ALL VACCINES":
            r_df = r_df[r_df['Vaccine'] == map_vax]
            r_stock = r_stock[r_stock['Vaccine'] == map_vax]
            
        total_qty = r_df['Qty'].sum() if not r_df.empty else 0
        
        # 3. Traffic Light Logic
        if total_qty == 0:
            status = "🚨 Stockout"
        elif not r_df.empty and r_df['Days to Expiry'].min() <= 60:
            status = "⚠️ At Risk (<60d Expiry)"
        else:
            status = "🟢 Healthy Stock"
            
        # 4. Hover Analytics Strings
        missing_str = ", ".join(r_stock['Vaccine'].unique().tolist()) if not r_stock.empty else "None"
        next_expiry = r_df['Expiry Date'].min().strftime('%b %d, %Y') if total_qty > 0 and pd.notnull(r_df['Expiry Date'].min()) else "N/A"
        
        map_data.append({
            'RHU': rhu,
            'Lat': lat,
            'Lon': lon,
            'Total Doses': total_qty,
            'Health Status': status,
            'Missing Vaccines': missing_str,
            'Next Expiry': next_expiry,
            'Display Size': max(total_qty, 1) # Ensures even 0 qty dots are visible
        })
        
    map_df = pd.DataFrame(map_data)
    
    c1, c2 = st.columns([2, 1])
    with c1:
        # 5. Render Map
        fig_map = px.scatter_mapbox(
            map_df, lat="Lat", lon="Lon", size="Display Size", color="Health Status",
            hover_name="RHU",
            hover_data={
                "Lat": False, "Lon": False, "Display Size": False,
                "Total Doses": ":,", 
                "Health Status": True, 
                "Missing Vaccines": True, 
                "Next Expiry": True
            },
            color_discrete_map={
                "🚨 Stockout": "#ff4b4b", 
                "⚠️ At Risk (<60d Expiry)": "#ffd700", 
                "🟢 Healthy Stock": "#00cc66"
            },
            size_max=25, zoom=9.2, mapbox_style="carto-darkmatter"
        )
        fig_map.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
        st.plotly_chart(fig_map, use_container_width=True)
        
    with c2:
        bar_df = map_df.sort_values(by='Total Doses', ascending=True)
        fig_rhu = px.bar(
            bar_df, x='Total Doses', y='RHU', orientation='h', color='Health Status', 
            color_discrete_map={
                "🚨 Stockout": "#ff4b4b", 
                "⚠️ At Risk (<60d Expiry)": "#ffd700", 
                "🟢 Healthy Stock": "#00cc66"
            }, 
            template='plotly_dark'
        )
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
    st.subheader("🚨 Stockouts & Redistribution Strategy")
    if not stockouts.empty:
        st.error(f"Alert: {len(stockouts['RHU'].unique())} municipalities are missing one or more vaccines.")
        
        c1, c2 = st.columns([1, 1.5])
        with c1:
            st.markdown("### Zero-Stock Facilities")
            summary = stockouts.groupby('RHU')['Vaccine'].apply(lambda x: ', '.join(x)).reset_index()
            summary.rename(columns={'Vaccine': 'Missing'}, inplace=True)
            st.dataframe(summary, use_container_width=True, hide_index=True)
            
        with c2:
            st.markdown("### 🧠 Smart Redistribution Matches")
            suggestions = []
            for _, row in stockouts.iterrows():
                missing_vax = row['Vaccine']
                dest_rhu = row['RHU']
                donors = df[(df['Vaccine'] == missing_vax) & (df['Qty'] > 50) & (df['RHU'] != dest_rhu)].copy()
                
                if not donors.empty:
                    best_donor = donors.sort_values(by='Days to Expiry').iloc[0]
                    suggestions.append({
                        'To RHU': dest_rhu,
                        'Vaccine needed': missing_vax,
                        'Take from RHU': best_donor['RHU'],
                        'Available': best_donor['Qty'],
                        'Donor Expiry': best_donor['Expiry Date'].strftime('%b %d')
                    })
                    
            if suggestions:
                st.dataframe(pd.DataFrame(suggestions), use_container_width=True, hide_index=True)
            else:
                st.info("No viable surplus donors found within the province for current stockouts.")
    else: 
        st.success("All RHUs are fully stocked across all vaccines.")

with tab6:
    st.subheader("📈 Historical Trends & Burn Rate")
    st.write("The system automatically archives a snapshot of your inventory to the `HISTORY LOG` Google Sheet every 7 days to calculate provincial burn rates.")
    st.markdown("---")
    
    if history_init.empty or 'Date' not in history_init.columns:
        st.warning("⚠️ Preparing database. Check back soon for trend analysis.")
    else:
        hist_df = history_init.copy()
        hist_df['Date'] = pd.to_datetime(hist_df['Date'], errors='coerce')
        hist_df['Qty'] = pd.to_numeric(hist_df['Qty'], errors='coerce').fillna(0)
        
        h_col1, h_col2 = st.columns(2)
        with h_col1:
            hist_vax = st.selectbox("Select Vaccine to Track:", options=sorted(hist_df['Vaccine'].astype(str).unique()))
        with h_col2:
            rhu_options = ["ALL RHUS (Provincial Total)"] + sorted(hist_df['RHU'].astype(str).unique())
            hist_rhu = st.multiselect("Select RHUs to Compare:", options=rhu_options, default=["ALL RHUS (Provincial Total)"])
            
        if "ALL RHUS (Provincial Total)" in hist_rhu:
            total_df = hist_df[hist_df['Vaccine'] == hist_vax].groupby('Date')['Qty'].sum().reset_index()
            total_df['RHU'] = 'PROVINCIAL TOTAL'
            
            other_rhus = [r for r in hist_rhu if r != "ALL RHUS (Provincial Total)"]
            if other_rhus:
                other_df = hist_df[(hist_df['Vaccine'] == hist_vax) & (hist_df['RHU'].isin(other_rhus))]
                plot_df = pd.concat([total_df, other_df], ignore_index=True)
            else:
                plot_df = total_df
        else:
            plot_df = hist_df[(hist_df['Vaccine'] == hist_vax) & (hist_df['RHU'].isin(hist_rhu))]
        
        if not plot_df.empty:
            fig_trend = px.line(plot_df, x='Date', y='Qty', color='RHU', markers=True, text='Qty',
                                title=f"{hist_vax} Stock Trend Over Time", template='plotly_dark')
            
            fig_trend.update_traces(textposition="top center")
            
            if "ALL RHUS (Provincial Total)" in hist_rhu:
                fig_trend.update_traces(line=dict(width=5), selector=dict(name='PROVINCIAL TOTAL'))
                
            st.plotly_chart(fig_trend, use_container_width=True)
        else:
            st.info("Not enough historical data to chart this selection yet.")
