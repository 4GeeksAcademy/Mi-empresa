from pathlib import Path

import pytest

from data.pipelines.rfp_intake.pipeline import (
    build_department_sections,
    classify_document,
    extract_metadata,
    readability_metrics,
)


def test_modaviva_routes_warehouse_and_reverse_only():
    markdown = """Request for Proposal
    Client: ModaViva
    Spain
    We need warehousing and reverse logistics for our returns.
    We use our own carrier for last mile.
    Deadline: 30 November 2026
    """
    accepted, reason = classify_document(markdown)
    metadata = extract_metadata(markdown)
    sections = build_department_sections(markdown, metadata)

    assert accepted and reason == "customer_request_with_logistics_scope"
    assert metadata["client_name"] == "ModaViva"
    assert metadata["client_country"] == "Spain"
    assert metadata["currency"] == "EUR"
    assert metadata["departments_needed"] == ["warehouse", "reverse"]
    assert [section["department_id"] for section in sections] == ["warehouse", "reverse"]
    assert all(section["approver"] for section in sections)


def test_luna_informal_email_is_accepted_without_inventing_data():
    markdown = "Hi, Luna Cosmetics in Los Angeles is looking for storage and delivery in the US. We expect about 5,000 orders per month."
    accepted, _ = classify_document(markdown)
    metadata = extract_metadata(markdown)

    assert accepted
    assert metadata["client_name"] == "Luna Cosmetics"
    assert metadata["client_country"] == "United States"
    assert metadata["currency"] == "USD"
    assert metadata["monthly_volume"] == 5000
    assert metadata["departments_needed"] == ["warehouse", "lastmile"]
    assert metadata["deadline"] is None
    assert metadata["budget_range"] is None


def test_luna_uploaded_email_wording_is_accepted_and_extracts_volume():
    markdown = """Luna Cosmetics — Los Angeles, CA, USA
    Subject: Looking for a 3PL partner
    We've been doing our own fulfillment but crossed 5,000 orders a month.
    We need someone to handle warehousing and shipping across the US, ideally
    someone who can handle carrier selection. Could you send over a proposal?
    """
    accepted, _ = classify_document(markdown)
    metadata = extract_metadata(markdown)

    assert accepted
    assert metadata["client_name"] == "Luna Cosmetics"
    assert metadata["client_country"] == "United States"
    assert metadata["currency"] == "USD"
    assert metadata["monthly_volume"] == 5000
    assert metadata["departments_needed"] == ["warehouse", "lastmile"]


def test_trackflow_carrier_sales_pitch_is_rejected():
    markdown = """Exclusive shipping rates for TrackFlow
    We'd love the opportunity to become one of TrackFlow's preferred carrier partners.
    We're currently offering aggressive introductory rates.
    """
    accepted, reason = classify_document(markdown)

    assert not accepted
    assert reason == "carrier_sales_pitch"


def test_carrier_rate_pitch_is_rejected():
    accepted, reason = classify_document("We offer shipping and carrier rates to e-commerce brands. Our transportation rates are competitive.")
    assert not accepted
    assert reason == "carrier_sales_pitch"


def test_missing_volume_becomes_open_question_and_readability_is_measured():
    markdown = "Please provide a proposal for warehouse storage in Spain. We want fulfillment services and need an onboarding plan."
    metadata = extract_metadata(markdown)
    sections = build_department_sections(markdown, metadata)
    metrics = readability_metrics(markdown)
    assert sections[0]["open_questions"] == ["What is the expected monthly order volume and storage footprint?"]
    assert metrics["word_count"] > 0
    assert metrics["readable"] is False
