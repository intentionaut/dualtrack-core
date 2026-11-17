# Standards

The shared layer both design agents judge by. `core.md` always applies. The profile's
**Surfaces** line adds one file per surface the product has, so each product gets the rules
for what people actually use. Add a file here for a new surface, and name it in Surfaces.

`checklists.md` and `writing.md` always apply too: they are the definition of done for
common parts and for every word a person reads.

Written in our own words. They draw on these sources, which are worth reading in full:

- Nielsen's ten usability heuristics, and his 0 to 4 severity scale: nngroup.com
- WCAG 2.2: w3.org/TR/WCAG22
- Command Line Interface Guidelines: clig.dev
- Checklist Design (MIT): github.com/Checklist-Design/skills
- design-skills by Carlos C. (MIT): github.com/cuellarfr/design-skills
- Web Interface Guidelines (MIT): github.com/vercel-labs/web-interface-guidelines

A design review is a judgement, not a measurement. Two 2025 studies of model-run heuristic
reviews disagreed widely on how many expert-found issues they caught. So the loop runs your
**Design checks**, deterministic tools such as axe-core, Lighthouse or impeccable's detector,
and the reviewers treat that output as ground truth.
