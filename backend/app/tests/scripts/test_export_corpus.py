"""export_corpus: the parts that decide what leaves the task. The DB and S3
are faked; no real corpus is built."""

from datetime import UTC, datetime

from app.scripts import export_corpus


def test_dry_run_review_list_goes_to_a_short_lived_key_not_stdout(monkeypatch, capsys):
    # The candidate-name list may hold a patient name every detector missed.
    # In-VPC, stdout is CloudWatch — so the names go to a tmp-uploads/ key
    # (1-day lifecycle) and only the key is printed.
    written: dict = {}
    monkeypatch.setattr(export_corpus.s3, "put_text", lambda key, text: written.update({key: text}))
    stamp = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
    key = export_corpus._write_review_list({"Zorp Yelling", "Acme Health"}, stamp)
    assert key == "tmp-uploads/corpus-review/20260829-120000.txt"
    assert written == {key: "Acme Health\nZorp Yelling\n"}
    assert "Zorp" not in capsys.readouterr().out
