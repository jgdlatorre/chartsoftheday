#!/usr/bin/env python3
"""
inject_notes.py — Merge notes_35.json into the 35 setup_*.json files in samples_with_notes/.

Usage:
    python3 inject_notes.py --notes notes_35.json --samples-dir cotd_notebook/samples_with_notes/ [--dry-run]

Looks up each setup by setup_num, finds the matching setup_NN_*.json file,
and overwrites its pedagogical_notes field. Keeps everything else intact.

Validates:
- Both files have same setup_num
- Both files have same symbol (sanity check)
- After merge, the injected field has the expected shape {tooltip, holistic} with es/en/zh

Fails loud if any setup_NN file is missing or mismatches.
"""

import argparse
import json
import re
import sys
from pathlib import Path


def load_notes(notes_path):
    """Load the generated notes. Returns dict keyed by setup_num."""
    data = json.load(open(notes_path))
    return {s['setup_num']: s for s in data['setups']}


def find_setup_files(samples_dir):
    """Returns dict keyed by setup_num → Path."""
    files = {}
    for p in Path(samples_dir).glob('setup_*.json'):
        m = re.match(r'setup_(\d+)_', p.name)
        if m:
            files[int(m.group(1))] = p
    return files


def validate_shape(notes):
    """Check the notes dict has the expected shape."""
    if not isinstance(notes, dict):
        return f"not a dict (got {type(notes).__name__})"
    for variant in ('tooltip', 'holistic'):
        if variant not in notes:
            return f"missing '{variant}'"
        if not isinstance(notes[variant], dict):
            return f"'{variant}' not a dict"
        for lang in ('es', 'en', 'zh'):
            txt = notes[variant].get(lang)
            if not txt or not isinstance(txt, str) or not txt.strip():
                return f"'{variant}.{lang}' empty or invalid"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--notes', required=True, help='Path to notes_35.json')
    ap.add_argument('--samples-dir', required=True, help='Directory with setup_NN_*.json files')
    ap.add_argument('--dry-run', action='store_true', help='Print what would change, do not write')
    args = ap.parse_args()

    notes_path = Path(args.notes)
    samples_dir = Path(args.samples_dir)

    if not notes_path.exists():
        print(f"ERROR: notes file not found: {notes_path}", file=sys.stderr)
        sys.exit(1)
    if not samples_dir.is_dir():
        print(f"ERROR: samples dir not found: {samples_dir}", file=sys.stderr)
        sys.exit(1)

    notes_by_num = load_notes(notes_path)
    files_by_num = find_setup_files(samples_dir)

    missing_in_files = set(notes_by_num.keys()) - set(files_by_num.keys())
    missing_in_notes = set(files_by_num.keys()) - set(notes_by_num.keys())

    if missing_in_files:
        print(f"ERROR: {len(missing_in_files)} setups in notes have no matching file: {sorted(missing_in_files)}", file=sys.stderr)
        sys.exit(1)
    if missing_in_notes:
        print(f"WARNING: {len(missing_in_notes)} files have no matching notes (will skip): {sorted(missing_in_notes)}")

    print(f"Will process {len(notes_by_num)} setups.")
    if args.dry_run:
        print("DRY RUN — no files will be written.\n")

    summary = []
    for num in sorted(notes_by_num.keys()):
        note_entry = notes_by_num[num]
        file_path = files_by_num[num]

        # Load existing JSON
        try:
            existing = json.load(open(file_path))
        except Exception as e:
            print(f"ERROR: setup {num:02d} failed to parse {file_path.name}: {e}", file=sys.stderr)
            sys.exit(1)

        # Sanity: symbol should match
        existing_symbol = existing.get('symbol')
        note_symbol = note_entry.get('symbol')
        if existing_symbol and note_symbol and existing_symbol != note_symbol:
            print(f"ERROR: setup {num:02d} symbol mismatch: file={existing_symbol} notes={note_symbol}", file=sys.stderr)
            sys.exit(1)

        # Validate shape of generated notes
        err = validate_shape(note_entry['pedagogical_notes'])
        if err:
            print(f"ERROR: setup {num:02d} bad notes shape: {err}", file=sys.stderr)
            sys.exit(1)

        # Show diff
        before = existing.get('pedagogical_notes')
        after = note_entry['pedagogical_notes']
        before_state = type(before).__name__ if before is not None else 'absent'
        after_tooltip_es = after['tooltip']['es'][:50]

        summary.append({
            'num': num,
            'file': file_path.name,
            'symbol': existing_symbol,
            'before': before_state,
            'tooltip_es': after_tooltip_es,
        })

        if not args.dry_run:
            # Merge & write
            existing['pedagogical_notes'] = after
            out_text = json.dumps(existing, indent=2, ensure_ascii=False)
            file_path.write_text(out_text, encoding='utf-8')

    # Report
    print(f"\n{'ACTION':<8} {'#':<3} {'SYMBOL':<10} {'BEFORE':<12} TOOLTIP_ES (preview)")
    print('-' * 90)
    for s in summary:
        action = 'DRY' if args.dry_run else 'WROTE'
        print(f"{action:<8} {s['num']:02d}  {s['symbol']:<10} {s['before']:<12} {s['tooltip_es']}")

    if args.dry_run:
        print(f"\nDRY RUN complete. {len(summary)} files would be updated.")
        print("Run without --dry-run to apply.")
    else:
        print(f"\n✓ Wrote {len(summary)} files.")


if __name__ == '__main__':
    main()
