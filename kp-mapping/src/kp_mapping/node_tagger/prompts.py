"""System prompts for the node_tagger 2-phase pipeline."""

COVERAGE_ANALYZER_SYSTEM = "You are a curriculum analyst. Return JSON only."

COVERAGE_ANALYZER_USER_TEMPLATE = """\
You are a curriculum analyst mapping a Python question to knowledge nodes.

Question:
{question}
{solution_block}
Existing knowledge node catalog (id | depth_level | label):
{catalog}

Task:
1. Identify the terminal skills a student needs to answer this question.
2. For each required terminal skill:
   - If an existing node matches it semantically → add its ID to `covered_node_ids`.
     Pick the HIGHEST-LEVEL (largest depth_level) existing node that captures the skill.
     Do NOT list tactical prerequisites separately — the closure walk handles those.
   - If no existing node matches → describe it in `gap_skills`.
3. Set `coverage_status`:
   - "full"    → ALL required terminal skills are covered by existing nodes
   - "partial" → some are covered, some are new gaps
   - "none"    → no existing node is relevant; all skills are gaps

Return JSON only — no markdown, no explanation outside JSON:
{{
  "covered_node_ids": ["<uuid>"],
  "gap_skills": [
    {{
      "label": "short descriptive name (2-5 words, lowercase)",
      "description": "1-2 sentence explanation of what learners master",
      "suggested_prerequisite_labels": ["existing node label or another gap label"]
    }}
  ],
  "coverage_status": "full|partial|none",
  "reasoning": "one sentence"
}}"""


NEW_KP_GENERATOR_SYSTEM = "You are a curriculum designer. Return JSON only."

NEW_KP_GENERATOR_USER_TEMPLATE = """\
You are a curriculum designer creating new knowledge nodes that are missing from the existing graph.

Question context:
{question}

Gap skills to define as new nodes:
{gaps_block}

Already-covered terminal nodes (available as prerequisites if relevant):
{covered_block}

Full existing catalog (use IDs from here for prerequisites):
{catalog}

Rules for each new node:
- `temp_id`: a short unique slug you assign (e.g. "new_kp_1") for cross-referencing between new nodes.
- `label`: concise, 2-6 words, lowercase (matches the existing node style).
- `description`: 1-2 sentence explanation of what learners master. No filler.
- `prerequisite_ids`: list of IDs that must be mastered BEFORE this node.
  Use UUIDs from the existing catalog, OR a temp_id of another new node you are creating.
  Do NOT invent fake UUIDs.
- Order new nodes so prerequisites come before the nodes that depend on them
  (i.e., if new_kp_2 requires new_kp_1, list new_kp_1 first).

Return JSON only:
{{
  "new_nodes": [
    {{
      "temp_id": "new_kp_1",
      "label": "...",
      "description": "...",
      "prerequisite_ids": ["existing-uuid-or-temp_id"]
    }}
  ]
}}"""
