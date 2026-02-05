"""Data models for Shopping List Manager."""
from dataclasses import dataclass, asdict
from typing import Dict


@dataclass
class Product:
    """
    Product catalog entry - authoritative product definition.
    
    Products exist independently of the shopping list.
    They define WHAT can be shopped, not HOW MUCH is needed.
    """
    key: str
    name: str
    category: str = "other"
    unit: str = "pcs"
    image: str = ""
    
    def to_dict(self) -> dict:
        """Convert to dictionary for storage/transmission."""
        return {
            "key": self.key,
            "name": self.name,
            "category": self.category,
            "unit": self.unit,
            "image": self.image
        }
    
    @staticmethod
    def from_dict(data: dict) -> 'Product':
        """Create Product from dictionary."""
        return Product(
            key=data["key"],
            name=data["name"],
            category=data.get("category", "other"),
            unit=data.get("unit", "pcs"),
            image=data.get("image", "")
        )
    
    def __post_init__(self):
        """Validate product data."""
        if not self.key:
            raise ValueError("Product key cannot be empty")
        if not self.name:
            raise ValueError("Product name cannot be empty")


@dataclass
class ActiveItem:
    """
    Shopping list state - quantity only.
    
    Contains NO product metadata, only references products by key.
    qty > 0 means "on the list"
    qty == 0 means "not on the list" (should be removed)
    """
    qty: int
    
    def to_dict(self) -> dict:
        """Convert to dictionary for storage/transmission."""
        return {"qty": self.qty}
    
    @staticmethod
    def from_dict(data: dict) -> 'ActiveItem':
        """Create ActiveItem from dictionary."""
        return ActiveItem(qty=data["qty"])
    
    def __post_init__(self):
        """Validate quantity."""
        if self.qty < 0:
            raise ValueError("Quantity cannot be negative")


class InvariantError(Exception):
    """
    Raised when the core data model invariant is violated.
    
    Invariant: Every key in active_list MUST exist in products.
    
    If this exception is raised, the system is in an inconsistent state
    and must be repaired before continuing.
    """
    pass


def validate_invariant(products: Dict[str, Product], 
                       active_list: Dict[str, ActiveItem]) -> None:
    """
    Validate the core data model invariant.
    
    Args:
        products: Product catalog dictionary
        active_list: Active shopping list dictionary
        
    Raises:
        InvariantError: If any key in active_list doesn't exist in products
    """
    for key in active_list:
        if key not in products:
            raise InvariantError(
                f"Invariant violated: active_list contains unknown product key '{key}'. "
                f"This product must be added to the catalog first."
            )
