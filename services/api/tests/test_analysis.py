from incidents.analysis import analyze_incidents_csv


def test_invalid_rows_are_counted_and_excluded() -> None:
    csv_text = """incident_id,category,status,satisfaction_score
I-1,tracking,cerrado,4.5
I-2,,abierto,
I-3,invalida,cerrado,4.8
I-4,soporte,inexistente,
"""

    result = analyze_incidents_csv(csv_text)

    assert result.total_processed == 4
    assert result.total_valid == 1
    assert result.total_invalid == 3
    assert result.invalid_breakdown == {
        "invalid_category": 1,
        "invalid_status": 1,
        "missing_required_field": 1,
    }
    assert result.category_totals == {"tracking": 1}
    assert result.status_totals == {"cerrado": 1}


def test_closed_satisfaction_index_uses_only_valid_closed_rows() -> None:
    csv_text = """incident_id,category,status,satisfaction_score
I-1,tracking,cerrado,5
I-2,tracking,cerrado,3
I-3,tracking,abierto,2
I-4,soporte,cerrado,
"""

    result = analyze_incidents_csv(csv_text)

    assert result.total_processed == 4
    assert result.total_valid == 4
    assert result.total_invalid == 0
    assert result.satisfaction_index_closed == 4.0
