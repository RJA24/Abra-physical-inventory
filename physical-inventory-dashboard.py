import streamlit as st
import pandas as pd
import plotly.express as px
from streamlit_gsheets import GSheetsConnection
import calendar
import datetime

# --- PAGE CONFIG ---
st.set_page_config(page_title="Abra PHO | Vaccine Inventory", layout="wide", page_icon="💉")

# --- SILENT ACCESS TRACKER (DEBUG MODE) ---
if 'has_logged_in' not in st.session_state:
    try:
        tracker_conn = st.connection("gsheets", type=GSheetsConnection)
        
        # The Master Google Sheet Link
        SHEET_URL = "https://docs.google.com/spreadsheets/d/1CYarF3POk_UYyXxff2jj-k803nfBA8nhghQ-9OAz0Y4"
        
        access_df = tracker_conn.read(
            spreadsheet=SHEET_URL,
            worksheet="ACCESS LOG",
            ttl=0 
        )
        
        pst_now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)
        new_entry = pd.DataFrame([{
            'Date': pst_now.strftime('%Y-%m-%d'), 
            'Time': pst_now.strftime('%I:%M:%S %p')
        }])
        
        if access_df.empty or 'Date' not in access_df.columns:
            updated_log = new_entry
        else:
            updated_log = pd.concat([access_df, new_entry], ignore_index=True)
            
        # FIX: We now explicitly tell it WHICH spreadsheet to update!
        tracker_conn.update(
            spreadsheet=SHEET_URL,
            worksheet="ACCESS LOG", 
            data=updated_log
        )
        st.session_state.has_logged_in = True
        
        # This will flash green on your screen if it works
        st.success("✅ DEBUG: Tracker successfully wrote to Google Sheets!") 
        
    except Exception as e:
        st.error(f"🚨 TRACKER ERROR: {e}")
# --- ABRA GEOSPATIAL DATA ---
ABRA_COORDS = {
    'BANGUED': [17.5958, 120.6186], 'BOLINEY': [17.3917, 120.8167], 'BUCAY': [17.5333, 120.7333],
    'BUCLOC': [17.4500, 120.8333], 'DAGUIOMAN': [17.4500, 120.9333], 'DANGLAS': [17.6333, 120.5833],
    'DOLORES': [17.6500, 120.6500], 'LA PAZ': [17.6667, 120.6333], 'LACUB': [17.6667, 120.9333],
    'LAGANGILANG': [17.6167, 120.7333], 'LAGAYAN': [17.7167, 120.6333], 'LANGIDEN': [17.5833, 120.5667],
    'LICUAN-BAAY': [17.5667, 120.8833], 'LUBA': [17.3167, 120.6833], 'MALIBCONG': [17.5667, 120.9833],
    'MANABO': [17.4333, 120.7000], 'PEÑARRUBIA': [17.5667, 120.6333], 'PENARRUBIA': [17.5667, 120.6333],
    'PIDIGAN': [17.5667, 120.5833], 'PILAR': [17.4167, 120.6000], 'SALLAPADAN': [17.4500, 120.7667],
    'SAN ISIDRO': [17.4667, 120.6000], 'SAN JUAN': [17.6833, 120.6167], 'SAN QUINTIN': [17.5333, 120.5167],
    'TAYUM': [17.6000, 120.6500], 'TINEG': [17.7833, 120.9333], 'TUBO': [17.2333, 120.8000], 
    'VILLAVICIOSA': [17.4333, 120.6333],
    'PHO': [17.5960, 120.6190], 'APH': [17.5940, 120.6180]
}

def render_footer():
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: #888888; padding: 10px;'>
            <p>Developed by <strong>JangTV</strong></p>
            <img src="https://github.com/RJA24/abra-inventory-data--entry/blob/main/357094382_2458785624282603_4372984338912374777_n.png?raw=true" width="80" style="margin-top: -10px; opacity: 0.8;">
        </div>
        """, 
        unsafe_allow_html=True
    )

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
            history_df = pd.DataFrame(columns=['Date', 'Health Facility', 'Vaccine', 'Qty'])

    except Exception as e:
        st.error(f"🚨 Connection Failed: {e}")
        st.stop()
    
    # Metadata Parsing
    vaccines = pd.Series(raw_df.iloc[0, 2:]).ffill().values 
    lots = raw_df.iloc[2, 2:].values
    expiries = raw_df.iloc[3, 2:].values
    
    grid_df = raw_df.iloc[4:, 1:].copy()
    col_indices = list(range(len(vaccines)))
    grid_df.columns = ['Health Facility'] + col_indices
    grid_df = grid_df.dropna(subset=['Health Facility'])
    
    # INDESTRUCTIBLE FILTER
    grid_df = grid_df[~grid_df['Health Facility'].astype(str).str.contains('TOTAL|EXPIRING|MONTHS', case=False, na=False)]
    
    # Reshaping Data
    melted = grid_df.melt(id_vars=['Health Facility'], var_name='ColIndex', value_name='Qty')
    melted['Vaccine'] = [vaccines[i] for i in melted['ColIndex']]
    melted['Lot'] = [str(lots[i]) for i in melted['ColIndex']]
    melted['Expiry'] = [str(expiries[i]) for i in melted['ColIndex']]
    melted['Qty'] = pd.to_numeric(melted['Qty'], errors='coerce').fillna(0).astype(int)
    
    melted['Facility_Clean'] = melted['Health Facility'].astype(str).str.strip().str.upper()
    
    # --- AUTOMATED 7-DAY HISTORICAL SNAPSHOT LOGIC ---
    if history_df.empty or 'Date' not in history_df.columns:
        history_df = pd.DataFrame(columns=['Date', 'Health Facility', 'Vaccine', 'Qty'])

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
        snap_df = melted.groupby(['Health Facility', 'Vaccine'])['Qty'].sum().reset_index()
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
    facility_vax_totals = melted.groupby(['Health Facility', 'Facility_Clean', 'Vaccine'])['Qty'].sum().reset_index()
    stockouts_df = facility_vax_totals[facility_vax_totals['Qty'] == 0].copy()
    
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
    
    # --- NEW: TYPO CATCHER ENGINE ---
    anomalies = []
    
    # Catch 1: Negative quantities
    neg_df = melted[melted['Qty'] < 0]
    for _, row in neg_df.iterrows():
        anomalies.append(f"**Negative Inventory:** {row['Health Facility']} reported {row['Qty']} vials of {row['Vaccine']}.")
        
    # Catch 2: Missing Lot numbers on active stock
    missing_lot = clean_df[clean_df['Lot'].astype(str).str.strip().isin(['', 'nan', 'None', 'NAN'])]
    for _, row in missing_lot.iterrows():
        anomalies.append(f"**Missing Lot Number:** {row['Health Facility']} has {row['Qty']} vials of {row['Vaccine']}, but the Lot Number is blank.")
        
    # Catch 3: Unreadable or missing Expiry dates on active stock
    missing_expiry = clean_df[pd.isna(clean_df['Expiry Date'])]
    for _, row in missing_expiry.iterrows():
        anomalies.append(f"**Missing/Invalid Expiry:** {row['Health Facility']} has {row['Qty']} vials of {row['Vaccine']} (Lot: {row['Lot']}), but the expiry date cannot be read.")

    return clean_df, stockouts_df, history_df, load_time, melted, anomalies

# --- INITIALIZE DATA ---
df_init, stockouts_init, history_init, last_sync, melted_init, anomalies_init = load_and_prep_data()

# --- SIDEBAR & GLOBAL FILTERS ---
with st.sidebar:
    # --- ABRA VALLEY BANNER ---
    st.image("https://github.com/RJA24/abra-inventory-data--entry/blob/main/Abra_Valley.jpg?raw=true", use_container_width=True)
    
    st.title("🏥 Abra PHO")
    st.markdown("**Cold Chain Management System**")
    st.info(f"🕒 Last Sync (PST): {last_sync}")
    
    if st.button("🔄 Force Refresh Now"):
        st.cache_data.clear()
        st.rerun()
        
    st.markdown("---")
    st.subheader("Global Filters")
    global_facility_filter = st.multiselect(
        "Filter by Health Facility:",
        options=sorted(df_init['Health Facility'].unique()),
        help="Filters all charts and tables across the entire dashboard."
    )

# Apply Global Filter
df = df_init.copy()
stockouts = stockouts_init.copy()
melted_df = melted_init.copy()

if global_facility_filter:
    df = df[df['Health Facility'].isin(global_facility_filter)]
    stockouts = stockouts[stockouts['Health Facility'].isin(global_facility_filter)]
    melted_df = melted_df[melted_df['Health Facility'].isin(global_facility_filter)]

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

# --- TYPO CATCHER UI ---
if anomalies_init:
    with st.expander("🚨 DATA QUALITY ALERTS (Typo Catcher Active)", expanded=True):
        st.error("The system detected potential data entry errors in the master Google Sheet. Please review:")
        for anomaly in anomalies_init:
            st.markdown(f"- {anomaly}")

# --- TOP METRICS ---
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Active Vials", f"{df['Qty'].sum():,}")
col2.metric("Locations Reported", f"{df['Health Facility'].nunique()}")
col3.metric("🚨 Expired", f"{df[df['Status'] == '🚨 EXPIRED']['Qty'].sum():,}")
col4.metric("🔴 Critical (<60d)", f"{df[df['Status'] == '🔴 CRITICAL (< 2 Mos)']['Qty'].sum():,}")
col5.metric("⚠️ Stockout Facilities", len(stockouts['Health Facility'].unique()))

st.markdown("---")

# --- TABS ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "⚠️ Expiry Radar", 
    "🗺️ Interactive Heat Map", 
    "📋 Raw Data Matrix", 
    "🔍 Recall Trace", 
    "🚨 Smart Redistribution",
    "📈 Historical Trends & AI"
])

with tab1:
    st.subheader("🚨 Expiry Radar & Action Items")
    st.write("Monitor and export batches that require immediate pull-out or rapid deployment.")
    
    urgent_df = df[df['Status'] != '🟢 SAFE'].sort_values(by='Days to Expiry')
    
    if not urgent_df.empty:
        e1, e2, e3, e4 = st.columns(4)
        expired_vials = urgent_df[urgent_df['Status'] == '🚨 EXPIRED']['Qty'].sum()
        critical_vials = urgent_df[urgent_df['Status'] == '🔴 CRITICAL (< 2 Mos)']['Qty'].sum()
        warning_vials = urgent_df[urgent_df['Status'] == '🟡 WARNING (2-4 Mos)']['Qty'].sum()
        
        e1.metric("Total Batches Flagged", len(urgent_df))
        e2.metric("🚨 Expired Vials", f"{expired_vials:,}")
        e3.metric("🔴 Critical Vials", f"{critical_vials:,}")
        e4.metric("🟡 Warning Vials", f"{warning_vials:,}")
        
        st.markdown("---")
        
        c1, c2 = st.columns([2, 1])
        with c1:
            fig_status = px.bar(urgent_df['Status'].value_counts().reset_index(), y='Status', x='count', 
                               color='Status', color_discrete_map={'🚨 EXPIRED': '#ff4b4b', '🔴 CRITICAL (< 2 Mos)': '#ff8c00', '🟡 WARNING (2-4 Mos)': '#ffd700'},
                               template='plotly_dark', height=250, orientation='h', title="Flagged Batches by Urgency")
            fig_status.update_layout(showlegend=False, xaxis_title="Number of Batches", yaxis_title="")
            st.plotly_chart(fig_status, use_container_width=True)
            
        with c2:
            st.markdown("<br><br>", unsafe_allow_html=True)
            st.info("Download the complete list of flagged batches to coordinate pull-outs or rapid deployments with facilities.")
            csv = urgent_df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Export Urgent Action List", csv, "urgent_list.csv", "text/csv", use_container_width=True)

        st.markdown("### 📋 Categorized Action Lists")
        
        display_df = urgent_df[['Health Facility', 'Vaccine', 'Lot', 'Expiry Date', 'Qty', 'Days to Expiry', 'Status']].copy()
        display_df['Expiry Date'] = display_df['Expiry Date'].dt.strftime('%b %d, %Y')
        
        exp_expired = display_df[display_df['Status'] == '🚨 EXPIRED']
        if not exp_expired.empty:
            with st.expander(f"🚨 EXPIRED BATCHES - Do Not Use ({len(exp_expired)} batches)", expanded=True):
                st.dataframe(exp_expired.drop(columns=['Status']), use_container_width=True, hide_index=True)
                
        exp_critical = display_df[display_df['Status'] == '🔴 CRITICAL (< 2 Mos)']
        if not exp_critical.empty:
            with st.expander(f"🔴 CRITICAL BATCHES - Deploy Immediately ({len(exp_critical)} batches)", expanded=True):
                st.dataframe(exp_critical.drop(columns=['Status']), use_container_width=True, hide_index=True)
                
        exp_warning = display_df[display_df['Status'] == '🟡 WARNING (2-4 Mos)']
        if not exp_warning.empty:
            with st.expander(f"🟡 WARNING BATCHES - Monitor Closely ({len(exp_warning)} batches)", expanded=False):
                st.dataframe(exp_warning.drop(columns=['Status']), use_container_width=True, hide_index=True)
                
    else:
        st.success("✅ All stock is currently within safe expiry limits. No action required.")

with tab2:
    st.subheader("Geographical Distribution Map")
    st.write("Visualizing cold chain stock levels and health statuses across the Cordillera Administrative Region.")
    
    map_vax = st.selectbox("🎯 Target Vaccine (Radar):", ["ALL VACCINES"] + sorted(melted_df['Vaccine'].unique()))
    
    active_facilities = df['Facility_Clean'].unique()
    map_data = []
    
    for facility in active_facilities:
        lat, lon = ABRA_COORDS.get(facility, [17.5958, 120.6186])
        
        r_df = df[df['Facility_Clean'] == facility]
        r_stock = stockouts[stockouts['Facility_Clean'] == facility]
        
        if map_vax != "ALL VACCINES":
            r_df = r_df[r_df['Vaccine'] == map_vax]
            r_stock = r_stock[r_stock['Vaccine'] == map_vax]
            
        total_qty = r_df['Qty'].sum() if not r_df.empty else 0
        
        if total_qty == 0:
            status = "🚨 Stockout"
        elif not r_df.empty and r_df['Days to Expiry'].min() <= 60:
            status = "⚠️ At Risk (<60d Expiry)"
        else:
            status = "🟢 Healthy Stock"
            
        missing_str = ", ".join(r_stock['Vaccine'].unique().tolist()) if not r_stock.empty else "None"
        next_expiry = r_df['Expiry Date'].min().strftime('%b %d, %Y') if total_qty > 0 and pd.notnull(r_df['Expiry Date'].min()) else "N/A"
        
        map_data.append({
            'Health Facility': facility,
            'Lat': lat,
            'Lon': lon,
            'Total Vials': total_qty,
            'Health Status': status,
            'Missing Vaccines': missing_str,
            'Next Expiry': next_expiry,
            'Display Size': max(total_qty, 1)
        })
        
    map_df = pd.DataFrame(map_data)
    
    if not map_df.empty:
        c1, c2 = st.columns([2, 1])
        with c1:
            fig_map = px.scatter_mapbox(
                map_df, lat="Lat", lon="Lon", size="Display Size", color="Health Status",
                hover_name="Health Facility",
                hover_data={
                    "Lat": False, "Lon": False, "Display Size": False,
                    "Total Vials": ":,", 
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
            bar_df = map_df.sort_values(by='Total Vials', ascending=True)
            fig_facility = px.bar(
                bar_df, x='Total Vials', y='Health Facility', orientation='h', color='Health Status', 
                color_discrete_map={
                    "🚨 Stockout": "#ff4b4b", 
                    "⚠️ At Risk (<60d Expiry)": "#ffd700", 
                    "🟢 Healthy Stock": "#00cc66"
                }, 
                template='plotly_dark'
            )
            st.plotly_chart(fig_facility, use_container_width=True)
    else:
        st.warning("No geospatial data available for this specific selection.")

with tab3:
    st.subheader("Searchable Data Grid")
    vax_filter = st.multiselect("Filter by Vaccine Type:", options=sorted(df['Vaccine'].unique()))
    grid_view = df.copy()
    if vax_filter: grid_view = grid_view[grid_view['Vaccine'].isin(vax_filter)]
    st.dataframe(grid_view[['Health Facility', 'Vaccine', 'Lot', 'Expiry', 'Qty', 'Status']], use_container_width=True, hide_index=True)

with tab4:
    st.subheader("🔍 Product Recall Search")
    search_lot = st.text_input("Enter Lot Number (e.g., 12854X007B):")
    if search_lot:
        res = df[df['Lot'].str.contains(search_lot, case=False, na=False)]
        if not res.empty:
            st.warning(f"Found {res['Qty'].sum()} vials of Lot {search_lot}")
            st.dataframe(res[['Health Facility', 'Vaccine', 'Qty', 'Status']], use_container_width=True, hide_index=True)
        else: st.success("No active vials found for this Lot.")

with tab5:
    st.subheader("🚨 Stockouts & Redistribution Strategy")
    if not stockouts.empty:
        st.error(f"Alert: {len(stockouts['Health Facility'].unique())} reporting centers are missing one or more vaccines.")
        
        c1, c2 = st.columns([1, 1.5])
        with c1:
            st.markdown("### Zero-Stock Facilities")
            summary = stockouts.groupby('Health Facility')['Vaccine'].apply(lambda x: ', '.join(x)).reset_index()
            summary.rename(columns={'Vaccine': 'Missing'}, inplace=True)
            st.dataframe(summary, use_container_width=True, hide_index=True)
            
        with c2:
            st.markdown("### 🧠 Smart Redistribution Matches")
            suggestions = []
            for _, row in stockouts.iterrows():
                missing_vax = row['Vaccine']
                dest_facility = row['Health Facility']
                donors = df[(df['Vaccine'] == missing_vax) & (df['Qty'] > 50) & (df['Health Facility'] != dest_facility)].copy()
                
                if not donors.empty:
                    best_donor = donors.sort_values(by='Days to Expiry').iloc[0]
                    suggestions.append({
                        'To Facility': dest_facility,
                        'Vaccine needed': missing_vax,
                        'Take from Facility': best_donor['Health Facility'],
                        'Available Vials': best_donor['Qty'],
                        'Donor Expiry': best_donor['Expiry Date'].strftime('%b %d')
                    })
                    
            if suggestions:
                st.dataframe(pd.DataFrame(suggestions), use_container_width=True, hide_index=True)
            else:
                st.info("No viable surplus donors found within the province for current stockouts.")
    else: 
        st.success("All Facilities are fully stocked across all vaccines.")

with tab6:
    st.subheader("📈 Historical Trends & AI Burn Rate")
    st.write("The system archives a snapshot every 7 days to calculate provincial burn rates and forecast future stockouts.")
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
            facility_options = ["ALL FACILITIES (Provincial Total)"] + sorted(hist_df['Health Facility'].astype(str).unique())
            hist_facility = st.multiselect("Select Facilities to Compare:", options=facility_options, default=["ALL FACILITIES (Provincial Total)"])
            
        if "ALL FACILITIES (Provincial Total)" in hist_facility:
            total_df = hist_df[hist_df['Vaccine'] == hist_vax].groupby('Date')['Qty'].sum().reset_index()
            total_df['Health Facility'] = 'PROVINCIAL TOTAL'
            
            other_facilities = [f for f in hist_facility if f != "ALL FACILITIES (Provincial Total)"]
            if other_facilities:
                other_df = hist_df[(hist_df['Vaccine'] == hist_vax) & (hist_df['Health Facility'].isin(other_facilities))]
                plot_df = pd.concat([total_df, other_df], ignore_index=True)
            else:
                plot_df = total_df
        else:
            plot_df = hist_df[(hist_df['Vaccine'] == hist_vax) & (hist_df['Health Facility'].isin(hist_facility))]
        
        if not plot_df.empty:
            fig_trend = px.line(plot_df, x='Date', y='Qty', color='Health Facility', markers=True, text='Qty',
                                title=f"{hist_vax} Stock Trend Over Time (Vials)", template='plotly_dark')
            
            fig_trend.update_traces(textposition="top center")
            
            if "ALL FACILITIES (Provincial Total)" in hist_facility:
                fig_trend.update_traces(line=dict(width=5), selector=dict(name='PROVINCIAL TOTAL'))
                
            st.plotly_chart(fig_trend, use_container_width=True)
            
            # --- NEW: PREDICTIVE FORECASTER AI ---
            st.markdown("### 🤖 Predictive Stockout Forecaster")
            for facility in hist_facility:
                fac_name = "PROVINCIAL TOTAL" if facility == "ALL FACILITIES (Provincial Total)" else facility
                fac_df = plot_df[plot_df['Health Facility'] == fac_name].sort_values('Date')
                
                if len(fac_df) >= 2:
                    first_record = fac_df.iloc[0]
                    last_record = fac_df.iloc[-1]
                    
                    days_diff = (last_record['Date'] - first_record['Date']).days
                    qty_diff = first_record['Qty'] - last_record['Qty']
                    current_stock = last_record['Qty']
                    
                    if days_diff > 0 and qty_diff > 0:
                        daily_burn = qty_diff / days_diff
                        if current_stock > 0:
                            days_left = int(current_stock / daily_burn)
                            est_zero_date = last_record['Date'] + datetime.timedelta(days=days_left)
                            st.info(f"**{fac_name}:** Burning ~{daily_burn:.1f} vials/day. Estimated stockout in **{days_left} days** ({est_zero_date.strftime('%b %d, %Y')}).")
                        else:
                            st.error(f"**{fac_name}:** Currently out of stock.")
                    elif qty_diff < 0:
                        st.success(f"**{fac_name}:** Stock levels have recently increased (Restocked).")
                    else:
                        st.write(f"**{fac_name}:** No vials consumed in the tracked period.")
                else:
                    st.write(f"**{fac_name}:** Not enough history generated yet to forecast (requires at least 7 days).")
            
        else:
            st.info("Not enough historical data to chart this selection yet.")

# Render custom footer
render_footer()
