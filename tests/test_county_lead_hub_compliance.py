"""
Comprehensive Test Suite for County Lead Hub Compliance & Emma Opener Overhaul
Verifies:
1. Permanent suppression list persistence, lookup, and outbound blocking
2. DNC list scrubbing and pre-touch filtering
3. Stage 1 Doorbell Openers with rotating human soft opt-outs (dropping 'Reply STOP')
4. Strict GSM-7 single SMS segment limit (<= 160 characters)
5. Opener-level rejection (instant opt-out & 'Got it, won't text again.') vs mid-conversation scope guard
6. Stage 1 -> Stage 2 Bridge golden replies ('what?', 'who is this?', 'when did we talk?')
7. First-touch Gemini enhancer bypass (deterministic openers)
8. Price extraction regex precision without zip code false positives
9. Script definitions, approved soft opt-out rotation, and zero-hyphen 'as is' rule
"""

import os
import sys
import math
import json
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.seller_bot_engine import (
    SellerBotEngine, DISTRESS_SCRIPTS, SOFT_OPT_OUTS,
    is_opt_out_reply, extract_dollar_amount,
    polish_seller_reply_with_gemini, get_soft_opt_out,
    is_multi_distress_lead, get_lead_area_name
)
from src.suppression_service import (
    normalize_phone_digits, is_number_suppressed, add_to_suppression_list,
    remove_from_suppression_list, load_suppression_list,
    is_dnc_number, add_to_dnc_list, is_lead_blocked_from_outreach, scrub_outbound_lead_list
)


class TestCountyLeadHubCompliance(unittest.TestCase):
    def setUp(self):
        self.bot = SellerBotEngine()
        self.single_list_lead = {
            "parcel_id": "TEST-UNIT-001",
            "owner_name": "Sarah Connor",
            "property_address": "450 Ocean Dr, Clearwater, FL 33767",
            "phone": "(727) 555-8899",
            "distress_category": "Code Violation",
            "distress_count": 1,
            "just_value": 260000.0,
            "market_value": 350000.0
        }
        self.multi_list_lead = {
            "parcel_id": "TEST-UNIT-002",
            "owner_name": "Marcus Wright",
            "property_address": "1200 Sunset Point Rd, Clearwater, FL 33755",
            "phone": "(727) 555-7744",
            "distress_category": "Code Violation",
            "is_stacked_distress": "Yes",
            "distress_count": 2,
            "just_value": 210000.0,
            "market_value": 290000.0
        }

    def test_opt_out_regex_coverage(self):
        """Test opt-out patterns catch all standard and opener-specific rejection phrases."""
        standard_opt_outs = [
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
        for phrase in standard_opt_outs:
            self.assertTrue(is_opt_out_reply(phrase, is_opener_reply=True), f"Failed to detect opt-out for: '{phrase}'")
            self.assertTrue(is_opt_out_reply(phrase, is_opener_reply=False), f"Failed to detect standard opt-out mid-convo for: '{phrase}'")

        # Opener-specific rejection: ANY 'no' to opener is an opt-out
        opener_rejections = [
            "no",
            "No",
            "NO!",
            "nah",
            "nope",
            "not interested",
            "no thanks",
            "no thank you",
            "no way",
            "never",
            "hell no"
        ]
        for phrase in opener_rejections:
            self.assertTrue(is_opt_out_reply(phrase, is_opener_reply=True), f"Failed to detect opener rejection for: '{phrase}'")

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
            self.assertFalse(is_opt_out_reply(inquiry, is_opener_reply=True), f"False positive opt-out detected on valid inquiry: '{inquiry}'")
            self.assertFalse(is_opt_out_reply(inquiry, is_opener_reply=False), f"False positive opt-out detected on valid inquiry: '{inquiry}'")

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

    def test_soft_opt_out_language_and_single_segment_limit(self):
        """
        Verify Emma Stage 1 Doorbell Openers:
        1. 'Reply STOP to opt out' is dropped entirely.
        2. Exactly one of the 3 approved human soft opt-outs is attached.
        3. Multi-list lead generates OPENER_MULTI_LIST.
        4. Single-list lead generates OPENER_SINGLE_LIST.
        5. Every opener is under 160 characters (GSM-7 single SMS segment).
        """
        # Test Forced Multi-List Lead
        outreach_multi = self.bot.generate_initial_outreach(self.multi_list_lead, forced_angle="multi_list")
        text_multi = outreach_multi.get("suggested_reply", "")
        self.assertNotIn("Reply STOP to opt out", text_multi, "Old 'Reply STOP' phrase found in multi-list outreach")
        self.assertIn("did you ever decide what you're doing with", text_multi, "Multi-list opener missing target hook")
        has_soft_opt_multi = any(opt in text_multi for opt in SOFT_OPT_OUTS)
        self.assertTrue(has_soft_opt_multi, f"No approved soft opt-out found in: '{text_multi}'")
        self.assertLessEqual(len(text_multi), 160, f"Multi-list opener exceeds 160 char limit: ({len(text_multi)} chars)")

        # Test Forced Single-List Lead
        outreach_single = self.bot.generate_initial_outreach(self.single_list_lead, forced_angle="single_list")
        text_single = outreach_single.get("suggested_reply", "")
        self.assertNotIn("Reply STOP to opt out", text_single, "Old 'Reply STOP' phrase found in single-list outreach")
        self.assertIn("quick question on", text_single, "Single-list opener missing target hook")
        has_soft_opt_single = any(opt in text_single for opt in SOFT_OPT_OUTS)
        self.assertTrue(has_soft_opt_single, f"No approved soft opt-out found in: '{text_single}'")
        self.assertLessEqual(len(text_single), 160, f"Single-list opener exceeds 160 char limit: ({len(text_single)} chars)")

        # Test Unforced Generation: must be <= 160 chars and contain an approved soft opt-out
        for _ in range(10):
            out_auto = self.bot.generate_initial_outreach(self.single_list_lead)
            t_auto = out_auto.get("suggested_reply", "")
            self.assertNotIn("Reply STOP", t_auto)
            self.assertTrue(any(opt in t_auto for opt in SOFT_OPT_OUTS))
            self.assertLessEqual(len(t_auto), 160)

        # Test all 3 tiers with all 3 soft opt-outs across various address lengths
        openers = [
            DISTRESS_SCRIPTS["OPENER_MULTI_LIST"],
            DISTRESS_SCRIPTS["OPENER_SINGLE_LIST"],
            DISTRESS_SCRIPTS["OPENER_ULTRA_SHORT"]
        ]
        sample_first_name = "Christopher"
        sample_address = "450 Ocean Dr"

        for opener in openers:
            base = opener.format(first_name=sample_first_name, address=sample_address)
            for soft_opt in SOFT_OPT_OUTS:
                full_msg = f"{base} {soft_opt}"
                self.assertLessEqual(len(full_msg), 160, f"Opener + soft opt-out exceeds 160 chars ({len(full_msg)} chars): '{full_msg}'")

    def test_opener_opt_out_vs_mid_convo_scope_guard(self):
        """
        Verify Engine Rule & Scope Guard:
        - Any 'no' to the initial opener = instant opt-out ('Got it, won't text again.' + permanent suppression).
        - Mid-conversation 'no' (e.g. after price negotiation) is an objection to work, NOT an opt-out.
        """
        test_phone = "(727) 555-4321"
        remove_from_suppression_list(test_phone)
        lead_with_phone = dict(self.single_list_lead)
        lead_with_phone["phone"] = test_phone

        # 1. First-touch rejection to opener -> OPT_OUT
        result_opener = self.bot.process_inbound_sms(
            lead=lead_with_phone,
            inbound_text="no",
            conversation_history=[]
        )
        self.assertEqual(result_opener.get("action"), "OPT_OUT")
        self.assertEqual(result_opener.get("suggested_reply"), "Got it, won't text again.")
        self.assertTrue(is_number_suppressed(test_phone), "Phone was not suppressed after opener rejection")

        remove_from_suppression_list(test_phone)

        # 2. Mid-conversation rejection (e.g. 3 messages deep into negotiation)
        convo_history = [
            {"direction": "OUTBOUND", "message": "Hey Sarah, quick question on 450 Ocean Dr, got a sec?"},
            {"direction": "INBOUND", "message": "Who is this?"},
            {"direction": "OUTBOUND", "message": "Emma, I work with a local investment group buying in Clearwater."},
            {"direction": "INBOUND", "message": "What are you offering?"},
            {"direction": "OUTBOUND", "message": "Would you consider $200k cash?"}
        ]
        result_mid_convo = self.bot.process_inbound_sms(
            lead=lead_with_phone,
            inbound_text="no",
            conversation_history=convo_history
        )
        self.assertNotEqual(result_mid_convo.get("action"), "OPT_OUT", "Mid-conversation 'no' was incorrectly classified as OPT_OUT")
        self.assertIn("bottom dollar number", result_mid_convo.get("suggested_reply", ""), "Mid-convo 'no' did not work the objection")
        self.assertFalse(is_number_suppressed(test_phone), "Phone was incorrectly suppressed on mid-convo negotiation 'no'")

    def test_stage_1_to_stage_2_bridges(self):
        """
        Verify Emma Stage 1 -> Stage 2 bridge replies for confused curiosity:
        - 'what?' / 'excuse me?' -> Identifies Emma & confirms ownership.
        - 'which one were you?' / 'when did we talk?' -> 'We haven't talked — sorry...'
        - 'who is this?' -> Identifies Emma & local investment group.
        - 'wrong number' -> Opt-out ('Got it, won't text again.').
        """
        lead = self.single_list_lead
        phone = lead["phone"]

        # Bridge 1: "what?"
        res_what = self.bot.process_inbound_sms(
            lead=lead,
            inbound_text="what?",
            conversation_history=[]
        )
        self.assertEqual(res_what.get("node"), "BRIDGE_WHAT_EXCUSE_ME")
        self.assertIn("It's Emma", res_what.get("suggested_reply", ""))
        self.assertIn("Clearwater", res_what.get("suggested_reply", ""))
        self.assertIn("450 Ocean Dr", res_what.get("suggested_reply", ""))

        # Bridge 2: "who is this?"
        res_who = self.bot.process_inbound_sms(
            lead=lead,
            inbound_text="who is this?",
            conversation_history=[]
        )
        self.assertEqual(res_who.get("node"), "BRIDGE_WHO_IS_THIS")
        self.assertIn("Emma, I work with a local investment group", res_who.get("suggested_reply", ""))
        self.assertIn("Not a realtor, no listings", res_who.get("suggested_reply", ""))

        # Bridge 3: "when did we talk?" / "which one were you?"
        res_when = self.bot.process_inbound_sms(
            lead=lead,
            inbound_text="when did we talk?",
            conversation_history=[]
        )
        self.assertEqual(res_when.get("node"), "BRIDGE_WHEN_DID_WE_TALK")
        self.assertIn("We haven't talked — sorry, should've led with that", res_when.get("suggested_reply", ""))

        # Bridge 4: "wrong number" -> opt-out
        res_wrong = self.bot.process_inbound_sms(
            lead=lead,
            inbound_text="wrong number",
            conversation_history=[]
        )
        self.assertEqual(res_wrong.get("action"), "OPT_OUT")
        self.assertEqual(res_wrong.get("suggested_reply"), "Got it, won't text again.")
        self.assertTrue(is_number_suppressed(phone))
        remove_from_suppression_list(phone)

    def test_enhancer_bypass_on_first_touch(self):
        """Test that first touch opener nodes bypass Gemini rewrite."""
        opener_nodes = [
            "OPENER_MULTI_LIST",
            "OPENER_SINGLE_LIST",
            "OPENER_ULTRA_SHORT",
            "CASUAL_LOCAL_HOOK"
        ]
        sample_template = "Hey Sarah, quick question on 450 Ocean Dr, got a sec? If I'm bothering you just say no and I won't text you no more."
        for node in opener_nodes:
            result = polish_seller_reply_with_gemini(
                node=node,
                template_reply=sample_template,
                lead=self.single_list_lead,
                inbound_message="Initial inquiry"
            )
            self.assertEqual(result, sample_template, f"Opener node '{node}' did not bypass Gemini enhancer")

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

    def test_script_definitions_and_zero_hyphen_as_is(self):
        """Verify updated script definitions, approved soft opt-out lines, and zero-hyphen 'as is' rule."""
        # 1. Stage 1 Openers
        self.assertIn("OPENER_MULTI_LIST", DISTRESS_SCRIPTS)
        self.assertIn("OPENER_SINGLE_LIST", DISTRESS_SCRIPTS)
        self.assertIn("OPENER_ULTRA_SHORT", DISTRESS_SCRIPTS)
        self.assertEqual(DISTRESS_SCRIPTS["OPENER_MULTI_LIST"], "Hey {first_name} — did you ever decide what you're doing with {address}?")
        self.assertEqual(DISTRESS_SCRIPTS["OPENER_SINGLE_LIST"], "Hey {first_name}, quick question on {address}, got a sec?")
        self.assertEqual(DISTRESS_SCRIPTS["OPENER_ULTRA_SHORT"], "Hey {first_name}?")

        # 2. Opt-Out Confirmation
        self.assertEqual(DISTRESS_SCRIPTS["OPT_OUT_CONFIRMATION"], "Got it, won't text again.")

        # 3. Approved Soft Opt-Outs (Exact 3 Lines)
        self.assertEqual(len(SOFT_OPT_OUTS), 3)
        self.assertIn("If I'm bothering you just say no and I won't text you no more.", SOFT_OPT_OUTS)
        self.assertIn("If you don't want these texts just say the word and I'm gone.", SOFT_OPT_OUTS)
        self.assertIn("Not interested? Just say no and I'll drop it.", SOFT_OPT_OUTS)

        # 4. Bridge Golden Scripts
        self.assertIn("It's Emma — I help homeowners in {area} figure out their options on {address}", DISTRESS_SCRIPTS["BRIDGE_WHAT_EXCUSE_ME"])
        self.assertIn("We haven't talked — sorry, should've led with that", DISTRESS_SCRIPTS["BRIDGE_WHEN_DID_WE_TALK"])
        self.assertIn("Emma, I work with a local investment group buying in {area}", DISTRESS_SCRIPTS["BRIDGE_WHO_IS_THIS"])

        # 5. Zero-hyphen 'as is' rule: check that 'as-is' is never hyphenated in script copy
        for name, script in DISTRESS_SCRIPTS.items():
            self.assertNotIn("as-is", script, f"Hyphenated 'as-is' found in script '{name}'")


if __name__ == "__main__":
    unittest.main()
