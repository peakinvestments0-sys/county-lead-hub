import os
import re
import time
import pandas as pd
from typing import Dict, List, Tuple, Any, Optional
from src.config import PCPAO_COLS, DEFAULT_MASTER_CSV, DEFAULT_MASTER_PARQUET
from src.normalizer import (
    normalize_name_for_matching,
    normalize_address,
    normalize_parcel_id,
    extract_legal_tokens
)

class ParcelDatabase:
    """
    High-speed in-memory indexed container for Pinellas County Master Parcels.
    Uses dictionary hash-indexes for O(1) lookups on 437k+ rows.
    """
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.total_records = len(df)
        
        # Build indexes
        t0 = time.time()
        self.parcel_index: Dict[str, int] = {}
        self.strap_index: Dict[str, int] = {}
        self.address_index: Dict[str, List[int]] = {}
        self.base_address_index: Dict[str, List[int]] = {}
        self.owner_exact_index: Dict[str, List[int]] = {}
        self.owner_last_name_index: Dict[str, List[int]] = {}
        self.legal_lot_block_index: Dict[Tuple[str, str], List[int]] = {}
        self.or_book_page_index: Dict[str, List[int]] = {}
        
        self._build_indexes()
        self.indexing_time_sec = round(time.time() - t0, 2)
        
    def _build_indexes(self):
        # Check if precomputed columns exist
        has_clean_p = 'CLEAN_PARCEL' in self.df.columns
        has_clean_st = 'CLEAN_STRAP' in self.df.columns
        has_norm_addr = 'NORM_ADDR' in self.df.columns
        has_norm_o1 = 'NORM_OWNER1' in self.df.columns
        
        parcels = self.df['CLEAN_PARCEL'].values if has_clean_p else (self.df['PARCEL_NUMBER'].astype(str).values if 'PARCEL_NUMBER' in self.df.columns else None)
        straps = self.df['CLEAN_STRAP'].values if has_clean_st else (self.df['STRAP'].astype(str).values if 'STRAP' in self.df.columns else None)
        addresses = self.df['NORM_ADDR'].values if has_norm_addr else (self.df['SITE_ADDRESS'].astype(str).values if 'SITE_ADDRESS' in self.df.columns else None)
        owner1 = self.df['NORM_OWNER1'].values if has_norm_o1 else (self.df['OWNER1'].astype(str).values if 'OWNER1' in self.df.columns else None)
        owner2 = self.df['OWNER2'].astype(str).values if 'OWNER2' in self.df.columns else None
        legals = self.df['LEGAL'].astype(str).values if 'LEGAL' in self.df.columns else None
        book_pages = self.df['OR_BOOK_PAGE'].astype(str).values if 'OR_BOOK_PAGE' in self.df.columns else None
        
        for i in range(self.total_records):
            # 1. Parcel Number Index
            if parcels is not None:
                p = parcels[i]
                if isinstance(p, str) and p and p != 'nan':
                    clean_p = p if has_clean_p else normalize_parcel_id(p)
                    if clean_p:
                        self.parcel_index[clean_p] = i
                    
            # 2. Strap Index
            if straps is not None:
                st = straps[i]
                if isinstance(st, str) and st and st != 'nan':
                    clean_st = st if has_clean_st else normalize_parcel_id(st)
                    if clean_st:
                        self.strap_index[clean_st] = i
                    
            # 3. Address Index
            if addresses is not None:
                addr = addresses[i]
                if isinstance(addr, str) and addr and addr != 'nan':
                    clean_addr = addr if has_norm_addr else normalize_address(addr)
                    if clean_addr:
                        if clean_addr not in self.address_index:
                            self.address_index[clean_addr] = []
                        self.address_index[clean_addr].append(i)
                        
                        # Base address without trailing directional (N, S, E, W, etc.)
                        base = re.sub(r'\s+(N|S|E|W|NE|NW|SE|SW)$', '', clean_addr)
                        if base != clean_addr:
                            if base not in self.base_address_index:
                                self.base_address_index[base] = []
                            self.base_address_index[base].append(i)
                        else:
                            if clean_addr not in self.base_address_index:
                                self.base_address_index[clean_addr] = []
                            self.base_address_index[clean_addr].append(i)
                    
            # 4. Owner 1 Index
            if owner1 is not None:
                o1 = owner1[i]
                if isinstance(o1, str) and o1 and o1 != 'nan':
                    norm_o1 = o1 if has_norm_o1 else normalize_name_for_matching(o1)
                    if norm_o1:
                        if norm_o1 not in self.owner_exact_index:
                            self.owner_exact_index[norm_o1] = []
                        self.owner_exact_index[norm_o1].append(i)
                        
                        # Last name index
                        tokens = norm_o1.split()
                        if tokens:
                            last = tokens[0]
                            if len(last) > 2:
                                if last not in self.owner_last_name_index:
                                    self.owner_last_name_index[last] = []
                                self.owner_last_name_index[last].append(i)

            # 5. Owner 2 Index
            if owner2 is not None:
                o2 = owner2[i]
                if isinstance(o2, str) and o2 and o2 != 'nan':
                    norm_o2 = normalize_name_for_matching(o2)
                    if norm_o2:
                        if norm_o2 not in self.owner_exact_index:
                            self.owner_exact_index[norm_o2] = []
                        self.owner_exact_index[norm_o2].append(i)
                    
            # 6. Legal Lot/Block Index
            if legals is not None:
                leg = legals[i]
                if isinstance(leg, str) and leg and leg != 'nan':
                    leg_tokens = extract_legal_tokens(leg)
                    lot = leg_tokens['lot']
                    blk = leg_tokens['block']
                    if lot and blk:
                        key = (lot, blk)
                        if key not in self.legal_lot_block_index:
                            self.legal_lot_block_index[key] = []
                        self.legal_lot_block_index[key].append(i)
                    
            # 7. Official Records Book/Page Index (e.g. 23669/1218)
            if book_pages is not None:
                bp = book_pages[i]
                if isinstance(bp, str) and bp and bp != 'nan':
                    bp_clean = bp.strip().replace(' ', '')
                    if bp_clean:
                        if bp_clean not in self.or_book_page_index:
                            self.or_book_page_index[bp_clean] = []
                        self.or_book_page_index[bp_clean].append(i)


def load_master_parcels(csv_path: str = DEFAULT_MASTER_CSV,
                         parquet_path: str = DEFAULT_MASTER_PARQUET,
                         force_reload: bool = False) -> ParcelDatabase:
    """
    Loads master county parcel dataset from Parquet cache or CSV.
    Auto-converts and caches any Florida CSV to Parquet on first load.
    """
    df = None
    
    # Ensure target directory exists for output parquet cache
    if parquet_path:
        os.makedirs(os.path.dirname(os.path.abspath(parquet_path)), exist_ok=True)

    # Check if Parquet cache exists, is non-empty (>10KB), and not force_reload
    if os.path.exists(parquet_path) and os.path.getsize(parquet_path) > 10000 and not force_reload:
        try:
            df = pd.read_parquet(parquet_path)
            if len(df) > 0:
                return ParcelDatabase(df)
        except Exception:
            pass

    # Read from CSV and convert
    if os.path.exists(csv_path):
        with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
            header_sample = f.readline()

        sep = '|' if header_sample.count('|') > header_sample.count(',') else (
            '\t' if header_sample.count('\t') > header_sample.count(',') else ','
        )

        df = pd.read_csv(csv_path, sep=sep, dtype=str, low_memory=False)

        # Standardize Florida DOR NAL columns to standard schema
        nal_map = {
            'Strap': 'STRAP',
            'Name': 'OWNER1',
            'SitusAddr1': 'SITE_ADDRESS',
            'SitusCity': 'SITE_CITY',
            'SitusZip': 'SITE_ZIP',
            'MailAddr1': 'MAILING_ADDRESS_1',
            'MailAddr2': 'MAILING_ADDRESS_2',
            'MailCity': 'MAILING_CITY',
            'MailState': 'MAILING_STATE',
            'MailZip': 'MAILING_ZIP',
            'TotalJust': 'CNTY_JST_VALUE',
            'SchoolAsd': 'CNTY_ASD_VALUE',
            'SchoolTaxable': 'CNTY_TAXABLE_VALUE',
            'LegalDscr': 'LEGAL',
            'TotLivArea': 'TOTAL_LIVING_SQFT',
            'ActYrBlt': 'YEAR_BUILT',
            'DORCode': 'PROPERTY_USE'
        }

        rename_cols = {k: v for k, v in nal_map.items() if k in df.columns and v not in df.columns}
        if rename_cols:
            df = df.rename(columns=rename_cols)

        if 'PARCEL_NUMBER' not in df.columns and 'STRAP' in df.columns:
            df['PARCEL_NUMBER'] = df['STRAP']

        if 'SITE_CITYZIP' not in df.columns and 'SITE_CITY' in df.columns:
            city = df['SITE_CITY'].fillna('')
            zip_code = df['SITE_ZIP'].fillna('') if 'SITE_ZIP' in df.columns else ''
            df['SITE_CITYZIP'] = (city + ', FL ' + zip_code).str.strip(', FL ')

        # Cache to Parquet for instant future loading
        try:
            df.to_parquet(parquet_path, engine='pyarrow', compression='snappy')
        except Exception:
            pass
    else:
        raise FileNotFoundError(f"Neither valid Parquet ({parquet_path}) nor CSV ({csv_path}) found.")
        
    return ParcelDatabase(df)
