"""
Scout Operator & Sentinel Agent Test Suite
Verifies:
1. Sentinel Status endpoint (HEALTHY, 37 counties, lead counts)
2. Executive Briefing compilation across counties
3. Statewide Columnar Cross-Query latency & multi-distress filtering
4. Natural Language Dispatcher & Chat routing
"""

import unittest
import urllib.request
import json

class TestScoutAgent(unittest.TestCase):
    def test_scout_sentinel_status(self):
        res = urllib.request.urlopen("http://127.0.0.1:8505/api/scout/status")
        self.assertEqual(res.status, 200)
        data = json.loads(res.read().decode())
        self.assertEqual(data.get("sentinel_status"), "HEALTHY")
        self.assertEqual(data.get("total_counties"), 37)
        self.assertGreater(data.get("total_active_leads", 0), 50000)

    def test_scout_briefing(self):
        res = urllib.request.urlopen("http://127.0.0.1:8505/api/scout/briefing?counties=Orange,Hillsborough")
        self.assertEqual(res.status, 200)
        data = json.loads(res.read().decode())
        self.assertEqual(data.get("status"), "success")
        self.assertIn("briefing_markdown", data)
        self.assertGreater(len(data.get("top_opportunities", [])), 0)

    def test_scout_cross_query(self):
        payload = json.dumps({"filter_type": "stacked", "max_records": 50}).encode()
        req = urllib.request.Request("http://127.0.0.1:8505/api/scout/cross-query", data=payload, headers={"Content-Type": "application/json"})
        res = urllib.request.urlopen(req)
        self.assertEqual(res.status, 200)
        data = json.loads(res.read().decode())
        self.assertGreater(data.get("total_matches", 0), 5000)
        # Verify warm cache sub-second response time
        req2 = urllib.request.Request("http://127.0.0.1:8505/api/scout/cross-query", data=payload, headers={"Content-Type": "application/json"})
        res2 = urllib.request.urlopen(req2)
        data2 = json.loads(res2.read().decode())
        self.assertLess(data2.get("elapsed_ms", 9999), 1000) # Sub-second execution on warm cache

    def test_scout_chat_status(self):
        payload = json.dumps({"message": "What is the system health?"}).encode()
        req = urllib.request.Request("http://127.0.0.1:8505/api/scout/chat", data=payload, headers={"Content-Type": "application/json"})
        res = urllib.request.urlopen(req)
        self.assertEqual(res.status, 200)
        data = json.loads(res.read().decode())
        self.assertEqual(data.get("action"), "status")

    def test_scout_chat_multi_county_query(self):
        payload = json.dumps({"message": "Show me all triple distress leads in Orange and Hillsborough"}).encode()
        req = urllib.request.Request("http://127.0.0.1:8505/api/scout/chat", data=payload, headers={"Content-Type": "application/json"})
        res = urllib.request.urlopen(req)
        self.assertEqual(res.status, 200)
        data = json.loads(res.read().decode())
        self.assertEqual(data.get("action"), "leads_query")
        self.assertGreater(data.get("total_matches", 0), 1000)

if __name__ == "__main__":
    unittest.main()
