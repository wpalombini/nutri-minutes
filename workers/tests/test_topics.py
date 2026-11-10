"""The topic list in the database matches the web app's topics."""

import re
from pathlib import Path

from pipeline.db.models import TOPIC_SLUGS

TOPICS_FILE = Path(__file__).resolve().parents[2] / "web" / "content" / "topics.md"


def test_topic_slugs_match_the_web_app() -> None:
    slugs = re.findall(r"^\|[^|]+\|\s*`([a-z0-9-]+)`\s*\|", TOPICS_FILE.read_text(), re.MULTILINE)
    assert tuple(slugs) == TOPIC_SLUGS
