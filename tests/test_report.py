"""ADR-0015 renderer checks: synthetic sources only, no generated analysis files."""

import json

import pytest

from late_delivery import report as R


@pytest.fixture
def report_sources():
    sources = {"money": {"tornado": [{"input": "other"}, {"input": "horizon_days", "low_revenue": 6,
                                                             "high_revenue": 12}],
                         "fx": {"brl_per_usd": 3}},
               "fe": {"primary": {"estimate": 0.4}},
               "ladder": {"rows": [{"method": "Donut RD", "estimate": 0.1}]},
               "robustness": {"checks": [{"id": 10, "estimate": 0.3}]}}
    sources["money"]["flags"] = [{"id": 1, "value": 0.05}]
    sources["fe"]["models"] = [{"id": "low_review/a", "n_obs": 90}]
    for window in (90, 180):
        sources["fe"]["models"].append({"id": f"repeat_{window}d/a", "n_sample": 100, "n_obs": 90,
            "estimates": [{"term": "late", "estimate": -0.01, "ci95_low": -0.02, "ci95_high": 0.005}]})
    sources["ladder"]["rows"] = [{"method": method, "role": "synthetic", "estimate": 0.1,
                                   "ci95_low": 0.05, "ci95_high": 0.15}
                                  for method in ("Matching", "Donut RD", "FE regression", "Naive difference")]
    sources["robustness"]["checks"] = [
        {"id": i, "label": f"Synthetic check {i}", "estimate": 0.3, "ci95_low": 0.2,
         "ci95_high": 0.4, "fired": i == 10} for i in (3, 7, 10)] + [
        {"id": 5, "covariates": [{"covariate": "promised_days", "estimate": 0.5}]},
        {"id": 6, "rv_q1": 0.4, "benchmarks": [{"benchmark": "customer_state", "r2dxj_x": 0.01}]},
        {"id": 8, "estimate": 0.2}]
    sources["robustness"]["flags_fired"] = [10]
    sources["diagnostics"] = {"repeat_mde": [{"window_days": 90, "pooled_base_rate": 0.01}]}
    sources["rd"] = {"estimates": [{"spec": "main", "estimate": 0.1}]}
    return sources


def test_memo_arithmetic_on_synthetic_sources(report_sources):
    assert {k: v for k, v in R.derived(report_sources).items() if k.startswith("memo_")} == {
        "memo_review_scale": 100, "memo_review_more": 40, "memo_rd_more": 10, "memo_disruption_more": 30,
        "memo_horizon_low_brl": 6, "memo_horizon_high_brl": 12,
        "memo_horizon_low_usd": 2, "memo_horizon_high_usd": 4,
    }


def test_writeup_selections_and_small_tables(report_sources):
    d = R.derived(report_sources)
    assert d["writeup_primary"]["n_obs"] == 90
    assert d["writeup_repeat_power"]["window_days"] == 90
    assert "-1.000" in d["writeup_repeat_table"] and "[-2.000, 0.500]" in d["writeup_repeat_table"]
    assert d["writeup_ladder_table"].index("Naive difference") < d["writeup_ladder_table"].index("Matching")
    assert "[0.050, 0.150]" in d["writeup_ladder_table"]
    assert d["writeup_rd"]["estimate"] == 0.1
    assert d["writeup_continuity"]["estimate"] == 0.5
    assert d["writeup_sensitivity"]["rv_q1"] == 0.4
    assert d["writeup_state_benchmark"]["r2dxj_x"] == 0.01
    assert d["writeup_checks_count"] == 6 and d["writeup_flags_count"] == 1
    assert "Synthetic check 10" in d["writeup_robust_table"]
    assert d["writeup_measured_share"] == 0.05


def test_nested_lookup_format_escape_and_determinism():
    sources = {"fe": {"primary": {"estimate": 0.51234}}, "assumptions": {"count": 1234}}
    template = "{{literal}} {fe:primary.estimate:.1%}; {assumptions:count:,}"
    expected = "{literal} 51.2%; 1,234"
    assert R.resolve("{fe:primary.estimate:.2f}", sources) == "0.51"
    assert R.render(template, sources) == expected == R.render(template, sources)


@pytest.mark.parametrize("token", [
    "{unknown:x}", "{fe:missing}", "{fe:nested.missing}", "{fe:rows.0.x}",
    "{fe:rows}", "{fe:nested.x.y}", "{fe:nested.x:bad}", "{fe:.nested}",
    "{fe:nested..x}", "{fe}", "{", "}", "{fe:nested.x", "fe:nested.x}",
])
def test_bad_placeholders_name_template_and_token(token):
    with pytest.raises(ValueError) as exc:
        R.render(token, {"fe": {"nested": {"x": 2}, "rows": [{"x": 1}]}}, template_name="memo.template.md")
    assert "memo.template.md" in str(exc.value)
    # A stray brace has no complete token; its actual brace must still be named.
    assert (token if token.startswith("{") and token.endswith("}") else ("{" if "{" in token else "}")) in str(exc.value)


def test_one_exact_match_and_missing_key_is_not_none():
    rows = [{"id": "a", "value": 3}, {"id": "b", "value": 4}]
    assert R.one(rows, id="b") is rows[1]
    for candidates, match, count in [(rows, {"id": "c"}, 0), (rows * 2, {"id": "a"}, 2),
                                     (rows, {"missing": None}, 0)]:
        with pytest.raises(ValueError, match=f"found {count}"):
            R.one(candidates, **match)


def test_derived_usage_is_shared_across_templates():
    sources = {"report": {"a": 2, "b": {"count": 3}}}
    used = set()
    R.render("{report:a}", sources, used=used)
    with pytest.raises(ValueError, match=r"unused.*\{report:b\}"):
        R.check_unused_derived(sources, used)
    R.render("{report:b.count}", sources, used=used)
    R.check_unused_derived(sources, used)


def test_word_count_and_memo_cap():
    assert R.word_count("# **Plain** _words_ — ! [] () | ---") == 2
    assert R.word_count("don't re-copy reader’s") == 3
    at_cap = "word " * R.C.MEMO_MAX_WORDS
    assert R.render(at_cap, {}, max_words=R.C.MEMO_MAX_WORDS) == at_cap
    with pytest.raises(ValueError, match="memo.template.md.*451.*450"):
        R.render(at_cap + "extra", {}, template_name="memo.template.md", max_words=R.C.MEMO_MAX_WORDS)


def test_links_relative_to_target_not_template(tmp_path):
    report_dir = tmp_path / "docs" / "report"
    report_dir.mkdir(parents=True)
    (tmp_path / "figure (draft).png").touch()
    (tmp_path / "some file.md").touch()
    text = ('![Figure](../../figure%20(draft).png) [Read](<../../some file.md> "Title") '
            '[Web](https://example.com/missing) [Anchor](#heading) [Mail](mailto:x@example.com) '
            '[CDN](//example.com/image.png)\n[ref]: ../../some%20file.md "Title"\n[Read][ref]')
    R.check_links(text, report_dir / "writeup.md")
    R.check_links('[Read](some%20file.md#heading)', tmp_path / "README.md")
    for text in ('[Bad](missing.md)', '![Bad](missing.png)', '[ref]: missing.md\n[Bad][ref]', '[Bad](<missing.md)'):
        with pytest.raises(ValueError, match="writeup.template.md"):
            R.check_links(text, report_dir / "writeup.md", template_name="writeup.template.md")


def test_load_sources_excludes_stale_report_and_rounds(tmp_path, monkeypatch):
    (tmp_path / "fe.json").write_text('{"primary": {"estimate": 0.51234}}')
    (tmp_path / "report.json").write_text('not valid JSON: never read this stale derived file')
    assumptions = tmp_path / "assumptions.toml"
    assumptions.write_text('[inputs]\nvalue = 0.2\n')
    monkeypatch.setattr(R, "derived", lambda s: {"computed": s["fe"]["primary"]["estimate"] / 3})
    sources = R.load_sources(tmp_path, assumptions)
    assert list(sources) == ["fe", "assumptions", "report"]
    assert sources["assumptions"]["inputs"]["value"] == 0.2
    assert sources["report"] == {"computed": 0.17078}


def setup_batch(tmp_path, monkeypatch):
    templates = tmp_path / "templates"
    templates.mkdir()
    report_dir = tmp_path / "docs" / "report"
    report_dir.mkdir(parents=True)
    pairs = tuple((templates / f"{name}.template.md", report_dir / f"{name}.md") for name in ("memo", "writeup"))
    for template, target in pairs:
        template.write_text("{report:value}")
        target.write_text("previous document")
    report_json = tmp_path / "report.json"
    report_json.write_text("previous report JSON")
    monkeypatch.setattr(R.C, "REPORT_DIR", report_dir)
    monkeypatch.setattr(R.C, "REPORT_JSON", report_json)
    monkeypatch.setattr(R.C, "REPORT_TEMPLATES", pairs)
    monkeypatch.setattr(R, "load_sources", lambda: {"report": {"value": 0.123456}})
    return pairs, report_json


@pytest.mark.parametrize("bad", ["{missing:value}", "[Bad](missing.md)", "word " * 451])
def test_batch_errors_leave_all_previous_documents_untouched(tmp_path, monkeypatch, bad):
    pairs, report_json = setup_batch(tmp_path, monkeypatch)
    # Put errors in the second document, except the memo-only word cap.
    index = 0 if bad.startswith("word ") else 1
    pairs[index][0].write_text(bad)
    with pytest.raises(ValueError):
        R.main()
    assert report_json.read_text() == "previous report JSON"
    assert all(target.read_text() == "previous document" for _, target in pairs)


def test_main_deterministic_json_documents_and_printed_counts(tmp_path, monkeypatch, capsys):
    pairs, report_json = setup_batch(tmp_path, monkeypatch)
    R.main()
    first = [p.read_bytes() for p in (report_json, *(target for _, target in pairs))]
    R.main()
    assert first == [p.read_bytes() for p in (report_json, *(target for _, target in pairs))]
    assert json.loads(first[0]) == {"value": 0.123456}
    assert first[0].endswith(b"\n")
    assert "words" in capsys.readouterr().out


def test_unused_derived_stops_batch_before_writes(tmp_path, monkeypatch):
    pairs, report_json = setup_batch(tmp_path, monkeypatch)
    monkeypatch.setattr(R, "load_sources", lambda: {"report": {"value": 2, "unused": 3}})
    with pytest.raises(ValueError, match=r"unused.*\{report:unused\}"):
        R.main()
    assert report_json.read_text() == "previous report JSON"
    assert all(target.read_text() == "previous document" for _, target in pairs)
