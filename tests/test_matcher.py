import sys
import os
import unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.normalizer import (
    normalize_name_for_matching,
    normalize_address,
    normalize_parcel_id,
    parse_owner_name,
    extract_legal_tokens
)
from src.wholesaling import determine_absentee_status

class TestPinellasMatcher(unittest.TestCase):
    def test_parse_owner_name_clerk_format(self):
        # Florida Clerk of Courts format: LAST FIRST MIDDLE
        res = parse_owner_name("EAST CATOURA JANET")
        self.assertEqual(res['Clean_First_Name'], 'Catoura')
        self.assertEqual(res['Clean_Last_Name'], 'East')
        self.assertEqual(res['Clean_Full_Name'], 'Catoura East')
        self.assertEqual(res['Owner_Entity_Type'], 'Individual')

    def test_parse_owner_name_pcpao_format(self):
        # PCPAO format: LAST, FIRST MIDDLE
        res = parse_owner_name("SMITH, JOHN A")
        self.assertEqual(res['Clean_First_Name'], 'John')
        self.assertEqual(res['Clean_Last_Name'], 'Smith')
        self.assertEqual(res['Owner_Entity_Type'], 'Individual')

    def test_parse_owner_name_trust(self):
        res = parse_owner_name("BUCK, CLIFFORD B TRE")
        self.assertEqual(res['Clean_First_Name'], 'Clifford')
        self.assertEqual(res['Clean_Last_Name'], 'Buck')
        self.assertEqual(res['Owner_Entity_Type'], 'Trust / Probate')
        self.assertEqual(res['Is_Trust_Or_Estate'], 'Yes')

    def test_parse_owner_name_corporate(self):
        res = parse_owner_name("3 GIRL PROPERTIES LLC")
        self.assertEqual(res['Owner_Entity_Type'], 'Company / LLC')
        self.assertEqual(res['Is_Trust_Or_Estate'], 'No')

    def test_normalize_address(self):
        self.assertEqual(normalize_address("123 4th Street North, Apt 2B"), "123 4TH ST N")
        self.assertEqual(normalize_address("843 62nd Avenue South"), "843 62ND AVE S")

    def test_normalize_parcel_id(self):
        self.assertEqual(normalize_parcel_id("07-32-17-04896-005-0070"), "073217048960050070")

    def test_extract_legal_tokens(self):
        tokens = extract_legal_tokens("LOT 7 BLOCK 5 BAY SHORE PARK")
        self.assertEqual(tokens['lot'], '7')
        self.assertEqual(tokens['block'], '5')
        self.assertIn('BAY SHORE PARK', tokens['subdivision'])

    def test_absentee_status_out_of_state(self):
        res = determine_absentee_status(
            site_addr="843 62ND AVE S", site_city="ST PETERSBURG", site_zip="33705",
            mail_addr="100 MAIN ST", mail_city="ATLANTA", mail_state="GA", mail_zip="30301",
            has_homestead=False
        )
        self.assertEqual(res['Absentee_Status'], 'Absentee Out-of-State')
        self.assertEqual(res['Is_Absentee'], 'Yes')

    def test_absentee_status_owner_occupied(self):
        res = determine_absentee_status(
            site_addr="843 62ND AVE S", site_city="ST PETERSBURG", site_zip="33705",
            mail_addr="843 62ND AVE S", mail_city="ST PETERSBURG", mail_state="FL", mail_zip="33705",
            has_homestead=True
        )
        self.assertEqual(res['Absentee_Status'], 'Owner Occupied')
        self.assertEqual(res['Is_Absentee'], 'No')

if __name__ == '__main__':
    unittest.main()
