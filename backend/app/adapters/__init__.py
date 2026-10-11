"""B-owned, read-only business data adapters (no Agent registration)."""

from .synthetic_dataset import ADAPTER_VERSION, SyntheticDataset, SyntheticDatasetAdapter

__all__ = ['ADAPTER_VERSION', 'SyntheticDataset', 'SyntheticDatasetAdapter']
