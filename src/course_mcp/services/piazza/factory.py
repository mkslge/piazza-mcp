from course_mcp.config import get_piazza_config

from .client import PiazzaClient
from .normalizer import PiazzaNormalizer
from .service import PiazzaService


_piazza_service: PiazzaService | None = None


def get_piazza_service() -> PiazzaService:
    """Return the lazily initialized configured Piazza service."""
    global _piazza_service

    if _piazza_service is None:
        config = get_piazza_config()
        _piazza_service = PiazzaService(
            config,
            PiazzaClient(config),
            PiazzaNormalizer(),
        )
    return _piazza_service
