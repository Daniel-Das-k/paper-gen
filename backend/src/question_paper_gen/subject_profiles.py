from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .models import ContentMap


class SubjectFamily(StrEnum):
    MATHEMATICS = "mathematics"
    COMPUTING = "computing"
    PHYSICAL_SCIENCE = "physical_science"
    LIFE_SCIENCE = "life_science"
    COMMERCE = "commerce"
    HUMANITIES = "humanities"
    GENERAL = "general"


@dataclass(frozen=True)
class SubjectProfile:
    family: SubjectFamily
    guidance: str

    def as_prompt(self) -> str:
        return f"family={self.family.value}; verification_guidance={self.guidance}"


_PROFILES = {
    SubjectFamily.MATHEMATICS: (
        "Independently recompute every numerical answer. Check domain assumptions, "
        "signs, units, notation, and whether exactly one MCQ option is correct. "
        "Numerical distractors must represent distinct plausible errors. Original "
        "values and applications are allowed when they are self-contained and solvable "
        "with a source-supported method."
    ),
    SubjectFamily.COMPUTING: (
        "Trace algorithms and code examples, verify inputs and outputs, distinguish "
        "syntax from semantics, and check complexity or scheduling calculations. "
        "Do not ask about technologies absent from the source."
    ),
    SubjectFamily.PHYSICAL_SCIENCE: (
        "Recompute numerical answers, verify formulas, dimensions, units, significant "
        "figures, and physical assumptions. Original experimental situations and values "
        "must be realistic and self-contained. A diagram must provide necessary information."
    ),
    SubjectFamily.LIFE_SCIENCE: (
        "Verify terminology, biological sequence, structure-function relationships, "
        "and causal claims directly against the source. Original cases may be used only "
        "when all required case facts are stated. Avoid unsupported clinical claims."
    ),
    SubjectFamily.COMMERCE: (
        "Recalculate ratios, interest, statistics, accounting totals, and monetary units. "
        "Ensure original scenarios are self-contained, internally consistent, and "
        "commercially realistic."
    ),
    SubjectFamily.HUMANITIES: (
        "Check dates, names, definitions, interpretations, and causal claims against the "
        "source. Any original source passage needed for analysis must be included in the "
        "question. Higher-order questions must require evidence-based argument, not recall."
    ),
    SubjectFamily.GENERAL: (
        "Verify that every tested concept and method is source-supported, independently "
        "solve original self-contained applications, ensure the workload matches the "
        "marks, and require authentic reasoning at the configured Bloom level."
    ),
}


def infer_subject_profile(content_map: ContentMap) -> SubjectProfile:
    corpus = " ".join(
        [
            content_map.subject,
            *(
                value
                for topic in content_map.topics
                for value in [topic.name, *topic.subtopics]
            ),
        ]
    ).lower()
    keyword_groups = {
        SubjectFamily.MATHEMATICS: {
            "math", "algebra", "calculus", "geometry", "statistics", "probability",
            "arithmetic", "equation", "matrix", "numerical", "trigonometry",
        },
        SubjectFamily.COMPUTING: {
            "computer", "software", "algorithm", "programming", "database", "network",
            "operating system", "cpu", "artificial intelligence", "machine learning",
        },
        SubjectFamily.PHYSICAL_SCIENCE: {
            "physics", "chemistry", "mechanics", "electricity", "thermodynamics",
            "optics", "molecule", "reaction", "circuit",
        },
        SubjectFamily.LIFE_SCIENCE: {
            "biology", "biotechnology", "anatomy", "physiology", "genetics",
            "ecology", "microbiology", "cell",
        },
        SubjectFamily.COMMERCE: {
            "commerce", "accounting", "finance", "economics", "business", "marketing",
            "taxation", "management",
        },
        SubjectFamily.HUMANITIES: {
            "history", "geography", "political science", "sociology", "psychology",
            "literature", "philosophy", "law",
        },
    }
    scores = {
        family: sum(keyword in corpus for keyword in keywords)
        for family, keywords in keyword_groups.items()
    }
    family = max(scores, key=scores.get)
    if scores[family] == 0:
        family = SubjectFamily.GENERAL
    return SubjectProfile(family=family, guidance=_PROFILES[family])
