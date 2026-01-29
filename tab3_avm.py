import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from utils import natural_key, calculate_avm, calculate_ssd_status, format_currency
from pdf_gen import generate_pdf_report, PDF_AVAILABLE

def render(df, project_name, chart_font_size):
    st.subheader("💎 AVM 智能估值计算器")
    c_sel_1, c_sel_2, c_sel_3 = st.columns(3)
    def_blk_idx, def_floor_idx, def_stack_idx = 0, 0, 0
    
    all_blks = sorted(df['BLK'].unique(), key=natural_key) if 'BLK' in df.columns else []
    cur_tgt = st.session_state.get('avm_target', {})
    if cur_tgt and cur_tgt.get('blk') in all_blks:
        def_blk_idx = all_blks.index(cur_tgt['blk'])
    
    with c_sel_1:
        sel_blk = st.selectbox("Block (楼栋)", all_blks, index=def_blk_idx, key="avm_blk")
    
    if sel_blk:
        blk_df = df[df['BLK'] == sel_blk]
        max_floor = int(blk_df['Floor_Num'].max())
        all_floors = sorted(list(range(1, max_floor + 1)))
        
        if cur_tgt.get('blk') == sel_blk and cur_tgt.get('floor') in all_floors:
            def_floor_idx = all_floors.index(cur_tgt['floor'])
        
        with c_sel_2:
            sel_floor = st.selectbox("Floor (楼层)", all_floors, index=def_floor_idx, key="avm_floor_sel")
            
        if sel_floor:
            all_stacks = sorted(blk_df['Stack'].unique(), key=natural_key)
            if cur_tgt.get('stack') and str(cur_tgt.get('stack')) in [str(s) for s in all_stacks]:
                stack_list = [str(s) for s in all_stacks]
                def_stack_idx = stack_list.index(str(cur_tgt['stack']))
            
            with c_sel_3:
                sel_stack = st.selectbox("Stack (单元)", all_stacks, index=def_stack_idx, key="avm_stack")
    
    st.divider()

    if sel_blk and sel_stack and sel_floor:
        s_str = str(sel_stack).strip()
        unit_label = f"#{int(sel_floor):02d}-{s_str.zfill(2) if s_str.isdigit() else s_str}"
        st.markdown(f"#### 🏠 估值对象：{sel_blk}, {unit_label}")
        
        try:
            area, est_psf, value, f_diff, prem_rate, comps_df, subj_cat = calculate_avm(df, sel_blk, sel_stack, sel_floor)
            
            if area:
                val_low, val_high = value * 0.9, value * 1.1
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("📐 单元面积", f"{int(area):,} sqft")
                m2.metric(f"📊 估算 PSF ({prem_rate*100:.1f}% 溢价)", f"${int(est_psf):,} psf", f"{f_diff:+.0f} 层 (vs 均值)", delta_color="normal" if f_diff > 0 else "inverse")
                m3.metric("💰 HAO 估值", f"${value/1e6:.2f}M")
                
                hist_unit = df[(df['BLK'] == sel_blk) & (df['Stack'] == sel_stack) & (df['Floor_Num'] == sel_floor)].sort_values('Sale Date', ascending=False)
                
                analysis_data = {'net_gain': 0, 'net_gain_pct': 0, 'ssd_cost': 0, 'last_price': 0, 'is_simulated': False, 'sim_year': 0}

                if not hist_unit.empty:
                    last_p = hist_unit.iloc[0]['Sale Price']
                    last_d = hist_unit.iloc[0]['Sale Date']
                    ssd_rate, _, ssd_txt = calculate_ssd_status(last_d)
                    gross_gain = value - last_p
                    ssd_cost = value * ssd_rate
                    net_gain = gross_gain - ssd_cost
                    m4.metric("🚀 预估净增值", f"${net_gain/1e6:.2f}M", f"{net_gain/last_p:+.1%}", delta_color="normal" if net_gain > 0 else "inverse")
                    if ssd_rate > 0: st.caption(f"⚠️ {ssd_txt}: 扣除 ${ssd_cost/1e6:.2f}M")
                    else: st.caption("✅ SSD Free")
                    analysis_data.update({'net_gain': net_gain, 'net_gain_pct': net_gain/last_p, 'ssd_cost': ssd_cost, 'last_price': last_p})
                else:
                    earliest_yr = int(df['Sale Year'].min())
                    base_recs = df[(df['Sale Year'] == earliest_yr) & (df['Category'] == subj_cat)]
                    if not base_recs.empty:
                        base_avg = base_recs['Sale PSF'].mean()
                        est_cost = area * base_avg
                        sim_gain = value - est_cost
                        m4.metric(f"🔮 模拟增值 (自{earliest_yr}年)", f"${sim_gain/1e6:.2f}M", f"{sim_gain/est_cost:+.1%} (基于当年均价)", delta_color="off")
                        st.caption(f"*注：无历史交易。")
                        analysis_data.update({'net_gain': sim_gain, 'net_gain_pct': sim_gain/est_cost, 'is_simulated': True, 'sim_year': earliest_yr})
                    else:
                        m4.metric("🚀 预估增值", "-", "无同期基准")

                fig_range = go.Figure()
                fig_range.add_trace(go.Scatter(x=[val_low, val_high], y=[0, 0], mode='lines', line=dict(color='#E0E0E0', width=12), hoverinfo='skip'))
                fig_range.add_trace(go.Scatter(x=[val_low, val_high], y=[0, 0], mode='markers+text', marker=dict(color=['#FF6B6B', '#4ECDC4'], size=18), text=[f"${val_low/1e6:.2f}M", f"${val_high/1e6:.2f}M"], textposition="bottom center", hoverinfo='skip'))
                fig_range.add_trace(go.Scatter(x=[value], y=[0], mode='markers+text', marker=dict(color='#2C3E50', size=25, symbol='diamond'), text=[f"${value/1e6:.2f}M"], textposition="top center"))
                fig_range.update_layout(title=dict(text="⚖️ 估值区间", x=0.5, xanchor='center', y=0.9), xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[val_low*0.9, val_high*1.1]), yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-0.5, 0.8]), height=180, margin=dict(l=20, r=20, t=40, b=10), plot_bgcolor='white')
                st.plotly_chart(fig_range, use_container_width=True)

                if PDF_AVAILABLE:
                    pdf_bytes = generate_pdf_report(project_name, {'blk': sel_blk, 'unit': unit_label}, {'value': value, 'area': area, 'psf': int(est_psf)}, analysis_data, hist_unit, comps_df, df['Sale Date'].max().strftime('%Y-%m-%d'))
                    st.download_button(label="📥 下载 PDF 估值报告 (Full Report)", data=pdf_bytes, file_name=f"Valuation_{sel_blk}_{unit_label}.pdf", mime='application/pdf', type="primary")
                else:
                    st.warning("⚠️ PDF 功能不可用 (Missing fpdf2)")

                st.divider()
                c1, c2 = st.columns(2)
                
                with c1:
                    st.write("##### 📜 该单元历史交易")
                    if not hist_unit.empty:
                        disp = hist_unit.copy()
                        disp['Sale Date'] = disp['Sale Date'].dt.date
                        disp['Sale Price'] = disp['Sale Price'].apply(format_currency)
                        disp['Sale PSF'] = disp['Sale PSF'].apply(format_currency)
                        st.dataframe(disp[['Sale Date', 'Unit', 'Sale Price', 'Sale PSF']], hide_index=True, use_container_width=True)
                    else: st.info("暂无历史交易记录")
                
                with c2:
                    st.write(f"##### ⚖️ 估值参考 ({len(comps_df)} 笔相似成交)")
                    if not comps_df.empty:
                        comps_df['Sale Price'] = comps_df['Sale Price'].apply(format_currency)
                        comps_df['Sale PSF'] = comps_df['Sale PSF'].apply(format_currency)
                        comps_df['Adj_PSF'] = comps_df['Adj_PSF'].apply(lambda x: f"{int(x)}")
                        cols = [c for c in ['Sale Date', 'BLK', 'Unit', 'Category', 'Area (sqft)', 'Sale Price', 'Sale PSF', 'Adj_PSF'] if c in comps_df.columns]
                        st.dataframe(comps_df[cols], hide_index=True, use_container_width=True)
                    else: st.warning("数据量不足")
            else: st.error("无法获取面积数据")
        except Exception as e: st.error(f"计算出错: {e}")
