# demo_app_lightning.py - Hybrid keyword + AI (ultra fast)
import streamlit as st
import pandas as pd
import json
from datetime import datetime
from io import BytesIO
from openai import OpenAI
from dotenv import load_dotenv
import os
from difflib import SequenceMatcher

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    st.error("OPENAI_API_KEY not found in .env file")
    st.stop()

client = OpenAI(api_key=api_key)

st.set_page_config(page_title="Supplier Matcher", layout="wide")

st.title("EOI Supplier Matching")
st.markdown("Lightning-fast keyword + AI matching.")

st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Procurement Opportunity")
    po_file = st.file_uploader("Excel or CSV", type=["xlsx", "csv"], key="po_upload")
    if po_file:
        df_pos = pd.read_excel(po_file) if po_file.name.endswith('xlsx') else pd.read_csv(po_file)
        st.success(f"Loaded {len(df_pos)} POs")
        st.session_state['df_pos'] = df_pos

with col2:
    st.subheader("EOI Suppliers")
    supplier_file = st.file_uploader("Excel or CSV", type=["xlsx", "csv"], key="supplier_upload")
    if supplier_file:
        df_suppliers = pd.read_excel(supplier_file) if supplier_file.name.endswith('xlsx') else pd.read_csv(supplier_file)
        st.success(f"Loaded {len(df_suppliers)} suppliers")
        st.session_state['df_suppliers'] = df_suppliers

st.markdown("---")

if ('df_pos' in st.session_state) and ('df_suppliers' in st.session_state) and st.button("RUN MATCHING", type="primary", use_container_width=True):
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    df_pos = st.session_state['df_pos']
    df_suppliers = st.session_state['df_suppliers']
    
    # Column detection
    po_code_col = next((c for c in df_pos.columns if any(x in str(c).upper() for x in ["CODE", "ID"])), df_pos.columns[0])
    desc_col = next((c for c in df_pos.columns if any(x in str(c).upper() for x in ["DESC", "DETAIL"])), df_pos.columns[1] if len(df_pos.columns) > 1 else df_pos.columns[0])
    supplier_id_col = next((c for c in df_suppliers.columns if any(x in str(c).upper() for x in ["ID", "EOI"])), df_suppliers.columns[0])
    supplier_name_col = next((c for c in df_suppliers.columns if "NAME" in str(c).upper() or "SUPPLIER" in str(c).upper()), df_suppliers.columns[1] if len(df_suppliers.columns) > 1 else df_suppliers.columns[0])
    
    # Filter
    df_pos = df_pos[df_pos[desc_col].notna()]
    df_pos = df_pos[~df_pos[desc_col].astype(str).isin(["0", "nan", ""])]
    
    total_pos = len(df_pos)
    if total_pos == 0:
        st.error("No valid POs")
        st.stop()
    
    st.write(f"Processing {total_pos} Procurement Opportunities vs {len(df_suppliers)} EOI Suppliers (keyword-first approach)")
    
    all_results = []
    
    # Keywords for fast matching
    keywords = {
        "mining": ["mining", "excavation", "drilling", "ore", "mineral"],
        "logistics": ["logistics", "freight", "shipping", "transport", "courier"],
        "hotel": ["hotel", "accommodation", "lodge", "hospitality", "rooms"],
        "software": ["software", "platform", "cloud", "saas", "it", "license"],
        "construction": ["construction", "materials", "steel", "concrete", "building"],
        "equipment": ["equipment", "rental", "machinery", "tools", "hire"]
    }
    
    def keyword_match(po_text, supplier_text):
        """Quick keyword matching 0-70"""
        po_lower = po_text.lower()
        sup_lower = supplier_text.lower()
        
        matches = 0
        for category, kw_list in keywords.items():
            if any(kw in po_lower for kw in kw_list) and any(kw in sup_lower for kw in kw_list):
                matches += 10
        
        # Sequence matching
        ratio = SequenceMatcher(None, po_lower[:50], sup_lower[:50]).ratio()
        matches += int(ratio * 70)
        
        return min(70, matches)
    
    # Fast pass - keyword matching
    status_text.text("Phase 1: Keyword matching...")
    
    for idx, (_, row) in enumerate(df_pos.iterrows()):
        po_code = str(row[po_code_col]).strip()
        po_text = str(row[desc_col]).strip()
        
        for _, sup_row in df_suppliers.iterrows():
            sup_id = str(sup_row[supplier_id_col])
            sup_name = str(sup_row[supplier_name_col])
            sup_text = sup_name + " " + str(sup_row.get(df_suppliers.columns[2], ""))
            
            score = keyword_match(po_text, sup_text)
            
            if score >= 30:  # Only keep decent matches
                all_results.append({
                    "Foreign Supplier Code": po_code,
                    "EOI Supplier ID": sup_id,
                    "EOI Supplier Name": sup_name,
                    "Score": score,
                    "Method": "Keyword"
                })
        
        progress_pct = int((idx / total_pos) * 50)
        progress_bar.progress(progress_pct)
    
    # AI enhancement for top candidates
    status_text.text("Phase 2: AI refinement...")
    
    if all_results:
        # Get unique POs with low confidence
        results_df = pd.DataFrame(all_results)
        low_conf = results_df[results_df["Score"] < 50]["Foreign Supplier Code"].unique()[:5]  # Max 5 POs for AI
        
        ai_boost_count = 0
        for po_code in low_conf:
            po_row = df_pos[df_pos[po_code_col] == po_code].iloc[0]
            po_text = str(po_row[desc_col])[:150]
            
            candidates = results_df[results_df["Foreign Supplier Code"] == po_code].head(3)
            cand_text = "\n".join([f"{r['EOI Supplier ID']}: {r['EOI Supplier Name']}" for _, r in candidates.iterrows()])
            
            prompt = f"""Rate these suppliers for: {po_text}
            
{cand_text}

Return JSON: {{"scores": [{{"id":"...", "boost": -20 to +20}}]}}"""
            
            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    max_tokens=100,
                    timeout=8
                )
                
                data = json.loads(response.choices[0].message.content)
                for score in data.get("scores", []):
                    sup_id = score.get("id")
                    boost = score.get("boost", 0)
                    results_df.loc[results_df["EOI Supplier ID"] == sup_id, "Score"] = results_df.loc[results_df["EOI Supplier ID"] == sup_id, "Score"] + boost
                    results_df.loc[results_df["EOI Supplier ID"] == sup_id, "Method"] = "AI-refined"
                
                ai_boost_count += 1
            except:
                pass
        
        all_results = results_df.to_dict('records')
    
    progress_bar.progress(100)
    status_text.text("Complete!")
    
    # Display
    st.markdown("---")
    st.subheader("Results")
    
    if all_results:
        results_df = pd.DataFrame(all_results).sort_values("Score", ascending=False)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Matches Found", len(results_df))
        with col2:
            st.metric("Avg Score", f"{results_df['Score'].mean():.0f}")
        with col3:
            st.metric("Procurement Opportunities Covered", results_df["Foreign Supplier Code"].nunique())
        
        st.dataframe(results_df, use_container_width=True)
        
        col1, col2 = st.columns(2)
        with col1:
            csv = results_df.to_csv(index=False)
            st.download_button("CSV", data=csv, file_name=f"matches_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", mime="text/csv")
        
        with col2:
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                results_df.to_excel(writer, index=False)
            st.download_button("Excel", data=output.getvalue(), file_name=f"matches_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.info("No matches found. Adjust filters if needed.")

st.markdown("---")
st.caption("Lightning: Keyword-first matching with optional AI refinement")
