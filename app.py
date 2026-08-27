import streamlit as st
import pandas as pd
import numpy as np
import gc

# Configure the web page
st.set_page_config(page_title="Project Alyson", layout="wide")
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
uploaded_file = st.file_uploader("📁 Step 1: Upload the Tracked Rewards Export file. Make sure to convert it to CSV format first!", type=["csv"])

if uploaded_file:
    with st.spinner("Reading data and calculating SLAs... (This takes a moment)"):
        df = load_and_process_data(uploaded_file)
        
    if 'leadId' not in df.columns:
        st.error("❌ ERROR: Could not find a column named 'leadId' in your file.")
    else:
        st.success(f"✅ Success! Loaded {len(df):,} rows.")
        
        # Create THREE separate tabs for your flows
        tab1, tab2, tab3 = st.tabs(["🔍 Search by Lead ID", "📈 SLA Reports", "🛠️ Bulk Solving"])
        
        # --- TAB 1: SEARCH FLOW ---
        with tab1:
            col1, col2 = st.columns(2)
            with col1:
                paste_area = st.text_area("Paste your Lead IDs here (one per line):", height=200)
            with col2:
                # Set up the requested default columns
                desired_defaults = [
                    'leadId', 'referenceId.ns', 'application.entry.status', 'operationStatus', 
                    'vendorName', 'poReference', 'redemptionEmailSentDate', 'batchNumber', 
                    'offerName', 'providerFeedbackDate', 'SLA Check'
                ]
                
                # Safety check: Only apply defaults that actually exist in the uploaded CSV
                actual_defaults = [col for col in desired_defaults if col in df.columns]
                
                selected_cols = st.multiselect("Select columns to display:", df.columns.tolist(), default=actual_defaults)
            
            if st.button("🔍 Search & Preview", type="primary"):
                search_list = [x.strip() for x in paste_area.strip().split('\n')]
                
                if not paste_area.strip() or not selected_cols:
                    st.warning("⚠️ Please paste at least one Lead ID AND select at least one column.")
                else:
                    search_df = pd.DataFrame({'leadId': search_list})
                    cols_to_pull = list(set(selected_cols + ['leadId']))
                    matched_df = df[df['leadId'].isin(search_list)][cols_to_pull]
                    merged_results = pd.merge(search_df, matched_df, on='leadId', how='left')
                    cols_to_fill = [col for col in selected_cols if col != 'leadId']
                    merged_results[cols_to_fill] = merged_results[cols_to_fill].fillna('No match found')
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
            elt_summary_df = elt_passed_df.groupby('referenceId.ns', as_index=False).agg(Number_of_leadIds=('leadId', 'count'))
            elt_summary_df = elt_summary_df.sort_values(by='Number_of_leadIds', ascending=False).reset_index(drop=True)
            
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
                if 'Apple Store Gift Card' in name_str: return 'Apple Store Gift Card'
                elif 'Wellcome' in name_str: return 'Wellcome Vouchers'
                elif 'HKTVMall' in name_str or 'HKTVmall' in name_str: return 'HKTVMall Vouchers'
                elif 'Apple iPad 11-inch (A16)' in name_str or 'iPad Pro 11-inch' in name_str or '11 inch iPad' in name_str: return 'Apple iPad 11-inch (A16)'
                elif 'DELONGHI DEDICA DUO' in name_str or 'DELONGHIDEDICA DUO' in name_str: return 'Delonghi Dedica Duo EC890'
                elif 'DYSON HD19' in name_str: return 'Dyson HD19 Hair Dryer'
                elif 'DYSON HD16' in name_str: return 'Dyson HD16 Hair Dryer'
                elif 'Delsey 30" GRENELLE SE' in name_str: return 'Delsey 30" GRENELLE SE'
                elif 'Cash Rebate' in name_str: return 'FPS Cash'
                elif 'LOJEL Cubo' in name_str or 'LOJEL CUBO' in name_str: return 'LOJEL Cubo'
                elif 'PHILIPS ADD6920 RO Water Dispenser' in name_str or 'Philips ADD6920' in name_str: return 'Philips ADD6920 RO Water Dispenser'
                else: return name_str 

            flt_passed_df['Preview Group'] = flt_passed_df['offerName'].apply(group_offer_names)
            flt_summary_df = flt_passed_df.groupby('Preview Group', as_index=False).agg(Number_of_leadIds=('leadId', 'count'))
            flt_summary_df = flt_summary_df.rename(columns={'Preview Group': 'offerName (Grouped)'})
            flt_summary_df = flt_summary_df.sort_values(by='Number_of_leadIds', ascending=False).reset_index(drop=True)
            
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

        # --- TAB 3: BULK SOLVING FLOW ---
        with tab3:
            st.write("Upload Support Team View export to cross-reference them with the Tracked Rewards Export.")
            zd_file = st.file_uploader("📁 Step 2: Upload Support Team View export in CSV format", type=["csv"], key="zd_upload")
            
            if zd_file:
                zd_df = pd.read_csv(zd_file, dtype=str)
                
                required_cols = ['ID', 'Leads ID', 'Provider']
                missing_cols = [c for c in required_cols if c not in zd_df.columns]
                
                if missing_cols:
                    st.error(f"❌ ERROR: Missing required columns in your file: {', '.join(missing_cols)}")
                else:
                    zd_df['Leads ID'] = zd_df['Leads ID'].fillna('').astype(str).str.strip()
                    zd_df['Provider'] = zd_df['Provider'].fillna('').astype(str).str.strip()
                    
                    invalid_mask = ~zd_df['Leads ID'].str.replace('000', '').str.isdigit()
                    invalid_df = zd_df[invalid_mask]
                    valid_df = zd_df[~invalid_mask].copy()
                    
                    if not invalid_df.empty:
                        st.warning(f"⚠️ Flagged {len(invalid_df)} entries with missing or invalid Leads IDs. You may reassign these tickets back to the ticket tagger")
                        inv_col1, inv_col2 = st.columns([1, 2])
                        with inv_col1:
                            invalid_display = invalid_df[['ID']].rename(columns={'ID': 'Zendesk Ticket #'})
                            st.dataframe(invalid_display, use_container_width=True)
                        with inv_col2:
                            st.write("📋 **Copy Zendesk Search Query:**")
                            search_string = " ".join([f'ticket_id:"{tid}"' for tid in invalid_df['ID'].dropna()])
                            st.code(search_string, language='text')
                        
                    if not valid_df.empty:
                        def split_lead_ids(val):
                            if len(val) > 7 and '000' in val:
                                return [v for v in val.split('000') if v]
                            return [val]
                            
                        valid_df['Leads ID'] = valid_df['Leads ID'].apply(split_lead_ids)
                        valid_df = valid_df.explode('Leads ID')
                        
                        master_cols_to_pull = [
                            'referenceId.ns', 'application.entry.status', 'operationStatus', 
                            'vendorName', 'poReference', 'redemptionEmailSentDate', 'batchNumber', 
                            'offerName', 'providerFeedbackDate', 'SLA Check'
                        ]
                        
                        actual_master_cols = [c for c in master_cols_to_pull if c in df.columns]
                        master_subset = df[['leadId'] + actual_master_cols]
                        
                        merged = pd.merge(valid_df, master_subset, left_on='Leads ID', right_on='leadId', how='left')
                        
                        for c in actual_master_cols:
                            merged[c] = merged[c].fillna('No match found')
                            
                        if 'leadId' in merged.columns:
                            merged = merged.drop(columns=['leadId'])
                        merged = merged.reset_index(drop=True)
                            
                        # Auto-Resolve
                        mismatch_indices = []
                        known_resolutions = {
                            ('citi', 'citibank'): 'Citibank',
                            ('uaf', 'ua'): 'UA',
                            ('tiger', 'tiger brokers'): 'Tiger Brokers',
                            ('longbrg', 'longbridge'): 'Longbridge',
                            ('htsc', 'huatai'): 'Huatai',
                            ('hase', 'hangseng'): 'HangSeng',
                            ('dahsing', 'dah sing'): 'Dah Sing',
                            ('citic', 'cncbi'): 'HangSeng'
                        }
                        
                        for idx, row in merged.iterrows():
                            provider_raw = str(row.get('Provider', '')).strip()
                            ref_raw = str(row.get('referenceId.ns', '')).strip()
                            provider = provider_raw.lower()
                            ref = ref_raw.lower()
                            
                            if provider != ref and ref != 'no match found' and ref != 'nan':
                                if provider == '':
                                    merged.at[idx, 'Provider'] = ref_raw
                                elif (ref, provider) in known_resolutions:
                                    resolved_val = known_resolutions[(ref, provider)]
                                    merged.at[idx, 'Provider'] = resolved_val
                                    merged.at[idx, 'referenceId.ns'] = resolved_val
                                else:
                                    mismatch_indices.append(idx)
                                
                        needs_review = len(mismatch_indices) > 0
                        
                        if needs_review:
                            st.warning(f"⚠️ Found {len(mismatch_indices)} rows where Provider and referenceId.ns do not match. Please check and update with the right value")
                            st.markdown("📝 **Instructions:** \n- **Edit Value:** Edit the `Resolved Value` column. Type or paste from your Excel file!\n- **Remove Entry:** Check the `Remove (Assign Back)` box if both values are incorrect and the ticket needs reassignment.\n- **Duplicates:** Yellow rows 🟡 indicate duplicate Zendesk Tickets.")
                            
                            mismatch_df = merged.loc[mismatch_indices, ['ID', 'Leads ID', 'Provider', 'referenceId.ns']].copy()
                            mismatch_df['Resolved Value'] = mismatch_df['referenceId.ns']
                            mismatch_df['Remove (Assign Back)'] = False
                            
                            def highlight_duplicates(data):
                                styles = pd.DataFrame('', index=data.index, columns=data.columns)
                                is_dup = data.duplicated(subset=['ID'], keep=False)
                                styles.loc[is_dup, :] = 'background-color: #fff2cc; color: #8a6d3b;'
                                return styles
                                
                            styled_mismatch = mismatch_df.style.apply(highlight_duplicates, axis=None)
                            
                            edited_mismatches = st.data_editor(
                                styled_mismatch,
                                column_config={
                                    "Resolved Value": st.column_config.TextColumn("Resolved Value (Edit Here)", required=True),
                                    "Remove (Assign Back)": st.column_config.CheckboxColumn("Remove (Assign Back)", help="Check this to remove the entry completely if the Lead ID is wrong.")
                                },
                                disabled=["ID", "Leads ID", "Provider", "referenceId.ns"],
                                hide_index=True,
                                use_container_width=True
                            )
                            st.write("---")
                            confirmed = st.checkbox("✅ I confirm all values are updated")
                        else:
                            confirmed = True
                            st.success(f"✅ Successfully processed {len(merged)} Leads IDs. No conflicts found!")

                        # ---------------------------------------------------------
                        # SCENARIO BUCKETING LOGIC (Only runs after confirmation)
                        # ---------------------------------------------------------
                        if confirmed:
                            final_merged = merged.copy()
                            indices_to_drop = []
                            
                            if needs_review:
                                for idx in mismatch_indices:
                                    if edited_mismatches.at[idx, 'Remove (Assign Back)']:
                                        indices_to_drop.append(idx)
                                    else:
                                        new_val = edited_mismatches.at[idx, 'Resolved Value']
                                        final_merged.at[idx, 'Provider'] = new_val
                                        final_merged.at[idx, 'referenceId.ns'] = new_val
                                        
                                # Drop the rows flagged for removal before bucketing
                                if indices_to_drop:
                                    final_merged = final_merged.drop(indices_to_drop)
                                
                                st.success(f"✅ Conflicts resolved! {len(indices_to_drop)} entries were removed. See the categorized scenarios below.")

                            st.write("### 🗂️ Bulk Solving Scenarios")
                            
                            # Track which indices have been bucketed
                            used_indices = set()

                            def claim_rows(mask):
                                df_subset = final_merged[mask & (~final_merged.index.isin(used_indices))].copy()
                                used_indices.update(df_subset.index)
                                return df_subset

                            # Ensure column exists before checking
                            if 'Fulfillment Issues' not in final_merged.columns:
                                final_merged['Fulfillment Issues'] = ''
                            
                            final_merged['operationStatus'] = final_merged['operationStatus'].fillna('')
                            
                            # Pre-calculate dataframes 1 through 7 to establish what is leftover
                            elt_within_mask = final_merged['operationStatus'].isin(['NONE', 'PENDING']) & (final_merged['SLA Check'] == '')
                            elt_within_df = claim_rows(elt_within_mask)

                            elt_past_mask = final_merged['operationStatus'].isin(['NONE', 'PENDING']) & (final_merged['SLA Check'] == 'ELT Passed SLA')
                            elt_past_df = claim_rows(elt_past_mask)

                            flt_within_mask = final_merged['operationStatus'].isin(['APPROVED', 'SPECIAL_APPROVAL']) & (final_merged['SLA Check'] == '')
                            flt_within_df = claim_rows(flt_within_mask)

                            flt_past_mask = final_merged['operationStatus'].isin(['APPROVED', 'SPECIAL_APPROVAL']) & (final_merged['SLA Check'] == 'FLT Passed SLA')
                            flt_past_df = claim_rows(flt_past_mask)

                            flt_comp_mask = (final_merged['Fulfillment Issues'] != 'Resend Redemption Email/Link (Digital)') & (final_merged['operationStatus'].isin(['FULFILLED', 'RECEIVED']))
                            flt_comp_df = claim_rows(flt_comp_mask)

                            reject_mask = final_merged['operationStatus'] == 'DECLINED'
                            reject_df = claim_rows(reject_mask)

                            resend_mask = (
                                (final_merged['Fulfillment Issues'] == 'Resend Redemption Email/Link (Digital)') & 
                                (final_merged['operationStatus'].isin(['FULFILLED', 'RECEIVED'])) & 
                                (final_merged['vendorName'].fillna('').str.contains('Reward 360', case=False, na=False))
                            )
                            resend_df = claim_rows(resend_mask)

                            # 8. Not meeting the requirements (Everything else left over)
                            leftover_mask = ~final_merged.index.isin(used_indices)
                            not_meeting_df = claim_rows(leftover_mask)

                            # --- UI RENDERING START ---

                            # Render "Not Meeting Requirements" fixed at the very top
                            if not not_meeting_df.empty:
                                st.subheader(f"⚠️ Not Meeting Requirements ({len(not_meeting_df['ID'].dropna().unique())} Tickets)")
                                st.write("These tickets do not match standard automated scenarios. Please review them manually.")
                                st.dataframe(not_meeting_df, use_container_width=True)
                                
                                csv_data = not_meeting_df.to_csv(index=False).encode('utf-8')
                                st.download_button(
                                    label="📥 Download CSV", 
                                    data=csv_data, 
                                    file_name="Not_Meeting_Requirements.csv", 
                                    mime="text/csv", 
                                    key="dl_Not_Meeting"
                                )
                                st.divider()
                                
                            st.write("Expand a category below to copy the Zendesk query or download the CSV file for bulk solving.")

                            # Helper function to generate UI for buckets 1-7 with full columns
                            def render_scenario(title, df_subset, file_key):
                                if df_subset.empty:
                                    return
                                    
                                unique_tickets = df_subset['ID'].dropna().unique()
                                
                                with st.expander(f"{title} ({len(unique_tickets)} Tickets)"):
                                    st.write("📋 **Copy Zendesk Search Query:**")
                                    st.code(" ".join([f'ticket_id:"{tid}"' for tid in unique_tickets]), language='text')
                                    
                                    st.write("👀 **Preview:**")
                                    st.dataframe(df_subset, use_container_width=True)
                                        
                                    csv_data = df_subset.to_csv(index=False).encode('utf-8')
                                    clean_filename = file_key.replace(" ", "_").replace("/", "_") + ".csv"
                                    st.download_button(label=f"📥 Download CSV", data=csv_data, file_name=clean_filename, mime="text/csv", key=f"dl_{file_key}")

                            # Render scenarios 1-7 using the expander format
                            render_scenario("ELT Within SLA", elt_within_df, "ELT_Within_SLA")
                            render_scenario("ELT Past SLA", elt_past_df, "ELT_Past_SLA")
                            
                            if not flt_within_df.empty:
                                for provider, group_df in flt_within_df.groupby('referenceId.ns'):
                                    render_scenario(f"FLT Within SLA - {provider}", group_df, f"FLT_Within_SLA_{provider}")
                                    
                            render_scenario("FLT Past SLA", flt_past_df, "FLT_Past_SLA")
                            
                            if not flt_comp_df.empty:
                                for date_val, group_df in flt_comp_df.groupby('redemptionEmailSentDate'):
                                    render_scenario(f"FLT Completed - {date_val}", group_df, f"FLT_Completed_{date_val}")
                                    
                            render_scenario("Rejected Application", reject_df, "Rejected_Application")
                            render_scenario("Resend Redemption Email", resend_df, "Resend_Redemption_Email")
