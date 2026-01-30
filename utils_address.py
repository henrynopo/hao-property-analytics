import json
import os
import pandas as pd

CONFIG_FILE = 'project_addresses.json'

DEFAULT_CONFIG = {
    "Braddell View": {"street": "Braddell Hill", "postal_base": "5797"},
    "Pine Grove": {"street": "Pine Grove", "postal_base": "59"}
}

def load_addresses():
    if not os.path.exists(CONFIG_FILE):
        save_addresses(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return DEFAULT_CONFIG

def save_addresses(data_dict):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data_dict, f, ensure_ascii=False, indent=4)

def get_address_df():
    data = load_addresses()
    rows = []
    for project, info in data.items():
        rows.append({
            "Project Name": project,
            "Street Name": info.get("street", ""),
            "Postal Prefix": info.get("postal_base", "")
        })
    return pd.DataFrame(rows)

def save_from_df(df):
    new_data = {}
    for _, row in df.iterrows():
        proj = str(row["Project Name"]).strip()
        if proj:
            new_data[proj] = {
                "street": str(row["Street Name"]).strip(),
                "postal_base": str(row["Postal Prefix"]).strip()
            }
    save_addresses(new_data)
