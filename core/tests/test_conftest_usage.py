def test_api_rf_fixture_produces_factory(api_rf):
    request = api_rf.get("/health/")
    assert request.path == "/health/"
