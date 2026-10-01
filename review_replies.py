'''Check chat replies to review chunks, then write the approved ones into sync.bible.

    python review_replies.py check   [--sync-bible ../sync.bible]
    python review_replies.py apply   [--sync-bible ../sync.bible]

Replies are saved by hand into review_replies/pending/. `check` validates every verse line in
them and writes a report next to each reply (<reply>.check.md) showing the current and
proposed tags side by side. After checking a reply (and editing or deleting any lines you
disagree with), move it into review_replies/approved/. `apply` re-validates the approved
replies, writes their verses into sync.bible's NMV_strongs.json, adds the verses to
retag/locked_verses.txt and moves the replies to review_replies/applied/.

See review_replies/README.md.'''
import argparse
import datetime
import json
import os
import shutil
import sys

from make_review_chunks import gloss, original_lines, persian_text, plain
from retag import data, manual, original, persian

ROOT = os.path.join(data.REPO, 'review_replies')
PENDING = os.path.join(ROOT, 'pending')
APPROVED = os.path.join(ROOT, 'approved')
APPLIED = os.path.join(ROOT, 'applied')
REPORT_SUFFIX = '.check.md'


class Proposal:
    def __init__(self, path, line, ref, entries):
        self.path, self.line, self.ref, self.entries = path, line, ref, entries
        self.key = None
        self.errors = []

    def where(self):
        return f'{os.path.basename(self.path)}, line {self.line} ({self.ref})'


def reply_files(folder):
    if not os.path.isdir(folder):
        return []
    return sorted(os.path.join(folder, n) for n in os.listdir(folder)
                  if not n.startswith('.') and not n.endswith(REPORT_SUFFIX) and n != 'README.md'
                  and os.path.isfile(os.path.join(folder, n)))


def parse_reply(path):
    '''Verse lines in a saved reply: any line that is a JSON object with "ref" and "entries".'''
    proposals, problems = [], []
    with open(path, encoding='utf8') as f:
        for n, line in enumerate(f, 1):
            text = line.strip()
            if not text.startswith('{'):
                continue
            try:
                obj = json.loads(text)
            except json.JSONDecodeError as error:
                problems.append(f'{os.path.basename(path)}, line {n}: not valid JSON ({error.msg})')
                continue
            if not isinstance(obj, dict) or 'ref' not in obj or 'entries' not in obj:
                problems.append(f'{os.path.basename(path)}, line {n}: needs "ref" and "entries"')
                continue
            proposals.append(Proposal(path, n, str(obj['ref']), obj['entries']))
    return proposals, problems


class Context:
    def __init__(self, sync_bible):
        paths = data.sync_bible_paths(sync_bible)
        self.nmv_path = paths['nmv_strongs']
        self.grid = data.load_token_grid()
        self.accented = data.load_bible(paths['accented'])
        self.nmv = data.load_bible(self.nmv_path)
        self.current = data.align_to_grid(self.nmv, self.grid)
        missing = set(self.grid) - set(self.current)
        if missing:
            raise SystemExit(f'{len(missing)} verses are missing from {self.nmv_path}; '
                             'run python -m retag run first.')
        self.locked = manual.read_locked(self.grid)
        self.dictionary = data.load_json(os.path.join(sync_bible, 'public', 'data', 'strongsDictionary.json'))

    def original(self, key):
        book, ci, vi = key
        try:
            return self.accented[book][ci][vi]
        except (KeyError, IndexError):
            return []


def validate(p, ctx):
    '''Fill p.key and p.errors.'''
    try:
        keys = data.parse_references(p.ref, ctx.grid)
    except ValueError as error:
        p.errors.append(str(error))
        return
    if len(keys) != 1:
        p.errors.append('"ref" must name a single verse')
        return
    p.key = keys[0]
    if p.key in ctx.locked:
        p.errors.append('already hand-reviewed (in retag/locked_verses.txt); change it in the app instead')

    entries = p.entries
    if not isinstance(entries, list) or not all(
            isinstance(e, list) and len(e) in (1, 2) and all(isinstance(x, str) for x in e) for e in entries):
        p.errors.append('"entries" must be a list of ["word"] or ["word", "numbers"]')
        return

    tokens = [t for e in entries for t in e[0].split(' ')]
    expected = ctx.grid[p.key]
    if tokens != expected:
        first = next((i for i, (a, b) in enumerate(zip(tokens, expected)) if a != b), min(len(tokens), len(expected)))
        got = tokens[first] if first < len(tokens) else '(nothing)'
        want = expected[first] if first < len(expected) else '(nothing)'
        p.errors.append(f'Persian words differ from the verse at word {first + 1}: got "{got}", expected "{want}"')
        return

    lemmas = {l for _, l in original.morphemes(ctx.original(p.key))}
    for n, entry in enumerate(entries, 1):
        words = entry[0].split(' ')
        tags = entry[1].split() if len(entry) > 1 else []
        if len(entry) > 1 and not tags:
            p.errors.append(f'entry {n} "{entry[0]}": empty tag; use ["{entry[0]}"] for an untagged word')
        if len(words) > 1 and any(persian.is_punctuation(w) for w in words):
            p.errors.append(f'entry {n} "{entry[0]}": a group cannot include punctuation')
        if tags and all(persian.is_punctuation(w) for w in words):
            p.errors.append(f'entry {n} "{entry[0]}": punctuation cannot be tagged')
        for tag in tags:
            if tag not in lemmas:
                p.errors.append(f'entry {n} "{entry[0]}": {tag} is not a Strong\'s number in this verse')
        if len(set(tags)) != len(tags):
            p.errors.append(f'entry {n} "{entry[0]}": repeated number')


def load_and_validate(files, ctx):
    proposals, problems = [], []
    for path in files:
        found, bad = parse_reply(path)
        problems += bad
        if not found and not bad:
            problems.append(f'{os.path.basename(path)}: no verse lines found')
        for p in found:
            validate(p, ctx)
        proposals += found
    seen = {}
    for p in proposals:
        if p.key and p.key in seen:
            p.errors.append(f'same verse also proposed in {seen[p.key].where()}')
        elif p.key:
            seen[p.key] = p
    return proposals, problems


def tag_text(tags, ctx):
    return '; '.join(f'{t} {gloss(t, ctx.dictionary, limit=30)}' for t in tags.split()) if tags else ''


def report_verse(p, ctx):
    current = ctx.current[p.key]
    tokens = ctx.grid[p.key]
    cur_rows = [(e[0], data.entry_tags(e) or '') for e in current for _ in e[0].split(' ')]
    new_rows = [(e[0], e[1] if len(e) > 1 else '') for e in p.entries for _ in e[0].split(' ')]
    changed = sum(c != n for c, n in zip(cur_rows, new_rows))
    out = [f'### {data.reference(p.key)}: {changed} word(s) changed', '',
           f'Reply line {p.line}.', '',
           'Original: ' + ' '.join(plain(w[0]) for w in ctx.original(p.key)),
           '', 'Persian: ' + persian_text(current), '', 'Original words:']
    out += original_lines(ctx.original(p.key), ctx.dictionary)
    out += ['', '| | Persian | Now | Proposed |', '| --- | --- | --- | --- |']
    for token, (c_text, c_tags), (n_text, n_tags) in zip(tokens, cur_rows, new_rows):
        mark = '✱' if (c_text, c_tags) != (n_text, n_tags) else ''
        c_label = (f'[{c_text}] ' if ' ' in c_text else '') + (tag_text(c_tags, ctx) if mark else c_tags)
        n_label = (f'[{n_text}] ' if ' ' in n_text else '') + (tag_text(n_tags, ctx) if mark else n_tags)
        out.append(f'| {mark} | {token} | {c_label} | {n_label} |')
    out.append('')
    return out, changed


def check(args):
    ctx = Context(args.sync_bible)
    total_errors = 0
    for folder in (PENDING, APPROVED):
        for path in reply_files(folder):
            proposals, problems = load_and_validate([path], ctx)
            lines = [f'# Check of {os.path.basename(path)}', '',
                     f'Generated {datetime.date.today().isoformat()} by `python review_replies.py check`. '
                     'Rows marked ✱ change. Edit or delete lines in the reply to change what is applied, '
                     'then run check again.', '']
            errors = problems + [f'{p.where()}: {e}' for p in proposals for e in p.errors]
            if errors:
                lines += ['## Problems (fix these in the reply before applying)', '']
                lines += [f'- {e}' for e in errors] + ['']
            ok = [p for p in proposals if not p.errors]
            unchanged = []
            body = []
            for p in ok:
                verse_lines, changed = report_verse(p, ctx)
                if changed:
                    body += verse_lines
                else:
                    unchanged.append(data.reference(p.key))
            if unchanged:
                lines += [f'No change from the current tags (will be skipped): {", ".join(unchanged)}.', '']
            lines += [f'## {len(ok) - len(unchanged)} verse(s) with changes', ''] + body
            with open(path + REPORT_SUFFIX, 'w', encoding='utf8') as f:
                f.write('\n'.join(lines))
            total_errors += len(errors)
            status = f'{len(errors)} problem(s)' if errors else 'OK'
            print(f'{os.path.relpath(path, data.REPO)}: {len(ok) - len(unchanged)} verses with changes, '
                  f'{status}. Report: {os.path.relpath(path + REPORT_SUFFIX, data.REPO)}')
    if total_errors:
        sys.exit(1)


def apply(args):
    files = reply_files(APPROVED)
    if not files:
        raise SystemExit('Nothing to apply: no replies in review_replies/approved/.')
    ctx = Context(args.sync_bible)
    proposals, problems = load_and_validate(files, ctx)
    errors = problems + [f'{p.where()}: {e}' for p in proposals for e in p.errors]
    if errors:
        print('Nothing written. Fix these in the approved replies first:', file=sys.stderr)
        for e in errors:
            print(f'  {e}', file=sys.stderr)
        sys.exit(1)

    written = []
    for p in proposals:
        book, ci, vi = p.key
        new = [list(e) for e in p.entries]
        if new != ctx.nmv[book][ci][vi]:
            ctx.nmv[book][ci][vi] = new
            written.append(p.key)
    if args.dry_run:
        print(f'Dry run: would write {len(written)} verses from {len(files)} replies.')
        return

    data.write_sync_bible_json(ctx.nmv, ctx.nmv_path)
    manual.record_locked(written, note='reviewed via chat reply, applied')
    os.makedirs(APPLIED, exist_ok=True)
    for path in files:
        for src in (path, path + REPORT_SUFFIX):
            if os.path.exists(src):
                dest = os.path.join(APPLIED, os.path.basename(src))
                if os.path.exists(dest):
                    stem, ext = os.path.splitext(dest)
                    dest = f'{stem}.{datetime.datetime.now():%Y%m%d%H%M%S}{ext}'
                shutil.move(src, dest)
    print(f'Wrote {len(written)} verses into {ctx.nmv_path}, added them to retag/locked_verses.txt '
          f'and moved {len(files)} replies to review_replies/applied/.\n'
          'Commit NMV_strongs.json in sync.bible, and review_replies/ and retag/locked_verses.txt here.')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    for name, help_text in [('check', 'Validate pending and approved replies and write check reports'),
                            ('apply', 'Write approved replies into sync.bible')]:
        p = sub.add_parser(name, help=help_text)
        p.add_argument('--sync-bible', default=os.path.join(data.REPO, '..', 'sync.bible'),
                       help='Path to a sync.bible checkout (default: ../sync.bible)')
        if name == 'apply':
            p.add_argument('--dry-run', action='store_true', help='Validate and count, but write nothing')
    args = parser.parse_args()
    {'check': check, 'apply': apply}[args.command](args)


if __name__ == '__main__':
    main()
