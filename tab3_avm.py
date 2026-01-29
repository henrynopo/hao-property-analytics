# tab3_avm.py
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from utils import calculate_avm, calculate_ssd_status, natural_key
from pdf_gen import generate_pdf_report, PDF_AVAILABLE

def render(df, project_name, chart_font_size):
    st.subheader("💎 单元智能估值 (AVM)")

    # --- 1. 初始化 Session State (关键：防止布局闪烁乱套) ---
    if 'avm_result' not in st.session_state:
        st.session_state.avm_result = None

    # --- 2. 自动定位逻辑 ---
    target_blk, target_floor, target_stack = None, None, None
    if 'avm_target' in st.session_state:
        tgt = st.session_state['avm_target']
        target_blk, target_floor, target_stack = tgt['blk'], tgt['floor'], tgt['stack']
        st.success(f"📍 已定位: {target_blk} #{target_floor}-{target_stack}")
        # 这里不立刻删除，防止刷新丢失，但在重新选择时会覆盖
        del st.session_state['avm_target']

    # --- 3. 输入区 (Block > Floor > Stack) ---
    # 保持下拉菜单和自然排序
    c1, c2, c3 = st.columns(3)
    
    with c1:
        blks = sorted(df['BLK'].unique(), key=natural_key)
        b_idx = blks.index(target_blk) if target_blk in blks else 0
        s_blk = st.selectbox("1. 楼座 (Block)", blks, index=b_idx, key="avm_blk_lock")

    with c2:
        blk_df = df[df['BLK'] == s_blk]
        if 'Floor_Num' in blk_df.columns:
            valid_floors = sorted(blk_df['Floor_Num'].dropna().unique().astype(int))
        else:
            valid_floors = [1]
        if not valid_floors: valid_floors = [1]
        
        f_idx = valid_floors.index(target_floor) if target_floor in valid_floors else len(valid_floors)//2
        s_floor = st.selectbox("2. 楼层 (Floor)", valid_floors, index=f_idx, key="avm_floor_lock")

    with c3:
        relevant_stacks = sorted(blk_df[blk_df['Floor_Num'] == s_floor]['Stack'].unique(), key=natural_key)
        if not relevant_stacks:
            relevant_stacks = sorted(blk_df['Stack'].unique(), key=natural_key)
        if not relevant_stacks: relevant_stacks = ['Unknown']
        
        s_idx = relevant_stacks.index(target_stack) if target_stack in relevant_stacks else 0
        s_stack = st.selectbox("3. 单元 (Stack)", relevant_stacks, index=s_idx, key="avm_stack_lock")

    # --- 4. 触发计算 (并将结果存入 Session State) ---
    if st.button("🚀 开始估值", type="primary", use_container_width=True):
        area, val_psf, valuation, floor_diff, prem_rate, comps_df, subject_cat = calculate_avm(df, s_blk, s_stack, s_floor)
        
        if area is None:
            st.error("❌ 数据不足，无法估值")
            st.session_state.avm_result = None # 清空旧结果
        else:
            # 存入 Session State，锁住结果！
            st.session_state.avm_result = {
                'area': area, 'val_psf': val_psf, 'valuation': valuation,
                's_blk': s_blk, 's_stack': s_stack, 's_floor': s_floor,
                'comps_df': comps_df
            }

    # --- 5. 结果渲染区 (从 Session State 读取，保证布局不乱) ---
    if st.session_state.avm_result is not None:
        res = st.session_state.avm_result
        
        # 解包数据
        area = res['area']
        valuation = res['valuation']
        val_psf = res['val_psf']
        curr_blk, curr_stack, curr_floor = res['s_blk'], res['s_stack'], res['s_floor']
        comps_df = res['comps_df']

        # 获取历史数据
        hist_df = df[(df['BLK'] == curr_blk) & (df['Stack'] == curr_stack) & (df['Floor_Num'] == curr_floor)].sort_values('Sale Date')
        
        # 计算增值与SSD
        last_price, net_gain, ssd_cost = 0, 0, 0
        if not hist_df.empty:
            last_tx = hist_df.iloc[-1]
            last_price = last_tx['Sale Price']
            last_date = last_tx['Sale Date']
            ssd_rate, ssd_emoji, ssd_text = calculate_ssd_status(last_date)
            ssd_cost = valuation * ssd_rate
            net_gain = valuation - last_price - ssd_cost
        else:
            ssd_rate, ssd_emoji, ssd_text = 0, "", ""

        st.markdown("---")
        
        # [布局 A] 核心指标 (Metrics)
        m1, m2, m3 = st.columns(3)
        m1.metric("预估总价", f"${valuation/1e6:.2f}M", delta=f"{net_gain/1e6:+.2f}M" if last_price else None)
        m2.metric("预估尺价", f"${val_psf:,.0f} psf")
        m3.metric("单位面积", f"{int(area):,} sqft")

        # [布局 B] 仪表盘 (深蓝指针)
        fig = go.Figure(go.Indicator(
            mode="number+gauge", value=valuation,
            number={'prefix': "$", 'valueformat': ",.0f"},
            gauge={
                'axis': {'range': [valuation*0.85, valuation*1.15]},
                'bar': {'color': "#1f77b4"}, # 深蓝色
                'steps': [
                    {'range': [valuation*0.85, valuation*0.95], 'color': "#f0f2f6"},
                    {'range': [valuation*0.95, valuation*1.05], 'color': "#cbf3f0"}, # 浅绿
                    {'range': [valuation*1.05, valuation*1.15], 'color': "#f0f2f6"}
                ]
            }
        ))
        fig.update_layout(height=120, margin=dict(t=30, b=20))
        st.plotly_chart(fig, use_container_width=True)

        # [布局 C] 历史成交 (在上)
        st.subheader("📜 本单位历史 (History)")
        if not hist_df.empty:
            # 🟢 终极防崩：只显示存在的列
            cols = [c for c in ['Sale Date', 'Sale Price', 'Sale PSF', 'Type of Sale'] if c in hist_df.columns]
            st.dataframe(hist_df[cols].style.format({'Sale Price': "${:,.0f}", 'Sale PSF': "${:,.0f}"}), use_container_width=True)
            
            if ssd_rate > 0: st.warning(f"⚠️ 需付 SSD: {ssd_text}")
            else: st.success("✅ SSD Free")
        else:
            st.info("无历史记录")

        # [布局 D] 周边成交 (在下)
        st.subheader("📉 周边参考 (Comps)")
        c_cols = [c for c in ['Sale Date', 'Unit', 'Sale Price', 'Sale PSF', 'Area (sqft)'] if c in comps_df.columns]
        st.dataframe(comps_df[c_cols].style.format({'Sale Price': "${:,.0f}", 'Sale PSF': "${:,.0f}", 'Area (sqft)': "{:,.0f}"}), use_container_width=True)

        # [布局 E] PDF 下载
        st.markdown("---")
        if PDF_AVAILABLE:
            u_info = {'blk': curr_blk, 'unit': f"{curr_floor:02d}-{curr_stack}"}
            v_data = {'value': valuation, 'area': area, 'psf': val_psf}
            a_data = {'net_gain': net_gain, 'ssd_cost': ssd_cost, 'last_price': last_price}
            d_cut = df['Sale Date'].max().strftime('%Y-%m-%d')
            
            try:
                # 传入数据生成 PDF
                pdf = generate_pdf_report(project_name, u_info, v_data, a_data, hist_df, comps_df, d_cut)
                st.download_button("📄 下载 PDF 信函", data=pdf, file_name=f"Valuation_{curr_blk}_{curr_floor}-{curr_stack}.pdf", mime="application/pdf", type="primary", use_container_width=True)
            except Exception as e:
                # 优雅处理 PDF 生成错误，不影响主界面
                st.warning(f"PDF生成暂时不可用: {e}")
