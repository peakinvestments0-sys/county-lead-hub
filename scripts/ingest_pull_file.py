"""Small bridge from chokidar to the same loader used by the Load List button."""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    # Importing the server does not run FastAPI startup or SMS/email workers.
    from server import read_lead_upload, match_lead_dataframe, load_county_portals
    from src.inbound_pull import ingest_pull_file
    path = Path(sys.argv[1])
    metadata = {'filename': path.name, 'list_type': 'unknown', 'county': 'unknown'}
    try:
        counties = load_county_portals()
        result = ingest_pull_file(path, read_lead_upload, match_lead_dataframe, counties)
        print('INBOUND_RESULT=' + json.dumps(result), flush=True)
    except Exception as exc:
        message = getattr(exc, 'detail', None) or str(exc)
        print('INBOUND_RESULT=' + json.dumps({**metadata, **getattr(exc, 'pull_metadata', {}), 'error': message}), flush=True)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
