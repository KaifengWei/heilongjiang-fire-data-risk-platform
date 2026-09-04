from fire_monitor.app import create_app


def test_statistics_regions_api(
    tmp_path,
):

    app = create_app(
        database_path=(
            tmp_path / "test.sqlite"
        ),
        testing=True,
    )

    client = app.test_client()

    response = client.get(
        "/api/statistics/regions"
    )

    assert (
        response.status_code
        == 200
    )

    data = response.get_json()

    assert (
        "regions"
        in data
    )

    assert isinstance(
        data["regions"],
        list,
    )


def test_statistics_ranking_api(
    tmp_path,
):

    app = create_app(
        database_path=(
            tmp_path / "test.sqlite"
        ),
        testing=True,
    )

    client = app.test_client()

    response = client.get(
        "/api/statistics/ranking"
    )

    assert (
        response.status_code
        == 200
    )

    data = response.get_json()

    assert (
        data["metric"]
        ==
        "burned_area_km2"
    )

    assert isinstance(
        data["ranking"],
        list,
    )