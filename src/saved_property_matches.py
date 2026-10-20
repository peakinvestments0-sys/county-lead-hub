"""Persist property identity and source-backed distress details on saved contacts."""
from collections import defaultdict
from datetime import datetime, timezone
import json
import re

from src.normalizer import clean_display_address


def address_key(value):
    return re.sub(r'[^A-Z0-9]', '', clean_display_address(str(value or '')).upper())


def distress_type(value):
    text = str(value or '').strip()
    low = text.lower()
    if not text or low in ('nan', 'none', 'skip-traced lead', 'unknown'):
        return ''
    if 'death certificate' in low:
        return 'Death Certificate'
    if 'probate' in low:
        return 'Probate'
    if 'lis pendens' in low or 'lis_pendens' in low or 'foreclosure' in low:
        return 'Lis Pendens'
    if 'code' in low and ('violation' in low or 'enforcement' in low):
        return 'Code Violation'
    if 'tax' in low and ('lien' in low or 'delinquen' in low):
        return 'Tax Lien'
    if 'judgment' in low:
        return 'Civil Judgment'
    if 'lien' in low:
        return 'Recorded Lien'
    if 'water' in low or 'ouc' in low:
        return 'Water Shutoff'
    if 'felony' in low or 'legal distress' in low:
        return 'Legal Distress (Felony)'
    if 'divorce' in low or 'domestic relations' in low:
        return 'Divorce'
    return text


def is_explicit_probate(value):
    text = str(value or '').lower()
    return 'probate' in text and 'death certificate' not in text


class PropertyMatchIndex:
    def __init__(self, records, source):
        self.by_parcel = defaultdict(list)
        self.by_address = defaultdict(set)
        self.source = str(source)
        for record in records:
            if str(record.get('Match_Status') or 'MATCHED').upper() != 'MATCHED':
                continue
            pid = str(record.get('Parcel_ID') or '').strip()
            if not pid or pid.lower() == 'nan':
                continue
            self.by_parcel[pid].append(record)
            key = address_key(record.get('Property_Address'))
            if key:
                self.by_address[key].add(pid)

    def resolve(self, parcel_id, contact):
        pid = str(contact.get('matched_parcel_id') or parcel_id)
        method = 'Saved parcel ID' if contact.get('matched_parcel_id') else 'Exact parcel ID'
        if pid not in self.by_parcel:
            candidates = self.by_address.get(address_key(contact.get('address')), set())
            if len(candidates) != 1:
                return None  # Never guess between multiple parcels or use a fuzzy match.
            pid = next(iter(candidates))
            method = 'Exact normalized address'
        records = self.by_parcel[pid]
        actual_types = {distress_type(r.get('Lead_Type')) for r in records} - {''}
        types, evidence = set(actual_types), []
        for record in records:
            category = distress_type(record.get('Lead_Type'))
            if category:
                types.add(category)
            notes = str(record.get('Distress_Stack_Notes') or '')
            # Legacy felony flags alone do not prove two distinct distress types.
            if re.search(r'\b(?:DOUBLE|TRIPLE) DISTRESS:', notes, re.I):
                for part in notes.split(':', 1)[1].split('+'):
                    if 'judgment' in part.lower() and 'lien' in part.lower():
                        known = actual_types & {'Civil Judgment', 'Recorded Lien'}
                        types.update(known or {'Judgment / Recorded Lien'})
                        continue  # An either/or legacy label is not two separate recorded conditions.
                    extra = distress_type(part)
                    # Probate requires its own explicit record, never a trust/stack inference.
                    if extra and extra != 'Probate':
                        types.add(extra)
            evidence.append({key: str(record.get(key) or '') for key in
                             ('Lead_Type', 'Case_Number', 'Document_Number', 'County_Book_Page',
                              'Filing_Date', 'Case_Date', 'Recording_Date', 'Subject_Case Number',
                              'Source_File', 'Distress_Stack_Notes')})
        ordered = sorted(types, key=lambda t: (t != 'Lis Pendens', t != 'Code Violation', t))
        first = records[0]
        fields = ('Property_Address', 'Property_City', 'Property_Zip', 'Clean_Full_Name',
                  'Clean_First_Name', 'Clean_Last_Name', 'Market_Value', 'Just_Value',
                  'Owner_Entity_Type', 'Absentee_Status', 'Is_Trust_Or_Estate', 'Mailing_Address',
                  'Mailing_City', 'Mailing_State', 'Living_Sqft', 'Year_Built', 'Photo_Url')
        details = {key: first[key] for key in fields if key in first and first[key] is not None}
        details.update({'Parcel_ID': pid, 'Lead_Type': ordered[0] if ordered else 'Unknown',
                        'All_Lead_Types': ordered, 'Is_Stacked_Distress': 'Yes' if len(ordered) >= 2 else 'No',
                        'Distress_Stack_Notes': ('DOUBLE DISTRESS: ' if len(ordered) >= 2 else 'Recorded distress: ')
                                              + ' + '.join(ordered),
                        'Has_Confirmed_Probate': 'Yes' if any(is_explicit_probate(r.get('Lead_Type'))
                                                           for r in records) else 'No',
                        'Match_Method': method, 'Match_Status': 'MATCHED'})
        return {'matched_parcel_id': pid, 'property_match': {
            'version': 1, 'county': contact.get('county', ''), 'state': contact.get('state') or 'FL',
            'checked_at': datetime.now(timezone.utc).isoformat(), 'cache_source': self.source,
            'record': details, 'evidence': evidence}}


def load_property_index(cache_path):
    import pandas as pd
    frame = pd.read_parquet(cache_path)
    # pandas handles numpy scalars, arrays and missing values in this JSON conversion.
    return PropertyMatchIndex(json.loads(frame.to_json(orient='records')), cache_path)
