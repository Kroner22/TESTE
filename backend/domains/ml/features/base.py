"""Abstract feature transformer base class."""

from abc import ABC, abstractmethod
from typing import Optional
import pandas as pd
import numpy as np


class FeatureTransformer(ABC):
    def __init__(self, name: str):
        self.name = name
        self._fitted = False
        self._feature_names: list[str] = []

    @abstractmethod
    def fit(self, matches: pd.DataFrame) -> "FeatureTransformer":
        ...

    @abstractmethod
    def transform(self, matches: pd.DataFrame) -> pd.DataFrame:
        ...

    def fit_transform(self, matches: pd.DataFrame) -> pd.DataFrame:
        return self.fit(matches).transform(matches)

    def get_feature_names(self) -> list[str]:
        return self._feature_names

    @property
    def is_fitted(self) -> bool:
        return self._fitted
