# Re-tagging NMV_strongs.json

Rebuilds the Strong's tagging of sync.bible's `public/bibles/NMV_strongs.json` (the NMV
Persian Bible) directly against the original languages in sync.bible's `accented.json`. It
keeps every verse that has been corrected by hand.

```sh
pip install -r retag/requirements.txt
python -m retag evaluate --sync-bible ../sync.bible   # score against the hand-corrected verses
python -m retag run --sync-bible ../sync.bible        # rewrite NMV_strongs.json in that checkout
python -m unittest retag.test_tagger
```

A full run takes about three minutes on four CPU cores.

Step-by-step instructions, accuracy figures and how to grow `locked_verses.txt` are in the
[main README](../README.md).

## Output rules

| Case | Entry |
| --- | --- |
| Persian word not in the original (added for sense) | `["خود"]` (untagged) |
| One Persian word for one original word | `["زمین", "H776"]` |
| One Persian word for several original words | `["خداوندمان", "G2962 G2249"]` (original word order) |
| Adjacent Persian words for one original word | `["ساکن گشتید", "H3427"]` (one grouped entry) |
| Non-adjacent Persian words for one original word | each word tagged with the same number |

Tags are the Strong's numbers used in `accented.json`, including the Hebrew prefix
morphemes (`Hc` and/conjunction, `Hl`, `Hb`, `Hm`, `Hk`...) and את (`H853`, normally
translated by را). Markers inherited from the ESV (`dvnNm`, `added`) are no longer produced.
Pronominal suffixes have no number in `accented.json`, so the Persian pronouns that
translate them stay untagged. The manual corrections tag them the same way.

## Keeping the hand corrections

The app lets editors retag words by hand, so the published file has two kinds of verses:
machine-tagged ones and hand-corrected ones. The tool tells them apart by diffing:

1. **First run:** sync.bible's file is compared with the original aligner output
   (`outputs/NMV_ESV_strongs.json`, which is exactly what was first published to
   sync.bible in Nov 2022). Every verse that differs has been edited by hand. At the
   time of writing that is 44 verses: Deuteronomy 26, Philemon 1:1-13, Song of Solomon
   6:1-3, Genesis 1:2,4-7, Colossians 1:3-4, Isaiah 66:13 and Zechariah 1:6.
2. Those verses are **locked**, listed in `retag/locked_verses.txt`, and copied from
   sync.bible's current file. Their tags are never changed. The one exception is that
   adjacent words carrying the same tag are grouped into one entry (e.g. `ساکن`+`گشتید`),
   and only when that number occurs once in the original verse. Pass `--no-group-locked`
   to copy them exactly.
3. Each run saves what it wrote to `outputs/NMV_strongs_machine.json`. **Later runs** diff
   sync.bible against that file instead, so any verse corrected in the app since the last
   run is detected, locked and added to `locked_verses.txt`.
4. To protect a passage that was reviewed but needed no changes, add it to
   `locked_verses.txt` by hand (`Philemon 1:14-25`, `Deuteronomy 27`, `John 3:16`).

So the workflow is: run the tool, commit the regenerated `NMV_strongs.json` to sync.bible
*and* `outputs/NMV_strongs_machine.json` plus `retag/locked_verses.txt` here. If the two
repos get out of step (e.g. the output was never copied to sync.bible), the tool refuses to
run instead of locking thousands of verses.

Each verse is tagged independently, so re-tagging never shifts a hand-corrected verse.
The tool also fixes an old bug: the original aligner dropped the 17 verses the ESV omits
(Matthew 17:21, Acts 8:37, Mark 9:44,46, ...), which shifted every later verse in those 16
chapters. These verses are restored from `transformations/NMV_hazm.parquet`. Matthew 12:47 is
tagged. The others have no text in Tischendorf's Greek; they now take their Greek from
`TR.json` (see below).

## Greek variant readings (`variants.py`)

The NMV New Testament follows a modern critical text close to NA27/UBS4. Verses found only
in the Textus Receptus are added in square brackets (Matthew 17:21, Acts 8:37, the doxology
of Matthew 6:13…). Tischendorf, the Greek in `accented.json`, differs from that text in a few
hundred places, e.g. Jude 22 (ἐλέγχετε, where the Persian has ἐλεᾶτε "have mercy"),
Acts 20:28 (κυρίου, where the Persian has θεοῦ "God"), 2 Peter 3:10, 1 Corinthians 2:1, and
Luke 24:12, which it leaves out. A comparison at 44 well-known variant units ranked the
Strong's-tagged Greek files in sync.bible: `WHNU.json` (Westcott-Hort with NA27/UBS4
variants) matched the Persian at 36, `accented.json` and `MorphGNT.json` at 34,
`grcsbl2010eb.json` at 30, the Byzantine texts at 17-23, and `TR.json` at 19.

So the original text for the New Testament is `accented.json` with words merged in from:

- **`WHNU.json`**, for every verse;
- **`TR.json`**, for verses whose Persian has square brackets, and for verses neither of the
  other files has.

Only words whose Strong's number isn't already in the verse are added, inserted where they
stand in that text. Numbers are converted to the `accented.json` conventions first: no zero
padding; `G1473`/`G2249` and `G4771`/`G5210` for singular/plural pronouns; and `G1510` for
TR's forms of εἰμί (`G2076`, `G2258`…). The same word under a different number (πλεῖον,
G4183 in Tischendorf and G4119 in WHNU) or part of a word written as one (διατί) isn't
counted as a different reading. About 350 verses get extra words: around 520 words from
WHNU and 270 from TR. Each added word has a fourth field naming its source, e.g.
`["ελεατε", "G1653", "V-PAM-2P", "WHNU"]`. The Old Testament is unchanged.

The re-tagger, `make_review_chunks.py` and `review_replies.py` all read the original text
this way. Each takes `--no-variants` to use `accented.json` alone.

## How tagging works

1. **Corpus.** Each Persian token (hazm tokenisation, as in the existing file) is reduced to
   a stem: diacritics removed, the content part of compounds kept (`خواهند_کُشت` → `کشت`),
   and plural/pronoun suffixes stripped when the remainder is itself a common word. The
   original side is the sequence of Strong's numbers of each verse's morphemes.
2. **Alignment.** [eflomal](https://github.com/robertostling/eflomal) aligns the whole Bible
   in both directions, three times (it is a sampler). Tags from the old simalign/ESV-pivot
   run are passed in as lexical priors.
3. **Classification.** Every candidate link (any eflomal link, or an old ESV-pivot tag that
   exists in the verse) gets features: eflomal votes per direction, pivot agreement, Bible-wide
   association of stem and Strong's number, relative position, morpheme type. A gradient
   boosted classifier trained on the locked (hand-corrected) verses keeps links whose
   probability is at least `--threshold` (0.45). Raise it for fewer, safer tags. The model
   retrains on each run, so every new hand correction also improves the rest of the Bible.
4. **Rules.**
   - An untagged light verb (`کرد`, `می‌دهد`, `داده_است`, `گشت`...) after a word tagged with
     an original verb joins it (`تسلی می‌دهد`).
   - `را` is tagged only as את (`H853`), and only when the verse has one.
   - Adjacent words linked to the same original word are grouped.

## Results

5-fold cross-validation on the 44 hand-corrected verses, scored per (Persian token,
Strong's number) pair:

| | Precision | Recall | F1 |
| --- | --- | --- | --- |
| Tags before hand correction (simalign via ESV) | 0.874 | 0.631 | 0.733 |
| This re-tagger | 0.791 | 0.796 | 0.793 |

The gold set favours the old tags, because editors kept old tags they judged acceptable.
Even so, recall rises sharply (prefixes, את, both halves of compound verbs). Hebrew gains
most: on Deuteronomy 26, F1 goes from 0.66 to about 0.82. On Greek (Philemon) the result
equals the old tagging, about 0.77.

Known limitations:

- The gold set is small.
- In the NT, some hand-corrected verses use traditional pronoun form numbers (e.g. `G4671`
  σοί) where `accented.json` has the lemma number (`G4771`). Those are compared as
  equivalent when scoring.
- eflomal sampling makes runs differ slightly.
- Tokens are never split, so a Persian token covering two original words gets both numbers
  rather than being split.

The biggest further gain would be hand-correcting more verses (especially NT) and rerunning,
or adding a verse-by-verse LLM review pass on top of these candidates.
