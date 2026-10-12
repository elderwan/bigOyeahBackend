import pytest

from app.services.schedule_service import build_schedule_table_name


@pytest.mark.parametrize(
    ("coach_no", "expected"),
    [
        ("1001", "coach_schedule_1001"),
        ("12345678", "coach_schedule_12345678"),
    ],
)
def test_build_schedule_table_name(coach_no: str, expected: str) -> None:
    assert build_schedule_table_name(coach_no) == expected


@pytest.mark.parametrize("coach_no", ["1", "123", "123456789", "1001;DROP TABLE booking"])
def test_build_schedule_table_name_rejects_invalid_identifiers(coach_no: str) -> None:
    with pytest.raises(ValueError):
        build_schedule_table_name(coach_no)
