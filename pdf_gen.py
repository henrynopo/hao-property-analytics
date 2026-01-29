# pdf_gen.py
from datetime import datetime
import pandas as pd
import numpy as np
from utils import AGENT_PROFILE

try:
    from fpdf import FPDF
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

if PDF_AVAILABLE:
    class PDFReport(FPDF):
        def header(self):
            self.set_font('Arial', 'B', 10)
            self.set_text_color(100, 100, 100)
            self.cell(0, 5, f"{AGENT_PROFILE['Company']} ({AGENT_PROFILE['License']})", 0, 1, 'L')
            self.set_y(10)
            self.set_font('Arial', '', 9)
            info = f"{AGENT_PROFILE['Name']} | {AGENT_PROFILE['RES_No']} | {AGENT_PROFILE['Mobile']}"
            self.cell(0, 5, info, 0, 1, 'R')
            self.ln(5)
            self.set_draw_color(200, 200, 200)
            self.line(10, self.get_y(), 200, self.get_y())
            self.ln(10)

        def footer(self):
            self.set_y(-25)
            self.set_font('Arial', 'I', 8)
            self.set_text_color(150, 150, 150)
            disclaimer = "Disclaimer: For reference only. Values are estimates (AVM), not certified. Data: URA/Huttons. Accuracy not guaranteed."
            self.multi_cell(0, 4, disclaimer, 0, 'C')
            self.set_y(-15)
            self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

        def add_watermark(self):
            self.set_font('Arial', 'B', 50)
            self.set_text_color(240, 240, 240)
            with self.rotation(45, 105, 148): # Center of A4
                self.text(50, 190, AGENT_PROFILE['Name'].upper())

    def generate_pdf_report(project_name, unit_info, valuation_data, analysis_data, history_df, comps_df, data_cutoff):
        pdf = PDFReport()
        pdf.add_page()
        pdf.add_watermark()
        
        # Title
        pdf.set_font('Arial', 'B', 24)
        pdf.set_text_color(44, 62, 80)
        pdf.cell(0, 10, f"Valuation Report: {project_name}", 0, 1, 'C')
        pdf.ln(5)
        
        pdf.set_font('Arial', '', 14)
        pdf.cell(0, 8, f"Unit: Block {unit_info['blk']} {unit_info['unit']}", 0, 1, 'C')
        pdf.set_font('Arial', 'I', 10)
        pdf.cell(0, 6, f"Generated: {datetime.now().strftime('%Y-%m-%d')} | Data Cutoff: {data_cutoff}", 0, 1, 'C')
        pdf.ln(10)
        
        # --- Box 1: Valuation ---
        pdf.set_fill_color(240, 248, 255) # Light Blue
        y_val_start = pdf.get_y()
        pdf.rect(10, y_val_start, 190, 35, 'F')
        pdf.set_y(y_val_start + 5)
        
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(63, 8, "Estimated Value", 0, 0, 'C')
        pdf.cell(63, 8, "Area (sqft)", 0, 0, 'C')
        pdf.cell(63, 8, "Est. PSF", 0, 1, 'C')
        
        pdf.set_font('Arial', 'B', 16)
        pdf.set_text_color(39, 174, 96)
        pdf.cell(63, 10, f"${valuation_data['value']/1e6:.2f}M", 0, 0, 'C')
        pdf.set_text_color(0, 0, 0)
        pdf.cell(63, 10, f"{int(valuation_data['area']):,}", 0, 0, 'C')
        pdf.cell(63, 10, f"${int(valuation_data['psf']):,}", 0, 1, 'C')
        
        # --- Box 2: Analysis ---
        pdf.set_y(y_val_start + 40) # Ensure spacing
        pdf.set_fill_color(255, 250, 240) # Floral White
        pdf.rect(10, pdf.get_y(), 190, 35, 'F')
        pdf.set_y(pdf.get_y() + 5)
        
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(63, 8, "Est. Net Gain", 0, 0, 'C')
        pdf.cell(63, 8, "SSD Cost", 0, 0, 'C')
        pdf.cell(63, 8, "Last Transacted", 0, 1, 'C')
        
        pdf.set_font('Arial', 'B', 14)
        if analysis_data['net_gain'] > 0: pdf.set_text_color(39, 174, 96)
        elif analysis_data['net_gain'] < 0: pdf.set_text_color(231, 76, 60)
        else: pdf.set_text_color(100, 100, 100)
        
        gain_str = f"${analysis_data['net_gain']/1e6:.2f}M ({analysis_data['net_gain_pct']:+.1%})"
        if analysis_data['is_simulated']: gain_str += "*"
        pdf.cell(63, 10, gain_str, 0, 0, 'C')
        
        pdf.set_text_color(0, 0, 0)
        pdf.cell(63, 10, f"${analysis_data['ssd_cost']/1e6:.2f}M", 0, 0, 'C')
        
        last_tx_str = f"${analysis_data['last_price']/1e6:.2f}M" if analysis_data['last_price'] > 0 else "N/A"
        pdf.cell(63, 10, last_tx_str, 0, 1, 'C')
        
        if analysis_data['is_simulated']:
            pdf.set_y(pdf.get_y())
            pdf.set_font('Arial', 'I', 8)
            pdf.set_text_color(100, 100, 100)
            pdf.cell(0, 6, f"* Simulated based on avg price in {analysis_data['sim_year']}. No actual history.", 0, 1, 'C')
        
        pdf.ln(10)
        
        # --- Tables ---
        # 🟢 Layout Fix: Force Y position to prevent overlap
        current_y = pdf.get_y()
        if current_y < 120: pdf.set_y(120) 

        def add_table(df, title):
            if pdf.get_y() > 250: pdf.add_page() # Auto page break check
            
            pdf.set_font('Arial', 'B', 12)
            pdf.set_text_color(44, 62, 80)
            pdf.cell(0, 8, title, 0, 1, 'L')
            pdf.ln(2)
            
            if df.empty:
                pdf.set_font('Arial', 'I', 10)
                pdf.cell(0, 8, "No records found.", 0, 1, 'L')
                pdf.ln(5)
                return

            pdf.set_font('Arial', 'B', 9)
            pdf.set_fill_color(220, 220, 220)
            col_widths = [30, 25, 30, 25, 30, 30] 
            headers = ['Date', 'Unit', 'Price ($)', 'PSF ($)', 'Area', 'Type']
            
            for i, h in enumerate(headers):
                pdf.cell(col_widths[i], 8, h, 1, 0, 'C', True)
            pdf.ln()
            
            pdf.set_font('Arial', '', 9)
            pdf.set_fill_color(255, 255, 255)
            
            for _, row in df.iterrows():
                date_str = row['Sale Date'].strftime('%Y-%m-%d')
                price_str = f"{row['Sale Price']:,.0f}" if pd.notnull(row['Sale Price']) else "-"
                psf_str = f"{row['Sale PSF']:,.0f}" if pd.notnull(row['Sale PSF']) else "-"
                area_str = f"{int(row['Area (sqft)']):,}" if pd.notnull(row['Area (sqft)']) else "-"
                unit_str = row['Unit'] if 'Unit' in row else f"#{int(row.get('Floor_Num',0)):02d}-{row.get('Stack','?')}"
                cat_str = str(row.get('Category', '-'))[:10]

                data = [date_str, unit_str, price_str, psf_str, area_str, cat_str]
                for i, d in enumerate(data):
                    pdf.cell(col_widths[i], 8, str(d), 1, 0, 'C')
                pdf.ln()
            pdf.ln(10)

        add_table(history_df.head(10), "Unit Transaction History")
        add_table(comps_df.head(10), "Comparable Transactions (Valuation Basis)")
        
        return bytes(pdf.output())
