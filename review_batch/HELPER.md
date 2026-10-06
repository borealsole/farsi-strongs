# Instructions for a review helper

You are reviewing the Strong's number tags of the Persian (NMV) Bible for one chunk, acting
exactly as a chat assistant would when a user pastes the review prompt plus the chunk file.
Your task message gives CHUNK (a path inside `review_chunks/`, e.g.
`01_Genesis/01_Genesis_002.001-002.025.md`). Below, NAME is its file name
(`01_Genesis_002.001-002.025.md`) and REPO is `/home/user/farsi-strongs`.

1. Read the review prompt in full. It is the text inside the ```` ```text ```` block under
   "## Prompt" at the end of REPO/review_chunks/README.md. Follow it exactly; it is your
   instruction set.
2. Read the chunk file in full: REPO/review_chunks/CHUNK (the "attached file" the prompt
   refers to).
3. Work through every verse under "Verses to review", entry by entry, using your knowledge of
   Biblical Hebrew or Koine Greek and Persian. In the New Testament, original words marked
   "variant reading" come from other Greek texts that the Persian often follows. Be careful
   and conservative: only change a tag where you are confident the current one is wrong or
   missing, and list doubtful cases in the notes.
4. Write your complete reply (the ```jsonl block, then the notes list) to
   REPO/review_replies/pending/NAME. Each JSON line must be valid JSON on one line, with the
   Persian copied exactly from the chunk file (don't retype or normalise it). Only verses of
   your own chunk may appear.
5. For temporary files use only `/tmp/review_batch/NAME/` (create it). Other helpers are
   working at the same time: never write anywhere else in /tmp, and never edit, move or delete
   any file in the repository except your own reply and its report.
6. Check your reply, and only yours:

       cd REPO && python3 review_replies.py check --sync-bible ../sync.bible review_replies/pending/NAME

   Read REPO/review_replies/pending/NAME.check.md. If it lists Problems (invalid JSON, Persian
   words not matching, numbers not in the verse or its neighbours, tagged punctuation, ...),
   fix the reply and check again until there are none. Only fix the problems; don't change your
   judgements just to make it pass. Confirm every "ref" belongs to your chunk.
7. Only when the check passes, append this line at the very end of the reply file, as your
   last action:

       <!-- review complete -->

   (Without it the reply counts as unfinished and is thrown away.)
8. Do not read anything in review_replies/superseded/. Do not commit, push or change
   anything else in either repository.

Finish with one line only: `NAME: changed X of Y verses, check OK`.
