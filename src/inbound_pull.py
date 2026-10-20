"""Inbound file metadata, schema validation, and durable row deduplication.

Parsing and cross-reference are supplied by server.py's existing Load List path.
"""
from datetime import date
from contextlib import closing
from pathlib import Path
import re
import sqlite3

LIS_PENDENS_HEADERS = [
    'recording_date', 'instrument_number', 'book_page', 'grantor', 'grantee',
    'property_address', 'legal_description',
]
SCHEMAS = {'lis-pendens': LIS_PENDENS_HEADERS}
LIST_TYPES = ('lis-pendens', 'probate', 'code-violations', 'tax-lien')
LEAD_SOURCES = {'lis-pendens': 'lis_pendens', 'probate': 'probate',
                'code-violations': 'code_violations', 'tax-lien': 'tax_liens'}
LEDGER_PATH = Path(__file__).resolve().parents[1] / 'data' / 'inbound_pulls.sqlite3'


class PullValidationError(ValueError):
    pass


def identify_pull(filename, counties):
    stem = re.fullmatch(r'(.+)-(\d{4}-\d{2}-\d{2})\.csv', filename, re.I)
    if not stem:
        raise PullValidationError('Expected <list-type>-<county>-<YYYY-MM-DD>.csv')
    try:
        date.fromisoformat(stem[2])
    except ValueError as exc:
        raise PullValidationError('Invalid pull date') from exc
    prefix = stem[1].lower()
    for list_type in LIST_TYPES:
        if prefix.startswith(list_type + '-'):
            county_slug = prefix[len(list_type) + 1:]
        elif prefix.endswith('-' + list_type):
            # Pepper's verified orange-county-lis-pendens example uses this order.
            county_slug = prefix[:-len(list_type) - 1]
        else:
            continue
        county_slug = re.sub(r'-county$', '', county_slug)
        for county in counties:
            if re.sub(r'[^a-z0-9]+', '-', county.lower()).strip('-') == county_slug:
                return list_type, county
        raise PullValidationError(f'Unknown county: {county_slug}')
    raise PullValidationError(f'Unknown list-type prefix: {prefix}')


def validate_schema(frame, list_type):
    expected = SCHEMAS.get(list_type)
    if expected is None:
        raise PullValidationError(f'Schema not defined for {list_type}; define verified headers before enabling these pulls')
    actual = list(frame.columns)
    if actual != expected:
        missing = [c for c in expected if c not in actual]
        extra = [c for c in actual if c not in expected]
        raise PullValidationError(f'Header mismatch: missing={missing}, unexpected={extra}, '
                                  f'order_changed={not missing and not extra}; expected={expected}, actual={actual}')


def ingest_once(frame, list_type, county, source_name, load_list, ledger_path=None):
    """Commit dedupe keys only after the shared Load List pipeline persists matches.

    A transaction serializes uploads and watcher imports. Replays after a crash
    remain safe because the shared cache merge is idempotent by parcel/type.
    """
    path = Path(ledger_path or LEDGER_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = frame['instrument_number'].fillna('').astype(str).str.strip()
    if keys.eq('').any():
        raise PullValidationError(f'{int(keys.eq("").sum())} row(s) lack instrument_number; cannot deduplicate safely')
    county_key = re.sub(r'[^a-z0-9]+', '-', county.lower()).strip('-')
    with closing(sqlite3.connect(path, timeout=120)) as conn, conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS ingested_rows (
            list_type TEXT NOT NULL, county TEXT NOT NULL, instrument_number TEXT NOT NULL,
            source_name TEXT NOT NULL, ingested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (list_type, county, instrument_number))''')
        conn.execute('BEGIN IMMEDIATE')
        seen = {row[0] for row in conn.execute(
            'SELECT instrument_number FROM ingested_rows WHERE list_type=? AND county=?', (list_type, county_key))}
        selected, new_keys = [], []
        for position, key in enumerate(keys):
            if key not in seen:
                selected.append(position)
                new_keys.append(key)
                seen.add(key)
        result = load_list(frame.iloc[selected].copy()) if selected else {
            'status': 'success', 'county': county, 'source_name': source_name,
            'records': [], 'kpis': {'total_leads': 0, 'matched_count': 0},
        }
        conn.executemany('INSERT INTO ingested_rows (list_type, county, instrument_number, source_name) VALUES (?, ?, ?, ?)',
                         [(list_type, county_key, key, source_name) for key in new_keys])
    return {'rows_ingested': len(selected), 'rows_skipped_duplicates': len(frame) - len(selected),
            'rows_quarantined': 0, 'result': result}


def ingest_pull_file(file_path, read_upload, load_list, counties, ledger_path=None):
    path = Path(file_path)
    metadata = {'filename': path.name, 'list_type': 'unknown', 'county': 'unknown', 'rows_total': None}
    try:
        frame = read_upload(path.read_bytes(), path.name)
        metadata['rows_total'] = len(frame)
        list_type, county = identify_pull(path.name, counties)
        metadata.update(list_type=list_type, county=county)
        validate_schema(frame, list_type)
        if frame.empty:
            raise PullValidationError('Lead file contains 0 records')
        summary = ingest_once(frame, list_type, county, path.name,
                              lambda rows: load_list(rows, county, LEAD_SOURCES[list_type], path.name, True), ledger_path)
    except Exception as exc:
        exc.pull_metadata = metadata
        raise
    summary.pop('result')
    return {'filename': path.name, 'list_type': list_type, 'county': county, **summary}
