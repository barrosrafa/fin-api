"""Export contracts without connecting to application dependencies."""
import json
from pathlib import Path
from app.main import create_app

if __name__ == '__main__':
    target = Path(__file__).resolve().parents[1] / 'contracts/openapi.json'
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(create_app().openapi(), ensure_ascii=False, indent=2) + '\n')
    print('OpenAPI contract exported.')
