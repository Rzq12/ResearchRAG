"""
Topic classifier for ResearchRAG.
Uses Groq LLM to assign one research topic label per paper from its title + abstract.
Single API call per paper — fast, accurate, no extra model dependencies.
"""

from __future__ import annotations

RESEARCH_TOPICS = [
    "Machine Learning",
    "Deep Learning",
    "NLP / Large Language Models",
    "Computer Vision",
    "RAG / Information Retrieval",
    "Reinforcement Learning",
    "Bioinformatics / Computational Biology",
    "Robotics / Control Systems",
    "Data Science / Statistics",
    "Security / Privacy",
    "Human-Computer Interaction",
    "Other",
]

_CLASSIFY_PROMPT = """\
You are a research topic classifier. Given a paper's title and abstract, \
assign EXACTLY ONE topic from the list below. Respond with only the topic name, nothing else.

Topics:
{topics}

Paper title: {title}
Abstract: {abstract}

Topic:"""


def classify_topic(
    title: str,
    abstract: str,
    groq_api_key: str,
    groq_model: str = "llama-3.3-70b-versatile",
) -> str:
    """
    Classify a paper into one research topic using Groq.
    Returns one of RESEARCH_TOPICS strings, or "Other" on failure.
    """
    try:
        from groq import Groq
        client = Groq(api_key=groq_api_key)
        prompt = _CLASSIFY_PROMPT.format(
            topics   = "\n".join(f"- {t}" for t in RESEARCH_TOPICS),
            title    = title[:200],
            abstract = abstract[:800],
        )
        response = client.chat.completions.create(
            model       = groq_model,
            messages    = [{"role": "user", "content": prompt}],
            temperature = 0.0,
            max_tokens  = 20,
        )
        label = response.choices[0].message.content.strip()
        # Validate: ensure it's one of our known topics
        for t in RESEARCH_TOPICS:
            if t.lower() in label.lower() or label.lower() in t.lower():
                return t
        return "Other"
    except Exception:
        return "Other"


def classify_topics_batch(
    works: list,
    groq_api_key: str,
    groq_model: str = "llama-3.3-70b-versatile",
) -> dict[str, str]:
    """
    Classify a list of OpenAlexWork objects.
    Returns {openalex_id: topic_label}.
    """
    results = {}
    for work in works:
        try:
            label = classify_topic(
                title       = getattr(work, "title", ""),
                abstract    = getattr(work, "abstract", ""),
                groq_api_key = groq_api_key,
                groq_model  = groq_model,
            )
            results[work.openalex_id] = label
        except Exception:
            results[work.openalex_id] = "Other"
    return results


# Topic → badge colour mapping for Streamlit UI
TOPIC_COLOURS: dict[str, str] = {
    "Machine Learning":                  "#6366f1",
    "Deep Learning":                     "#8b5cf6",
    "NLP / Large Language Models":       "#06b6d4",
    "Computer Vision":                   "#10b981",
    "RAG / Information Retrieval":       "#f59e0b",
    "Reinforcement Learning":            "#ef4444",
    "Bioinformatics / Computational Biology": "#84cc16",
    "Robotics / Control Systems":        "#f97316",
    "Data Science / Statistics":         "#3b82f6",
    "Security / Privacy":                "#ec4899",
    "Human-Computer Interaction":        "#14b8a6",
    "Other":                             "#6b7280",
}


def topic_badge_html(topic: str) -> str:
    colour = TOPIC_COLOURS.get(topic, "#6b7280")
    return (
        f"<span style='background:{colour};color:white;"
        f"padding:2px 8px;border-radius:12px;"
        f"font-size:11px;font-weight:600'>{topic}</span>"
    )
