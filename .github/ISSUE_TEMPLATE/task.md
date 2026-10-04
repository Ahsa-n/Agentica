---
name: Task or bug (AG-xxx)
about: A new work item for one of the 19 core features. Use the next free AG-ID.
title: "[AG-xxx] "
labels: []
assignees: []
---

**ID:** AG-xxx · **Milestone:** M? · **Feature(s):** F? · **Epic:** E?
**Suggested owner:** <name>
**Blocked by:** #n (AG-xxx), … | none
**Spec:** `docs/AGENTICA_SPEC.md` §x.y

<!-- Keep the "Blocked by" line in exactly this format and also add each blocker under
     Relationships → "Blocked by" in the sidebar. The dependency-lock workflow keeps the
     issue locked (status:blocked) until every blocker is closed as completed.
     Add the matching feature:Fxx, type:, area:, and priority: labels. -->

## Context

<why this issue exists>

## Tasks

- [ ] …

## Files (expected)

- `path`

## Acceptance criteria

- [ ] …

## Tests that must pass

- [ ] …

## Out of scope

- Anything listed in spec §6 (removed, excluded, or dropped features).

## Definition of done

- [ ] All acceptance criteria are met, every listed test passes, and CI is green on `ubuntu-22.04` and `windows-latest`.
- [ ] Delivered through a pull request that references this issue (`Closes #n`), passes the `dependency-gate` check, and is approved by @Ahsa-n.
