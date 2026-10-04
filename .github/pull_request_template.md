## Summary

<!-- What does this pull request change, and why? -->

Closes #<issue-number>
Issue ID: AG-<xxx> · Feature(s): F<n>

## How it was tested

<!-- List every test from the issue's "Tests that must pass" section with its result.
     Link CI runs, and attach evidence for manual or recorded checks. -->

## Definition of done

- [ ] The linked issue was `status:ready` (all of its dependencies closed) before work started.
- [ ] All acceptance criteria in the issue are met.
- [ ] Every test in the issue's "Tests that must pass" exists and passes; CI is green on `ubuntu-22.04` and `windows-latest`.
- [ ] New code has unit tests; integration tests are added where the DB, the graph, or a target is touched.
- [ ] No secrets in code, config, logs, prompts, or API responses.
- [ ] No `shell=True` and no string commands built from model output.
- [ ] New tools: Pydantic input model (`extra="forbid"`), output model, risk tier, `verify()` for modify/destructive tools, catalogue entry (spec §14.5), and ≥ 3 benchmark tasks.
- [ ] `risk:modifies-systems` issues: policy tests prove Confirm under the default policy, and guardrail tests are added.
- [ ] Any change to a [D] design item is recorded as an ADR in `docs/adr/`.

> Merging needs approval from @Ahsa-n. Direct pushes to `main` are blocked, and the `dependency-gate` check fails while the linked issue is still blocked.
