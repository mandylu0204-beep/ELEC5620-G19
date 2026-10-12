"""B-owned, read-only business data adapters (no Agent registration)."""

from .synthetic_dataset import ADAPTER_VERSION, SyntheticDataset, SyntheticDatasetAdapter
from .synthetic_dataset_v2 import ADAPTER_VERSION_V2, SyntheticDatasetV2Adapter

__all__ = ['ADAPTER_VERSION', 'SyntheticDataset', 'SyntheticDatasetAdapter', 'ADAPTER_VERSION_V2', 'SyntheticDatasetV2Adapter']
