import streamlit as st
import pandas as pd
import numpy as np
import gc

# Configure the web page
st.set_page_config(page_title="Bulk Lookup & SLA Tool", layout="wide")
st.title("Project Alyson")

# FIX 1: Change to cache_resource. This stops Streamlit from duplicating 
# the massive dataframe in memory on every button click.
@st.cache_resource
def load_and_process_data(file):
    df = pd.read_csv(file, dtype=str, low_memory=False, on_bad_lines='skip')
    
    # FIX 2: Pre-clean the leadId column here so it doesn't consume memory during the search
    if 'leadId' in df.columns:
        df['leadId'] = df['leadId'].fillna('').astype(str).str.strip()
    
    # Calculate the SLA Check column automatically
    if 'SLA Check' not in df.columns:
        today = pd.Timestamp.today().normalize()
        fb_date = pd.to_datetime(df['providerFeedbackDate'].astype(str).str[:10], errors='coerce')
        created_date = pd.to_datetime(df['lead.createdAt'].astype(str).str[:10], errors='coerce')
        
        days_since_fb = (today - fb_date).dt.days
        days_since_created = (today - created_date).dt.days
        
        conditions = [
            (df['operationStatus'] == 'APPROVED') & (days_since_fb > 56),
            (df['operationStatus'].isin(['PENDING', 'NONE'])) & (days_since_created > 56)
        ]
        choices = ['FLT Passed SLA', 'ELT Passed SLA']
        
        df['SLA Check'] = np.select(conditions, choices, default='')
        
        # FIX 3: Immediately delete heavy temporary variables to free up RAM
        del today, fb_date, created_date, days_since_fb, days_since_created, conditions, choices
        gc.collect()
        
    return df

# --- 1. FILE UPLOAD ---
uploaded_file = st.file_uploader("📁 Step 1: Upload your Master CSV", type=["csv"])

if uploaded_file:
    with st.spinner("Reading data and calculating SLAs... (This takes a moment)"):
        df = load_and_process_data(uploaded_file)
        
    if 'leadId' not in df.columns:
        st.error("❌ ERROR: Could not find a column named 'leadId' in your file.")
    else:
        st.success(f"✅ Success! Loaded {len(df):,} rows.")
        
        # Create two separate tabs for your flows
        tab1, tab2 = st.tabs(["🔍 Search by leadId", "📈 SLA Reports"])
        
        # --- TAB 1: SEARCH FLOW ---
        with tab1:
            col1, col2 = st.columns(2)
            with col1:
                paste_area = st.text_area("Paste your leadIds here (one per line):", height=200)
            with col2:
                selected_cols = st.multiselect("Select columns to display:", df.columns.tolist(), default=['leadId', 'SLA Check'])
            
            if st.button("🔍 Search & Preview", type="primary"):
                # .strip() on the outside removes accidental blank spaces at the very bottom of the box, # but keeps all dashes and blanks in the middle so your row count stays perfectly aligned!
            search_list = [x.strip() for x in paste_area.strip().split('\n')]
                
                if not search_list or not selected_cols:
                    st.warning("⚠️ Please paste at least one valid leadId AND select at least one column.")
                else:
                    # 1. Create a dataframe from the exact IDs the user searched for
                    search_df = pd.DataFrame({'leadId': search_list})
                    
                    # 2. Ensure 'leadId' is included in the extraction so we can merge on it
                    cols_to_pull = list(set(selected_cols + ['leadId']))
                    
                    # 3. Extract only the actual matches from the master file to save memory
                    matched_df = df[df['leadId'].isin(search_list)][cols_to_pull]
                    
                    # 4. LEFT JOIN: This keeps every ID the user pasted, even if it has no match in matched_df
                    merged_results = pd.merge(search_df, matched_df, on='leadId', how='left')
                    
                    # 5. Fill the empty cells for missing matches with "No match found"
                    cols_to_fill = [col for col in selected_cols if col != 'leadId']
                    merged_results[cols_to_fill] = merged_results[cols_to_fill].fillna('No match found')
                    
                    # 6. Restore the final visual order to exactly what the user selected in the dropdown
                    final_results = merged_results[selected_cols]
                    
                    st.write(f"✅ Processed {len(search_list):,} searched IDs!")
                    st.write("👀 **Here is a preview of the first 10 rows:**")
                    
                    st.dataframe(final_results.head(10))
                    
                    st.caption("Note: Click download to get all of your records, including the 'No match found' ones.")
                    
                    csv = final_results.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Download Full CSV",
                        data=csv,
                        file_name="Lookup_Results.csv",
                        mime="text/csv",
                    )

        # --- TAB 2: SLA EXPORT FLOW ---
        with tab2:
            st.write("Extract records based on SLA Check status.")
            
            # --- ELT List ---
            st.subheader("ELT Passed SLA Records")
            
            elt_passed_df = df[df['SLA Check'] == 'ELT Passed SLA'][['referenceId.ns', 'lead.createdAt', 'leadId']]
            
            elt_summary_df = elt_passed_df.groupby('referenceId.ns', as_index=False).agg(
                Number_of_leadIds=('leadId', 'count')
            )
            
            st.write("👀 **Preview:** (Total leads per Reference ID)")
            st.dataframe(elt_summary_df)
            
            st.caption("Note: The downloaded file contains all details (referenceId.ns, lead.createdAt, leadId).")
            elt_csv = elt_passed_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Full ELT List", 
                data=elt_csv, 
                file_name="elt_passed_sla_list.csv", 
                mime="text/csv"
            )
            
            st.divider() 
            
            # --- FLT List ---
            st.subheader("FLT Passed SLA Records")
            
            flt_passed_df = df[df['SLA Check'] == 'FLT Passed SLA'][['offerName', 'leadId', 'providerFeedbackDate']].copy()
            
            def group_offer_names(name):
                name_str = str(name)
                if 'Apple Store Gift Card' in name_str:
                    return 'Apple Store Gift Card'
                elif 'Wellcome' in name_str:
                    return 'Wellcome Vouchers'
                elif 'HKTVMall' in name_str or 'HKTVmall' in name_str:
                    return 'HKTVMall Vouchers'
                elif 'Apple iPad 11-inch (A16)' in name_str or 'iPad Pro 11-inch' in name_str or '11 inch iPad' in name_str:
                    return 'Apple iPad 11-inch (A16)'
                elif 'DELONGHI DEDICA DUO' in name_str or 'DELONGHIDEDICA DUO' in name_str:
                    return 'Delonghi Dedica Duo EC890'
                elif 'DYSON HD19' in name_str:
                    return 'Dyson HD19 Hair Dryer'
                elif 'DYSON HD16' in name_str:
                    return 'Dyson HD16 Hair Dryer'
                elif 'Delsey 30" GRENELLE SE' in name_str:
                    return 'Delsey 30" GRENELLE SE'
                elif 'Cash Rebate' in name_str:
                    return 'FPS Cash'
                elif 'LOJEL Cubo' in name_str or 'LOJEL CUBO' in name_str:
                    return 'LOJEL Cubo'
                elif 'PHILIPS ADD6920 RO Water Dispenser' in name_str or 'Philips ADD6920' in name_str:
                    return 'Philips ADD6920 RO Water Dispenser'
                else:
                    return name_str 

            flt_passed_df['Preview Group'] = flt_passed_df['offerName'].apply(group_offer_names)
            
            flt_summary_df = flt_passed_df.groupby('Preview Group', as_index=False).agg(
                Number_of_leadIds=('leadId', 'count')
            )
            
            flt_summary_df = flt_summary_df.rename(columns={'Preview Group': 'offerName (Grouped)'})
            
            st.write("👀 **Preview:** (Total leads per Reward Category)")
            st.dataframe(flt_summary_df)
            
            st.caption("Note: The downloaded file contains all details (original offerName, leadId, providerFeedbackDate).")
            
            flt_csv = flt_passed_df.drop(columns=['Preview Group']).to_csv(index=False).encode('utf-8')
            
            st.download_button(
                label="📥 Download Full FLT List", 
                data=flt_csv, 
                file_name="flt_passed_sla_list.csv", 
                mime="text/csv"
            )
