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
            self.set_font('helvetica', 'B', 12)
            self.set_text_color(50, 50, 50)
            self.cell(0, 6, f"{AGENT_PROFILE['Company']}", new_x="LMARGIN", new_y="NEXT", align='R')
            self.set_font('helvetica', '', 8)
            self.cell(0, 4, f"Agency License: {AGENT_PROFILE['License']}", new_x="LMARGIN", new_y="NEXT", align='R')
            self.ln(2)
            self.set_font('helvetica', 'B', 10)
            self.cell(0, 5, f"{AGENT_PROFILE['Name']} ({AGENT_PROFILE['Title']})", new_x="LMARGIN", new_y="NEXT", align='R')
            self.set_font('helvetica', '', 9)
            self.cell(0, 5, f"CEA Reg: {AGENT_PROFILE['RES_No']} | Mobile: {AGENT_PROFILE['Mobile']}", new_x="LMARGIN", new_y="NEXT", align='R')
            self.ln(5)
            self.set_draw_color(200, 200, 200)
            self.set_line_width(0.5)
            self.line(10, self.get_y(), 200, self.get_y())
            self.ln(5)

        def footer(self):
            self.set_y(-20)
            self.set_font('helvetica', 'I', 7)
            self.set_text_color(150, 150, 150)
            self.cell(0, 4, "Note: Estimates for reference only.", new_x="LMARGIN", new_y="NEXT", align='C')
            self.cell(0, 4, f"Page {self.page_no()}", new_x="LMARGIN", new_y="NEXT", align='C')

    def draw_gauge_bar(pdf, x, y, w, h, low, high, current):
        pdf.set_fill_color(240, 240, 240)
        pdf.rect(x, y, w, h, 'F')
        val_range = high - low if high != low else 1
        safe_w = ((current - low) / val_range) * w
        safe_w = max(0, min(w, safe_w))
        pdf.set_fill_color(100, 200, 100) 
        pdf.rect(x, y, safe_w, h, 'F')
        pdf.set_draw_color(0, 0, 0)
        pdf.line(x + safe_w, y - 2, x + safe_w, y + h + 2)
        pdf.set_font('helvetica', '', 7)
        pdf.set_text_color(100, 100, 100)
        pdf.text(x, y + h + 4, f"${low/1e6:.2f}M")
        pdf.text(x + w - 10, y + h + 4, f"${high/1e6:.2f}M")

    def generate_pdf_report(project_name, unit_info, valuation_data, analysis_data, history_df, comps_df, data_cutoff):
        pdf = PDFReport()
        pdf.set_margins(20, 20, 20)
        pdf.add_page()
        
        # Date & To
        pdf.set_y(40)
        pdf.set_font('helvetica', '', 10)
        pdf.cell(0, 5, datetime.now().strftime('%d %B, %Y'), new_x="LMARGIN", new_y="NEXT", align='R')
        pdf.set_y(45)
        pdf.set_font('helvetica', 'B', 11)
        pdf.cell(0, 5, "To: The Subsidiary Proprietor / Owner", new_x="LMARGIN", new_y="NEXT", align='L')
        pdf.set_font('helvetica', '', 11)
        pdf.cell(0, 5, f"Unit #{unit_info['unit']}", new_x="LMARGIN", new_y="NEXT", align='L') 
        pdf.cell(0, 5, f"Block {unit_info['blk']}, {project_name}", new_x="LMARGIN", new_y="NEXT", align='L')
        pdf.ln(10)
        
        # Body
        pdf.cell(0, 6, "Dear Homeowner,", new_x="LMARGIN", new_y="NEXT", align='L')
        pdf.ln(2)
        pdf.multi_cell(0, 6, f"Here is a market update and estimated valuation for your unit at {project_name}.")
        pdf.ln(5)
        
        # Box
        box_y = pdf.get_y()
        pdf.set_fill_color(248, 250, 252)
        pdf.rect(20, box_y, 170, 35, 'F')
        pdf.set_y(box_y + 5)
        pdf.set_font('helvetica', 'B', 14)
        pdf.cell(0, 8, f"Estimated Value: ${valuation_data['value']/1e6:.2f} Million", new_x="LMARGIN", new_y="NEXT", align='C')
        pdf.set_font('helvetica', '', 11)
        pdf.cell(0, 6, f"{int(valuation_data['area']):,} sqft  |  ${int(valuation_data['psf']):,} psf", new_x="LMARGIN", new_y="NEXT", align='C')
        draw_gauge_bar(pdf, 45, pdf.get_y()+2, 120, 4, valuation_data['value']*0.9, valuation_data['value']*1.1, valuation_data['value'])
        pdf.ln(15)
        
        # Analysis
        pdf.set_y(pdf.get_y() + 5)
        gain = analysis_data['net_gain']
        ssd = analysis_data['ssd_cost']
        pdf.set_font('helvetica', 'B', 10)
        pdf.cell(30, 6, "Analysis:", 0, 0)
        pdf.set_font('helvetica', '', 10)
        pdf.cell(50, 6, f"${gain/1e6:+.2f}M Gain" if gain != 0 else "-", 0, 0)
        pdf.set_font('helvetica', 'B', 10)
        pdf.cell(25, 6, "SSD Status:", 0, 0)
        pdf.set_font('helvetica', '', 10)
        pdf.cell(40, 6, "Subject to SSD" if ssd > 0 else "SSD Free", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5)
        
        # Tables
        def print_table(df, title):
            if df.empty: return
            if pdf.get_y() > 220: pdf.add_page()
            pdf.set_font('helvetica', 'B', 10)
            pdf.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT", align='L')
            pdf.set_fill_color(230, 230, 230)
            pdf.set_font('helvetica', 'B', 8)
            
            # 🟢 动态列适配：不强制要求 Type of Sale
            cols_map = {'Sale Date': 25, 'Unit': 25, 'Sale Price': 30, 'Sale PSF': 25, 'Area': 25, 'Type of Sale': 30}
            # 找出 df 中有的列，并且是我们想要的
            valid_cols = [c for c in cols_map.keys() if c in df.columns or c == 'Unit' or c == 'Area']
            # 这里简化处理，强制打印固定列，防止错位，但做空值保护
            
            headers = ['Date', 'Price ($)', 'PSF ($)']
            widths = [30, 40, 30]
            if 'Unit' in df.columns or 'Floor_Num' in df.columns: 
                headers.insert(1, 'Unit'); widths.insert(1, 30)
            
            for i, h in enumerate(headers):
                pdf.cell(widths[i], 6, h, border=1, align='C', fill=True)
            pdf.ln()
            
            pdf.set_font('helvetica', '', 8)
            for _, row in df.iterrows():
                dt = str(row.get('Sale Date', '-'))[:10]
                px = f"${row.get('Sale Price', 0):,.0f}"
                psf = f"${row.get('Sale PSF', 0):,.0f}"
                
                pdf.cell(widths[0], 6, dt, 1, 0, 'C')
                
                idx = 1
                if 'Unit' in headers:
                    u = row.get('Unit', f"#{int(row.get('Floor_Num',0))}-xx")
                    pdf.cell(widths[idx], 6, str(u), 1, 0, 'C')
                    idx += 1
                    
                pdf.cell(widths[idx], 6, px, 1, 0, 'C')
                pdf.cell(widths[idx+1], 6, psf, 1, 0, 'C')
                pdf.ln()
            pdf.ln(5)

        print_table(history_df, "Unit History")
        print_table(comps_df.head(5), "Comparables")
        
        # Sign
        if pdf.get_y() > 240: pdf.add_page()
        pdf.ln(5)
        pdf.cell(0, 6, "Sincerely,", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(10)
        pdf.set_font('helvetica', 'B', 11)
        pdf.cell(0, 5, AGENT_PROFILE['Name'], new_x="LMARGIN", new_y="NEXT")
        
        return pdf.output()
