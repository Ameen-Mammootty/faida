"""The ground-truth sign-off stays honest (F8, plan.md §7.1).

"Truth no human checked is not truth" only means something if the checking
survives the next edit. A sign-off records a verdict against *specific file
contents*, so this fails the moment a verified truth file changes underneath
it - which is the signal to go and look again, not a nuisance.

Run from the repo root: apps/api/.venv/bin/python -m pytest eval/tests -q
"""

import hashlib
import json
import pathlib

import pytest

GENERATED = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "generated"
SIGNOFF = GENERATED / "SIGNOFF.json"
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png")


def load() -> dict:
    return json.loads(SIGNOFF.read_text())


def has_image(case: str) -> bool:
    return any((GENERATED / case / f"{case}{suffix}").exists() for suffix in IMAGE_SUFFIXES)


def test_every_case_in_the_corpus_is_accounted_for():
    """A new case cannot quietly join the corpus without a verdict: either a
    human has checked it or it is recorded as unverifiable."""
    signoff = load()
    on_disk = {d.name for d in GENERATED.iterdir() if d.is_dir() and (d / "truth.json").exists()}
    assert on_disk == set(signoff["cases"]), (
        "the corpus and the sign-off disagree about which cases exist; "
        "re-run the review for anything new and update SIGNOFF.json"
    )


@pytest.mark.parametrize("case", sorted(load()["cases"]))
def test_verified_truth_has_not_changed_since_it_was_signed_off(case):
    entry = load()["cases"][case]
    if entry["verdict"] != "ok":
        pytest.skip(f"{case} was not verified ({entry['verdict']})")
    actual = hashlib.sha256((GENERATED / case / "truth.json").read_bytes()).hexdigest()
    assert actual == entry["truth_sha256"], (
        f"{case}/truth.json has changed since it was signed off on "
        f"{load()['reviewed_at']}. A human verified the old contents, not these. "
        f"Re-run Docs/f8-review.html for this case and update SIGNOFF.json."
    )


@pytest.mark.parametrize("case", sorted(load()["cases"]))
def test_an_unverifiable_case_stays_unverifiable_only_while_it_has_no_image(case):
    """The five cases without images cannot be checked against anything. The
    moment someone generates one, it becomes reviewable and must not keep
    coasting on 'unverifiable'."""
    entry = load()["cases"][case]
    if entry["verdict"] != "unverifiable":
        return
    assert not has_image(case), (
        f"{case} now has an image, so its ground truth can finally be checked. "
        f"Review it in Docs/f8-review.html and update SIGNOFF.json."
    )


def test_the_signoff_names_a_person_and_a_commit():
    """A sign-off nobody's name is on is the thing F8 exists to prevent."""
    signoff = load()
    assert signoff["reviewer"].strip() not in ("", "(unnamed)", "unknown")
    assert signoff["repo_commit_at_signoff"].strip()
    assert signoff["reviewed_at"].strip()
