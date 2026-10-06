'''Resumable batch review of the chunks in review_chunks/ by helper agents.

    python review_batch/batch.py status        # how far the batch has got
    python review_batch/batch.py next 8        # the next chunks to hand to helpers
    python review_batch/batch.py commit        # verify, commit and push finished replies
    python review_batch/batch.py clean         # delete half-written replies (no helpers running!)

A chunk is done when a reply named after it is committed in review_replies/pending, approved
or applied. A helper writes its reply into review_replies/pending and, as its very last step,
appends the line COMPLETE_MARKER. Replies without it were cut off (e.g. by a usage limit) and
are removed by `clean`, so those chunks are simply handed out again. See review_batch/README.md.'''
import argparse
import os
import re
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHUNKS = os.path.join(REPO, 'review_chunks')
REPLIES = os.path.join(REPO, 'review_replies')
FOLDERS = ['pending', 'approved', 'applied']
COMPLETE_MARKER = '<!-- review complete -->'
CHUNK_NAME = re.compile(r'^\d+_(.+)_(\d{3})\.(\d{3})-(\d{3})\.(\d{3})\.md$')


def git(*args, check=True):
    return subprocess.run(['git', '-C', REPO, *args], check=check, capture_output=True, text=True).stdout


def all_chunks():
    '''Chunk paths relative to review_chunks/, in Bible order (as in INDEX.md).'''
    with open(os.path.join(CHUNKS, 'INDEX.md'), encoding='utf8') as f:
        return re.findall(r'^\| \[[^\]]*\]\(([^)]+)\)', f.read(), re.M)


def tracked_replies():
    names = set()
    for line in git('ls-files', 'review_replies').splitlines():
        folder, name = line.split('/')[-2:]
        if folder in FOLDERS and not name.endswith('.check.md'):
            names.add(name)
    return names


def untracked_replies():
    '''{name: complete?} for reply files in pending/ that are not committed yet.'''
    out = {}
    for line in git('ls-files', '--others', '--exclude-standard', 'review_replies/pending').splitlines():
        name = os.path.basename(line)
        if name.endswith('.md') and not name.endswith('.check.md'):
            with open(os.path.join(REPO, line), encoding='utf8') as f:
                out[name] = COMPLETE_MARKER in f.read()
    return out


def state():
    done, untracked = tracked_replies(), untracked_replies()
    chunks = all_chunks()
    remaining = [c for c in chunks if os.path.basename(c) not in done and os.path.basename(c) not in untracked]
    return chunks, done, untracked, remaining


def cmd_status(args):
    chunks, done, untracked, remaining = state()
    n_done = sum(os.path.basename(c) in done for c in chunks)
    finished = [n for n, ok in untracked.items() if ok]
    print(f'{n_done} of {len(chunks)} chunks reviewed and committed, {len(remaining)} not started.')
    if finished:
        print(f'{len(finished)} finished but not committed yet (run commit): {", ".join(sorted(finished))}')
    partial = [n for n, ok in untracked.items() if not ok]
    if partial:
        print(f'{len(partial)} in progress or cut off (run clean once no helpers are running): {", ".join(sorted(partial))}')
    if remaining:
        print(f'Next: {remaining[0]}')


def cmd_next(args):
    '''The next chunks not started, after --after (the last chunk handed out, whose helpers
    may not have written anything yet).'''
    remaining = state()[3]
    if args.after:
        order = all_chunks()
        start = order.index(args.after) + 1 if args.after in order else 0
        later = set(order[start:])
        remaining = [c for c in remaining if c in later]
    for chunk in remaining[:args.n]:
        print(chunk)


def cmd_clean(args):
    removed = 0
    for name, complete in untracked_replies().items():
        if not complete:
            for path in (name, name + '.check.md'):
                full = os.path.join(REPLIES, 'pending', path)
                if os.path.exists(full):
                    os.remove(full)
            removed += 1
    print(f'Removed {removed} unfinished replies; their chunks will be handed out again.')


def refs_outside(name, text):
    m = CHUNK_NAME.match(name)
    book = m.group(1).replace('_', ' ')
    lo, hi = (int(m.group(2)), int(m.group(3))), (int(m.group(4)), int(m.group(5)))
    bad = []
    for ref in re.findall(r'"ref":\s*"([^"]*)"', text):
        rb, _, cv = ref.rpartition(' ')
        try:
            c, v = map(int, cv.split(':'))
        except ValueError:
            bad.append(ref)
            continue
        if rb != book or not lo <= (c, v) <= hi:
            bad.append(ref)
    return bad


def cmd_commit(args):
    finished = sorted(n for n, ok in untracked_replies().items() if ok)
    if not finished:
        print('Nothing finished to commit.')
        return
    paths = [os.path.join(REPLIES, 'pending', n) for n in finished]
    out = subprocess.run([sys.executable, os.path.join(REPO, 'review_replies.py'), 'check',
                          '--sync-bible', args.sync_bible, *paths], capture_output=True, text=True, cwd=REPO).stdout
    good, bad = [], []
    for name, path in zip(finished, paths):
        line = next((l for l in out.splitlines() if f'/{name}:' in l), '')
        with open(path, encoding='utf8') as f:
            outside = refs_outside(name, f.read())
        if ', OK.' in line and not outside:
            good.append(name)
        else:
            bad.append(f'{name}: {"refs outside the chunk: " + ", ".join(outside) if outside else line or "not checked"}')
    for b in bad:
        print('NOT COMMITTED', b)
    if not good:
        return
    files = [f'review_replies/pending/{n}{s}' for n in good for s in ('', '.check.md')]
    git('add', *files)
    label = ', '.join(n[:-3] for n in good) if len(good) <= 3 else f'{len(good)} chunks ({good[0][:-3]} … {good[-1][:-3]})'
    git('commit', '-q', '-m', f'Chat review replies for {label} (pending human check)\n\n'
        'Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
        + (f'\nClaude-Session: {args.session}' if args.session else ''))
    for attempt in range(5):
        if subprocess.run(['git', '-C', REPO, 'pull', '-q', '--rebase', 'origin', args.branch]).returncode == 0:
            break
        time.sleep(2 ** attempt)
    for attempt in range(5):
        if subprocess.run(['git', '-C', REPO, 'push', '-q', 'origin', f'HEAD:{args.branch}']).returncode == 0:
            break
        time.sleep(2 ** attempt)
    print(f'Committed and pushed {len(good)}: {", ".join(good)}')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('status')
    p = sub.add_parser('next')
    p.add_argument('n', type=int, nargs='?', default=8)
    p.add_argument('--after', help='Only chunks after this one (e.g. the last one handed out)')
    sub.add_parser('clean')
    p = sub.add_parser('commit')
    p.add_argument('--sync-bible', default=os.path.join(REPO, '..', 'sync.bible'))
    p.add_argument('--branch', default='review-chunks')
    p.add_argument('--session', default=os.environ.get('CLAUDE_SESSION_URL', ''),
                   help='Claude session link for the commit message (default: $CLAUDE_SESSION_URL)')
    args = parser.parse_args()
    {'status': cmd_status, 'next': cmd_next, 'clean': cmd_clean, 'commit': cmd_commit}[args.command](args)


if __name__ == '__main__':
    main()
