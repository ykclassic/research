from abc import ABC, abstractmethod
from datetime import datetime

from app.models import Quote


class MarketDataProvider(ABC):
    name: str

    @abstractmethod
    async def get_quote(self, internal_symbol: str) -> Quote:
        raise NotImplementedError

    @abstractmethod
    async def health(self) -> bool:
        raise NotImplementedError
