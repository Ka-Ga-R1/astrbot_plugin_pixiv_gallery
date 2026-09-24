from pixiv_gallery.config import Settings


def test_settings_defaults_keep_optional_id_features_off_and_redact_token():
    settings = Settings.from_mapping({"refresh_token": "secret-token"})
    assert settings.default_count == 5
    assert settings.enable_artist_random is False
    assert settings.enable_illust_id_send is False
    assert settings.public_dict()["refresh_token_configured"] is True
    assert "refresh_token" not in settings.public_dict()


def test_settings_normalize_bounds_and_proxy():
    settings = Settings.from_mapping(
        {
            "timeout_seconds": 999,
            "default_count": 0,
            "max_count": 999,
            "download_concurrency": -2,
            "proxy": "not-a-url",
        }
    )
    assert settings.timeout_seconds == 120
    assert settings.default_count == 1
    assert settings.max_count == 20
    assert settings.download_concurrency == 1
    assert settings.proxy == ""


def test_settings_parse_boolean_strings_safely():
    settings = Settings.from_mapping(
        {
            "enable_natural_language_tool": "false",
            "enable_fallback_command": "0",
            "filter_r18": "true",
            "allow_group_r18": "1",
        }
    )

    assert settings.enable_natural_language_tool is False
    assert settings.enable_fallback_command is False
    assert settings.filter_r18 is True
    assert settings.allow_group_r18 is True


def test_candidate_count_is_independent_of_total_image_page_cap():
    settings = Settings.from_mapping({"default_count": 8, "max_count": 2})
    assert settings.default_count == 8
    assert settings.max_count == 2


def test_nonfinite_or_unhashable_configuration_is_normalized_without_crashing():
    settings = Settings.from_mapping(
        {"timeout_seconds": float("inf"), "search_target": ["invalid"]}
    )
    assert settings.timeout_seconds == 20
    assert settings.search_target == "partial_match_for_tags"
