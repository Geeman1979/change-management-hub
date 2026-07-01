"""Analytics processing utilities for statistics data."""

import json
import csv
import io


def parse_stat_file(filepath):
    """Parse an uploaded statistics file and return structured data."""
    ext = filepath.rsplit('.', 1)[-1].lower() if '.' in filepath else ''
    
    if ext == 'csv':
        return _parse_csv(filepath)
    elif ext == 'json':
        return _parse_json(filepath)
    elif ext == 'txt':
        return _parse_txt(filepath)
    else:
        return {'error': f'Unsupported file type: .{ext}', 'headers': [], 'rows': []}


def _parse_csv(filepath):
    """Parse a CSV file into structured data."""
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            content = f.read()
    except UnicodeDecodeError:
        with open(filepath, 'r', encoding='latin-1') as f:
            content = f.read()

    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)
    headers = reader.fieldnames if reader.fieldnames else []

    # Also return raw text for AI
    raw_text = content[:5000]

    return {
        'headers': headers,
        'rows': rows[:200],  # Limit rows
        'row_count': len(rows),
        'raw_text': raw_text,
        'error': None
    }


def _parse_json(filepath):
    """Parse a JSON file into structured data."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return {'error': str(e), 'headers': [], 'rows': []}

    # Normalise to list of dicts
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        # Could be { "data": [...], "meta": {...} }
        for key in ['data', 'results', 'values', 'items', 'records']:
            if key in data and isinstance(data[key], list):
                rows = data[key]
                break
        else:
            rows = [data]
    else:
        return {'error': 'Unrecognised JSON structure', 'headers': [], 'rows': []}

    headers = list(rows[0].keys()) if rows else []
    raw_text = json.dumps(rows[:50], indent=2)

    return {
        'headers': headers,
        'rows': rows[:200],
        'row_count': len(rows),
        'raw_text': raw_text,
        'error': None
    }


def _parse_txt(filepath):
    """Parse a tab/space-delimited text file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
    except UnicodeDecodeError:
        with open(filepath, 'r', encoding='latin-1') as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]

    if not lines:
        return {'error': 'Empty file', 'headers': [], 'rows': []}

    # Try to detect delimiter
    first = lines[0]
    if '\t' in first:
        delimiter = '\t'
    elif '|' in first:
        delimiter = '|'
    elif ',' in first:
        delimiter = ','
    else:
        delimiter = None

    if delimiter:
        headers = [h.strip() for h in lines[0].split(delimiter)]
        rows = []
        for line in lines[1:]:
            vals = [v.strip() for v in line.split(delimiter)]
            row = {}
            for i, h in enumerate(headers):
                row[h] = vals[i] if i < len(vals) else ''
            rows.append(row)
    else:
        # Plain text — return as raw
        headers = ['content']
        rows = [{'content': line} for line in lines]

    raw_text = '\n'.join(lines[:100])

    return {
        'headers': headers,
        'rows': rows[:200],
        'row_count': len(rows),
        'raw_text': raw_text,
        'error': None
    }


def compute_summary_stats(parsed_data):
    """Compute basic summary statistics from parsed data."""
    rows = parsed_data.get('rows', [])
    headers = parsed_data.get('headers', [])

    if not rows or not headers:
        return {}

    numeric_cols = []
    for h in headers:
        vals = []
        for row in rows:
            v = row.get(h, '')
            try:
                vals.append(float(v.replace('%', '').replace(',', '').strip()))
            except (ValueError, AttributeError):
                pass
        if vals:
            numeric_cols.append({
                'column': h,
                'min': min(vals),
                'max': max(vals),
                'avg': round(sum(vals) / len(vals), 2),
                'sum': round(sum(vals), 2),
                'count': len(vals)
            })

    return {
        'numeric_columns': numeric_cols,
        'total_rows': len(rows),
        'total_columns': len(headers),
        'columns': headers
    }
