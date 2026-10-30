"""Unit tests for error mapping and classification from yt-dlp messages (Section 6.3)."""

from playlist_sync.core.errors import (
    ErrorCode,
    classify_ytdlp_error,
    get_user_message,
)


def test_classify_private_source() -> None:
    errors = [
        "ERROR: [youtube:tab] This playlist is private",
        "ERROR: This video is private. Sign in if you've been granted access to this video",
        "ERROR: The playlist does not exist or is private",
    ]
    for msg in errors:
        err = classify_ytdlp_error(msg)
        assert err.code == ErrorCode.PRIVATE_SOURCE
        assert not err.retryable
        assert "privada" in err.user_message


def test_classify_source_not_found() -> None:
    errors = [
        "ERROR: [youtube:tab] The playlist does not exist",
        "ERROR: [youtube] Incomplete YouTube ID 123",
        "ERROR: The requested video cannot be found",
    ]
    for msg in errors:
        err = classify_ytdlp_error(msg)
        assert err.code == ErrorCode.SOURCE_NOT_FOUND
        assert not err.retryable
        assert "No encontré esa playlist" in err.user_message


def test_classify_invalid_url() -> None:
    errors = [
        "ERROR: Unsupported URL: ftp://example.com/playlist",
        "ERROR: 'foo_bar' is not a valid URL",
    ]
    for msg in errors:
        err = classify_ytdlp_error(msg)
        assert err.code == ErrorCode.INVALID_URL
        assert not err.retryable
        assert "no parece de YouTube" in err.user_message


def test_classify_item_unavailable() -> None:
    errors = [
        "ERROR: Video unavailable. This video has been removed by the uploader",
        "ERROR: This video is no longer available because the YouTube account has been closed",
        "ERROR: [youtube] 12345: Video unavailable",
    ]
    for msg in errors:
        err = classify_ytdlp_error(msg)
        assert err.code == ErrorCode.ITEM_UNAVAILABLE
        assert not err.retryable
        assert "ya no está disponible" in err.user_message


def test_classify_age_restricted() -> None:
    errors = [
        "ERROR: Sign in to confirm your age. This video may be inappropriate for some users",
        "ERROR: [youtube] 12345: age-restricted content",
    ]
    for msg in errors:
        err = classify_ytdlp_error(msg)
        assert err.code == ErrorCode.AGE_RESTRICTED
        assert not err.retryable
        assert "restricción de edad" in err.user_message


def test_classify_geo_blocked() -> None:
    errors = [
        "ERROR: The uploader has not made this video available in your country",
        "ERROR: [youtube] 12345: geoblocked content",
        "ERROR: blocked in your country",
    ]
    for msg in errors:
        err = classify_ytdlp_error(msg)
        assert err.code == ErrorCode.GEO_BLOCKED
        assert not err.retryable
        assert "no está disponible en tu país" in err.user_message


def test_classify_rate_limited() -> None:
    errors = [
        "ERROR: [youtube] 12345: HTTP Error 429: Too Many Requests",
        "ERROR: Sign in to confirm you're not a bot",
        "ERROR: The following content is not available on this app",
    ]
    for msg in errors:
        err = classify_ytdlp_error(msg)
        assert err.code == ErrorCode.RATE_LIMITED
        assert err.retryable
        assert "YouTube pidió esperar" in err.user_message


def test_classify_network() -> None:
    errors = [
        "ERROR: <urlopen error [Errno 11001] getaddrinfo failed>",
        "ERROR: [youtube] 12345: Connection refused",
        "ERROR: The read operation timed out",
        "ERROR: [youtube] 12345: Failed to establish a new connection: Name or service not known",
    ]
    for msg in errors:
        err = classify_ytdlp_error(msg)
        assert err.code == ErrorCode.NETWORK
        assert err.retryable
        assert "No hay conexión a internet" in err.user_message


def test_classify_tool_missing() -> None:
    msg = "ERROR: ffmpeg is not installed"
    err = classify_ytdlp_error(msg)
    assert err.code == ErrorCode.TOOL_MISSING
    assert not err.retryable
    assert "ffmpeg" in err.user_message


def test_classify_disk_full() -> None:
    msg = "ERROR: [download] No space left on device"
    err = classify_ytdlp_error(msg)
    assert err.code == ErrorCode.DISK_FULL
    assert not err.retryable
    assert "No hay espacio en el disco" in err.user_message


def test_classify_unknown() -> None:
    msg = "ERROR: Completely unexpected error 9999"
    err = classify_ytdlp_error(msg)
    assert err.code == ErrorCode.UNKNOWN
    assert not err.retryable
    assert "problema inesperado" in err.user_message


def test_app_error_user_message_formatting() -> None:
    msg = get_user_message(ErrorCode.TOOL_MISSING, nombre="Deno")
    assert "Deno" in msg
    assert "{nombre}" not in msg
