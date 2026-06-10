from app.domain.snowflake import (
    SnowflakeGenerator,
    extract_app_id,
    extract_node_id,
)


def test_snowflake_contains_app_and_node_ids() -> None:
    generator = SnowflakeGenerator(app_id=3, node_id=7)

    snowflake_id = generator.next_id()

    assert extract_app_id(snowflake_id) == 3
    assert extract_node_id(snowflake_id) == 7


def test_snowflake_generates_monotonic_ids() -> None:
    generator = SnowflakeGenerator(app_id=1, node_id=1)

    first_id = generator.next_id()
    second_id = generator.next_id()

    assert second_id > first_id
