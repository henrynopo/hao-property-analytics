# tab3_avm.py
import streamlit as st
import pandas as pd
from utils import calculate_avm, calculate_ssd_status
from pdf_gen import generate_pdf_report, PDF_AVAILABLE

def render(df, project_name, chart_font_size):
    st.subheader("💎 单元智能估值 (AVM)")

    # 1. 接收来自 Tower View 的跳转参数
    default_blk_idx = 0
    default_stack_idx = 0
    default_floor = 10

    if 'avm_target' in st.session_state:
        tgt = st.session_state['avm_target']
        try:
            blks = sorted(df['BLK'].unique())
            default_blk_idx = blks.index(tgt['blk'])
            
            stacks = sorted(df[df['BLK']==tgt['blk']]['Stack'].unique())
            default_stack_idx = stacks.index(tgt['stack'])
            
            default_floor = tgt['floor']
            st.success(f"已自动定位: Block {tgt['blk']} #{tgt['floor']}-{tgt['stack']}")
            del st.session_state['avm_target'] # 清除状态
        except:
            pass

    # 2. 输入区域 (保持简洁)
    c1, c2, c3 = st.columns(3)
    with c1:
        blks = sorted(df['BLK'].unique())
        s_blk = st.selectbox("Block", blks, index=default_blk_idx, key="avm_blk")
    with c2:
        stacks = sorted(df[df['BLK']==s_blk]['Stack'].unique())
        if not stacks: stacks = ['Unknown']
        s_stack = st.selectbox("Stack", stacks, index=min(default_stack_idx, len(stacks)-1), key="avm_stack")
    with c3:
        s_floor = st.number_input("Floor", min_value=1, max_value=50, value=default_floor, step=1, key="avm_floor")

    # 3. 触发估值
    if st.button("🚀 开始估值", type="primary", use_container_width=True):
        
        # 计算核心数据
        area, val_psf, valuation, floor_diff, prem_rate, comps_df, subject_cat = calculate_avm(df, s_blk, s_stack, s_floor)

        if area is None:
            st.error("❌ 无法估值：该 Stack 数据不足，或者找不到基础户型信息。")
            return

        # === 恢复简洁的 UI 布局 ===
        st.markdown("---")
        
        # 顶部：核心指标 (三列 Metric)
        m1, m2, m3 = st.columns(3)
        m1.metric("预估总价 (Est. Value)", f"${valuation/1e6:.2f}M")
        m2.metric("预估尺价 (Est. PSF)", f"${val_psf:,.0f} psf")
        m3.metric("单位面积 (Area)", f"{int(area):,} sqft")
        
        # 中部：分析信息 (两列)
        col_main, col_chart = st.columns([1, 1])
        
        with col_main:
            st.caption("📊 盈利与风险分析")
            
            # 获取历史记录
            target_unit_history = df[(df['BLK'] == s_blk) & (df['Stack'] == s_stack) & (df['Floor_Num'] == s_floor)].sort_values('Sale Date')
            
            last_price = 0
            net_gain = 0
            ssd_cost = 0
            
            if not target_unit_history.empty:
                last_tx = target_unit_history.iloc[-1]
                last_price = last_tx['Sale Price']
                last_date = last_tx['Sale Date']
                
                # 计算 SSD 和 净利
                ssd_rate, ssd_emoji, ssd_text = calculate_ssd_status(last_date)
                ssd_cost = valuation * ssd_rate
                net_gain = valuation - last_price - ssd_cost
                
                # 显示上次成交
                st.info(f"上次成交: ${last_price/1e6:.2f}M ({last_date.strftime('%Y-%m-%d')})")
                
                # 显示 SSD 警告
                if ssd_rate > 0:
                    st.warning(f"⚠️ {ssd_text}: 需缴纳约 ${ssd_cost/1e6:.2f}M 税费")
                else:
                    st.success(f"✅ SSD Free: 无需缴纳卖家印花税")
                
                # 显示潜在收益
                color = "green" if net_gain > 0 else "red"
                st.markdown(f"**潜在账面收益:** :{color}[${net_gain/1e6:.2f}M]")
            else:
                st.warning("⚠️ 此单位无历史成交记录，无法计算具体增值。")

        with col_chart:
            st.caption("📉 最近同类成交参考 (Comps)")
            st.dataframe(
                comps_df[['Sale Date', 'Unit', 'Sale Price', 'Sale PSF']].style.format({
                    'Sale Price': "${:,.0f}", 'Sale PSF': "${:,.0f}"
                }), 
                height=200, use_container_width=True
            )

        # === PDF 导出 (这里调用信函格式，但网页不显示信函) ===
        st.markdown("---")
        if PDF_AVAILABLE:
            # 数据打包
            unit_info = {'blk': s_blk, 'unit': f"{s_floor:02d}-{s_stack}"}
            valuation_data = {'value': valuation, 'area': area, 'psf': val_psf}
            analysis_data = {'net_gain': net_gain, 'ssd_cost': ssd_cost, 'last_price': last_price}
            data_cutoff = df['Sale Date'].max().strftime('%Y-%m-%d')
            
            # 生成
            pdf_bytes = generate_pdf_report(
                project_name, 
                unit_info, 
                valuation_data, 
                analysis_data, 
                target_unit_history, 
                comps_df, 
                data_cutoff
            )
            
            st.download_button(
                label="📄 下载正式估值信函 (PDF Letter)",
                data=pdf_bytes,
                file_name=f"Letter_{project_name}_{s_blk}_{s_floor}-{s_stack}.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True
            )
