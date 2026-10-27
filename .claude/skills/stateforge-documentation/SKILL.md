---
name: stateforge-documentation
description: Write, redesign, or review public StateForge Protocol documentation, including versioned MkDocs pages, procedure guides, Mermaid diagrams, declarative interactive walkthroughs, Python contract references, and the shared StateForge documentation presentation.
---

# StateForge Documentation

Write documentation as a public product surface. A reader should be able to
learn the protocol, find its canonical implementation APIs, and understand its
failure behavior without knowing the internal development plan or repository
history.

Use this skill together with `stateforge-protocol-development` when a page
describes SFP semantics and with `stateforge-python-development` when it
documents Python APIs or changes MkDocs configuration.

## Establish the source of truth

Before editing a procedure page, inspect the current version of:

- the procedure's protobuf or filesystem schema;
- its public `contract.py` and `validation.py` modules, when they exist;
- packaged JSON schemas and generated public APIs;
- focused contract tests and established error mappings; and
- the preceding and following procedures in the SFP lifecycle.

Document implemented behavior. Do not infer semantics from an old design
document, milestone text, diagram, or similarly named field when current code
and tests define the contract more precisely. If the implementation and public
contract materially disagree, surface the disagreement instead of writing
around it.

## Write for the reader

- Open with the procedure's purpose and where it fits in the lifecycle. State
  the useful positive contract before listing exclusions.
- Use plain, direct language. Define a concept before presenting its detailed
  rules. Explain why a rule matters when the reason is not obvious.
- Keep paragraphs focused on one idea. Replace dense runs of independent rules
  with a table, diagram, short example, or named subsection.
- Avoid filler, slogans inside technical pages, and text that merely narrates
  the interface, such as explaining that a selector selects a version.
- Do not expose internal planning language, unpublished specifications,
  milestone IDs, review history, or CI implementation detail as product
  documentation.
- Do not describe unrelated repository contents merely to say they are out of
  scope. Explain an ownership boundary only when it changes how a reader uses
  or implements the contract.
- Do not repeat the same explanation in the root home page, version home page,
  procedure map, and procedure page. Give each page one job.

Use consistent StateForge terms and capitalization: Agent, Provider, Control
Plane, StateForge Protocol, SFP, operation, trigger, session, endpoint, and
manifest. Preserve exact wire identifiers, field names, service names, and
status codes in code formatting.

## Organize the documentation by reader task

### Root documentation home

The unversioned `docs/index.md` introduces the component, links to the current
documentation, and routes readers to the major surfaces. It may provide an
engaging interactive overview, but it must not duplicate the complete version
overview or a procedure page.

### Version home

`docs/vX.Y.Z/index.md` is the entry point for one released contract. Use
scannable grids to route readers by task and lifecycle phase. It should feel
like a version home page, not another general product description.

### Procedure map

Present procedures in lifecycle order and group them into meaningful phases,
such as connect, qualify, exchange, and recover. Distinguish Agent-initiated
and Provider-initiated paths where that distinction helps the reader. Every
card or link should have one unique destination.

### Procedure page

Adapt the page to the procedure, but prefer this reading order when the
sections apply:

1. concise purpose and lifecycle context;
2. declarative interactive walkthrough;
3. collapsible Mermaid sequence or state diagram;
4. who implements the procedure;
5. public Python contract and canonical source files;
6. wire or filesystem contract and field meanings;
7. validation and ownership boundaries;
8. outcomes, retries, replacement, or recovery behavior.

Do not force an irrelevant section merely to make every page identical.

## Use the shared StateForge documentation system

- Use the shared `stateforge-docs` theme and plugin through the repository's
  pinned dependency. Do not copy shared branding, JavaScript, styles, or logo
  assets into this repository.
- Keep repository CSS narrow and content-specific. A generally reusable
  component belongs in `stateforge-docs`, not a local override.
- Preserve Material for MkDocs compatibility until the shared system performs
  its planned framework migration. Do not redesign a repository around a
  future documentation engine independently.
- Configure search, repository metadata, the version selector, historical
  warnings, and procedure players through the shared plugin rather than
  rebuilding them locally.

## Treat versions as documentation trees

- The directory determines the documentation version: `docs/vX.Y.Z/`. Do not
  repeat `v1`, `vX.Y.Z`, or `current` in every page title when the navigation
  and version selector already provide that context.
- Keep the unversioned home outside the version tree. Keep procedure Markdown,
  its walkthrough data, and version-specific examples inside the matching
  tree.
- Make the complete version navigation collapsible under its version label so
  additional releases do not bloat the global navigation.
- Use one literal version selector supplied by the shared theme. Do not render
  versions as an accumulating row of buttons.
- Prefer version-local relative links. A historical page must not silently
  send readers into the current version of another procedure.
- Mark the current version through configuration, not prose scattered across
  pages.

## Choose the smallest useful visual

Use a visual when it makes a sequence, state transition, mapping, or layered
validation boundary easier to understand.

- Use Mermaid for maintained sequence diagrams, flowcharts, validation
  pipelines, and state transitions. Do not use ASCII art for relationships a
  Mermaid diagram can express more clearly.
- Keep Mermaid source next to the prose it explains. Give the diagram a useful
  title, keep labels short, and use line breaks before labels become wide
  enough to clip.
- Keep the Mermaid diagram even when the page has an interactive walkthrough.
  The walkthrough teaches by exploration; Mermaid remains the compact,
  printable reference.
- Put a large supporting sequence diagram in a collapsed details block after
  the interactive walkthrough. Do not make readers cross it before reaching
  the implementation guidance.
- Use tables for exact mappings, field ownership, status behavior, limits,
  valid versus invalid examples, and concept comparisons.
- Use a decomposed identifier example before listing identifier grammar.
- Use admonitions only for genuinely important consequences, not ordinary
  paragraphs with decoration.

Never add a visual only to make a page look busy. A diagram must encode real
contract information and remain readable in light mode, dark mode, desktop
layouts, and narrow content widths.

## Build interactive walkthroughs declaratively

Use the shared `stateforge-procedure` player and keep the scenario data in a
YAML file beside the versioned procedure page:

````markdown
```stateforge-procedure
source: procedure-name.yaml
scenario: success
```
````

The walkthrough must:

- model the real participants and resources required by the procedure rather
  than forcing every procedure into a fixed number of entities;
- include the primary success path and every materially distinct failure,
  retry, replacement, or recovery scenario described by the page;
- play every step of every selectable scenario;
- show one clear event and its resulting internal state changes at a time;
- keep labels short enough to remain inside their lanes;
- distinguish direction, owner, and resulting state without requiring the
  reader to track duplicate labels in several places; and
- use accurate wire messages, filesystem artifacts, statuses, and runtime
  decisions instead of illustrative behavior that the implementation does not
  provide.

Prefer one focused walkthrough over a large animation that makes the reader
follow several unrelated changes simultaneously. Animation may add delight,
but it must respect reduced-motion preferences and the page must remain fully
understandable without it.

## Show developers how to use the contract

For each procedure, identify the canonical sources that actually exist:

| Source | What to explain |
| --- | --- |
| `.proto` | Messages, field numbers, services, and RPC methods. |
| `contract.py` | Canonical service identity, limits, identifiers, and stable procedure constants. |
| `validation.py` | Context-independent semantic validation shared by independent implementations. |
| Packaged schema | Machine-readable document or ProtoJSON shape. |
| Generated modules | Messages, client stubs, server interfaces, and registration helpers. |

Link directly to the source and describe its responsibility. If a procedure
intentionally has no protobuf or no separate `validation.py`, say what owns
that contract instead; do not invent uniformity.

Make these boundaries explicit:

- generated protobuf classes enforce wire types, not the full StateForge
  semantic contract;
- Protocol validators decide facts derivable from a message or document
  alone;
- Agent and Provider runtimes decide facts that depend on live sessions,
  processes, filesystem state, retry state, caches, admission, or local policy;
  and
- Provider authors using StateForge Provider Python should not be instructed
  to manually reproduce behavior already owned by the framework.

Keep examples small and centered on the public surface being taught. Do not
turn a documentation example into a second runtime, conformance suite, or CI
system. An example should be executable when execution materially helps, but
the canonical tests remain the proof of edge cases and limits.

## Make dense contract rules scannable

When a section starts to read like several specifications joined into one
paragraph:

1. identify the concepts the reader must distinguish;
2. define each concept in one short paragraph;
3. show its shape or relationship visually when useful;
4. put exact rules and empty/default meanings in tables; and
5. isolate the important consequence in one concise admonition.

For example, define a profile before explaining a profile claim, show which
operation makes the claim, and only then list validation and interoperability
rules. Do not make readers infer a concept from a validation paragraph.

## Pair field references with executable message examples

When a procedure page explains a request, response, event, descriptor, or
other structured envelope, let readers switch between its exact field
reference and a realistic serialized example when both views materially aid
understanding. Use Material content tabs rather than showing the table and
payload one after the other:

- Put the reference view first. Use a specific label such as `Field reference`
  or `Method reference`.
- Label protobuf JSON projections `Example ProtoJSON`. When request and
  response examples deserve separate views, use `Example request` and
  `Example response`. Call non-protobuf documents what they are, such as
  `Example descriptor`; do not describe ordinary JSON as ProtoJSON.
- Keep examples complete enough to pass the real contract, but no larger than
  needed to teach the shape. Do not invent fields or use malformed shorthand.
- Use a titled annotated JSON block for values that need explanation:

  ````markdown
  ``` { .json .annotate title="HandshakeResponse" }
  {
    "sessionId": "session-A (1)"
  }
  ```

  1. Fences later session-bound procedures.
  ````

- Enable JSON annotations with Material's custom string-token selector,
  `extra.annotate.json: [.s2]`, and keep `pymdownx.highlight`,
  `pymdownx.superfences`, and `pymdownx.tabbed` with
  `alternate_style: true`. Reuse the shared configuration when it already
  provides these settings; do not copy theme assets or JavaScript locally.
- Place annotation markers only inside JSON string values so the rendered
  marker is removed from the displayed value by the custom selector. Keep
  annotations concise and use them for relationships or consequences that are
  not obvious from the field name.
- Add a contract test that extracts the documented JSON, removes annotation
  markers, and validates it with the canonical parser, generated protobuf
  message plus semantic validator, or packaged JSON Schema. Reuse the
  repository-wide documentation-example helper instead of writing a new
  extractor in every procedure test.

Do not force tabs onto a short table or payload when switching views adds no
value. The table and example are two representations of the same contract,
not an excuse to repeat the surrounding prose.

## Verify content and presentation

Run the focused contract tests affected by factual documentation changes, the
documentation-system tests, and a strict site build. Use the repository's
configured commands; a typical check is:

```console
pytest tests/test_documentation_system.py tests/test_<procedure>_contract.py
mkdocs build --strict
git diff --check
```

Preview every material presentation change in the built site. Check:

- light and dark modes;
- the main desktop layout and a narrower viewport;
- Mermaid rendering, centering, and label clipping;
- every interactive scenario, including complete playback;
- collapsed details, navigation, search, and version selection;
- relative links and anchors; and
- accidental duplication between pages.

Do not claim a page is finished because Markdown compiles. Report the exact
automated checks and the visual states inspected.

## Final review checklist

- The page has one clear reader job and begins with useful context.
- Statements match current contract sources and tests.
- Internal planning language and irrelevant exclusions are absent.
- Dense rules are decomposed into understandable concepts.
- Canonical source files and public Python APIs are linked and explained.
- Mermaid and walkthroughs complement rather than duplicate each other.
- All walkthrough scenarios are accurate, complete, and visually readable.
- Version location, navigation, and links preserve the correct release.
- Shared presentation remains owned by `stateforge-docs`.
- Focused tests, strict MkDocs, diff checks, and visual inspection pass.
