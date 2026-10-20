"""One initial SMS template set shared by every county and outreach entry point."""
from copy import deepcopy
import json
from pathlib import Path

TEMPLATE_IDS = ('casual_direct', 'quick_question', 'neighbor_investor', 'quick_checkin')
LEGACY_TEMPLATE_IDS = {'multi_list': 'casual_direct', 'single_list': 'quick_question',
                       'ultra_short': 'neighbor_investor', 'cash_offer': 'casual_direct'}
TEMPLATES_FILE = Path(__file__).resolve().parents[1] / 'data' / 'outreach_templates.json'
OWNER_CHECK_BODIES = (
    "Hello, I'm trying to locate the property owner of {Address}. Would that be you?",
    "Hi, I'm looking for the homeowner at {Address}. Is that you?",
    "Hello, is this the right person to reach about ownership of {Address}?",
    "Hi there, I'm trying to get in touch with the owner of {Address}. Are you the owner?",
)
DEFAULT_SMS_TEMPLATES = [
    {'id': template_id, 'name': f'Owner Check {i}', 'category': 'owner_check', 'body': body}
    for i, (template_id, body) in enumerate(zip(TEMPLATE_IDS, OWNER_CHECK_BODIES), 1)
]


def load_initial_sms_templates(document=None):
    if document is None:
        try:
            document = json.loads(TEMPLATES_FILE.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            document = {}
    if not isinstance(document, dict):
        document = {}
    rows = document.get('sms') or []
    configured = {t.get('id'): t for t in rows if isinstance(t, dict)} if isinstance(rows, list) else {}
    templates = []
    for default in DEFAULT_SMS_TEMPLATES:
        template = deepcopy(default)
        custom = configured.get(default['id'], {})
        if str(custom.get('body') or '').strip():
            template.update(custom)
        templates.append(template)
    return templates
