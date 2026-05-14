from abc import ABC, abstractmethod
from typing import List
from src.models import NewsItem


class BaseCollector(ABC):
    """所有采集器的抽象基类。"""

    def __init__(self, config: dict):
        self.enabled = config.get("sources", {}).get(self.source_key, True)

    @property
    @abstractmethod
    def source_key(self) -> str:
        """config.yaml 中对应的 key 名。"""
        pass

    @property
    @abstractmethod
    def source_name(self) -> str:
        """人类可读的来源名称。"""
        pass

    @abstractmethod
    async def fetch(self) -> List[NewsItem]:
        """从数据源获取最新新闻列表。"""
        pass
