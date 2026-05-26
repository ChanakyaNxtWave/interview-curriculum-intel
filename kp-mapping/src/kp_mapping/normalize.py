from __future__ import annotations

import logging
import re

import dspy

from .interview_store import InterviewStore
from .theory.dspy_modules import configure_lm
from .theory.store import TheoryStore

logger = logging.getLogger("kp_mapping.normalize")

NORMALIZER_VERSION = "normalizer-v1"
SLUG_MERGE_JACCARD_THRESHOLD = 0.7


class NormalizeQuestion(dspy.Signature):
    """Generate a stable canonical phrasing + slug for an interview question.

    Two questions that ask the same thing in different words must produce
    the same canonical_slug. The slug should be short, lowercase, snake_case,
    and stable across paraphrases.

    If the question is semantically equivalent to one of the
    existing_canonical_slugs (provided for this company), REUSE that
    exact slug verbatim — do not invent a near-duplicate.
    """

    question: str = dspy.InputField()
    company: str = dspy.InputField()
    existing_canonical_slugs: str = dspy.InputField(
        desc="Newline list of canonical_slugs already used for this company. "
             "Reuse one verbatim if the meaning matches."
    )
    canonical_question: str = dspy.OutputField(
        desc='Short canonical phrasing, e.g. "What is the difference between while and do-while loop?"'
    )
    canonical_slug: str = dspy.OutputField(
        desc='snake_case, 3-6 tokens, stable across paraphrases, e.g. "while_vs_do_while_loop"'
    )


class Normalizer(dspy.Module):
    def __init__(self) -> None:
        super().__init__()
        self.pred = dspy.Predict(NormalizeQuestion)


_PIPELINE: Normalizer | None = None


def _pipeline() -> Normalizer:
    global _PIPELINE
    if _PIPELINE is None:
        configure_lm()
        _PIPELINE = Normalizer()
    return _PIPELINE


def _slug_tokens(slug: str) -> set[str]:
    return {t for t in re.split(r"[_\s]+", (slug or "").lower()) if t}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def _sanitize_slug(raw: str) -> str:
    if not raw:
        return ""
    s = raw.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def normalize_pending_groups(
    store: InterviewStore,
    *,
    limit: int = 50,
    theory_store: TheoryStore | None = None,
) -> dict:
    """Normalize up to `limit` pending groups. Merge semantically-equivalent ones.

    When a group is merged into a winner, also delete the loser group's
    representative theory_question_tags row (if any) so that the JOIN displays
    the winner's verdict.
    """
    pending = store.pending_normalization_groups(limit=limit)
    if not pending:
        return {"normalized": 0, "merged": 0, "remaining": 0}

    pipeline = _pipeline()
    normalized_count = 0
    merged_count = 0

    for grp in pending:
        company = grp.get("company_name") or ""
        existing = store.normalized_groups_for_company(company) if company else []
        existing = [e for e in existing if e["group_key"] != grp["group_key"]]
        existing_slug_text = "\n".join(
            f"- {e['canonical_slug']}: {e['canonical_question']}"
            for e in existing
            if e.get("canonical_slug")
        )
        try:
            pred = pipeline.pred(
                question=grp["exact_question"],
                company=company,
                existing_canonical_slugs=existing_slug_text or "(none yet)",
            )
        except Exception as exc:
            logger.exception("Normalizer LLM call failed for %s: %s", grp["group_key"], exc)
            continue

        canonical_question = str(pred.canonical_question or "").strip()
        candidate_slug = _sanitize_slug(str(pred.canonical_slug or ""))
        if not canonical_question or not candidate_slug:
            logger.warning(
                "Empty normalizer output for group %s, skipping", grp["group_key"]
            )
            continue

        winner = _find_merge_target(existing, candidate_slug)
        if winner is not None:
            store.merge_group(
                loser_key=grp["group_key"],
                winner_key=winner["group_key"],
                normalizer_version=NORMALIZER_VERSION,
            )
            # Drop the loser group's theory tag so the JOIN surfaces the winner's
            if theory_store is not None:
                loser_rep = grp.get("representative_row_key")
                if loser_rep:
                    theory_store.delete_tag(loser_rep)
            merged_count += 1
            logger.info(
                "Merged group %s -> %s (slug %s ~= %s)",
                grp["group_key"],
                winner["group_key"],
                candidate_slug,
                winner["canonical_slug"],
            )
        else:
            store.mark_group_normalized(
                grp["group_key"],
                canonical_question=canonical_question,
                canonical_slug=candidate_slug,
                normalizer_version=NORMALIZER_VERSION,
            )
            normalized_count += 1

    status = store.normalize_status()
    return {
        "normalized": normalized_count,
        "merged": merged_count,
        "remaining": status["pending"],
        "status": status,
    }


def _find_merge_target(existing: list[dict], candidate_slug: str) -> dict | None:
    cand_tokens = _slug_tokens(candidate_slug)
    best: tuple[float, dict] | None = None
    for e in existing:
        slug = e.get("canonical_slug") or ""
        if slug == candidate_slug:
            return e
        score = _jaccard(cand_tokens, _slug_tokens(slug))
        if score >= SLUG_MERGE_JACCARD_THRESHOLD:
            if best is None or score > best[0]:
                best = (score, e)
    return best[1] if best else None
