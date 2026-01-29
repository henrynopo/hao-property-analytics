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
            # === Agent Letterhead (页眉) ===
            self.set_font('Arial', 'B', 12)
            self.set_text_color(50, 50, 50)
            # 公司名 & 执照
            self.cell(0, 6, f"{AGENT_PROFILE['Company']}", 0, 1, 'R')
            self.set_font('Arial', '', 8)
            self.cell(0, 4, f"Agency License: {AGENT_PROFILE['License']}", 0, 1, 'R')
            
            # 经纪人信息
            self.ln(2)
            self.set_font('Arial', 'B', 10)
            self.cell(0, 5, f"{AGENT_PROFILE['Name']} ({AGENT_PROFILE['Title']})", 0, 1, 'R')
            self.set_font('Arial', '', 9)
            self.cell(0, 5, f"CEA Reg: {AGENT_PROFILE['RES_No']} | Mobile: {AGENT_PROFILE['Mobile']}", 0, 1, 'R')
            
            # 分割线
            self.ln(5)
            self.set_draw_color(200, 200, 200)
            self.set_line_width(0.5)
            self.line(10, self.get_y(), 200, self.get_y())
            self.ln(5)

        def footer(self):
            self.set_y(-20)
            self.set_font('Arial', 'I', 7)
            self.set_text_color(150, 150, 150)
            disclaimer = "Note: This valuation is an estimate based on recent transaction data (URA/Huttons) and is for reference only."
            self.cell(0, 4, disclaimer, 0, 1, 'C')
            self.cell(0, 4, f"Page {self.page_no()}", 0, 0, 'C')

    def draw_gauge_bar(pdf, x, y, w, h, low, high, current):
        # 绘制估值区间条
        pdf.set_fill_color(240, 240, 240)
        pdf.rect(x, y, w, h, 'F')
        
        val_range = high - low
        if val_range == 0: val_range = 1
        safe_w = ((current - low) / val_range) * w
        safe_w = max(0, min(w, safe_w))
        
        # 绿色进度条
        pdf.set_fill_color(100, 200, 100) 
        pdf.rect(x, y, safe_w, h, 'F')
        
        # 标记线
        pdf.set_draw_color(0, 0, 0)
        pdf.set_line_width(0.5)
        pdf.line(x + safe_w, y - 2, x + safe_w, y + h + 2)
        
        # 标签
        pdf.set_font('Arial', '', 7)
        pdf.set_text_color(100, 100, 100)
        pdf.text(x, y + h + 4, f"${low/1e6:.2f}M")
        pdf.text(x + w - 10, y + h + 4, f"${high/1e6:.2f}M")
        
        pdf.set_font('Arial', 'B', 8)
        pdf.set_text_color(0, 0, 0)
        pdf.text(x + safe_w - 5, y - 3, "Est. Price")

    def generate_pdf_report(project_name, unit_info, valuation_data, analysis_data, history_df, comps_df, data_cutoff):
        pdf = PDFReport()
        pdf.set_margins(20, 20, 20) # 增加页边距，像正式信函
        pdf.add_page()
        
        # === 1. 信函顶部信息 ===
        
        # 日期 (右对齐)
        pdf.set_y(40) # 留出 Header 空间
        pdf.set_font('Arial', '', 10)
        pdf.cell(0, 5, datetime.now().strftime('%d %B, %Y'), 0, 1, 'R')
        
        # 收件人地址 (左对齐 - 适合开窗信封)
        pdf.set_y(45)
        pdf.set_font('Arial', 'B', 11)
        pdf.cell(0, 5, "To: The Subsidiary Proprietor / Owner", 0, 1, 'L')
        pdf.set_font('Arial', '', 11)
        pdf.cell(0, 5, f"Unit #{unit_info['unit']}", 0, 1, 'L') # 例如 #05-12
        pdf.cell(0, 5, f"Block {unit_info['blk']}, {project_name}", 0, 1, 'L')
        pdf.cell(0, 5, "Singapore", 0, 1, 'L')
        
        pdf.ln(15)
        
        # === 2. 正文开头 ===
        pdf.set_font('Arial', '', 11)
        pdf.cell(0, 6, "Dear Homeowner,", 0, 1, 'L')
        pdf.ln(2)
        
        # 引导语
        intro_text = (
            f"I am writing to share a personalized market update for your unit at {project_name}. "
            f"Based on recent transaction trends and our proprietary data models, we have prepared an estimated valuation for your property."
        )
        pdf.multi_cell(0, 6, intro_text)
        pdf.ln(5)
        
        # === 3. 核心估值卡片 (Highlight Box) ===
        box_y = pdf.get_y()
        pdf.set_fill_color(248, 250, 252) # Very light blue background
        pdf.rect(20, box_y, 170, 35, 'F')
        
        # 标题: 估值结果
        pdf.set_y(box_y + 5)
        pdf.set_font('Arial', 'B', 14)
        pdf.set_text_color(44, 62, 80)
        pdf.cell(0, 8, f"Estimated Value: ${valuation_data['value']/1e6:.2f} Million", 0, 1, 'C')
        
        # 副标题: 面积与单价
        pdf.set_font('Arial', '', 11)
        pdf.set_text_color(100, 100, 100)
        detail_str = f"{int(valuation_data['area']):,} sqft  |  ${int(valuation_data['psf']):,} psf"
        pdf.cell(0, 6, detail_str, 0, 1, 'C')
        
        # 仪表盘图表 (嵌入在卡片下方)
        draw_gauge_bar(pdf, 45, pdf.get_y()+2, 120, 4, valuation_data['value']*0.95, valuation_data['value']*1.05, valuation_data['value'])
        pdf.ln(15) # 跳过图表区域
        
        # === 4. 市场分析摘要 ===
        pdf.set_y(pdf.get_y() + 5)
        
        # 盈利分析
        gain = analysis_data['net_gain']
        gain_txt = f"Potential Gain: ${gain/1e6:.2f}M" if gain > 0 else "Analysis: Hold for Upside"
        color = (39, 174, 96) if gain > 0 else (100, 100, 100)
        
        pdf.set_font('Arial', 'B', 10)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(30, 6, "Analysis:", 0, 0)
        pdf.set_text_color(*color)
        pdf.cell(50, 6, gain_txt, 0, 0)
        
        # SSD 状态
        pdf.set_text_color(0, 0, 0)
        pdf.cell(25, 6, "SSD Status:", 0, 0)
        ssd = analysis_data['ssd_cost']
        if ssd > 0:
            pdf.set_text_color(231, 76, 60)
            pdf.cell(40, 6, f"Subject to SSD (${ssd/1e6:.2f}M)", 0, 1)
        else:
            pdf.set_text_color(39, 174, 96)
            pdf.cell(40, 6, "SSD Free (Ready to Sell)", 0, 1)
            
        pdf.ln(5)
        
        # === 5. 交易数据表格 ===
        
        def print_table(df, title):
            if df.empty: return
            # Check page break
            if pdf.get_y() > 220: pdf.add_page()
            
            pdf.set_font('Arial', 'B', 10)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(0, 8, title, 0, 1, 'L')
            
            # Header
            pdf.set_fill_color(230, 230, 230)
            pdf.set_font('Arial', 'B', 8)
            col_w = [25, 30, 30, 25, 25] # Date, Unit, Price, PSF, Area
            headers = ['Date', 'Unit', 'Price ($)', 'PSF ($)', 'Area']
            
            for i, h in enumerate(headers):
                pdf.cell(col_w[i], 6, h, 1, 0, 'C', True)
            pdf.ln()
            
            # Rows
            pdf.set_font('Arial', '', 8)
            for _, row in df.iterrows():
                dt = row['Sale Date'].strftime('%d-%b-%y')
                unit = row['Unit'] if 'Unit' in row else f"#{int(row.get('Floor_Num',0)):02d}-??"
                px = f"${row['Sale Price']:,.0f}"
                psf = f"${row['Sale PSF']:,.0f}"
                area = f"{int(row['Area (sqft)'])}"
                
                pdf.cell(col_w[0], 6, dt, 1, 0, 'C')
                pdf.cell(col_w[1], 6, unit, 1, 0, 'C')
                pdf.cell(col_w[2], 6, px, 1, 0, 'C')
                pdf.cell(col_w[3], 6, psf, 1, 0, 'C')
                pdf.cell(col_w[4], 6, area, 1, 1, 'C')
            pdf.ln(5)

        # 打印表格
        print_table(comps_df.head(5), "Recent Comparable Transactions (Neighbours)")
        if not history_df.empty:
            print_table(history_df, "Transaction History of This Unit")
            
        # === 6. 落款 (Call to Action) ===
        if pdf.get_y() > 240: pdf.add_page()
        pdf.ln(5)
        
        pdf.set_font('Arial', '', 11)
        closing_text = (
            "If you are considering restructuring your portfolio or would like a more detailed "
            "financial calculation regarding your property assets, please feel free to contact me."
        )
        pdf.multi_cell(0, 6, closing_text)
        pdf.ln(10)
        
        pdf.cell(0, 6, "Sincerely,", 0, 1)
        pdf.ln(10) # 签名空间
        
        pdf.set_font('Arial', 'B', 11)
        pdf.cell(0, 5, AGENT_PROFILE['Name'], 0, 1)
        
        pdf.set_font('Arial', '', 10)
        pdf.cell(0, 5, f"{AGENT_PROFILE['Title']} | {AGENT_PROFILE['Company']}", 0, 1)
        pdf.cell(0, 5, f"Mobile: {AGENT_PROFILE['Mobile']}", 0, 1)
        
        return bytes(pdf.output())
