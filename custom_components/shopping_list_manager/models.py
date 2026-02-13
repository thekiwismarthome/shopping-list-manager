"""Data models for Shopping List Manager."""
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List, Dict, Any
import uuid


def generate_id() -> str:
    """Generate a unique ID."""
    return str(uuid.uuid4())


def current_timestamp() -> str:
    """Get current ISO timestamp."""
    return datetime.utcnow().isoformat() + "Z"


@dataclass
class Category:
    """Category model."""
    id: str
    name: str
    icon: str
    color: str
    sort_order: int
    system: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class Product:
    """Product model."""
    id: str
    name: str
    category_id: str
    aliases: List[str] = field(default_factory=list)
    default_unit: str = "units"
    default_quantity: float = 1
    price: Optional[float] = None
    currency: Optional[str] = None
    price_per_unit: Optional[float] = None
    price_updated: Optional[str] = None
    image_url: Optional[str] = None
    image_source: Optional[str] = None
    barcode: Optional[str] = None
    brands: List[str] = field(default_factory=list)
    nutrition: Optional[Dict[str, Any]] = None
    user_frequency: int = 0
    last_used: Optional[str] = None
    custom: bool = False
    source: str = "user"
    tags: List[str] = field(default_factory=list)
    collections: List[str] = field(default_factory=list)
    taxonomy: Dict[str, Any] = field(default_factory=dict)
    allergens: List[str] = field(default_factory=list)
    substitution_group: str = ""
    priority_level: int = 0
    image_hint: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class Item:
    """Shopping list item model."""
    id: str
    list_id: str
    name: str
    category_id: str
    product_id: Optional[str] = None
    quantity: float = 1
    unit: str = "units"
    note: Optional[str] = None
    checked: bool = False
    checked_at: Optional[str] = None
    created_at: str = field(default_factory=current_timestamp)
    updated_at: str = field(default_factory=current_timestamp)
    image_url: Optional[str] = None
    order_index: int = 0
    price: Optional[float] = None
    estimated_total: Optional[float] = None
    barcode: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    def calculate_total(self) -> None:
        """Calculate estimated total from quantity and price."""
        if self.price is not None:
            self.estimated_total = self.quantity * self.price


@dataclass
class ShoppingList:
    """Shopping list model."""
    id: str
    name: str
    icon: str = "mdi:cart"
    created_at: str = field(default_factory=current_timestamp)
    updated_at: str = field(default_factory=current_timestamp)
    item_order: List[str] = field(default_factory=list)
    category_order: List[str] = field(default_factory=list)
    active: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
