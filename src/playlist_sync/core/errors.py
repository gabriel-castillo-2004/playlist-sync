"""Error catalog and classification for Playlist Sync (Section 6.3)."""

from __future__ import annotations

import re


class ErrorCode:
    PRIVATE_SOURCE = "PRIVATE_SOURCE"
    SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
    INVALID_URL = "INVALID_URL"
    ITEM_UNAVAILABLE = "ITEM_UNAVAILABLE"
    AGE_RESTRICTED = "AGE_RESTRICTED"
    GEO_BLOCKED = "GEO_BLOCKED"
    RATE_LIMITED = "RATE_LIMITED"
    NETWORK = "NETWORK"
    DISK_FULL = "DISK_FULL"
    TOOL_MISSING = "TOOL_MISSING"
    EMPTY_OR_SHRUNK = "EMPTY_OR_SHRUNK"
    UNKNOWN = "UNKNOWN"


ERROR_MESSAGES: dict[str, str] = {
    ErrorCode.PRIVATE_SOURCE: "Esta playlist es privada. En YouTube cámbiala a Pública o No listada y vuelve a intentar.",
    ErrorCode.SOURCE_NOT_FOUND: "No encontré esa playlist. Revisa que el link esté completo.",
    ErrorCode.INVALID_URL: "Ese link no parece de YouTube ni de un podcast.",
    ErrorCode.ITEM_UNAVAILABLE: "Este video ya no está disponible.",
    ErrorCode.AGE_RESTRICTED: "Este video tiene restricción de edad y no se puede descargar.",
    ErrorCode.GEO_BLOCKED: "Este video no está disponible en tu país.",
    ErrorCode.RATE_LIMITED: "YouTube pidió esperar un poco. Intenta de nuevo en unos minutos.",
    ErrorCode.NETWORK: "No hay conexión a internet.",
    ErrorCode.DISK_FULL: "No hay espacio en el disco.",
    ErrorCode.TOOL_MISSING: "Falta un programa necesario ({nombre}). Ejecuta la revisión del sistema.",
    ErrorCode.EMPTY_OR_SHRUNK: "La playlist apareció vacía o con muchas menos canciones. No cambié nada por seguridad.",
    ErrorCode.UNKNOWN: "Ocurrió un problema inesperado. Se guardó el detalle técnico en el registro.",
}

RETRYABLE_ERRORS = {
    ErrorCode.RATE_LIMITED,
    ErrorCode.NETWORK,
}


class AppError(Exception):
    """Normalized application error (Section 5.2)."""

    def __init__(
        self,
        code: str,
        user_message: str | None = None,
        technical_detail: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        self.code = code
        self.user_message = user_message or ERROR_MESSAGES.get(
            code, ERROR_MESSAGES[ErrorCode.UNKNOWN]
        )
        self.technical_detail = technical_detail or ""
        self.retryable = retryable if retryable is not None else (code in RETRYABLE_ERRORS)
        super().__init__(f"[{self.code}] {self.user_message}: {self.technical_detail}")


def get_user_message(code: str, **kwargs: str) -> str:
    """Retrieve localized user-facing message, formatting placeholders if any."""
    template = ERROR_MESSAGES.get(code, ERROR_MESSAGES[ErrorCode.UNKNOWN])
    if kwargs:
        try:
            return template.format(**kwargs)
        except KeyError:
            return template
    return template


def classify_ytdlp_error(exc: Exception | str) -> AppError:
    """Classify a yt-dlp error string or exception into a standardized AppError."""
    detail = str(exc)
    detail_lower = detail.lower()

    # 1. Private source
    if any(
        phrase in detail_lower
        for phrase in [
            "private playlist",
            "this playlist is private",
            "this video is private",
            "playlist does not exist or is private",
            "sign in if you've been granted access",
        ]
    ):
        return AppError(
            code=ErrorCode.PRIVATE_SOURCE,
            technical_detail=detail,
            retryable=False,
        )

    # 2. Source / Item not found
    if any(
        phrase in detail_lower
        for phrase in [
            "the playlist does not exist",
            "incomplete youtube id",
            "the requested video cannot be found",
            "playlist not found",
            "does not exist",
            "http error 400",
            "bad request",
        ]
    ):
        return AppError(
            code=ErrorCode.SOURCE_NOT_FOUND,
            technical_detail=detail,
            retryable=False,
        )

    # 3. Invalid URL
    if any(
        phrase in detail_lower
        for phrase in [
            "unsupported url",
            "is not a valid url",
        ]
    ):
        return AppError(
            code=ErrorCode.INVALID_URL,
            technical_detail=detail,
            retryable=False,
        )

    # 4. Age restricted
    if any(
        phrase in detail_lower
        for phrase in [
            "sign in to confirm your age",
            "age-restricted",
            "inappropriate for some users",
        ]
    ):
        return AppError(
            code=ErrorCode.AGE_RESTRICTED,
            technical_detail=detail,
            retryable=False,
        )

    # 5. Geo blocked (checked before general unavailable)
    if any(
        phrase in detail_lower
        for phrase in [
            "in your country",
            "geoblocked",
            "blocked in your country",
        ]
    ):
        return AppError(
            code=ErrorCode.GEO_BLOCKED,
            technical_detail=detail,
            retryable=False,
        )

    # 6. Rate limited / Bot detection (checked before general unavailable)
    if any(
        phrase in detail_lower
        for phrase in [
            "http error 429",
            "too many requests",
            "sign in to confirm you're not a bot",
            "not available on this app",
        ]
    ):
        return AppError(
            code=ErrorCode.RATE_LIMITED,
            technical_detail=detail,
            retryable=True,
        )

    # 7. Item unavailable
    if any(
        phrase in detail_lower
        for phrase in [
            "video unavailable",
            "video is unavailable",
            "is unavailable",
            "this video has been removed",
            "this video is no longer available",
            "not available",
            "deleted video",
        ]
    ):
        return AppError(
            code=ErrorCode.ITEM_UNAVAILABLE,
            technical_detail=detail,
            retryable=False,
        )

    # 8. Network failure
    if any(
        phrase in detail_lower
        for phrase in [
            "connection refused",
            "timed out",
            "network is unreachable",
            "urlopen error",
            "failed to establish a new connection",
            "name or service not known",
            "getaddrinfo failed",
            "remotedisconnected",
        ]
    ):
        return AppError(
            code=ErrorCode.NETWORK,
            technical_detail=detail,
            retryable=True,
        )

    # 9. Tool missing
    tool_match = re.search(r"(\w+) is not installed", detail, re.IGNORECASE)
    if tool_match or "ffmpeg not found" in detail_lower:
        tool_name = tool_match.group(1) if tool_match else "ffmpeg"
        return AppError(
            code=ErrorCode.TOOL_MISSING,
            user_message=get_user_message(ErrorCode.TOOL_MISSING, nombre=tool_name),
            technical_detail=detail,
            retryable=False,
        )

    # 10. Disk full
    if any(
        phrase in detail_lower
        for phrase in [
            "no space left on device",
            "disk full",
            "not enough space",
        ]
    ):
        return AppError(
            code=ErrorCode.DISK_FULL,
            technical_detail=detail,
            retryable=False,
        )

    # Default: Unknown
    return AppError(
        code=ErrorCode.UNKNOWN,
        technical_detail=detail,
        retryable=False,
    )
