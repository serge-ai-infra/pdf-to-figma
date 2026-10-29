# S1 — Extract

Turn a PDF into the intermediate representation everything downstream reads.

This stage decides the contract for the whole project, so it is worth getting
narrow and exact rather than broad and approximate. Nothing here interprets the
document; it only records what is on the page.

## Goal

`pdf2figma extract input.pdf -o out.ir.json` produces a validated, versioned
description of every element on every page — geometry, style, text — with no
semantics, no chart types, and no domain vocabulary.

## Non-goals

Explicitly out of this stage, to keep it finishable:

- Clustering, tokens, component candidates — S2.
- Anything touching Figma — S3.
- Recognizing what an element *means*. A donut is an ellipse and some curves.
- Reconstructing datasets from charts. The source is rendered graphics; the
  numbers are not in there.
- Font extraction and repair. Deferred until a document actually needs it; the
  stage records what fonts are referenced and whether they are embedded.

## Stack

Python 3.12, `pdfplumber` (MIT) for extraction, `pydantic` for the model and
validation. TypeScript enters at S3 with the plugin, not before.

License constraint is deliberate and documented in
[`../../architecture.md`](../../architecture.md#stack): PyMuPDF is the stronger
extractor but AGPL, which an MIT project cannot depend on.

## Layout

```
src/pdf2figma/
  ir/
    model.py        pydantic models, IR_VERSION
    schema.py       JSON Schema export
  extract/
    base.py         Extractor protocol
    pdf.py          pdfplumber implementation
  cli.py            extract command, argparse
tests/
  fixtures/synthetic.py   builds PDFs byte by byte, known coordinates
  test_ir.py
  test_extract.py
  test_privacy.py
pyproject.toml
```

## The IR

Deliberately dumb. Geometry, style, text — nothing else.

**Coordinates.** Origin top-left, y down, matching Figma. PDF's bottom-up space
is converted once, here, so no stage downstream has to think about it. Units are
PDF points (1/72"); pixels and DPI appear only at render time.

**Document.**

```
IRDocument   ir_version, source: SourceInfo, pages: [IRPage]
SourceInfo   page_count, producer?, creator?, title?
IRPage       index, width, height, rotation, nodes: [IRNode]
```

`SourceInfo` carries no path and no filename — see privacy below.

**Nodes.** Common: `id`, `bbox {x, y, w, h}`, `z`.

```
IRText    text, font {family, size, weight?, italic?},
          color: Color, color_confidence: exact | approx | unknown
IRShape   shape: rect | ellipse | line | path,
          fill?: Color, stroke?: {color, width}, closed: bool
IRImage   image_id, mime?
```

`Color` is sRGB hex plus alpha. A non-sRGB source color space is recorded on the
document, because the conversion caps achievable accuracy and downstream should
know it was lossy before it starts.

**Uncertainty is a field, never a guess.** Anything the extractor cannot
establish carries a confidence marker instead of a plausible value.

**Versioned.** A schema mismatch is an error. No silent migration.

## Extractor interface

The reason input is an interface: a PDF parser is one source, a layout
specification from an upstream generator is another, and both produce the same
IR. See architecture, *When the document has a generator*.

```python
class Extractor(Protocol):
    name: str
    def supports(self, inp: ExtractInput) -> bool: ...
    def extract(self, inp: ExtractInput, opts: ExtractOptions) -> IRDocument: ...
```

`ExtractInput` carries **bytes**, not a path. Core code never touches the
filesystem; only the CLI does I/O. This keeps tests free of fixtures on disk and
makes it structurally impossible to leak a path into an artifact.

## Shape classification

From path construction alone, no interpretation:

- one rectangle subpath → `rect`
- one move plus one line → `line`
- four curves whose bbox is near-square → `ellipse`
- anything else → `path`

Ambiguous cases resolve to `path`. Being wrong here is worse than being vague,
because S2 clusters on these labels.

## Privacy

Extracts get shared, attached to issues, pasted into chats. They must not carry
where they came from:

- no absolute paths, no source filename, in any artifact
- `work/` and `*.ir.json` are gitignored
- a test asserts the property rather than trusting review

## Verification

Two independent checks, because "it ran without crashing" says nothing about
completeness.

**Synthetic fixtures.** PDFs assembled byte by byte in the test suite with known
coordinates, colors and text. Exact assertions: a rect declared at a known
position must land at the converted top-left position, to within a rounding
epsilon. No binary fixtures committed.

**Cross-check against an independent converter.** Convert the same page with
`pdftocairo -svg` and compare element counts: paths and glyph references there
against shapes and text runs in the IR. Wide tolerance — the two disagree by
construction, since one outlines glyphs and the other keeps text runs — but an
order-of-magnitude gap means the extractor is dropping content silently, which is
the failure mode that matters and the one that is invisible without a second
opinion.

## Risks

- **Text color.** pdfplumber exposes `non_stroking_color` per character, so color
  should be exact rather than inferred. If a document defeats that, the field
  says `approx` and the reason is logged — it does not get a plausible value.
- **Glyph-level characters.** pdfplumber yields characters, not runs. Grouping
  into runs is our logic and can merge or split wrongly; grouping rules are
  parameters, and the synthetic fixtures pin the expected behaviour.
- **Rotated or transformed text** is out of scope for S1 and recorded as
  unsupported rather than approximated.
