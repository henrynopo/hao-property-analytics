# pdf_gen.py
from datetime import datetime
from utils import AGENT_PROFILE
import pandas as pd

try:
    from fpdf import FPDF
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

if PDF_AVAILABLE:
    class PDFReport(FPDF):
        def header(self):
            # 简洁的 Header
            self.set_font('Arial', 'B', 10)
            self.set_text_color(100, 100, 100)
            self.cell(0, 5, f"{AGENT_PROFILE['Company']} ({AGENT_PROFILE['License']})", 0, 1, 'L')
            
            self.set_y(10)
            self.set_font('Arial', '', 9)
            info = f"{AGENT_PROFILE['Name']} | {AGENT_PROFILE['RES_No']} | {AGENT_PROFILE['Mobile']}"
            self.cell(0, 5, info, 0, 1, 'R')
            
            self.ln(2)
            self.set_draw_color(200, 200, 200)
            self.line(10, self.get_y(), 200, self.get_y())
            self.ln(5)

        def footer(self):
            self.set_y(-15)
            self.set_font('Arial', 'I', 7)
            self.set_text_color(150, 150, 150)
            disclaimer = "Disclaimer: Values are estimates (AVM) for reference only. Data source: URA/Huttons. Accuracy not guaranteed."
            self.cell(0, 5, f'{disclaimer} | Page {self.page_no()}', 0, 0, 'C')

        def add_watermark(self):
            # 水印颜色更淡
            self.set_font('Arial', 'B', 40)
            self.set_text_color(245, 245, 245)
            with self.rotation(45, 105, 148):
                self.text(40, 190, AGENT_PROFILE['Name'].upper())

    def draw_gauge_bar(pdf, x, y, w, h, low, high, current):
        # 绘制简单的估值区间条
        # 背景条 (灰色)
        pdf.set_fill_color(230, 230, 230)
        pdf.rect(x, y, w, h, 'F')
        
        # 计算相对位置
        val_range = high - low
        if val_range == 0: val_range = 1
        
        # 绿色安全区 (Low ~ Current)
        safe_w = ((current - low) / val_range) * w
        safe_w = max(0, min(w, safe_w)) # Clamp
        
        pdf.set_fill_color(144, 238, 144) # Light Green
        pdf.rect(x, y, safe_w, h, 'F')
        
        # 当前值标记线
        pdf.set_draw_color(0, 0, 0)
        pdf.set_line_width(0.5)
        pdf.line(x + safe_w, y - 2, x + safe_w, y + h + 2)
        
        # 文字标签
        pdf.set_font('Arial', '', 7)
        pdf.set_text_color(100, 100, 100)
        pdf.text(x, y + h + 4, f"${low/1e6:.2f}M")
        pdf.text(x + w - 10, y + h + 4, f"${high/1e6:.2f}M")
        
        pdf.set_font('Arial', 'B', 8)
        pdf.set_text_color(0, 0, 0)
        pdf.text(x + safe_w - 5, y - 3, "Valuation")

    def generate_pdf_report(project_name, unit_info, valuation_data, analysis_data, history_df, comps_df, data_cutoff):
        pdf = PDFReport()
        pdf.add_page()
        pdf.add_watermark()
        
        # === 1. Title Section ===
        pdf.set_font('Arial', 'B', 18)
        pdf.set_text_color(44, 62, 80)
        pdf.cell(0, 8, f"Valuation Report: {project_name}", 0, 1, 'C')
        
        pdf.set_font('Arial', '', 12)
        pdf.cell(0, 6, f"Unit: Block {unit_info['blk']} {unit_info['unit']}", 0, 1, 'C')
        
        pdf.set_font('Arial', 'I', 8)
        pdf.set_text_color(120, 120, 120)
        pdf.cell(0, 5, f"Generated: {datetime.now().strftime('%Y-%m-%d')} | Data Cutoff: {data_cutoff}", 0, 1, 'C')
        pdf.ln(5)
        
        # === 2. Valuation Box (紧凑版) ===
        box_h = 24 # 降低高度
        y_val = pdf.get_y()
        
        pdf.set_fill_color(240, 248, 255) # AliceBlue
        pdf.rect(10, y_val, 190, box_h, 'F')
        pdf.set_y(y_val + 4)
        
        # Row 1: Headers
        pdf.set_font('Arial', 'B', 10)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(63, 5, "Estimated Value", 0, 0, 'C')
        pdf.cell(63, 5, "Unit Area", 0, 0, 'C')
        pdf.cell(63, 5, "Est. PSF", 0, 1, 'C')
        
        # Row 2: Values
        pdf.set_font('Arial', 'B', 14)
        pdf.set_text_color(39, 174, 96) # Green
        pdf.cell(63, 8, f"${valuation_data['value']/1e6:.2f}M", 0, 0, 'C')
        
        pdf.set_text_color(0, 0, 0)
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(63, 8, f"{int(valuation_data['area']):,} sqft", 0, 0, 'C')
        pdf.cell(63, 8, f"${int(valuation_data['psf']):,}", 0, 1, 'C')
        
        # === 3. Analysis Box (紧凑版) ===
        pdf.set_y(y_val + box_h + 5)
        y_ana = pdf.get_y()
        
        pdf.set_fill_color(255, 250, 240) # FloralWhite
        pdf.rect(10, y_ana, 190, box_h, 'F')
        pdf.set_y(y_ana + 4)
        
        pdf.set_font('Arial', 'B', 10)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(63, 5, "Est. Net Gain", 0, 0, 'C')
        pdf.cell(63, 5, "SSD Liability", 0, 0, 'C')
        pdf.cell(63, 5, "Last Transacted", 0, 1, 'C')
        
        # Values
        pdf.set_font('Arial', 'B', 12)
        gain = analysis_data['net_gain']
        if gain > 0: 
            pdf.set_text_color(39, 174, 96)
            gain_str = f"+${gain/1e6:.2f}M"
        elif gain < 0:
            pdf.set_text_color(231, 76, 60)
            gain_str = f"-${abs(gain)/1e6:.2f}M"
        else:
            pdf.set_text_color(100, 100, 100)
            gain_str = "-"
            
        pdf.cell(63, 8, gain_str, 0, 0, 'C')
        
        pdf.set_text_color(0, 0, 0)
        ssd = analysis_data['ssd_cost']
        pdf.cell(63, 8, f"${ssd/1e6:.2f}M" if ssd > 0 else "N.A.", 0, 0, 'C')
        
        last_px = analysis_data['last_price']
        pdf.cell(63, 8, f"${last_px/1e6:.2f}M" if last_px > 0 else "Unknown", 0, 1, 'C')
        
        # === 4. Valuation Range Chart (新功能) ===
        pdf.ln(8)
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(0, 6, "Valuation Confidence Range", 0, 1, 'L')
        
        # 绘制图表
        low_val = valuation_data['value'] * 0.95
        high_val = valuation_data['value'] * 1.05
        draw_gauge_bar(pdf, 15, pdf.get_y()+2, 180, 4, low_val, high_val, valuation_data['value'])
        pdf.ln(12)
        
        # === 5. Comps Table (紧凑表格) ===
        
        def render_table(df_data, title):
            if pdf.get_y() > 240: pdf.add_page() # 自动分页
            
            pdf.set_font('Arial', 'B', 11)
            pdf.set_text_color(44, 62, 80)
            pdf.cell(0, 8, title, 0, 1, 'L')
            
            if df_data.empty:
                pdf.set_font('Arial', 'I', 9)
                pdf.cell(0, 6, "No recent records found.", 0, 1, 'L')
                pdf.ln(5)
                return

            # Table Header
            pdf.set_fill_color(220, 220, 220)
            pdf.set_text_color(0, 0, 0)
            pdf.set_font('Arial', 'B', 8)
            
            # Cols: Date, Unit, Price, PSF, Area
            w_date, w_unit, w_price, w_psf, w_area = 30, 30, 35, 25, 25
            pdf.cell(w_date, 6, 'Date', 1, 0, 'C', True)
            pdf.cell(w_unit, 6, 'Unit', 1, 0, 'C', True)
            pdf.cell(w_price, 6, 'Price ($)', 1, 0, 'C', True)
            pdf.cell(w_psf, 6, 'PSF ($)', 1, 0, 'C', True)
            pdf.cell(w_area, 6, 'Area', 1, 1, 'C', True)
            
            # Table Body
            pdf.set_font('Arial', '', 8)
            pdf.set_fill_color(255, 255, 255)
            
            for _, row in df_data.iterrows():
                # Format
                dt_str = row['Sale Date'].strftime('%d-%b-%y') if hasattr(row['Sale Date'], 'strftime') else str(row['Sale Date'])
                
                # Unit check
                unit_str = row['Unit'] if 'Unit' in row else f"#{int(row.get('Floor_Num', 0)):02d}-??"
                
                px_str = f"${row['Sale Price']:,.0f}" if pd.notnull(row['Sale Price']) else "-"
                psf_str = f"${row['Sale PSF']:,.0f}" if pd.notnull(row['Sale PSF']) else "-"
                area_str = f"{int(row['Area (sqft)'])}" if pd.notnull(row['Area (sqft)']) else "-"
                
                pdf.cell(w_date, 6, dt_str, 1, 0, 'C')
                pdf.cell(w_unit, 6, unit_str, 1, 0, 'C')
                pdf.cell(w_price, 6, px_str, 1, 0, 'C')
                pdf.cell(w_psf, 6, psf_str, 1, 0, 'C')
                pdf.cell(w_area, 6, area_str, 1, 1, 'C')
            
            pdf.ln(5)

        # 渲染两个表格
        # 1. 最近成交 (Comps)
        render_table(comps_df.head(5), "Recent Comparable Transactions (Comps)")
        
        # 2. 本单位历史 (History)
        render_table(history_df, "Unit Transaction History")
        
        return bytes(pdf.output())
