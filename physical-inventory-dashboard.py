import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection

st.set_page_config(layout="wide")
st.title("🛑 Robot Vision: Raw Sheet Data")

conn = st.connection("gsheets", type=GSheetsConnection)
raw_df = conn.read(
    spreadsheet="https://docs.google.com/spreadsheets/d/1CYarF3POk_UYyXxff2jj-k803nfBA8nhghQ-9OAz0Y4",
    worksheet="PHYSICAL INVENTORY1",
    header=None
)

st.write("Here is exactly how Streamlit sees your rows. Look at the numbers on the far left!")
st.dataframe(raw_df, use_container_width=True)
