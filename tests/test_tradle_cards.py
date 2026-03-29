from tradle.cards import TradleCardRenderer


def _sample_guesses():
    return [
        {
            "country_iso": "FR",
            "country_name": "France",
            "distance_km": 1442.3,
            "direction": "↗️",
            "proximity_pct": 74,
            "is_correct": False,
        },
        {
            "country_iso": "TH",
            "country_name": "Thailand",
            "distance_km": 0,
            "direction": "🎉",
            "proximity_pct": 100,
            "is_correct": True,
        },
    ]


def test_color_thresholds():
    assert TradleCardRenderer.color_for_proximity(90) == TradleCardRenderer.GREEN
    assert TradleCardRenderer.color_for_proximity(89) == TradleCardRenderer.YELLOW
    assert TradleCardRenderer.color_for_proximity(70) == TradleCardRenderer.YELLOW
    assert TradleCardRenderer.color_for_proximity(69) == TradleCardRenderer.GRAY


def test_format_public_guess_line_no_country_name():
    guess = _sample_guesses()[0]
    line = TradleCardRenderer.format_live_guess_line(guess)
    assert "France" not in line
    assert "1,442 km" in line
    assert "74%" in line


def test_render_live_progress_png():
    buf = TradleCardRenderer.render_live_progress(
        round_id=22,
        player_name="Player1",
        guesses=_sample_guesses(),
        status_text="Player1 is playing Tradle #22",
    )
    assert buf.getvalue().startswith(b"\x89PNG\r\n\x1a\n")


def test_render_round_announcement_png_with_players():
    players = [
        {"name": "A", "score": 2, "guesses": _sample_guesses(), "avatar_bytes": None},
        {"name": "B", "score": 4, "guesses": _sample_guesses()[:1], "avatar_bytes": None},
    ]
    buf = TradleCardRenderer.render_round_announcement(
        new_round_id=23,
        previous_round_id=22,
        players=players,
    )
    assert buf.getvalue().startswith(b"\x89PNG\r\n\x1a\n")


def test_render_round_announcement_png_without_players():
    buf = TradleCardRenderer.render_round_announcement(
        new_round_id=23,
        previous_round_id=22,
        players=[],
    )
    assert buf.getvalue().startswith(b"\x89PNG\r\n\x1a\n")
