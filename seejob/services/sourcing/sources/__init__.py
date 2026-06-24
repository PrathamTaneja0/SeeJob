"""Concrete job source adapters."""

from seejob.services.sourcing.sources.board_api import BoardApiSource
from seejob.services.sourcing.sources.manual import ManualUrlSource
from seejob.services.sourcing.sources.rss import RssJobSource

__all__ = ["BoardApiSource", "ManualUrlSource", "RssJobSource"]
