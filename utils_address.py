import streamlit as st
import json
import os
import pandas as pd

# 配置文件路径
CONFIG_FILE = 'project_addresses.json'

# 默认配置 (示例数据)
DEFAULT_CONFIG = [
    {
        "project": "Braddell View",
        "block": "10A", 
        "street": "Braddell Hill",
        "postal": "579720"
    },
    {
        "project": "Braddell View",
        "block": "10B", 
        "street": "Braddell Hill",
        "postal": "579721"
    },
    {
        "project": "Pine Grove",
        "block": "DEFAULT", # 通用匹配符
        "street": "Pine Grove",
        "postal": "590001"
    }
]

def load_addresses():
    """加载地址配置，返回列表结构"""
    if not os.path.exists(CONFIG_FILE):
        save_addresses(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # 简单的格式兼容性检查：如果是旧字典格式，强制重置或转换
            if isinstance(data, dict): 
                return DEFAULT_CONFIG
            return data
    except:
        return DEFAULT_CONFIG

def save_addresses(data_list):
    """保存地址配置到 JSON"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)

def get_address_df():
    """将列表转换为 DataFrame 供 DataEditor 使用"""
    data = load_addresses()
    # 确保列顺序
    df = pd.DataFrame(data)
    # 重命名列以符合用户直觉
    rename_map = {
        "project": "Condo Name",
        "block": "Block No",
        "street": "Road Name",
        "postal": "Post Code"
    }
    # 确保所有列都存在，防止空数据报错
    for col in rename_map.keys():
        if col not in df.columns:
            df[col] = ""
            
    return df.rename(columns=rename_map)

def save_from_df(df):
    """将 DataEditor 修改后的 DataFrame 存回列表文件"""
    # 恢复列名
    reverse_map = {
        "Condo Name": "project",
        "Block No": "block",
        "Road Name": "street",
        "Post Code": "postal"
    }
    df_save = df.rename(columns=reverse_map)
    
    # 转换为列表并清洗空行
    new_data = []
    for _, row in df_save.iterrows():
        proj = str(row.get("project", "")).strip()
        if proj: # 只要有项目名就保存
            new_data.append({
                "project": proj,
                "block": str(row.get("block", "")).strip() or "DEFAULT", # 空block视为默认
                "street": str(row.get("street", "")).strip(),
                "postal": str(row.get("postal", "")).strip()
            })
    save_addresses(new_data)

def find_address_info(project_name, target_block):
    """
    根据项目名和楼座查找最佳匹配的地址信息
    优先级: 
    1. 精确匹配 Project + Block
    2. 匹配 Project + "DEFAULT"
    3. 匹配 Project + 空 Block
    """
    data = load_addresses()
    
    # 转换为 DataFrame 方便查询 (数据量不大时性能可接受)
    df = pd.DataFrame(data)
    if df.empty: return None, None
    
    # 筛选项目
    df_proj = df[df['project'] == project_name]
    if df_proj.empty: return None, None
    
    # 1. 尝试精确匹配 Block
    match = df_proj[df_proj['block'] == str(target_block)]
    
    # 2. 如果没找到，尝试 "DEFAULT" 或 空
    if match.empty:
        match = df_proj[df_proj['block'].isin(["DEFAULT", "", "All", "General"])]
    
    # 3. 如果还是空，随便取第一条做兜底（可选）
    if match.empty:
        match = df_proj.iloc[[0]]
        
    if not match.empty:
        rec = match.iloc[0]
        return rec.get('street', ''), rec.get('postal', '')
        
    return None, None
