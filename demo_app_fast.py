# demo_app_fast.py - Optimized for speed
import streamlit as st
import pandas as pd
import time
import os
import json
from datetime import datetime
from io import BytesIO
from openai import OpenAI
from dotenv import load_dotenv

# Load environment
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    st.error("OPENAI_API_KEY not found in .env file")
    st.stop()

client = OpenAI(api_key=api_key)

# Page configuration - MUST be first Streamlit command
st.set_page_config(
    page_title="Supplier Matcher",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# SIDEBAR - Configuration
# ============================================================
with st.sidebar:
    st.header("Settings")
    
    min_relevance = st.slider(
        "Minimum Relevance Score",
        min_value=0,
        max_value=100,
        value=50,
        help="Lower scores return more matches"
    )
    
    st.markdown("---")
    st.caption("Matching Engine - Fast Version")

# ============================================================
# MAIN HEADER
# ============================================================
st.title("EOI Supplier Matching")
st.markdown("Upload your Procurement Opportunity and EOI Suppliers, then click **Run Matching** to get ranked results.")

st.markdown("---")

# ============================================================
# TWO COLUMN LAYOUT FOR UPLOADS
# ============================================================
col1, col2 = st.columns(2)

with col1:
    st.subheader("Procurement Opportunity")
    po_file = st.file_uploader(
        "Excel or CSV file with Procurement Opportunity data",
        type=["xlsx", "csv"],
        key="po_upload"
    )
    
    if po_file:
        if po_file.name.endswith('xlsx'):
            df_pos = pd.read_excel(po_file)
        else:
            df_pos = pd.read_csv(po_file)
        
        st.success(f"Loaded {len(df_pos)} POs")
        
        with st.expander("Preview PO data"):
            st.dataframe(df_pos.head(5), use_container_width=True)
        
        st.session_state['df_pos'] = df_pos

with col2:
    st.subheader("EOI Suppliers")
    supplier_file = st.file_uploader(
        "Excel or CSV file with EOI Supplier data",
        type=["xlsx", "csv"],
        key="supplier_upload"
    )
    
    if supplier_file:
        if supplier_file.name.endswith('xlsx'):
            df_suppliers = pd.read_excel(supplier_file)
        else:
            df_suppliers = pd.read_csv(supplier_file)
        
        st.success(f"Loaded {len(df_suppliers)} suppliers")
        
        with st.expander("Preview supplier data"):
            st.dataframe(df_suppliers.head(5), use_container_width=True)
        
        st.session_state['df_suppliers'] = df_suppliers

# ============================================================
# RUN MATCHING BUTTON
# ============================================================
st.markdown("---")

files_ready = ('df_pos' in st.session_state) and ('df_suppliers' in st.session_state)

if not files_ready:
    st.info("Please upload both Procurement Opportunity and EOI Supplier files to continue")
else:
    if st.button("RUN MATCHING", type="primary", use_container_width=True):
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        df_pos = st.session_state['df_pos']
        df_suppliers = st.session_state['df_suppliers']
        
        # ====================================================
        # COLUMN DETECTION
        # ====================================================
        status_text.text("Detecting columns...")
        progress_bar.progress(5)
        
        po_code_col = None
        for col in df_pos.columns:
            col_upper = str(col).upper()
            if any(x in col_upper for x in ["CODE", "PO CODE", "SUPPLIER CODE", "FOREIGN SUPPLIER CODE"]):
                po_code_col = col
                break
        if po_code_col is None:
            po_code_col = df_pos.columns[0]
        
        desc_col = None
        for col in df_pos.columns:
            col_upper = str(col).upper()
            if any(x in col_upper for x in ["DESCRIPTION", "DETAILS", "DESC"]):
                desc_col = col
                break
        if desc_col is None:
            desc_col = df_pos.columns[1] if len(df_pos.columns) > 1 else df_pos.columns[0]
        
        supplier_id_col = None
        for col in df_suppliers.columns:
            col_upper = str(col).upper()
            if any(x in col_upper for x in ["ID", "EOI", "UNIQUE"]):
                supplier_id_col = col
                break
        if supplier_id_col is None:
            supplier_id_col = df_suppliers.columns[0]
        
        # ====================================================
        # FILTER DATA
        # ====================================================
        status_text.text("Filtering data...")
        progress_bar.progress(10)
        
        df_pos = df_pos[df_pos[desc_col].notna()]
        df_pos = df_pos[~df_pos[desc_col].astype(str).isin(["0", "nan", ""])]
        
        total_pos = len(df_pos)
        
        if total_pos == 0:
            st.error("No valid POs found after filtering.")
            st.stop()
        
        st.write(f"Processing **{total_pos}** Procurement Opportunities against **{len(df_suppliers)}** EOI Suppliers")
        
        # ====================================================
        # FAST MATCHING FUNCTION
        # ====================================================
        def fast_match(po_code: str, po_text: str, suppliers: pd.DataFrame, min_score: int):
            """Simple, fast matching via OpenAI"""
            if len(suppliers) == 0:
                return []
            
            # Format suppliers concisely
            supplier_text = "\n".join([
                f"{row.get(supplier_id_col, 'N/A')}: {row.get(df_suppliers.columns[1], 'N/A')} - {str(row.get(df_suppliers.columns[2], 'N/A'))[:80]}"
                for _, row in suppliers.head(50).iterrows()
            ])
            
            prompt = f"""Match suppliers to PO. Rate 0-100. Return JSON.

PO {po_code}: {po_text[:200]}

SUPPLIERS:
{supplier_text}

Return 3-5 best matches:
{{"matches": [{{"id":"...", "name":"...", "score":0-100, "reason":"..."}}]}}"""
            
            try:
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    max_tokens=300,
                    timeout=20
                )
                
                data = json.loads(response.choices[0].message.content)
                return data.get("matches", [])
            except Exception as e:
                st.warning(f"Error on {po_code}: {str(e)[:50]}")
                return []
        
        # ====================================================
        # RUN MATCHING
        # ====================================================
        all_results = []
        
        for idx, row in df_pos.iterrows():
            po_code = str(row[po_code_col]).strip()
            po_text = str(row[desc_col]).strip()
            
            progress_pct = 10 + int((idx / total_pos) * 80)
            progress_bar.progress(progress_pct)
            status_text.text(f"Matching {idx+1}/{total_pos}: {po_code}")
            
            matches = fast_match(po_code, po_text, df_suppliers, min_relevance)
            
            if matches:
                for rank, match in enumerate(matches, 1):
                    all_results.append({
                        "PO_Code": po_code,
                        "Rank": rank,
                        "Supplier_ID": match.get("id", "N/A"),
                        "Supplier_Name": match.get("name", "N/A"),
                        "Score": match.get("score", 0),
                        "Reason": match.get("reason", "")
                    })
            else:
                all_results.append({
                    "PO_Code": po_code,
                    "Rank": 1,
                    "Supplier_ID": "N/A",
                    "Supplier_Name": "No match",
                    "Score": 0,
                    "Reason": "No suitable match found"
                })
            
            time.sleep(0.2)  # Rate limit
        
        # ====================================================
        # DISPLAY RESULTS
        # ====================================================
        progress_bar.progress(95)
        status_text.text("Preparing results...")
        
        results_df = pd.DataFrame(all_results)
        st.session_state['results_df'] = results_df
        
        progress_bar.progress(100)
        status_text.text("Matching complete!")
        
        # Metrics
        st.markdown("---")
        st.subheader("Results Summary")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total POs", total_pos)
        with col2:
            matches_found = len(results_df[results_df["Supplier_ID"] != "N/A"])
            st.metric("Matches Found", matches_found)
        with col3:
            avg = results_df[results_df["Supplier_ID"] != "N/A"]["Score"].mean() if matches_found > 0 else 0
            st.metric("Average Score", f"{avg:.0f}")
        
        # Display results
        st.markdown("### Results")
        st.dataframe(results_df, use_container_width=True)
        
        # Downloads
        st.markdown("### Download")
        col1, col2 = st.columns(2)
        
        with col1:
            csv = results_df.to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name=f"matches_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
        
        with col2:
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                results_df.to_excel(writer, index=False)
            st.download_button(
                label="Download Excel",
                data=output.getvalue(),
                file_name=f"matches_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

st.markdown("---")
