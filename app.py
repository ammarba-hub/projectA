import streamlit as st
import pandas as pd
import numpy as np

# Configure the web page
st.set_page_config(page_title="Bulk Lookup & SLA Tool", layout="wide")
st.title("Project Alyson")

# CACHING: This tells the website to remember the 200MB file after it loads once, 
# so clicking "Search" is instantaneous.
@st.cache_data
def load_and_process_data(file):
    # Read the CSV
    df = pd.read_csv(file, dtype=str)
    
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
                search_list = [x.strip() for x in paste_area.split('\n') if x.strip()]
                
                if not search_list or not selected_cols:
                    st.warning("⚠️ Please paste at least one leadId AND select at least one column.")
                else:
                    search_results = df[df['leadId'].isin(search_list)][selected_cols]
                    st.write(f"✅ Found {len(search_results):,} matches! Here is your preview:")
                    st.dataframe(search_results)
                    
                    # Create the download button directly underneath the preview
                    csv = search_results.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Download CSV",
                        data=csv,
                        file_name="Lookup_Results.csv",
                        mime="text/csv",
                    )

        # --- TAB 2: SLA EXPORT FLOW ---
        with tab2:
            st.write("Extract records based on SLA Check status.")
            
            # --- ELT List ---
            st.subheader("ELT Passed SLA Records")
            
            # 1. Extract the full data (This is held in the background for the download)
            elt_passed_df = df[df['SLA Check'] == 'ELT Passed SLA'][['referenceId.ns', 'lead.createdAt', 'leadId']]
            
            # 2. Create a summary for the screen (Group by referenceId.ns and count leadIds)
            elt_summary_df = elt_passed_df.groupby('referenceId.ns', as_index=False).agg(
                Number_of_leadIds=('leadId', 'count')
            )
            
            # 3. Display the summary table
            st.write("👀 **Preview:** (Total leads per Reference ID)")
            st.dataframe(elt_summary_df)
            
            # 4. Keep the download button linked to the FULL dataframe
            st.caption("Note: The downloaded file contains all details (referenceId.ns, lead.createdAt, leadId).")
            elt_csv = elt_passed_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Full ELT List", 
                data=elt_csv, 
                file_name="elt_passed_sla_list.csv", 
                mime="text/csv"
            )
            
            st.divider() # Clean visual line
            
            # --- FLT List ---
            st.subheader("FLT Passed SLA Records")
            
            # 1. Extract the full data (use .copy() to safely add temporary columns)
            flt_passed_df = df[df['SLA Check'] == 'FLT Passed SLA'][['offerName', 'leadId', 'providerFeedbackDate']].copy()
            
            # 2. Create a rule to group similar offer names
            def group_offer_names(name):
                name_str = str(name)
                # You can add as many keyword rules here as you need!
                if 'Apple Store Gift Card' in name_str:
                    return 'Apple Store Gift Card'
                elif 'Apple iPad 11-inch (A16)' in name_str or 'iPad Pro 11-inch' in name_str:
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
                elif 'LOJEL Cubo' in name_str:
                    return 'LOJEL Cubo'
                elif 'PHILIPS ADD6920 RO Water Dispenser' in name_str or 'Philips ADD6920' in name_str:
                    return 'Philips ADD6920 RO Water Dispenser'
                else:
                    return name_str # Keep the original name if no keywords match

            # Apply the rules to create a clean grouping column
            flt_passed_df['Preview Group'] = flt_passed_df['offerName'].apply(group_offer_names)
            
            # 3. Create a summary for the screen
            flt_summary_df = flt_passed_df.groupby('Preview Group', as_index=False).agg(
                Number_of_leadIds=('leadId', 'count')
            )
            
            # Rename the column for a cleaner presentation
            flt_summary_df = flt_summary_df.rename(columns={'Preview Group': 'offerName (Grouped)'})
            
            # 4. Display the summary table
            st.write("👀 **Preview:** (Total leads per Reward Category)")
            st.dataframe(flt_summary_df)
            
            # 5. Keep the download button linked to the FULL detailed dataframe
            st.caption("Note: The downloaded file contains all details (original offerName, leadId, providerFeedbackDate).")
            
            # We drop the temporary 'Preview Group' column before downloading so the CSV stays clean
            flt_csv = flt_passed_df.drop(columns=['Preview Group']).to_csv(index=False).encode('utf-8')
            
            st.download_button(
                label="📥 Download Full FLT List", 
                data=flt_csv, 
                file_name="flt_passed_sla_list.csv", 
                mime="text/csv"
            )
