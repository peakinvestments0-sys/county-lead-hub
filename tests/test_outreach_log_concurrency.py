import ast
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest


class OutreachPersistenceTests(unittest.TestCase):
    def test_simultaneous_inbound_outbound_and_contact_updates_are_preserved(self):
        names = {'load_saved_contacts', 'atomic_outreach_json_write', 'append_outreach_log', 'save_contact', 'save_contact_locked'}
        root = Path(__file__).resolve().parents[1]
        tree = ast.parse((root / 'server.py').read_text(encoding='utf-8'))
        funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        self.assertEqual(len(funcs), 5)
        with tempfile.TemporaryDirectory() as directory:
            contacts = Path(directory) / 'contacts.json'
            logs = Path(directory) / 'history.json'
            contacts.write_text(json.dumps({'p1': {'owner': 'Seller', 'phone': '4072000001'}}))
            logs.write_text('[]')
            ns = {'json': json, 'os': os, 'time': time, 'CONTACTS_FILE': str(contacts), 'OUTREACH_LOG_FILE': str(logs), 'OUTREACH_DATA_LOCK': threading.RLock()}
            exec(compile(ast.Module(body=funcs, type_ignores=[]), 'server.py', 'exec'), ns)
            def update(i):
                ns['append_outreach_log']({'direction': 'INBOUND' if i % 2 else 'OUTBOUND', 'message': str(i)})
                ns['save_contact']('p1', {f'field_{i}': i})
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(update, range(20)))
            self.assertEqual(len(json.loads(logs.read_text())), 20)
            saved = json.loads(contacts.read_text())['p1']
            self.assertEqual(saved['phone'], '4072000001')
            self.assertTrue(all(saved[f'field_{i}'] == i for i in range(20)))


if __name__ == '__main__':
    unittest.main()
