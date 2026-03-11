import pandas as pd
import datetime
from streamlit.connections import BaseConnection
from streamlit_gsheets import GSheetsConnection
import streamlit as st

def run_snapshot():
    # Connect to Google Sheets
    conn = st.connection("gsheets", type=GSheetsConnection)
    SHEET_URL = "https://docs.google.com/spreadsheets/d/1CYarF3POk_UYyXxff2jj-k803nfBA8nhghQ-9OAz0Y4"

    print("Fetching raw data...")
    raw_df = conn.read(spreadsheet=SHEET_URL, worksheet="PHYSICAL INVENTORY1", header=None, ttl=0)
    
    try:
        history_df = conn.read(spreadsheet=SHEET_URL, worksheet="HISTORY LOG", ttl=0)
    except:
        history_df = pd.DataFrame(columns=['Date', 'Health Facility', 'Vaccine', 'Qty'])

    # Parse data (Matching your exact app logic)
    vaccines = pd.Series(raw_df.iloc[0, 2:]).ffill().values 
    grid_df = raw_df.iloc[4:, 1:].copy()
    grid_df.columns = ['Health Facility'] + list(range(len(vaccines)))
    grid_df = grid_df.dropna(subset=['Health Facility'])
    grid_df = grid_df[~grid_df['Health Facility'].astype(str).str.contains('TOTAL|EXPIRING|MONTHS', case=False, na=False)]

    melted = grid_df.melt(id_vars=['Health Facility'], var_name='ColIndex', value_name='Qty')
    melted['Vaccine'] = [vaccines[i] for i in melted['ColIndex']]
    melted['Qty'] = pd.to_numeric(melted['Qty'], errors='coerce').fillna(0).astype(int)

    # Calculate Totals
    snap_df = melted.groupby(['Health Facility', 'Vaccine'])['Qty'].sum().reset_index()
    
    # Tag with today's date
    pst_now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)
    snap_df.insert(0, 'Date', pst_now.strftime('%Y-%m-%d'))

    # Update History Log
    updated_history = pd.concat([history_df, snap_df], ignore_index=True)
    
    print("Saving snapshot to Google Sheets...")
    conn.update(
        spreadsheet=SHEET_URL,
        worksheet="HISTORY LOG", 
        data=updated_history
    )
    print("Snapshot saved successfully!")

if __name__ == "__main__":
    run_snapshot()
