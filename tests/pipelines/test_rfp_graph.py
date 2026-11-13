from services.rfp_graph import process_rfp_markdown


def test_graph_fans_out_to_only_requested_departments_and_synthesizes_handoff(tmp_path):
    markdown = """Request for Proposal
Client: ModaViva
Spain
We need warehousing and reverse logistics for our returns.
We use our own carrier for last mile.
"""
    markdown_path = tmp_path / "source.md"
    markdown_path.write_text(markdown, encoding="utf-8")
    result = process_rfp_markdown(markdown_path.read_text(encoding="utf-8"), str(markdown_path))
    assert result["accepted"]
    assert [worker["department_id"] for worker in result["department_sections"]] == ["warehouse", "reverse"]
    assert result["handoff"]["source_markdown_path"] == str(tmp_path / "source.md")
    assert result["handoff"]["department_workstreams"] == result["department_sections"]
    assert all("pdf" not in str(worker).casefold() for worker in result["department_sections"])


def test_graph_rejects_carrier_pitch_without_metadata_or_department_workers(tmp_path):
    markdown = "We offer shipping and carrier rates to e-commerce brands. Our transportation rates are competitive."
    result = process_rfp_markdown(markdown, str(tmp_path / "pitch.md"))

    assert result["accepted"] is False
    assert result["reason"] == "carrier_sales_pitch"
    assert "metadata" not in result
    assert "department_sections" not in result
