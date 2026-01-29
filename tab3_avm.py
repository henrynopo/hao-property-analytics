# 文件名: tab3_avm.py
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from utils import calculate_avm, calculate_ssd_status, natural_key
from pdf_gen import generate_pdf_report, PDF_AVAILABLE

def render(df, project_name, chart_font_size):
    st.subheader("💎 单元智能估值 (AVM) V81")

    # 1. 状态锁定
    if 'avm_res' not in st.session_state: st.session_state.avm_res = None

    # 2. 自动定位
    t_blk, t_flr, t_stk = None, None, None
    if 'avm_target' in st.session_state:
        t = st.session_state['avm_target']
        t_blk, t_flr, t_stk = t['blk'], t['floor'], t['stack']
        st.success(f"📍 定位: {t_blk} #{t_flr}-{t_stk}")
        del st.session_state['avm_target']

    # 3. 输入区
    c1, c2, c3 = st.columns(3)
    with c1:
        blks = sorted(df['BLK'].unique(), key=natural_key)
        b_idx = blks.index(t_blk) if t_blk in blks else 0
        s_blk = st.selectbox("1. 楼座", blks, index=b_idx, key="blk_v82")
    
    with c2:
        blk_df = df[df['BLK'] == s_blk]
        floors = sorted(blk_df['Floor_Num'].dropna().unique().astype(int)) if 'Floor_Num' in blk_df.columns else [1]
        if not floors: floors = [1]
        f_idx = floors.index(t_flr) if t_flr in floors else len(floors)//2
        s_flr = st.selectbox("2. 楼层", floors, index=f_idx, key="flr_v82")
        
    with c3:
        stacks = sorted(blk_df[blk_df['Floor_Num']==s_flr]['Stack'].unique(), key=natural_key)
        if not stacks: stacks = sorted(blk_df['Stack'].unique(), key=natural_key)
        if not stacks: stacks = ['Unknown']
        s_idx = stacks.index(t_stk) if t_stk in stacks else 0
        s_stk = st.selectbox("3. 单元", stacks, index=s_idx, key="stk_v82")

    # 4. 计算
    if st.button("🚀 开始估值", type="primary", use_container_width=True):
        area, psf, val, _, _, comps, _ = calculate_avm(df, s_blk, s_stk, s_flr)
        if area:
            st.session_state.avm_res = {'area':area, 'psf':psf, 'val':val, 'blk':s_blk, 'stk':s_stk, 'flr':s_flr, 'comps':comps}
        else:
            st.error("数据不足"); st.session_state.avm_res = None

    # 5. 显示
    if st.session_state.avm_res:
        res = st.session_state.avm_res
        val = res['val']
        
        # 历史数据获取
        hist = df[(df['BLK']==res['blk']) & (df['Stack']==res['stk']) & (df['Floor_Num']==res['flr'])].sort_values('Sale Date')
        last_p, gain, ssd = 0, 0, 0
        if not hist.empty:
            last = hist.iloc[-1]
            last_p = last['Sale Price']
            ssd_rate, _, ssd_txt = calculate_ssd_status(last['Sale Date'])
            ssd = val * ssd_rate
            gain = val - last_p - ssd

        st.markdown("---")
        k1, k2, k3 = st.columns(3)
        k1.metric("估值", f"${val/1e6:.2f}M", delta=f"{gain/1e6:+.2f}M" if last_p else None)
        k2.metric("尺价", f"${res['psf']:,.0f} psf")
        k3.metric("面积", f"{int(res['area']):,} sqft")

        # 仪表盘
        fig = go.Figure(go.Indicator(mode="number+gauge", value=val, number={'prefix':"$",'valueformat':",.0f"},
            gauge={'axis':{'range':[val*0.85, val*1.15]}, 'bar':{'color':"#1f77b4"}, 
                   'steps':[{'range':[val*0.85, val*0.95], 'color':"#f2f2f2"},{'range':[val*0.95, val*1.05], 'color':"#cbf3f0"},{'range':[val*1.05, val*1.15], 'color':"#f2f2f2"}]}))
        fig.update_layout(height=120, margin=dict(t=20, b=20)); st.plotly_chart(fig, use_container_width=True)

        # 历史 (防崩)
        st.subheader("📜 本单位历史")
        if not hist.empty:
            cols = [c for c in ['Sale Date','Sale Price','Sale PSF','Type of Sale'] if c in hist.columns]
            st.dataframe(hist[cols].style.format({'Sale Price':"${:,.0f}",'Sale PSF':"${:,.0f}"}), use_container_width=True)
            if ssd > 0: st.warning(f"SSD: {ssd_txt}")
            else: st.success("SSD Free")
        else: st.info("无记录")

        # 周边
        st.subheader("📉 周边参考")
        ccols = [c for c in ['Sale Date','Unit','Sale Price','Sale PSF','Area (sqft)'] if c in res['comps'].columns]
        st.dataframe(res['comps'][ccols].style.format({'Sale Price':"${:,.0f}",'Sale PSF':"${:,.0f}",'Area (sqft)':"{:,.0f}"}), use_container_width=True)

        # PDF
        st.markdown("---")
        if PDF_AVAILABLE:
            u_info = {'blk':res['blk'], 'unit':f"{res['flr']:02d}-{res['stk']}"}
            v_data = {'value':val, 'area':res['area'], 'psf':res['psf']}
            a_data = {'net_gain':gain, 'ssd_cost':ssd, 'last_price':last_p}
            try:
                pdf = generate_pdf_report(project_name, u_info, v_data, a_data, hist, res['comps'], df['Sale Date'].max().strftime('%Y-%m-%d'))
                st.download_button("📥 下载PDF", data=pdf, file_name="Valuation.pdf", mime="application/pdf", type="primary", use_container_width=True)
            except Exception as e: st.warning(f"PDF生成失败: {e}")
