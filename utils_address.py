import streamlit as st
import json
import os
import pandas as pd

# 配置文件路径
CONFIG_FILE = 'project_addresses.json'

# 默认配置 (作为初始化兜底)
DEFAULT_CONFIG = {
    "Braddell View": {
        "street": "Braddell Hill",
        "postal_base": "5797"
    },
    "Pine Grove": {
        "street": "Pine Grove",
        "postal_base": "59"
    }
}

def load_addresses():
    """加载地址配置，如果文件不存在则加载默认值"""
    if not os.path.exists(CONFIG_FILE):
        save_addresses(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return DEFAULT_CONFIG

def save_addresses(data_dict):
    """保存地址配置到 JSON"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data_dict, f, ensure_ascii=False, indent=4)

def get_address_df():
    """将字典转换为 DataFrame 供 DataEditor 使用"""
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
    """将 DataEditor 修改后的 DataFrame 存回字典和文件"""
    new_data = {}
    for _, row in df.iterrows():
        proj = str(row["Project Name"]).strip()
        if proj: # 防止空行
            new_data[proj] = {
                "street": str(row["Street Name"]).strip(),
                "postal_base": str(row["Postal Prefix"]).strip()
            }
    save_addresses(new_data)
