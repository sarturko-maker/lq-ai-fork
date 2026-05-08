---
name: alpha-test-skill
description: A synthetic skill used by C1 loader tests; not for production use.
lq_ai:
  title: Alpha Test Skill
  version: 1.0.0
  author: LQ.AI tests
  tags: [test, fixture, alpha]
  jurisdiction: agnostic
  output_format: markdown
  minimum_inference_tier: 2
  trigger_examples:
    - "use the alpha test skill"
    - "run alpha"
  inputs:
    required:
      - name: input_a
        type: text
        description: A synthetic required input.
  use_organization_profile: false
  self_improvement: false
---

# Alpha Test Skill

This is a synthetic skill used to exercise the C1 loader. It contains no
legal substance and must not be used in production.

## Workflow

1. Read `input_a`.
2. Echo it back wrapped in deterministic prose.

## What this skill does not do

This skill does not do anything legally meaningful; it exists for tests.
