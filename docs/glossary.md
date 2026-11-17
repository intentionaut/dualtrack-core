# Glossary

Dualtrack works alongside people, so every name says whether a person or an agent did the work. The README carries the same list; this file is the full one.

## Who

| Term | Means |
|---|---|
| **the team** | The people and the Dualtrack agents working on the product together. |
| **Dualtrack agents** | Work only the agents did, with no person involved. "Dualtrack agents ranked the backlog." |
| **Dualtrack [role]** | One agent, named by its role. "The Dualtrack navigator approved it." |
| **the owner** | The person who confirms what gets built and merges it. The owner's call beats every other signal. |
| **a person** | Anyone on the team who is not an agent, named by their GitHub or tracker name in the record. |

## Dualtrack roles

| Agent file | Name | Job |
|---|---|---|
| `setup` | Dualtrack setup | drafts the profile; asks only what it cannot infer |
| `product-manager` | Dualtrack product manager | researches, tries to disprove its ideas, proposes bets |
| `product-design` | Dualtrack product designer | designs each visible change before it is built |
| `ux-review` | Dualtrack UX reviewer | walks the path to first value and reviews every visible change |
| `engineer` | Dualtrack engineer | builds one item test-first on a branch |
| `navigator` | Dualtrack navigator | reviews plan and branch on a different model; answers APPROVE or CHANGES |
| `intent-check` | Dualtrack intent checker | after the navigator approves, answers MET or NOT MET for each Done when line |
| `source-reader` | Dualtrack source reader | reads one analytics source read-only and writes down what it says |
| `input-reader` | Dualtrack input reader | sorts outside comments into themes for the Dualtrack product manager |

## Work

| Term | Means |
|---|---|
| **bet** | A change the team expects to move an outcome, with the evidence it will be judged by. |
| **the trail** | The record on a pull request of who did what: each line names a person or a Dualtrack role. |
| **the kit** | The Dualtrack software itself: agents, scripts and standards. |

## Rules

- Never "PM", "the PM" or a bare role name for an agent. A human product manager may be on the team, and the reader must be able to tell them apart. A test (`tests/test_glossary.py`) blocks the label PM followed by a colon anywhere in the kit.
- "The team" means people and agents together. Use "Dualtrack agents" when only the agents acted.
