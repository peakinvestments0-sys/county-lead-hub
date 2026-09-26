import re
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
from rapidfuzz import fuzz

from src.data_loader import ParcelDatabase
from src.normalizer import (
    normalize_name_for_matching,
    normalize_address,
    normalize_parcel_id,
    extract_legal_tokens,
    clean_text
)
from src.wholesaling import enrich_wholesale_record

class CrossReferenceEngine:
    """
    Multi-Tier cascading cross-reference matcher:
    Cross-references an incoming subject lead list against the Master Pinellas County Parcel Database.
    """
    def __init__(self, db: ParcelDatabase):
        self.db = db
        self.df = db.df
        
    def match_row(self, subject_row: Dict[str, Any], column_mapping: Dict[str, str]) -> Dict[str, Any]:
        """
        Attempts to match a single row from the subject file against Pinellas County master parcels.
        """
        # Extract fields based on user's column mapping
        raw_name = str(subject_row.get(column_mapping.get('name_col', ''), '')) if column_mapping.get('name_col') else ''
        raw_addr = str(subject_row.get(column_mapping.get('address_col', ''), '')) if column_mapping.get('address_col') else ''
        raw_parcel = str(subject_row.get(column_mapping.get('parcel_col', ''), '')) if column_mapping.get('parcel_col') else ''
        raw_legal = str(subject_row.get(column_mapping.get('legal_col', ''), '')) if column_mapping.get('legal_col') else ''
        raw_bookpage = str(subject_row.get(column_mapping.get('bookpage_col', ''), '')) if column_mapping.get('bookpage_col') else ''
        
        # --- TIER 1: Exact Parcel Number / Strap ---
        if raw_parcel and raw_parcel != 'nan':
            clean_pid = normalize_parcel_id(raw_parcel)
            if clean_pid:
                if clean_pid in self.db.parcel_index:
                    idx = self.db.parcel_index[clean_pid]
                    return self._build_match(idx, subject_row, 'MATCHED', 100, 'Exact Parcel ID', f"Matched on Parcel Number {raw_parcel}")
                if clean_pid in self.db.strap_index:
                    idx = self.db.strap_index[clean_pid]
                    return self._build_match(idx, subject_row, 'MATCHED', 100, 'Exact Strap ID', f"Matched on Strap {raw_parcel}")

        # --- TIER 2: Street Address ---
        if raw_addr and raw_addr != 'nan':
            # Extract street portion before comma if city/zip or unit is included (e.g. "3675 BENT OAK RD, 7, PALM HARBOR FL")
            street_part = raw_addr.split(',')[0].strip() if ',' in raw_addr else raw_addr
            clean_addr = normalize_address(street_part)
            
            indices = []
            match_type = 'Exact Physical Address'
            
            if clean_addr and clean_addr in self.db.address_index:
                indices = self.db.address_index[clean_addr]
            elif clean_addr:
                # Try stripping directional (e.g. 14465 86TH AVE N -> 14465 86TH AVE)
                clean_base = re.sub(r'\s+(N|S|E|W|NE|NW|SE|SW)$', '', clean_addr)
                if clean_base in self.db.base_address_index:
                    indices = self.db.base_address_index[clean_base]
                    match_type = 'Base Address (Directional Adjusted)'
                else:
                    # Try stripping street suffix (e.g. 625 MAYO ST -> 625 MAYO)
                    clean_no_sfx = re.sub(r'\s+(ST|AVE|RD|DR|BLVD|TER|LN|CT|CIR|WAY|PKWY)$', '', clean_addr)
                    if clean_no_sfx in self.db.base_address_index:
                        indices = self.db.base_address_index[clean_no_sfx]
                        match_type = 'Base Address (Suffix Adjusted)'
                        
            if indices:
                if len(indices) == 1:
                    return self._build_match(indices[0], subject_row, 'MATCHED', 98, match_type, f"Matched on Address '{clean_addr}'")
                elif len(indices) > 1 and raw_name:
                    best_idx = self._pick_best_by_name(indices, raw_name)
                    return self._build_match(best_idx, subject_row, 'MATCHED', 95, f"{match_type} + Name", f"Matched address with multiple parcels, resolved by name")
                else:
                    return self._build_match(indices[0], subject_row, 'MATCHED', 90, f"{match_type} (First Parcel)", f"Matched address ({len(indices)} parcels found)")

        # --- TIER 3: Exact Normalized Owner Name ---
        if raw_name and raw_name != 'nan':
            norm_name = normalize_name_for_matching(raw_name)
            if norm_name:
                # 3a. Direct check
                if norm_name in self.db.owner_exact_index:
                    indices = self.db.owner_exact_index[norm_name]
                    best_idx = self._pick_best_by_legal_or_first(indices, raw_legal)
                    return self._build_match(best_idx, subject_row, 'MATCHED', 95, 'Exact Owner Name', f"Exact name match on '{norm_name}'")
                    
                # 3b. Reversed check (e.g. FIRST LAST vs LAST FIRST)
                tokens = norm_name.split()
                if len(tokens) >= 2:
                    # Invert: LAST FIRST -> FIRST LAST or vice versa
                    inv_name = f"{tokens[-1]} " + " ".join(tokens[:-1])
                    if inv_name in self.db.owner_exact_index:
                        indices = self.db.owner_exact_index[inv_name]
                        best_idx = self._pick_best_by_legal_or_first(indices, raw_legal)
                        return self._build_match(best_idx, subject_row, 'MATCHED', 92, 'Exact Name (Inverted)', f"Inverted name match: '{raw_name}'")

        # --- TIER 4: Owner Name + Legal Lot/Block/Unit Match ---
        # Crucial for Florida Lis Pendens where document only lists Defendant Name and Lot/Unit/Subdivision!
        if raw_legal and raw_legal != 'nan':
            legal_info = extract_legal_tokens(raw_legal)
            lot = legal_info['lot']
            blk = legal_info['block']
            unit = legal_info['unit']
            sub_query = legal_info['subdivision']
            
            # 4a. Lot + Block exact index match
            if lot and blk and (lot, blk) in self.db.legal_lot_block_index:
                candidates = self.db.legal_lot_block_index[(lot, blk)]
                if raw_name:
                    norm_name = normalize_name_for_matching(raw_name)
                    name_tokens = set(norm_name.split())
                    for c_idx in candidates:
                        c_owner = normalize_name_for_matching(str(self.df.iloc[c_idx].get('OWNER1', '')))
                        c_tokens = set(c_owner.split())
                        if name_tokens.intersection(c_tokens):
                            return self._build_match(c_idx, subject_row, 'MATCHED', 95, 'Legal Lot/Block + Name Match',
                                                     f"Matched Lot {lot} Block {blk} with owner '{c_owner}'")
                                                     
                if sub_query:
                    for c_idx in candidates:
                        c_legal = clean_text(str(self.df.iloc[c_idx].get('LEGAL', '')))
                        ratio = fuzz.partial_ratio(sub_query, c_legal)
                        if ratio >= 80:
                            return self._build_match(c_idx, subject_row, 'MATCHED', 90, 'Legal Lot/Block + Subdivision Match',
                                                     f"Matched Lot {lot} Block {blk} in subdivision")
            
            # 4b. Owner Last Name candidate + Legal Description match (e.g. FAVA + LOT 56 GOLFWOODS)
            if raw_name:
                norm_name = normalize_name_for_matching(raw_name)
                tokens = norm_name.split()
                if tokens and len(tokens[0]) > 2:
                    last_name = tokens[0]
                    if last_name in self.db.owner_last_name_index:
                        candidates = self.db.owner_last_name_index[last_name]
                        clean_lp_legal = clean_text(raw_legal)
                        best_score = 0
                        best_idx = None
                        for c_idx in candidates:
                            c_legal = clean_text(str(self.df.iloc[c_idx].get('LEGAL', '')))
                            ratio = fuzz.token_set_ratio(clean_lp_legal, c_legal)
                            if ratio > best_score:
                                best_score = ratio
                                best_idx = c_idx
                        if best_score >= 60 and best_idx is not None:
                            return self._build_match(best_idx, subject_row, 'MATCHED', 93, 'Owner Last Name + Legal Match',
                                                     f"Matched owner last name '{last_name}' with legal description ({best_score:.0f}% similarity)")

        # --- TIER 5: Fuzzy Owner Name Matching (Fast Candidate Lookup) ---
        if raw_name and raw_name != 'nan':
            norm_name = normalize_name_for_matching(raw_name)
            tokens = norm_name.split()
            if tokens and len(tokens[0]) > 2:
                last_name = tokens[0]
                candidates = []
                # Direct last name
                if last_name in self.db.owner_last_name_index:
                    candidates = self.db.owner_last_name_index[last_name]
                elif len(last_name) >= 4:
                    # Try prefix of 4-5 chars for minor typos (e.g. WARFIEL vs WARFIELD)
                    prefix = last_name[:4]
                    for k, idx_list in self.db.owner_last_name_index.items():
                        if k.startswith(prefix):
                            candidates.extend(idx_list[:10])
                            if len(candidates) > 50:
                                break
                                
                if candidates:
                    best_score = 0
                    best_idx = None
                    for c_idx in candidates[:50]:
                        c_owner = normalize_name_for_matching(str(self.df.iloc[c_idx].get('OWNER1', '')))
                        score = fuzz.token_sort_ratio(norm_name, c_owner)
                        if score > best_score:
                            best_score = score
                            best_idx = c_idx
                            
                    if best_score >= 80 and best_idx is not None:
                        return self._build_match(best_idx, subject_row, 'MATCHED', int(best_score), 'Fuzzy Owner Name',
                                                 f"Fuzzy name match ({best_score:.0f}%): '{raw_name}' <-> '{self.df.iloc[best_idx].get('OWNER1')}'")

        # --- TIER 6: Official Records Book/Page ---
        if raw_bookpage and raw_bookpage != 'nan':
            bp_clean = raw_bookpage.strip().replace(' ', '')
            if bp_clean and bp_clean in self.db.or_book_page_index:
                indices = self.db.or_book_page_index[bp_clean]
                return self._build_match(indices[0], subject_row, 'MATCHED', 85, 'Official Records Book/Page',
                                         f"Matched on Book/Page {bp_clean}")

        # --- UNMATCHED ---
        return self._build_unmatched(subject_row)
        
    def _pick_best_by_name(self, indices: List[int], target_name: str) -> int:
        norm_target = normalize_name_for_matching(target_name)
        best_score = -1
        best_idx = indices[0]
        for idx in indices:
            owner = normalize_name_for_matching(str(self.df.iloc[idx].get('OWNER1', '')))
            score = fuzz.token_sort_ratio(norm_target, owner)
            if score > best_score:
                best_score = score
                best_idx = idx
        return best_idx
        
    def _pick_best_by_legal_or_first(self, indices: List[int], legal_str: str) -> int:
        if len(indices) == 1 or not legal_str or legal_str == 'nan':
            return indices[0]
        clean_leg = clean_text(legal_str)
        best_score = -1
        best_idx = indices[0]
        for idx in indices:
            c_leg = clean_text(str(self.df.iloc[idx].get('LEGAL', '')))
            score = fuzz.partial_ratio(clean_leg, c_leg)
            if score > best_score:
                best_score = score
                best_idx = idx
        return best_idx

    def _build_match(self, idx: int, subject_row: Dict[str, Any], status: str, confidence: int, method: str, notes: str) -> Dict[str, Any]:
        county_row = self.df.iloc[idx].to_dict()
        match_meta = {
            'status': status,
            'confidence': confidence,
            'method': method,
            'notes': notes
        }
        return enrich_wholesale_record(county_row, subject_row, match_meta)
        
    def _build_unmatched(self, subject_row: Dict[str, Any]) -> Dict[str, Any]:
        res = {
            'Match_Status': 'UNMATCHED',
            'Match_Confidence': 0,
            'Match_Method': 'None',
            'Match_Notes': 'No confident parcel found in Pinellas County database',
            'Clean_First_Name': '',
            'Clean_Last_Name': '',
            'Clean_Full_Name': '',
            'Owner_Entity_Type': '',
            'Is_Trust_Or_Estate': 'No',
            'County_Owner_1': '',
            'County_Owner_2': '',
            'Secondary_Owner': '',
            'Property_Address': '',
            'Property_City': '',
            'Property_Zip': '',
            'Parcel_ID': '',
            'Strap': '',
            'Mailing_Address': '',
            'Mailing_City': '',
            'Mailing_State': '',
            'Mailing_Zip': '',
            'Absentee_Status': 'Unknown',
            'Is_Absentee': 'Unknown',
            'Absentee_Priority': 'None',
            'Homestead_Exemption': '',
            'Market_Value': 0.0,
            'Assessed_Value': 0.0,
            'Taxable_Value': 0.0,
            'Year_Built': '',
            'Living_Sqft': '',
            'Property_Type': '',
            'Property_Use': '',
            'County_Book_Page': '',
            'Legal_Description': ''
        }
        for k, v in subject_row.items():
            res[f"Subject_{k}"] = v
        return res
        
    def cross_reference_dataframe(self, subject_df: pd.DataFrame, column_mapping: Dict[str, str], progress_callback=None) -> pd.DataFrame:
        """
        Cross-references an entire subject dataframe and returns the enriched matched dataframe.
        """
        results = []
        total = len(subject_df)
        for idx, (_, row) in enumerate(subject_df.iterrows()):
            res = self.match_row(row.to_dict(), column_mapping)
            results.append(res)
            if progress_callback and (idx % 10 == 0 or idx == total - 1):
                progress_callback(idx + 1, total)
        res_df = pd.DataFrame(results)
        for col in ['Market_Value', 'Assessed_Value', 'Taxable_Value']:
            if col in res_df.columns:
                res_df[col] = pd.to_numeric(res_df[col], errors='coerce').fillna(0.0)
        return res_df
