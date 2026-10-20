"""Import the user-selected ZIP through Lead Hub's existing import endpoint."""
import csv
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import sys
import zipfile
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.saved_property_matches import address_key, PropertyMatchIndex

SOURCE = Path(r'C:\Users\johng\Downloads\Pinellas_County_Top_400-14ab8a56.zip')
BASE = 'http://127.0.0.1:8505'


class Response:
    def __init__(self, response):
        self.body = response.read()
    def json(self):
        return json.loads(self.body)
    def raise_for_status(self):
        pass  # urllib raises HTTPError for unsuccessful responses.


class HttpClient:
    @staticmethod
    def get(url, timeout):
        return Response(urllib.request.urlopen(url, timeout=timeout))

    @staticmethod
    def post(url, files, data, timeout):
        boundary = 'LeadHub' + uuid.uuid4().hex
        parts = []
        for key, value in data.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
        for key, (name, content, mime) in files.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"; filename="{name}"\r\nContent-Type: {mime}\r\n\r\n'.encode() + content + b'\r\n')
        parts.append(f'--{boundary}--\r\n'.encode())
        req = urllib.request.Request(url, data=b''.join(parts), headers={'Content-Type': 'multipart/form-data; boundary=' + boundary}, method='POST')
        return Response(urllib.request.urlopen(req, timeout=timeout))


requests = HttpClient()


def phone(value):
    digits = re.sub(r'\D', '', str(value or ''))
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    return digits if len(digits) == 10 and digits[0] in '23456789' else ''


def email(value):
    value = str(value or '').strip().lower()
    return value if re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+", value) else ''


def main():
    with zipfile.ZipFile(SOURCE) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith('.csv')]
        assert len(names) == 1
        csv_name, raw = Path(names[0]).name, archive.read(names[0])
    rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    assert len(rows) == 126
    assert all(r['County'].strip().casefold() == 'pinellas' and r['PropertyState'].strip().upper() == 'FL' for r in rows)
    assert all(r['PropertyAddress'].strip() for r in rows)
    keys = [address_key(r['PropertyAddress']) for r in rows]
    assert len(set(keys)) == len(rows), 'Duplicate property addresses require review'
    contacts = requests.get(BASE + '/api/leads/contacts', timeout=15).json()
    existing = defaultdict(list)
    for pid, c in contacts.items():
        if c.get('county') == 'Pinellas' and not pid.startswith('TEST-'):
            key = address_key(c.get('address') or c.get('property_match', {}).get('record', {}).get('Property_Address'))
            if key:
                existing[key].append(pid)
    live = requests.get(BASE + '/api/leads?county=Pinellas&state=FL', timeout=30).json()
    index = PropertyMatchIndex(live.get('records', []), 'Existing Pinellas lead records')
    output, used_emails, used_ids, mapping = [], set(), set(), []
    stats = Counter()
    for row, key in zip(rows, keys):
        address = row['PropertyAddress'].strip()
        match = index.resolve('', {'address': address, 'county': 'Pinellas', 'state': 'FL'})
        candidates = existing.get(key, [])
        if not candidates and match and match['matched_parcel_id'] in contacts:
            candidate = contacts[match['matched_parcel_id']]
            if candidate.get('county') == 'Pinellas':
                candidates = [match['matched_parcel_id']]
        candidates.sort(key=lambda pid: (not str(contacts[pid].get('source', '')).startswith('Skip Trace CSV'), pid))
        pid = candidates[0] if candidates else (match['matched_parcel_id'] if match else 'SKIP-PINELLAS-' + hashlib.sha256(key.encode()).hexdigest()[:16].upper())
        assert pid not in used_ids, 'Multiple rows resolve to one parcel'
        used_ids.add(pid)
        stats['existing_updated' if pid in contacts else 'new_contacts'] += 1
        stats['matched_distress'] += bool(match)
        numbers = []
        emails = []
        for n in range(1, 9):
            for i in range(1, 4):
                number = phone(row.get(f'Contact{n}Phone_{i}'))
                if number and number not in numbers:
                    numbers.append(number)
                mail = email(row.get(f'Contact{n}Email_{i}'))
                if mail and mail not in emails:
                    emails.append(mail)
        selected_email = next((e for e in emails if e not in used_emails), '')
        if selected_email:
            used_emails.add(selected_email)
        primary = numbers[0] if numbers else ''
        stats['rows_with_phone'] += bool(primary)
        stats['rows_with_email'] += bool(selected_email)
        prepared = {'Parcel_ID': pid, 'County': 'Pinellas', 'Property_Address': address,
                    'Property_City': row['PropertyCity'], 'Property_State': 'FL', 'Property_Zip': row['PropertyPostalCode'],
                    'Owner_Name': ' '.join(str(row.get(k) or '').strip() for k in ('FirstName', 'LastName')).strip(),
                    'Phone_1': primary, 'Phone_2': numbers[1] if len(numbers) > 1 else '', 'Email': selected_email,
                    'Lead_Type': match['property_match']['record']['Lead_Type'] if match else 'Skip-Traced Lead'}
        output.append(prepared)
        mapping.append({'parcel_id': pid, 'property_address': address, 'source_id': row.get('Id'), 'address_hash': row.get('AddressHash')})
    print('Verified source rows:', len(rows), 'County: Pinellas only. Unique properties:', len(keys))
    print('Import plan:', json.dumps(dict(stats), sort_keys=True))
    if '--apply' not in sys.argv:
        return
    for kind in ('sms', 'email'):
        q = requests.get(BASE + f'/api/{kind}/auto/status', timeout=10).json()['queue']
        assert q['status'] not in ('running', 'paused') and not q.get('in_flight'), 'An outreach batch is active'
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = ROOT / 'data/backups' / ('before_pinellas_top400_' + stamp)
    backup.mkdir(parents=True)
    for name in ('saved_contacts.json', 'outreach_history.json', 'auto_sms_queue.json', 'auto_email_queue.json'):
        shutil.copy2(ROOT / 'data' / name, backup / name)
    archive_dir = ROOT / 'data/FL/pinellas/imports' / ('top400_' + stamp)
    archive_dir.mkdir(parents=True)
    shutil.copy2(SOURCE, archive_dir / SOURCE.name)
    (archive_dir / csv_name).write_bytes(raw)
    intermediate = io.StringIO(newline='')
    writer = csv.DictWriter(intermediate, fieldnames=list(output[0]))
    writer.writeheader()
    writer.writerows(output)
    response = requests.post(BASE + '/api/leads/import-skiptrace',
                             files={'file': (csv_name, intermediate.getvalue().encode('utf-8'), 'text/csv')},
                             data={'default_county': 'Pinellas'}, timeout=90)
    response.raise_for_status()
    result = response.json()
    assert result['imported_count'] == len(rows), result
    assert result['counties_breakdown'] == {'Pinellas': len(rows)}, result
    after = requests.get(BASE + '/api/leads/contacts', timeout=15).json()
    for row in output:
        saved = after[row['Parcel_ID']]
        assert saved['county'] == 'Pinellas' and saved['state'] == 'FL'
        assert address_key(saved['address']) == address_key(row['Property_Address'])
        if row['Phone_1']:
            assert phone(saved['phone']) == row['Phone_1']
        if row['Email']:
            assert saved['email'] == row['Email']
    for pid, before in contacts.items():
        if before.get('county') == 'Orange':
            assert {k:v for k,v in after[pid].items() if k != 'sms_initial_resend_pending'} == {k:v for k,v in before.items() if k != 'sms_initial_resend_pending'}
        for k,v in before.items():
            if k.startswith('last_'):
                assert after[pid].get(k) == v, 'Existing outreach history changed'
    report = {'source_zip': str(SOURCE), 'rows': len(rows), 'stats': dict(stats), 'import_result': result, 'properties': mapping}
    (archive_dir / 'import_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('SUCCESS: all 126 verified under Pinellas. Existing outreach timestamps and Orange contacts preserved.')
    print('Original ZIP and CSV archived in the app Pinellas imports folder. No outreach started.')


if __name__ == '__main__':
    main()
