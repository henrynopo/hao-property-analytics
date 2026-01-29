# tab3_avm.py
import streamlit as st
import pandas as pd
from utils import calculate_avm, calculate_ssd_status, calculate_resale_metrics
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
            # 清除状态，避免锁死
            del st.session_state['avm_target']
        except:
            pass

    # 2. 输入区域
    c1, c2, c3 = st.columns(3)
    with c1:
        blks = sorted(df['BLK'].unique())
        s_blk = st.selectbox("Block", blks, index=default_blk_idx, key="avm_blk")
    with c2:
        stacks = sorted(df[df['BLK']==s_blk]['Stack'].unique())
        # 保护逻辑：防止 stack 列表为空
        if not stacks: stacks = ['Unknown']
        s_stack = st.selectbox("Stack", stacks, index=min(default_stack_idx, len(stacks)-1), key="avm_stack")
    with c3:
        s_floor = st.number_input("Floor", min_value=1, max_value=50, value=default_floor, step=1, key="avm_floor")

    # 3. 触发估值
    if st.button("🚀 开始估值", type="primary", use_container_width=True):
        
        # 调用 utils.py 中的核心算法
        area, val_psf, valuation, floor_diff, prem_rate, comps_df, subject_cat = calculate_avm(df, s_blk, s_stack, s_floor)

        if area is None:
            st.error("❌ 无法估值：该 Stack 数据不足，或者找不到基础户型信息。")
            return

        # === 显示结果 ===
        st.markdown("---")
        
        # 核心大卡片
        col_main, col_chart = st.columns([1, 1])
        
        with col_main:
            st.caption(f"🎯 估值对象: {project_name} | {subject_cat}")
            st.markdown(f"## {s_blk} #{s_floor:02d}-{s_stack}")
            
            metric_cols = st.columns(3)
            metric_cols[0].metric("预估总价", f"${valuation/1e6:.2f}M")
            metric_cols[1].metric("预估尺价", f"${val_psf:,.0f} psf")
            metric_cols[2].metric("单位面积", f"{int(area):,} sqft")
            
            # 盈利与风险分析
            # 获取上一次交易记录
            target_unit_history = df[(df['BLK'] == s_blk) & (df['Stack'] == s_stack) & (df['Floor_Num'] == s_floor)].sort_values('Sale Date')
            
            last_price = 0
            net_gain = 0
            ssd_cost = 0
            
            if not target_unit_history.empty:
                last_tx = target_unit_history.iloc[-1]
                last_price = last_tx['Sale Price']
                last_date = last_tx['Sale Date']
                
                # SSD 计算
                ssd_rate, ssd_emoji, ssd_text = calculate_ssd_status(last_date)
                ssd_cost = valuation * ssd_rate
                
                # 净利计算 (简单减法，不含印花税等)
                net_gain = valuation - last_price - ssd_cost
                
                st.info(f"上次成交: ${last_price/1e6:.2f}M ({last_date.strftime('%Y-%m-%d')})")
                
                if ssd_rate > 0:
                    st.warning(f"⚠️ {ssd_text}: 需缴纳约 ${ssd_cost/1e6:.2f}M 税费")
                else:
                    st.success(f"✅ SSD Free: 无需缴纳卖家印花税")
                    
                color = "green" if net_gain > 0 else "red"
                st.markdown(f"**潜在账面收益:** :{color}[${net_gain/1e6:.2f}M]")
            else:
                st.warning("⚠️ 此单位无历史成交记录，无法计算增值。")

        # 参考数据展示
        with col_chart:
            st.caption("📉 最近同类成交参考 (Comps)")
            st.dataframe(
                comps_df[['Sale Date', 'Unit', 'Sale Price', 'Sale PSF', 'Area (sqft)']].style.format({
                    'Sale Price': "${:,.0f}", 'Sale PSF': "${:,.0f}", 'Area (sqft)': "{:,.0f}"
                }), 
                height=200, use_container_width=True
            )

        # === 4. PDF 导出功能 ===
        st.markdown("---")
        if PDF_AVAILABLE:
            # 准备数据包
            unit_info = {'blk': s_blk, 'unit': f"{s_floor:02d}-{s_stack}"}
            valuation_data = {'value': valuation, 'area': area, 'psf': val_psf}
            analysis_data = {'net_gain': net_gain, 'ssd_cost': ssd_cost, 'last_price': last_price}
            data_cutoff = df['Sale Date'].max().strftime('%Y-%m-%d')
            
            # 生成 PDF
            pdf_bytes = generate_pdf_report(
                project_name, 
                unit_info, 
                valuation_data, 
                analysis_data, 
                target_unit_history, # 历史记录
                comps_df,            # 周边参考
                data_cutoff
            )
            
            st.download_button(
                label="📄 下载正式估值报告 (PDF Letter)",
                data=pdf_bytes,
                file_name=f"Valuation_{project_name}_{s_blk}_{s_floor}-{s_stack}.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True
            )
        else:
            st.warning("⚠️ PDF 生成组件不可用，请检查 server 端 fpdf 库是否安装。")
