from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_instant_navigation_stays_off():
    # Instant navigation re-runs inline scripts on page swap and fails on the
    # JSON data blocks that the tour widgets embed, which leaves them unrendered.
    config = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    assert "navigation.instant" not in config
