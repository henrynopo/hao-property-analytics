# tab3_avm.py
import streamlit as st
import pandas as pd
from utils import calculate_avm, calculate_ssd_status
from pdf_gen import generate_pdf_report, PDF_AVAILABLE

def render(df, project_name, chart_font_size):
    st.subheader("💎 单元智能估值 (AVM)")

    # 1. 自动定位逻辑 (处理从 Tower View 跳转过来的请求)
    default_blk_idx = 0
    default_stack_idx = 0
    default_floor = 10

    if 'avm_target' in st.session_state:
        tgt = st.session_state['avm_target']
        try:
            blks = sorted(df['BLK'].unique())
            if tgt['blk'] in blks:
                default_blk_idx = blks.index(tgt['blk'])
                
            stacks = sorted(df[df['BLK']==tgt['blk']]['Stack'].unique())
            if tgt['stack'] in stacks:
                default_stack_idx = stacks.index(tgt['stack'])
            
            default_floor = tgt['floor']
            st.success(f"已定位到: Block {tgt['blk']} #{tgt['floor']}-{tgt['stack']}")
            del st.session_state['avm_target'] # 用完即焚
        except:
            pass # 如果定位失败，就用默认值，不报错

    # 2. 简洁的输入栏 (三列布局)
    c1, c2, c3 = st.columns(3)
    with c1:
        blks = sorted(df['BLK'].unique())
        s_blk = st.selectbox("Block", blks, index=default_blk_idx, key="avm_blk_input")
    with c2:
        stacks = sorted(df[df['BLK']==s_blk]['Stack'].unique())
        if not stacks: stacks = ['Unknown']
        s_stack = st.selectbox("Stack", stacks, index=min(default_stack_idx, len(stacks)-1), key="avm_stack_input")
    with c3:
        s_floor = st.number_input("Floor", min_value=1, max_value=50, value=default_floor, step=1, key="avm_floor_input")

    # 3. 核心功能区
    if st.button("🚀 开始估值", type="primary", use_container_width=True):
        
        # 计算逻辑
        area, val_psf, valuation, floor_diff, prem_rate, comps_df, subject_cat = calculate_avm(df, s_blk, s_stack, s_floor)

        if area is None:
            st.error("❌ 数据不足，无法估值。")
            return

        # === 界面渲染 (V46 经典样式) ===
        st.markdown("---")
        
        # 顶部指标卡 (Metrics)
        m1, m2, m3 = st.columns(3)
        m1.metric("预估总价 (Est. Value)", f"${valuation/1e6:.2f}M")
        m2.metric("预估尺价 (Est. PSF)", f"${val_psf:,.0f} psf")
        m3.metric("单位面积 (Area)", f"{int(area):,} sqft")
        
        # 详细分析区 (左侧文字，右侧表格)
        c_left, c_right = st.columns([1, 1])
        
        with c_left:
            st.caption("📊 盈利分析")
            
            # 获取历史数据
            hist_df = df[(df['BLK'] == s_blk) & (df['Stack'] == s_stack) & (df['Floor_Num'] == s_floor)].sort_values('Sale Date')
            
            last_price = 0
            net_gain = 0
            ssd_cost = 0
            
            if not hist_df.empty:
                last_tx = hist_df.iloc[-1]
                last_price = last_tx['Sale Price']
                last_date = last_tx['Sale Date']
                
                # SSD & Gain
                ssd_rate, ssd_emoji, ssd_text = calculate_ssd_status(last_date)
                ssd_cost = valuation * ssd_rate
                net_gain = valuation - last_price - ssd_cost
                
                st.info(f"上次成交: ${last_price/1e6:.2f}M ({last_date.strftime('%Y-%m-%d')})")
                
                if ssd_rate > 0:
                    st.warning(f"⚠️ {ssd_text}: 需付 ${ssd_cost/1e6:.2f}M SSD")
                else:
                    st.success("✅ SSD Free")
                    
                color = "green" if net_gain > 0 else "red"
                st.markdown(f"**潜在收益:** :{color}[${net_gain/1e6:.2f}M]")
            else:
                st.warning("⚠️ 无历史成交记录")

        with c_right:
            st.caption("📉 参考成交 (Comps)")
            st.dataframe(
                comps_df[['Sale Date', 'Unit', 'Sale Price', 'Sale PSF']].style.format({
                    'Sale Price': "${:,.0f}", 'Sale PSF': "${:,.0f}"
                }),
                height=200, use_container_width=True
            )

        # PDF 下载区
        st.markdown("---")
        if PDF_AVAILABLE:
            # 准备数据包
            u_info = {'blk': s_blk, 'unit': f"{s_floor:02d}-{s_stack}"}
            v_data = {'value': valuation, 'area': area, 'psf': val_psf}
            a_data = {'net_gain': net_gain, 'ssd_cost': ssd_cost, 'last_price': last_price}
            d_cut = df['Sale Date'].max().strftime('%Y-%m-%d')
            
            # 生成信函版 PDF (调用 pdf_gen.py)
            pdf_data = generate_pdf_report(
                project_name, u_info, v_data, a_data, hist_df, comps_df, d_cut
            )
            
            st.download_button(
                label="📄 下载正式估值信函 (PDF Letter)",
                data=pdf_data,
                file_name=f"Valuation_{project_name}_{s_blk}_{s_floor}-{s_stack}.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True
            )
