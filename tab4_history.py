import streamlit as st
from utils import format_currency

def render(df):
    st.subheader("📝 详细成交记录")
    display_df = df.copy()
    if 'Unit' not in display_df.columns:
        display_df['Unit'] = display_df.apply(lambda x: f"#{int(x['Floor_Num']):02d}-{x['Stack']}", axis=1)

    bed_col = 'Category' 
    for c in ['No. of Bedrooms', 'Bedrooms', 'Bedroom Type', 'Bedroom_Type', 'Type']:
        if c in display_df.columns: bed_col = c; break
    
    display_df['Sale Price'] = display_df['Sale Price'].apply(format_currency)
    display_df['Sale PSF'] = display_df['Sale PSF'].apply(format_currency)
    
    show_cols = ['Sale Date', 'BLK', 'Unit', bed_col, 'Area (sqft)', 'Sale Price', 'Sale PSF']
    st.dataframe(
        display_df[show_cols].sort_values('Sale Date', ascending=False), 
        use_container_width=True, hide_index=True,
        column_config={
            "Sale Date": st.column_config.DateColumn("成交日期"),
            "Area (sqft)": st.column_config.NumberColumn("面积 (sqft)", format="%d"),
            bed_col: st.column_config.TextColumn("卧室 (Bedrooms)"),
            "Sale Price": st.column_config.TextColumn("成交价 ($)"),
            "Sale PSF": st.column_config.TextColumn("尺价 ($psf)"),
        }
    )
