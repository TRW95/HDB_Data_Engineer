import pandas as pd

from hdb_etl.transform import _block_component, calculate_remaining_lease, create_resale_identifiers, hash_identifiers


def test_block_component():
    assert _block_component("19") == "019"
    assert _block_component("10B") == "010"
    assert _block_component("1A") == "001"
    assert _block_component("123A") == "123"


def test_remaining_lease_year_only_assumption():
    df = pd.DataFrame({"lease_commence_date":[1985]})
    out = calculate_remaining_lease(df, "2027-01-01", 99)
    assert int(out.loc[0, "remaining_lease_years_2027"]) == 57
    assert int(out.loc[0, "remaining_lease_months_2027"]) == 0


def test_identifier_collision_and_hash_uniqueness():
    df = pd.DataFrame([
        {"month":"2012-01","town":"ANG MO KIO","flat_type":"3 ROOM","block":"19","resale_price":230000,"_source_file":"a.csv","_source_row_number":2},
        {"month":"2012-01","town":"ANG MO KIO","flat_type":"3 ROOM","block":"19","resale_price":230000,"_source_file":"a.csv","_source_row_number":3},
    ])
    transformed = create_resale_identifiers(df)
    assert transformed["resale_identifier"].is_unique
    assert transformed["resale_identifier"].str.startswith("S0192301201A-").all()
    hashed = hash_identifiers(transformed, "0123456789abcdef")
    assert hashed["hashed_resale_identifier"].is_unique
    assert "resale_identifier" not in hashed.columns
