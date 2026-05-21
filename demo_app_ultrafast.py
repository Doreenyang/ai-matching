# demo_app_ultrafast.py - Batch + Parallel Processing
import streamlit as st
import pandas as pd
import json
from datetime import datetime
from io import BytesIO
from openai import OpenAI
from dotenv import load_dotenv
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    st.error("OPENAI_API_KEY not found in .env file")
    st.stop()

client = OpenAI(api_key=api_key)

st.set_page_config(page_title="Supplier Matcher", layout="wide")

st.title("EOI Supplier Matching")
st.markdown("Upload your Procurement Opportunity and EOI Suppliers, then click **Run Matching** for fast results.")

st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Procurement Opportunity")
    po_file = st.file_uploader("Excel or CSV with Procurement Opportunity data", type=["xlsx", "csv"], key="po_upload")
    if po_file:
        df_pos = pd.read_excel(po_file) if po_file.name.endswith('xlsx') else pd.read_csv(po_file)
        st.success(f"Loaded {len(df_pos)} POs")
        with st.expander("Preview"):
            st.dataframe(df_pos.head(3), use_container_width=True)
        st.session_state['df_pos'] = df_pos

with col2:
    st.subheader("EOI Suppliers")
    supplier_file = st.file_uploader("Excel or CSV with EOI Supplier data", type=["xlsx", "csv"], key="supplier_upload")
    if supplier_file:
        df_suppliers = pd.read_excel(supplier_file) if supplier_file.name.endswith('xlsx') else pd.read_csv(supplier_file)
        st.success(f"Loaded {len(df_suppliers)} suppliers")
        with st.expander("Preview"):
            st.dataframe(df_suppliers.head(3), use_container_width=True)
        st.session_state['df_suppliers'] = df_suppliers

st.markdown("---")

files_ready = ('df_pos' in st.session_state) and ('df_suppliers' in st.session_state)

if not files_ready:
    st.info("Upload both files to continue")
else:
    if st.button("RUN MATCHING", type="primary", use_container_width=True):
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        df_pos = st.session_state['df_pos']
        df_suppliers = st.session_state['df_suppliers']
        
        # Column detection
        status_text.text("Detecting columns...")
        po_code_col = next((col for col in df_pos.columns if any(x in str(col).upper() for x in ["CODE", "ID"])), df_pos.columns[0])
        desc_col = next((col for col in df_pos.columns if any(x in str(col).upper() for x in ["DESC", "DETAIL", "REQUEST"])), df_pos.columns[1] if len(df_pos.columns) > 1 else df_pos.columns[0])
        supplier_id_col = next((col for col in df_suppliers.columns if any(x in str(col).upper() for x in ["ID", "EOI"])), df_suppliers.columns[0])
        supplier_name_col = next((col for col in df_suppliers.columns if any(x in str(col).upper() for x in ["NAME", "SUPPLIER"])), df_suppliers.columns[1] if len(df_suppliers.columns) > 1 else df_suppliers.columns[0])
        
        # Filter data
        status_text.text("Filtering data...")
        df_pos = df_pos[df_pos[desc_col].notna()]
        df_pos = df_pos[~df_pos[desc_col].astype(str).isin(["0", "nan", ""])]
        
        total_pos = len(df_pos)
        if total_pos == 0:
            st.error("No valid POs found")
            st.stop()
        
        st.write(f"Processing **{total_pos}** Procurement Opportunities against **{len(df_suppliers)}** EOI Suppliers (parallel mode)")
        
        # Format suppliers once
        supplier_list = "\n".join([
            f"{row.get(supplier_id_col, 'N/A')}: {row.get(supplier_name_col, 'N/A')}"
            for _, row in df_suppliers.head(100).iterrows()
        ])
        
        # Batch processing function
        def process_po_batch(pos_batch):
            """Process multiple POs in a single API call"""
            po_text = "\n".join([
                f"- {row[po_code_col]}: {row[desc_col][:100]}"
                for _, row in pos_batch.iterrows()
            ])
            
            prompt = f"""Match these POs to suppliers. Quick scoring 0-100.

POs:
{po_text}

SUPPLIERS:
{supplier_list}

Return JSON with top matches per PO:
{{"matches": [{{"po": "...", "id": "...", "name": "...", "score": 0-100}}]}}"""
            
            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",  # Fastest model
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    max_tokens=200,
                    timeout=15
                )
                
                data = json.loads(response.choices[0].message.content)
                return data.get("matches", [])
            except Exception as e:
                st.warning(f"Batch error: {str(e)[:40]}")
                return []
        
        # Split into batches of 5 POs
        batch_size = 5
        po_batches = [df_pos.iloc[i:i+batch_size] for i in range(0, len(df_pos), batch_size)]
        
        all_results = []
        
        # Process batches in parallel (max 3 concurrent requests)
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(process_po_batch, batch): i for i, batch in enumerate(po_batches)}
            completed = 0
            
            for future in as_completed(futures):
                batch_idx = futures[future]
                completed += 1
                progress_pct = 10 + int((completed / len(po_batches)) * 80)
                progress_bar.progress(progress_pct)
                status_text.text(f"Processing batch {completed}/{len(po_batches)}")
                
                matches = future.result()
                
                for match in matches:
                    all_results.append({
                        "Foreign Supplier Code": match.get("po", "?"),
                        "EOI Supplier ID": match.get("id", "N/A"),
                        "EOI Supplier Name": match.get("name", "N/A"),
                        "Score": match.get("score", 0)
                    })
        
        # If no results from batching, do individual calls
        if not all_results:
            status_text.text("Retrying with individual PO calls...")
            for idx, (_, row) in enumerate(df_pos.iterrows()):
                po_code = str(row[po_code_col]).strip()
                po_text = str(row[desc_col]).strip()[:150]
                
                prompt = f"""Quick match: {po_code}: {po_text}
                
SUPPLIERS: {supplier_list[:500]}

Return top 2 matches JSON: {{"matches": [{{"id":"...", "name":"...", "score":0-100}}]}}"""
                
                try:
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": prompt}],
                        response_format={"type": "json_object"},
                        max_tokens=150,
                        timeout=10
                    )
                    
                    data = json.loads(response.choices[0].message.content)
                    for match in data.get("matches", []):
                        all_results.append({
                            "Foreign Supplier Code": po_code,
                            "EOI Supplier ID": match.get("id", "N/A"),
                            "EOI Supplier Name": match.get("name", "N/A"),
                            "Score": match.get("score", 0)
                        })
                
                except:
                    pass
                
                progress = 10 + int((idx / len(df_pos)) * 80)
                progress_bar.progress(progress)
                status_text.text(f"PO {idx+1}/{len(df_pos)}")
        
        # Display results
        progress_bar.progress(100)
        status_text.text("Complete!")
        
        results_df = pd.DataFrame(all_results) if all_results else pd.DataFrame({"Error": ["No matches found"]})
        
        st.markdown("---")
        st.subheader("Results")
        st.dataframe(results_df, use_container_width=True)
        
        # Downloads
        if len(results_df) > 0 and "Error" not in results_df.columns:
            col1, col2 = st.columns(2)
            
            with col1:
                csv = results_df.to_csv(index=False)
                st.download_button("Download CSV", data=csv, file_name=f"matches_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", mime="text/csv")
            
            with col2:
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    results_df.to_excel(writer, index=False)
                st.download_button("Download Excel", data=output.getvalue(), file_name=f"matches_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

st.markdown("---")
