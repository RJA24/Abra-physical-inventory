import datetime
import sys
import pandas as pd
import gspread
import toml

# --- 1. THE BOUNCER (FRIDAY ONLY) ---
pst_now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)
if pst_now.weekday() != 4:
    print("Today is not Friday. Going back to sleep.")
    sys.exit()

print("Waking up! Starting snapshot process...")

# --- 2. AUTHENTICATION ---
SECRETS_PATH = ".streamlit/secrets.toml"
with open(SECRETS_PATH, "r") as f:
    secrets = toml.load(f)

gcp_creds = secrets["connections"]["gsheets"]
gc = gspread.service_account_from_dict(gcp_creds)

SPREADSHEET_ID = "1CYarF3POk_UYyXxff2jj-k803nfBA8nhghQ-9OAz0Y4"
workbook = gc.open_by_key(SPREADSHEET_ID)

# --- 3. FETCH LIVE INVENTORY ---
print("Fetching raw data...")
raw_sheet = workbook.worksheet("PHYSICAL INVENTORY1")
raw_df = pd.DataFrame(raw_sheet.get_all_values())

# --- 4. FETCH HISTORY ---
history_sheet = workbook.worksheet("HISTORY LOG")
try:
    history_data = history_sheet.get_all_values()
    if len(history_data) > 1:
        history_df = pd.DataFrame(history_data[1:], columns=history_data[0])
    else:
        history_df = pd.DataFrame(columns=['Date', 'Health Facility', 'Vaccine', 'Qty'])
except:
    history_df = pd.DataFrame(columns=['Date', 'Health Facility', 'Vaccine', 'Qty'])

# --- 5. DYNAMIC ALIGNMENT ENGINE ---
fac_col_idx = 1
for col in range(min(5, raw_df.shape[1])):
    if raw_df[col].astype(str).str.contains('BANGUED', case=False, na=False).any():
        fac_col_idx = col
        break

# Parse Vaccines
vaccines = pd.Series(raw_df.iloc[0, fac_col_idx + 1:]).replace("", float("NaN")).ffill().values

# Parse Grid (Locks exactly to the bounds of the vaccines)
grid_df = raw_df.iloc[4:, fac_col_idx:fac_col_idx + len(vaccines) + 1].copy()
grid_df.columns = ['Health Facility'] + list(range(len(vaccines)))

# Clean Data
grid_df = grid_df[grid_df['Health Facility'].astype(str).str.strip() != ""]
grid_df = grid_df[~grid_df['Health Facility'].astype(str).str.contains('TOTAL|EXPIRING|MONTHS', case=False, na=False)]

# Melt & Calculate
melted = grid_df.melt(id_vars=['Health Facility'], var_name='ColIndex', value_name='Qty')
melted['Vaccine'] = [vaccines[i] for i in melted['ColIndex']]
melted['Qty'] = pd.to_numeric(melted['Qty'], errors='coerce').fillna(0).astype(int)

snap_df = melted.groupby(['Health Facility', 'Vaccine'])['Qty'].sum().reset_index()
snap_df.insert(0, 'Date', pst_now.strftime('%Y-%m-%d'))

print(f"✅ Calculated {len(snap_df)} new active inventory records.")

# --- 6. SAVE DATA ---
updated_history = pd.concat([history_df, snap_df], ignore_index=True)

# THE FIX: Scrub out JSON-breaking NaN values
updated_history = updated_history.fillna("")

# Bulletproof write command formatting as USER_ENTERED
data_to_write = [updated_history.columns.values.tolist()] + updated_history.values.tolist()
history_sheet.clear()

history_sheet.update(values=data_to_write, range_name="A1", value_input_option="USER_ENTERED")

print(f"✅ Successfully saved {len(updated_history)} total rows to Google Sheets!")
