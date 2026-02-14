"""Enhanced product search utilities."""
import logging
from typing import List, Dict, Any, Optional
from rapidfuzz import fuzz, process

_LOGGER = logging.getLogger(__name__)


class ProductSearch:
    """Advanced product search with fuzzy matching and filtering."""
    
    def __init__(self, products: Dict[str, Any]):
        """Initialize search with product catalog.
        
        Args:
            products: Dictionary of product_id -> Product objects
        """
        self.products = products
    
    def search(
        self,
        query: str,
        limit: int = 10,
        exclude_allergens: Optional[List[str]] = None,
        include_tags: Optional[List[str]] = None,
        substitution_group: Optional[str] = None,
        taxonomy_filters: Optional[Dict[str, Any]] = None,
        min_score: int = 60,
    ) -> List[Dict[str, Any]]:
        """Advanced product search with multiple filters.
        
        Args:
            query: Search query string
            limit: Maximum results to return
            exclude_allergens: List of allergens to exclude (e.g., ["milk", "gluten"])
            include_tags: Only include products with these tags
            substitution_group: Filter by substitution group
            taxonomy_filters: Filter by taxonomy (e.g., {"dietary": ["vegan"]})
            min_score: Minimum fuzzy match score (0-100)
            
        Returns:
            List of matching products with scores
        """
        query_lower = query.lower().strip()
        
        if not query_lower:
            return []
        
        candidates = []
        
        for product_id, product in self.products.items():
            # Apply allergen filter
            if exclude_allergens:
                if any(
                    allergen in product.get("allergens", [])
                    for allergen in exclude_allergens
                ):
                    continue
            
            # Apply tag filter
            if include_tags:
                if not any(
                    tag in product.get("tags", [])
                    for tag in include_tags
                ):
                    continue
            
            # Apply substitution group filter
            if substitution_group:
                if product.get("substitution_group") != substitution_group:
                    continue
            
            # Apply taxonomy filters
            if taxonomy_filters:
                product_taxonomy = product.get("taxonomy", {})
                matches_taxonomy = True
                
                for key, values in taxonomy_filters.items():
                    if key not in product_taxonomy:
                        matches_taxonomy = False
                        break
                    
                    product_values = product_taxonomy[key]
                    if isinstance(product_values, list):
                        if not any(v in product_values for v in values):
                            matches_taxonomy = False
                            break
                    else:
                        if product_values not in values:
                            matches_taxonomy = False
                            break
                
                if not matches_taxonomy:
                    continue
            
            # Calculate match score
            score = self._calculate_score(query_lower, product)
            
            if score >= min_score:
                candidates.append({
                    "product": product,
                    "score": score,
                })
        
        # Sort by score (descending), then by user frequency, then by priority
        candidates.sort(
            key=lambda x: (
                x["score"],
                x["product"].get("user_frequency", 0),
                x["product"].get("priority_level", 0),
            ),
            reverse=True
        )
        
        # Return top results
        return [c["product"] for c in candidates[:limit]]
    
    def _calculate_score(self, query: str, product: Dict[str, Any]) -> int:
        """Calculate fuzzy match score for a product.
        
        Args:
            query: Search query
            product: Product dictionary
            
        Returns:
            Score from 0-100
        """
        product_name = product.get("name", "").lower()
        aliases = [a.lower() for a in product.get("aliases", [])]
        
        # Exact match gets highest score
        if query == product_name:
            return 100
        
        # Check aliases for exact match
        if query in aliases:
            return 95
        
        # Check if query is substring of product name
        if query in product_name:
            return 90
        
        # Check if query is substring of any alias
        for alias in aliases:
            if query in alias:
                return 85
        
        # Fuzzy match on product name
        name_score = fuzz.WRatio(query, product_name)
        
        # Fuzzy match on aliases
        alias_scores = [fuzz.WRatio(query, alias) for alias in aliases]
        best_alias_score = max(alias_scores) if alias_scores else 0
        
        # Return best score
        return max(name_score, best_alias_score)
    
    def find_substitutes(self, product_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Find substitute products for a given product.
        
        Args:
            product_id: ID of product to find substitutes for
            limit: Maximum substitutes to return
            
        Returns:
            List of substitute products
        """
        if product_id not in self.products:
            return []
        
        product = self.products[product_id]
        substitution_group = product.get("substitution_group")
        
        if not substitution_group:
            return []
        
        # Find all products in the same substitution group
        substitutes = []
        for pid, p in self.products.items():
            if pid != product_id and p.get("substitution_group") == substitution_group:
                substitutes.append(p)
        
        # Sort by priority and frequency
        substitutes.sort(
            key=lambda x: (
                x.get("priority_level", 0),
                x.get("user_frequency", 0),
            ),
            reverse=True
        )
        
        return substitutes[:limit]
