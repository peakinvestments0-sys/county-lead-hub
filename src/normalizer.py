import re
from typing import Tuple, Dict, Any, List

STREET_SUFFIX_MAP = {
    'STREET': 'ST',
    'STR': 'ST',
    'AVENUE': 'AVE',
    'AV': 'AVE',
    'BOULEVARD': 'BLVD',
    'BL': 'BLVD',
    'BLV': 'BLVD',
    'ROAD': 'RD',
    'DRIVE': 'DR',
    'COURT': 'CT',
    'LANE': 'LN',
    'CIRCLE': 'CIR',
    'CI': 'CIR',
    'CR': 'CIR',
    'PLACE': 'PL',
    'WAY': 'WAY',
    'WA': 'WAY',
    'WY': 'WAY',
    'PARKWAY': 'PKWY',
    'PK': 'PKWY',
    'PKY': 'PKWY',
    'TERRACE': 'TER',
    'TE': 'TER',
    'HIGHWAY': 'HWY',
    'HW': 'HWY',
    'TRAIL': 'TRL',
    'TR': 'TRL',
    'ALLEY': 'ALY',
    'LOOP': 'LOOP',
    'LP': 'LOOP',
    'PASS': 'PASS',
    'RUN': 'RUN',
    'PATH': 'PATH',
    'COVE': 'CV',
    'POINT': 'PT',
    'ISLAND': 'ISL',
    'BEACH': 'BCH',
    'BEND': 'BND',
    'BN': 'BND'
}

DIRECTIONAL_MAP = {
    'NORTH': 'N',
    'SOUTH': 'S',
    'EAST': 'E',
    'WEST': 'W',
    'NORTHEAST': 'NE',
    'NORTHWEST': 'NW',
    'SOUTHEAST': 'SE',
    'SOUTHWEST': 'SW'
}

COMMERCIAL_PATTERNS = [
    r'\bLLC\b', r'\bINC\b', r'\bCORP\b', r'\bLTD\b', r'\bCO\b',
    r'\bLP\b', r'\bLLP\b', r'\bPA\b', r'\bPLLC\b',
    r'\bPROPERTIES\b', r'\bHOLDINGS\b', r'\bINVESTMENTS\b',
    r'\bBANK\b', r'\bASSOCIATION\b', r'\bASSN\b', r'\bCHURCH\b',
    r'\bMANAGEMENT\b', r'\bENTERPRISES\b', r'\bCOMMUNITY\b',
    r'\bVENTURES\b', r'\bCAPITAL\b', r'\bREALTY\b', r'\bSERVICES\b',
    r'\bFOUNDATION\b', r'\bCOUNTY\b', r'\bCITY\s+OF\b'
]

TRUST_PATTERNS = [
    r'\bTRUST\b', r'\bTRUSTEE\b', r'\bTRE\b', r'\bTR\b',
    r'\bREVOCABLE\b', r'\bIRREVOCABLE\b', r'\bLIVING\s+TRUST\b',
    r'\bLIV\s+TRUST\b', r'\bREV\s+TRUST\b', r'\bFAMILY\s+TRUST\b',
    r'\bESTATE\b', r'\bESTATE\s+OF\b'
]

COMMERCIAL_REGEX = re.compile('|'.join(COMMERCIAL_PATTERNS), re.IGNORECASE)
TRUST_REGEX = re.compile('|'.join(TRUST_PATTERNS), re.IGNORECASE)

def is_commercial_entity(name_str: str) -> bool:
    """Detect if name is a commercial business (LLC, Inc, Bank, Realty, etc.)."""
    if not isinstance(name_str, str):
        return False
    return bool(COMMERCIAL_REGEX.search(name_str.upper()))

def is_trust_or_estate(name_str: str) -> bool:
    """Detect if name is a Trust, Trustee, or Probate Estate."""
    if not isinstance(name_str, str):
        return False
    return bool(TRUST_REGEX.search(name_str.upper()))

def clean_text(s: Any) -> str:
    """Generic uppercase text cleaner removing extra whitespace and punctuation."""
    if s is None or (isinstance(s, float) and str(s) == 'nan'):
        return ""
    text = str(s).upper()
    text = re.sub(r'[^\w\s]', ' ', text)
    return ' '.join(text.split())

def normalize_parcel_id(pid: Any) -> str:
    """Normalize parcel numbers by stripping dashes, dots, and spaces."""
    if pid is None or (isinstance(pid, float) and str(pid) == 'nan'):
        return ""
    return re.sub(r'[^A-Z0-9]', '', str(pid).upper())

def normalize_address(address_str: Any) -> str:
    """
    Normalizes street address into a standard format:
    - Uppercase
    - Strips apartment/suite numbers
    - Normalizes street suffixes (STREET -> ST, AVENUE -> AVE)
    - Normalizes directionals (NORTH -> N)
    """
    if not isinstance(address_str, str) or not address_str.strip():
        return ""
    
    addr = address_str.upper().strip()
    
    # Remove unit/apt/suite (# 101, APT 2B, UNIT 304, STE 5)
    addr = re.sub(r'\b(APT|SUITE|STE|UNIT|BLDG|BUILDING|LOT|SPAC|SPC|#)\s*#?\s*[A-Z0-9\-]+', '', addr)
    
    # Remove punctuation
    addr = re.sub(r'[^\w\s]', ' ', addr)
    tokens = addr.split()
    
    normalized_tokens = []
    for t in tokens:
        if t in STREET_SUFFIX_MAP:
            normalized_tokens.append(STREET_SUFFIX_MAP[t])
        elif t in DIRECTIONAL_MAP:
            normalized_tokens.append(DIRECTIONAL_MAP[t])
        else:
            normalized_tokens.append(t)
            
    return ' '.join(normalized_tokens)

def parse_owner_name(owner_str: Any) -> Dict[str, str]:
    """
    Parses owner name string into Clean First Name, Clean Last Name,
    Full Name, Secondary Owner, and Entity Type.
    
    Rules:
    - Commercial Businesses (LLC, Inc, Corp, Bank):
      Leaves First/Last blank, flags as 'Company / LLC'.
    - Trusts & Probate Estates (TRE, TR, Trustee, Family Trust, Rev Trust):
      Flags as 'Trust / Probate', strips trust markers, and extracts human Trustee/Family name!
    - Individuals (Smith, John A):
      Parses First, Last, and Secondary Owner.
    """
    if not isinstance(owner_str, str) or not owner_str.strip():
        return {
            'Clean_First_Name': '',
            'Clean_Last_Name': '',
            'Clean_Full_Name': '',
            'Secondary_Owner': '',
            'Owner_Entity_Type': 'Unknown',
            'Is_Trust_Or_Estate': 'No'
        }
    
    raw = owner_str.strip()
    is_comm = is_commercial_entity(raw)
    is_trust = is_trust_or_estate(raw)
    
    # Clean basic string
    cleaned = re.sub(r'\s+', ' ', raw).strip()
    
    # 1. Standard Commercial Entities (e.g. 3 GIRL PROPERTIES LLC, LAKEVIEW LOAN SERVICING)
    if is_comm and not is_trust:
        return {
            'Clean_First_Name': '',
            'Clean_Last_Name': '',
            'Clean_Full_Name': cleaned.title(),
            'Secondary_Owner': '',
            'Owner_Entity_Type': 'Company / LLC',
            'Is_Trust_Or_Estate': 'No'
        }
    
    # 2. Trusts / Probate Estates (e.g. BUCK, CLIFFORD B TRE, DRISCOLL, DANIEL D JR TRE, SMITH FAMILY TRUST)
    if is_trust:
        # Strip trust words for person extraction
        name_part = re.sub(r'\b(REVOCABLE|IRREVOCABLE|LIVING|LIV|REV|FAMILY|TRUST|TRUSTEE|TRE|TR|ESTATE\s+OF|ESTATE|DECEASED|JR|SR|II|III|IV)\b', '', cleaned, flags=re.IGNORECASE)
        name_part = re.sub(r'[^\w\s,]', ' ', name_part).strip()
        name_part = re.sub(r'\s+', ' ', name_part)
        
        first_name = ""
        last_name = ""
        
        if ',' in name_part:
            parts = name_part.split(',', 1)
            last_name = parts[0].strip().title()
            f_tokens = parts[1].strip().split()
            first_name = f_tokens[0].title() if f_tokens else ""
        else:
            tokens = name_part.split()
            if len(tokens) >= 2:
                last_name = tokens[0].title()
                first_name = tokens[1].title()
            elif len(tokens) == 1:
                last_name = tokens[0].title()
                first_name = ""
                
        # Clean non-alpha
        first_name = re.sub(r'[^A-Za-z]', '', first_name).title()
        last_name = re.sub(r'[^A-Za-z]', '', last_name).title()
        
        full_label = f"{first_name} {last_name} (Trustee)".strip() if first_name else f"{last_name} Trust".strip()
        if not full_label:
            full_label = cleaned.title()
            
        return {
            'Clean_First_Name': first_name,
            'Clean_Last_Name': last_name,
            'Clean_Full_Name': full_label,
            'Secondary_Owner': '',
            'Owner_Entity_Type': 'Trust / Probate',
            'Is_Trust_Or_Estate': 'Yes'
        }
    
    # 3. Individual Owners
    first_name = ""
    last_name = ""
    secondary = ""
    
    # Check for joint owner indicated by & or AND
    joint_split = re.split(r'\s+(?:&|AND)\s+', cleaned, maxsplit=1, flags=re.IGNORECASE)
    primary_part = joint_split[0]
    if len(joint_split) > 1:
        secondary = joint_split[1].strip().title()
        
    # Check if comma is used: "LAST, FIRST MIDDLE"
    if ',' in primary_part:
        parts = primary_part.split(',', 1)
        last_name = parts[0].strip()
        first_tokens = parts[1].strip().split()
        first_name = first_tokens[0] if first_tokens else ""
    else:
        # Florida Clerk format: "LASTNAME FIRSTNAME [MIDDLENAME]"
        tokens = primary_part.split()
        tokens = [t for t in tokens if t.upper() not in ('DECEASED', 'ESTATE', 'OF', 'ET', 'AL', 'TR', 'TRE', 'JR', 'SR', 'II', 'III')]
        
        if len(tokens) == 1:
            last_name = tokens[0]
            first_name = ""
        elif len(tokens) >= 2:
            last_name = tokens[0]
            first_name = tokens[1]
            
    # Clean up non-alphabetics
    first_name = re.sub(r'[^A-Za-z]', '', first_name).title()
    last_name = re.sub(r'[^A-Za-z]', '', last_name).title()
    
    full_name = f"{first_name} {last_name}".strip() if (first_name and last_name) else (first_name or last_name)
    
    return {
        'Clean_First_Name': first_name,
        'Clean_Last_Name': last_name,
        'Clean_Full_Name': full_name,
        'Secondary_Owner': secondary,
        'Owner_Entity_Type': 'Individual',
        'Is_Trust_Or_Estate': 'No'
    }

def normalize_name_for_matching(name_str: Any) -> str:
    """
    Prepares a normalized search key from an owner string for comparison:
    Removes entities, legal suffixes, commas, punctuation, extra whitespace.
    """
    if not isinstance(name_str, str):
        return ""
    s = name_str.upper()
    # Remove entity suffixes
    s = re.sub(r'\b(LLC|INC|CORP|LTD|CO|TRE|TRUST|TRUSTEE|ET\s+AL|ESTATE\s+OF|DECEASED)\b', '', s)
    # Remove punctuation
    s = re.sub(r'[^\w\s]', ' ', s)
    return ' '.join(s.split())

def extract_legal_tokens(legal_str: Any) -> Dict[str, Any]:
    """
    Extracts Lot, Block, Unit, and Subdivision keywords from Florida legal descriptions.
    e.g. 'BAY SHORE PARK BLK 5, LOT 7' or 'LOT 7 BLOCK 5 BAY SHORE PARK' or 'LOT 56 GOLFWOODS'
    """
    if not isinstance(legal_str, str) or not legal_str.strip():
        return {'lot': None, 'block': None, 'unit': None, 'subdivision': ''}
        
    s = legal_str.upper()
    lot_match = re.search(r'\bLOT\s+([A-Z0-9\-]+)\b', s)
    block_match = re.search(r'\b(?:BLK|BLOCK)\s+([A-Z0-9\-]+)\b', s)
    unit_match = re.search(r'\b(?:UNIT|NO|SUITE|APT)\s*(?:NO\s*)?([A-Z0-9\-]+)\b', s)
    
    lot = lot_match.group(1) if lot_match else None
    block = block_match.group(1) if block_match else None
    unit = unit_match.group(1) if unit_match else None
    
    # Clean out lot/block/unit markers to leave substantive subdivision words
    sub_text = re.sub(r'\b(?:LOT|BLK|BLOCK|UNIT|BLDG|BUILDING|NO|CONDOMINIUM|CONDO|PHASE|THE|ADDITION|ADD|OF|A)\b', ' ', s)
    sub_text = re.sub(r'[^\w\s]', ' ', sub_text)
    subdivision_tokens = ' '.join(sub_text.split())
    
    return {
        'lot': lot,
        'block': block,
        'unit': unit,
        'subdivision': subdivision_tokens
    }

def extract_human_defendants(grantee_str: Any) -> List[Dict[str, str]]:
    """
    Parses a combined Clerk Grantee/Defendant cell, filters out institutional entities
    (HOAs, Banks, HUD, Government, Insurance, Mortgage companies, Trusts, fictitious parties),
    and extracts separate clean human First, Last, Middle, and Full Name entries.
    """
    if not isinstance(grantee_str, str) or not grantee_str.strip():
        return []
    
    parts = [p.strip() for p in grantee_str.split(',') if p.strip()]
    results = []
    
    # Institutional & Fictitious Foreclosure placeholders to exclude
    inst_pattern = re.compile(
        r'\b(UNITED STATES|AMERICA|SECRETARY|HOUSING|URBAN|DEVELOPMENT|DEPT|DEPARTMENT|'
        r'HOMEOWNERS|ASSOCIATION|HOA|CONDOMINIUM|CONODMINIUM|CONDO|PROPERTY OWNERS|CIVIC|'
        r'INSURANCE|INSURACE|BROKERS|FINANCE|FINANCIAL|MORTGAGE|LOAN|SERVICING|BANK|BA\s*NK|LENDER|CREDIT|CREDT|'
        r'UNION|PARTNERSHIP|ENTERPRISES|INVESTMENTS|HOLDINGS|COMMUNITY|CLERK|COMMISSIONER|'
        r'COUNTY|STATE OF|CITY OF|TREASURER|REVENUE|DISCOVER|CAPITAL ONE|WELLS FARGO|'
        r'CITIGROUP|TRUIST|SUN\s*TRUST|ONITY|SUNFLO ROOFING|LAWNSHAPER|GOODLEAP|ISPC|MERS|'
        r'UNKNOWN\s+SPOUSE|UNKNOWN\s+TENANT|UNKNOWN\s+PARTY|UNKNOWN\s+PARTIES|UNKNOWN\s+HEIR|UNKNOWN\s+HEIRS|'
        r'UNKNOWN\s+BENEFICIAR|UNKNOWN\s+SUCCESSOR|ANY\s+AND\s+ALL|'
        r'DOE\s+JOHN|DOE\s+JANE|JOHN\s+DOE|JANE\s+DOE)\b',
        re.IGNORECASE
    )
    
    for part in parts:
        cleaned = clean_text(part)
        if not cleaned:
            continue
        if is_commercial_entity(cleaned) or is_trust_or_estate(cleaned) or inst_pattern.search(cleaned):
            continue
            
        tokens = cleaned.split()
        # Single acronym or non-name (like ISPC)
        if len(tokens) == 1 and (len(tokens[0]) <= 4 and tokens[0].isupper()):
            continue
            
        # Humans have 1 to 8 name tokens (handles Hispanic/compound names)
        if not (1 <= len(tokens) <= 8):
            continue
            
        # Parse Florida Clerk format: LAST FIRST [MIDDLE] [SUFFIX]
        suffix = ""
        if tokens[-1] in ('JR', 'SR', 'II', 'III', 'IV'):
            suffix = tokens.pop()
            
        if len(tokens) == 1:
            last = tokens[0].title()
            first = ""
            middle = ""
        elif len(tokens) == 2:
            last = tokens[0].title()
            first = tokens[1].title()
            middle = ""
        else:
            last = tokens[0].title()
            first = tokens[1].title()
            middle = " ".join(tokens[2:]).title()
            
        full_human = f"{first} {last}".strip() if (first and last) else (first or last)
        
        results.append({
            'First_Name': first,
            'Last_Name': last,
            'Middle_Name': middle,
            'Suffix': suffix,
            'Human_Name_Original': part.strip(),
            'Full_Name': full_human
        })
        
    return results

