# 文件名: tab3_avm.py
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import re
from utils import calculate_avm, calculate_ssd_status
from pdf_gen import generate_pdf_report, PDF_AVAILABLE

# --- UI组件 ---
def kpi_card(label, value, sub_value=None, color="default"):
    color_map = {
        "default": "#111827",
        "green": "#059669",
        "red": "#dc2626",
        "blue": "#2563eb"
    }
    text_color = color_map.get(color, "#111827")
    sub_html = f'<div style="font-size: 12px; color: #6b7280; margin-top: 2px;">{sub_value}</div>' if sub_value else ""
    return f"""
    <div style="
        background-color: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px;
        text-align: center; height: 100%; display: flex; flex-direction: column; justify-content: center; align-items: center;
    ">
        <div style="font-size: 13px; color: #6b7280; margin-bottom: 4px; font-weight: 500;">{label}</div>
        <div style="font-size: 18px; font-weight: 700; color: {text_color}; line-height: 1.2;">{value}</div>
        {sub_html}
    </div>
    """

def natural_key(string_):
    if not isinstance(string_, str): return [0]
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', string_)]

def render(df, project_name, chart_font_size):
    st.subheader("💎 单元智能估值 (AVM)")

    if 'avm_res' not in st.session_state: st.session_state.avm_res = None

    # --- 1. 自动定位逻辑 (含自动触发) ---
    t_blk, t_flr, t_stk = None, None, None
    auto_run = False  # 默认不自动运行

    if 'avm_target' in st.session_state:
        t = st.session_state['avm_target']
        t_blk, t_flr, t_stk = t['blk'], t['floor'], t['stack']
        
        # 成功提示
        st.toast(f"📍 已定位至 {t_blk} #{t_flr}-{t_stk}，正在估值...", icon="🚀")
        
        # 标记为需要自动运行
        auto_run = True
        
        # 清除信号，防止刷新页面时重复触发
        del st.session_state['avm_target']

    # --- 2. 输入表单 (自动填充) ---
    c1, c2, c3 = st.columns(3)
    
    with c1:
        blks = sorted(df['BLK'].unique(), key=natural_key)
        # 如果有跳转目标，使用目标的 Block，否则维持现状或默认
        b_idx = blks.index(t_blk) if t_blk in blks else 0
        s_blk = st.selectbox("1. 楼座 (Block)", blks, index=b_idx, key="blk_v107")
    
    with c2:
        blk_df = df[df['BLK'] == s_blk]
        floors = sorted(blk_df['Floor_Num'].dropna().unique().astype(int)) if 'Floor_Num' in blk_df.columns else [1]
        if not floors: floors = [1]
        
        # 智能匹配楼层
        if t_flr in floors:
            f_idx = floors.index(t_flr)
        else:
            # 如果是手动切换Block，默认选中中间楼层
            f_idx = len(floors)//2
            
        s_flr = st.selectbox("2. 楼层 (Floor)", floors, index=f_idx, key="flr_v107")
        
    with c3:
        stacks = sorted(blk_df[blk_df['Floor_Num']==s_flr]['Stack'].unique(), key=natural_key)
        if not stacks: stacks = sorted(blk_df['Stack'].unique(), key=natural_key) # 兜底
        if not stacks: stacks = ['Unknown']
        
        # 智能匹配单元
        if t_stk in stacks:
            s_idx = stacks.index(t_stk)
        else:
            s_idx = 0
            
        s_stk = st.selectbox("3. 单元 (Stack)", stacks, index=s_idx, key="stk_v107")

    # --- 3. 计算逻辑 (按钮点击 OR 自动触发) ---
    # 逻辑：如果用户点了按钮，或者 auto_run 标志位为 True，都执行计算
    trigger = st.button("🚀 开始估值", type="primary", use_container_width=True)
    
    if trigger or auto_run:
        area, psf, val, _, _, comps, _ = calculate_avm(df, s_blk, s_stk, s_flr)
        
        if area:
            st.session_state.avm_res = {
                'area':area, 'psf':psf, 'val':val, 
                'blk':s_blk, 'stk':s_stk, 'flr':s_flr, 
                'comps':comps
            }
        else:
            st.error("❌ 数据不足，无法估值")
            st.session_state.avm_res = None

    # --- 4. 结果展示 ---
    if st.session_state.avm_res:
        res = st.session_state.avm_res
        val = res['val']
        
        # 历史数据
        hist = df[(df['BLK']==res['blk']) & (df['Stack']==res['stk']) & (df['Floor_Num']==res['flr'])].sort_values('Sale Date')
        last_p, gain, ssd = 0, 0, 0
        if not hist.empty:
            last = hist.iloc[-1]
            last_p = last['Sale Price']
            ssd_rate, _, ssd_txt = calculate_ssd_status(last['Sale Date'])
            ssd = val * ssd_rate
            gain = val - last_p - ssd

        st.markdown("---")
        
        # KPI Cards
        k1, k2, k3 = st.columns(3)
        val_color = "green" if gain > 0 else ("red" if gain < 0 else "default")
        gain_str = f"{gain/1e6:+.2f}M Gain" if last_p else "无历史参考"
        
        with k1: st.markdown(kpi_card("预估总价", f"${val/1e6:.2f}M", gain_str, color=val_color), unsafe_allow_html=True)
        with k2: st.markdown(kpi_card("预估尺价", f"${res['psf']:,.0f} psf", color="blue"), unsafe_allow_html=True)
        with k3: st.markdown(kpi_card("单位面积", f"{int(res['area']):,} sqft", color="default"), unsafe_allow_html=True)

        # 仪表盘
        fig = go.Figure(go.Indicator(
            mode="number+gauge", value=val, number={'prefix':"$",'valueformat':",.0f"},
            gauge={'axis':{'range':[val*0.85, val*1.15]}, 'bar':{'color':"#1f77b4"}, 
                   'steps':[{'range':[val*0.85, val*0.95], 'color':"#f2f2f2"},{'range':[val*0.95, val*1.05], 'color':"#cbf3f0"},{'range':[val*1.05, val*1.15], 'color':"#f2f2f2"}]}
        ))
        fig.update_layout(height=120, margin=dict(t=20, b=20), font=dict(size=chart_font_size))
        st.plotly_chart(fig, use_container_width=True)

        # 详情表格
        st.subheader("📜 本单位历史")
        if not hist.empty:
            cols = [c for c in ['Sale Date','Sale Price','Sale PSF','Type of Sale'] if c in hist.columns]
            st.dataframe(hist[cols].style.format({'Sale Price':"${:,.0f}",'Sale PSF':"${:,.0f}"}), use_container_width=True, hide_index=True)
            if ssd > 0: st.warning(f"⚠️ 需付 SSD: {ssd_txt}")
            else: st.success("✅ SSD Free")
        else: st.info("无历史记录")

        st.subheader("📉 周边参考")
        ccols = [c for c in ['Sale Date','Unit','Sale Price','Sale PSF','Area (sqft)'] if c in res['comps'].columns]
        st.dataframe(res['comps'][ccols].style.format({'Sale Price':"${:,.0f}",'Sale PSF':"${:,.0f}",'Area (sqft)':"{:,.0f}"}), use_container_width=True, hide_index=True)

        # PDF
        st.markdown("---")
        if PDF_AVAILABLE:
            u_info = {'blk':res['blk'], 'unit':f"{res['flr']:02d}-{res['stk']}"}
            v_data = {'value':val, 'area':res['area'], 'psf':res['psf']}
            a_data = {'net_gain':gain, 'ssd_cost':ssd, 'last_price':last_p}
            d_cut = df['Sale Date'].max().strftime('%Y-%m-%d')
            try:
                pdf = generate_pdf_report(project_name, u_info, v_data, a_data, hist, res['comps'], d_cut)
                st.download_button("📄 下载 PDF 信函", data=pdf, file_name="Valuation.pdf", mime="application/pdf", type="primary", use_container_width=True)
            except Exception: st.warning("PDF暂不可用")
