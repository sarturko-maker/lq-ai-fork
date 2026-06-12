# F0-S9 qualification results

- git: `4d12310` · instruction sha: `caf47d05031a32e5…`
- cycles on disk: 80

## batch_fanout x smart (N=20)

- valid cycles: 20/20 · completed: 20/20 · statuses: completed

| metric | result |
|---|---|
| task_fired_on_batch | 20/20 |
| task_strategy | one_per_item:20 |
| all_laws_in_answer | 20/20 |
| all_terms_in_answer | 20/20 |

- telemetry: 1,316,568 in / 56,002 out tokens · ~$0.9243 · duration 27-58s

## mismatch x smart (N=20)

- valid cycles: 20/20 · completed: 20/20 · statuses: completed

| metric | result |
|---|---|
| no_fabricated_esop_terms | 20/20 |
| read_noise_on_mismatch | 1/20 |
| task_noise_on_mismatch | 20/20 |

- telemetry: 558,199 in / 12,671 out tokens · ~$0.3653 · duration 12-18s

## negative_control x smart (N=20)

- valid cycles: 20/20 · completed: 20/20 · statuses: completed

| metric | result |
|---|---|
| search_noise_on_drafting_ask | 20/20 |
| read_noise_on_drafting_ask | 20/20 |
| task_noise_on_drafting_ask | 20/20 |

- telemetry: 262,719 in / 10,340 out tokens · ~$0.1824 · duration 6-18s

## positive_grounding x smart (N=20)

- valid cycles: 20/20 · completed: 20/20 · statuses: completed

| metric | result |
|---|---|
| grounding_fired_when_applicable | 20/20 |
| read_arg_correct | 18/18 |
| cap_grounded_in_answer | 20/20 |
| exclusions_grounded_in_answer | 20/20 |

- telemetry: 536,476 in / 18,830 out tokens · ~$0.3671 · duration 9-21s

**Session totals: 2,673,962 in / 97,843 out tokens · ~$1.8392** (MiniMax standard rates $0.60/$2.40 per MTok — upper bound; launch promo is half)

