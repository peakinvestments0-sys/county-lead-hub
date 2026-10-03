"""
Comprehensive Test Suite for County Lead Hub Compliance & Engine Fixes
Verifies:
1. Permanent suppression list persistence, lookup, and outbound blocking
2. DNC list scrubbing and pre-touch filtering
3. Mandatory STOP language on initial outreach
4. Opt-out regex coverage and inquiry collision guards
5. First-touch Gemini enhancer bypass (deterministic outreach)
6. Price extraction regex precision without zip code false positives
7. Updated Emma / Peak Investments scripts and zero hyphens rule
"""

import os
import sys
import json
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.seller_bot_engine import (
    SellerBotEngine, DISTRESS_SCRIPTS, is_opt_out_reply, extract_dollar_amount,
    polish_seller_reply_with_gemini
)
from src.suppression_service import (
    normalize_phone_digits, is_number_suppressed, add_to_suppression_list,
    remove_from_suppression_list, load_suppression_list,
    is_dnc_number, add_to_dnc_list, is_lead_blocked_from_outreach, scrub_outbound_lead_list
)


class TestCountyLeadHubCompliance(unittest.TestCase):
    def setUp(self):
        self.bot = SellerBotEngine()
        self.test_lead = {
            "parcel_id": "TEST-UNIT-001",
            "owner_name": "Sarah Connor",
            "property_address": "450 Ocean Dr, Clearwater, FL 33767",
            "phone": "(727) 555-8899",
            "distress_category": "Code Violation",
            "just_value": 260000.0,
            "market_value": 350000.0
        }

    def test_opt_out_regex_coverage(self):
        """Test opt-out patterns catch all requested variations."""
        opt_out_phrases = [
            "stop",
            "Stop.",
            "STOP!",
            "stop texting me",
            "stop calling me",
            "stop messaging me",
            "please stop",
            "quit texting me",
            "quit texting",
            "leave me alone",
            "do not text me",
            "don't text me",
            "do not contact me",
            "dont message me",
            "unsubscribe",
            "opt out",
            "remove me",
            "remove my number",
            "take me off your list",
            "wrong number",
            "lose my number",
            "cease and desist"
        ]
        for phrase in opt_out_phrases:
            self.assertTrue(is_opt_out_reply(phrase), f"Failed to detect opt-out for: '{phrase}'")

    def test_opt_out_inquiry_guards(self):
        """Test that legitimate seller inquiries about removing trash/furniture or stopping by are NOT flagged as opt-out."""
        valid_inquiries = [
            "Can you remove the furniture?",
            "Do you remove old trash and clutter from the house?",
            "Will your team remove the code violations at closing?",
            "Will you stop by tomorrow at 2pm?",
            "Can someone stop in and check the roof?"
        ]
        for inquiry in valid_inquiries:
            self.assertFalse(is_opt_out_reply(inquiry), f"False positive opt-out detected on valid inquiry: '{inquiry}'")

    def test_price_extraction_no_zip_misfires(self):
        """Test that Florida zip codes inside addresses do NOT extract as prices."""
        zip_test_cases = [
            "Tampa 33602",
            "St. Petersburg FL 33701",
            "Clearwater, FL 33756",
            "Orlando 32801",
            "33602",
            "33701",
            "My address is 742 Evergreen Terr, Tampa 33602"
        ]
        for case in zip_test_cases:
            price = extract_dollar_amount(case)
            self.assertIsNone(price, f"Zip code incorrectly extracted as price ({price}) from: '{case}'")

    def test_price_extraction_valid_amounts(self):
        """Test that legitimate price statements extract accurately."""
        price_cases = [
            ("$150k", 150000.0),
            ("220k", 220000.0),
            ("$180,000", 180000.0),
            ("I want 130000", 130000.0),
            ("We are asking 250000", 250000.0),
            ("I will take 175000 cash", 175000.0),
            ("1.5 million", 1500000.0),
            ("$2m", 2000000.0),
            ("Tampa 33602, asking $160k", 160000.0),
            ("bottom dollar is 210000", 210000.0)
        ]
        for text, expected in price_cases:
            price = extract_dollar_amount(text)
            self.assertEqual(price, expected, f"Price extraction failed for '{text}': got {price}, expected {expected}")

    def test_stop_language_on_initial_outreach(self):
        """Test that initial outreach always appends 'Reply STOP to opt out'."""
        outreach = self.bot.generate_initial_outreach(self.test_lead)
        text = outreach.get("suggested_reply", "")
        self.assertIn("Reply STOP to opt out", text, "Initial outreach missing mandatory STOP compliance language")

    def test_enhancer_bypass_on_first_touch(self):
        """Test that first touch opener nodes bypass Gemini rewrite."""
        raw_template = "Hey Sarah, Emma here with Peak Investments. Quick question, are you still the owner over at 450 Ocean Dr? Reply STOP to opt out"
        result = polish_seller_reply_with_gemini(
            node="CASUAL_LOCAL_HOOK",
            template_reply=raw_template,
            lead=self.test_lead,
            inbound_message="Initial inquiry"
        )
        self.assertEqual(result, raw_template, "First-touch node did not bypass Gemini enhancer")

    def test_suppression_list_persistence_and_blocking(self):
        """Test adding a number to suppression list and verifying outbound blocking."""
        test_phone = "7275559922"
        formatted_phone = "(727) 555-9922"
        
        # Clean test number initially
        remove_from_suppression_list(test_phone)
        self.assertFalse(is_number_suppressed(test_phone))

        # Add to suppression
        add_to_suppression_list(formatted_phone, reason="OPT_OUT", lead_info={"owner_name": "Test User"})
        self.assertTrue(is_number_suppressed(test_phone))
        self.assertTrue(is_number_suppressed(formatted_phone))
        self.assertTrue(is_number_suppressed("+17275559922"))

        # Verify blocking check
        is_blocked, reason = is_lead_blocked_from_outreach(formatted_phone)
        self.assertTrue(is_blocked)
        self.assertIn("suppression list", reason.lower())

        # Cleanup
        remove_from_suppression_list(test_phone)
        self.assertFalse(is_number_suppressed(test_phone))

    def test_dnc_scrubbing(self):
        """Test DNC list scrubbing on outbound batches."""
        dnc_phone = "4075551133"
        add_to_dnc_list(dnc_phone, registry_name="FEDERAL_DNC")

        batch = [
            {"owner": "Clean Lead 1", "phone": "7275551111"},
            {"owner": "DNC Lead 2", "phone": "(407) 555-1133"},
            {"owner": "Flagged DNC Lead 3", "phone": "7275552222", "dnc": True}
        ]

        clean_leads, blocked_leads = scrub_outbound_lead_list(batch)
        self.assertEqual(len(clean_leads), 1)
        self.assertEqual(clean_leads[0]["owner"], "Clean Lead 1")
        self.assertEqual(len(blocked_leads), 2)

    def test_script_updates_and_zero_hyphens(self):
        """Verify updated scripts and strict zero hyphens rule for SMS copy."""
        # 1. Casual Local Hook
        casual = DISTRESS_SCRIPTS["CASUAL_LOCAL_HOOK"]
        self.assertIn("Emma here with Peak Investments", casual)
        self.assertIn("{address}", casual)

        # 2. Driveby Hook
        driveby = DISTRESS_SCRIPTS["DRIVEBY_HOOK"]
        self.assertIn("Emma with Peak Investments", driveby)
        self.assertIn("We buy houses as is for cash", driveby)

        # 3. As-Is Hook
        asis = DISTRESS_SCRIPTS["AS_IS_NO_FEES_HOOK"]
        self.assertIn("Emma with Peak Investments", asis)

        # 4. Payoff Script
        payoff = DISTRESS_SCRIPTS["LIS_PENDENS_PAYOFF"]
        self.assertIn("Understood. We can move fast enough to close before the auction date", payoff)
        self.assertIn("What would you need to net to make a move work?", payoff)

        # 5. Dream Price Script (drop emoji)
        dream = DISTRESS_SCRIPTS["UNREALISTIC_DREAM_PRICE"]
        self.assertNotIn("😄", dream)
        self.assertIn("pack my bags today too", dream)

        # 6. Objection How'd You Get My Number
        how_number = DISTRESS_SCRIPTS["OBJ_HOW_DID_YOU_GET_NUMBER"]
        self.assertIn("skip trace service", how_number)
        self.assertIn("county clerk and property appraiser", how_number)

        # 7. Check for forbidden dashes/em-dashes in all distress scripts
        for name, script in DISTRESS_SCRIPTS.items():
            self.assertNotIn("—", script, f"Em-dash found in script '{name}'")
            self.assertNotIn("–", script, f"En-dash found in script '{name}'")
            self.assertNotIn("as-is", script, f"Hyphenated 'as-is' found in script '{name}'")


if __name__ == "__main__":
    unittest.main()
