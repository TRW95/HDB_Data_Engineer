import pandas as pd

from hdb_etl.validate import build_reference_domains, validate_records


def sample_df():
    return pd.DataFrame([
        {"month":"2012-01","town":"A","flat_type":"3 ROOM","block":"1","street_name":"X","storey_range":"01 TO 03","floor_area_sqm":60,"flat_model":"Improved","lease_commence_date":1980,"resale_price":200000},
        {"month":"2012-02","town":"B","flat_type":"3 ROOM","block":"2","street_name":"Y","storey_range":"01 TO 03","floor_area_sqm":60,"flat_model":"Improved","lease_commence_date":1980,"resale_price":210000},
    ])


def test_later_unseen_town_is_quarantined():
    df = sample_df()
    domains = build_reference_domains(df, "2012-01", ["town","flat_type","flat_model","storey_range"])
    clean, quarantine = validate_records(df, domains, df.columns, "2012-01", "2017-12")
    assert len(clean) == 1
    assert len(quarantine) == 1
    assert "INVALID_TOWN" in quarantine.iloc[0]["validation_errors"]
