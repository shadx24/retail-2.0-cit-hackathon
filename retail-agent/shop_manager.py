"""
Shop Manager & Category-Based Keyword System
Handles multi-tenant shop management and category-specific keywords.
"""
from typing import List, Optional, Dict, Set
from dataclasses import dataclass
from datetime import datetime

from database import SupabaseStore
from config import CORE_VOCABULARY


@dataclass
class Shop:
    """Shop/tenant configuration."""
    id: int
    shop_name: str
    shop_domain: str
    category: str  # e.g., 'electronics', 'fashion', 'appliances'
    description: str
    is_active: bool
    created_at: datetime
    last_active: datetime


@dataclass
class CategoryKeywords:
    """Category-specific keyword collection."""
    category: str
    core_keywords: List[str]
    product_specific: List[str]
    competitor_keywords: List[str]
    total_keywords: int


class ShopManager:
    """
    Multi-tenant shop management.
    Each shop has its own category focus and keyword set.
    """

    def __init__(self, db: SupabaseStore):
        self.db = db

    async def create_shop(self, shop_name: str, shop_domain: str, category: str, description: str = "") -> Optional[Shop]:
        """Create a new shop/tenant."""
        result = self.db.client.table("shops").insert({
            "shop_name": shop_name,
            "shop_domain": shop_domain,
            "category": category,
            "description": description,
            "is_active": True,
            "created_at": datetime.utcnow().isoformat(),
            "last_active": datetime.utcnow().isoformat()
        }).execute()

        if result.data:
            data = result.data[0]
            return Shop(
                id=data["id"],
                shop_name=data["shop_name"],
                shop_domain=data["shop_domain"],
                category=data["category"],
                description=data["description"],
                is_active=data["is_active"],
                created_at=datetime.fromisoformat(data["created_at"]),
                last_active=datetime.fromisoformat(data["last_active"])
            )
        return None

    async def get_shop(self, shop_id: int) -> Optional[Shop]:
        """Get shop by ID."""
        result = self.db.client.table("shops")\
            .select("*")\
            .eq("id", shop_id)\
            .limit(1)\
            .execute()

        if result.data:
            data = result.data[0]
            return Shop(
                id=data["id"],
                shop_name=data["shop_name"],
                shop_domain=data["shop_domain"],
                category=data["category"],
                description=data["description"],
                is_active=data["is_active"],
                created_at=datetime.fromisoformat(data["created_at"]),
                last_active=datetime.fromisoformat(data["last_active"])
            )
        return None

    async def get_shop_by_name(self, shop_name: str) -> Optional[Shop]:
        """Get shop by name."""
        result = self.db.client.table("shops")\
            .select("*")\
            .eq("shop_name", shop_name)\
            .limit(1)\
            .execute()

        if result.data:
            data = result.data[0]
            return Shop(
                id=data["id"],
                shop_name=data["shop_name"],
                shop_domain=data["shop_domain"],
                category=data["category"],
                description=data["description"],
                is_active=data["is_active"],
                created_at=datetime.fromisoformat(data["created_at"]),
                last_active=datetime.fromisoformat(data["last_active"])
            )
        return None

    async def list_shops(self, active_only: bool = True) -> List[Shop]:
        """List all shops."""
        query = self.db.client.table("shops").select("*")
        if active_only:
            query = query.eq("is_active", True)
        
        result = query.execute()
        shops = []
        for data in result.data:
            shops.append(Shop(
                id=data["id"],
                shop_name=data["shop_name"],
                shop_domain=data["shop_domain"],
                category=data["category"],
                description=data["description"],
                is_active=data["is_active"],
                created_at=datetime.fromisoformat(data["created_at"]),
                last_active=datetime.fromisoformat(data["last_active"])
            ))
        return shops

    async def update_shop_last_active(self, shop_id: int):
        """Update shop's last active timestamp."""
        self.db.client.table("shops")\
            .update({"last_active": datetime.utcnow().isoformat()})\
            .eq("id", shop_id)\
            .execute()

    async def deactivate_shop(self, shop_id: int):
        """Deactivate a shop."""
        self.db.client.table("shops")\
            .update({"is_active": False})\
            .eq("id", shop_id)\
            .execute()


class CategoryKeywordManager:
    """
    Manage category-specific keywords for product discovery.
    Each shop gets keywords matched to their category.
    """

    def __init__(self, db: SupabaseStore):
        self.db = db
        self.category_keywords = self._init_category_keywords()

    def _init_category_keywords(self) -> Dict[str, CategoryKeywords]:
        """Initialize category → keywords mapping."""
        return {
            "electronics": CategoryKeywords(
                category="electronics",
                core_keywords=[
                    "price", "deal", "discount", "sale", "offer",
                    "smartphone", "laptop", "tablet", "headphones",
                    "monitor", "keyboard", "mouse", "camera",
                    "best price", "lowest price", "buy online", "shop online"
                ],
                product_specific=[
                    "iPhone", "Samsung", "MacBook", "Dell", "HP",
                    "Sony", "LG", "Canon", "Nikon", "GoPro"
                ],
                competitor_keywords=[
                    "amazon electronics", "flipkart electronics", "bestbuy",
                    "newegg", "walmart electronics", "target electronics"
                ],
                total_keywords=0
            ),
            "fashion": CategoryKeywords(
                category="fashion",
                core_keywords=[
                    "price", "discount", "sale", "offer", "deal",
                    "clothing", "shoes", "dress", "shirt", "pant",
                    "best price", "lowest price", "buy online", "shop"
                ],
                product_specific=[
                    "Nike", "Adidas", "Puma", "Gucci", "Zara",
                    "H&M", "Forever 21", "Calvin Klein", "Tommy Hilfiger"
                ],
                competitor_keywords=[
                    "amazon fashion", "flipkart fashion", "myntra",
                    "forever 21", "zara", "h&m online"
                ],
                total_keywords=0
            ),
            "appliances": CategoryKeywords(
                category="appliances",
                core_keywords=[
                    "price", "discount", "sale", "offer", "deal",
                    "refrigerator", "washing machine", "microwave", "oven",
                    "cooker", "blender", "best price", "buy online"
                ],
                product_specific=[
                    "LG appliances", "Samsung appliances", "Whirlpool",
                    "Godrej", "Bosch", "IFB", "Haier", "Philips"
                ],
                competitor_keywords=[
                    "amazon appliances", "flipkart appliances", "bestbuy",
                    "walmart appliances", "target appliances", "croma"
                ],
                total_keywords=0
            ),
            "books": CategoryKeywords(
                category="books",
                core_keywords=[
                    "price", "discount", "sale", "offer", "deal",
                    "book", "ebook", "novel", "fiction", "non-fiction",
                    "best price", "buy online", "shop"
                ],
                product_specific=[
                    "Stephen King", "JK Rowling", "Dan Brown",
                    "Agatha Christie", "J.R.R. Tolkien"
                ],
                competitor_keywords=[
                    "amazon books", "flipkart books", "goodreads",
                    "bookswagon", "kindle"
                ],
                total_keywords=0
            ),
            "home": CategoryKeywords(
                category="home",
                core_keywords=[
                    "price", "discount", "sale", "offer", "deal",
                    "furniture", "decor", "bedding", "kitchen",
                    "best price", "buy online", "shop"
                ],
                product_specific=[
                    "sofa", "bed", "table", "chair", "shelf",
                    "lamp", "curtain", "rug", "pillow", "mattress"
                ],
                competitor_keywords=[
                    "amazon furniture", "flipkart furniture", "ikea",
                    "urban ladder", "woodenstreet", "pepperfry"
                ],
                total_keywords=0
            ),
            "gaming": CategoryKeywords(
                category="gaming",
                core_keywords=[
                    "price", "deal", "discount", "sale", "offer",
                    "gaming laptop", "gaming mouse", "gaming keyboard",
                    "gaming headset", "gaming monitor", "gaming chair",
                    "best price", "lowest price", "buy online", "shop online"
                ],
                product_specific=[
                    "RTX 4080", "RTX 4090", "RTX 5090", "Mechanical Keyboard",
                    "Gaming Mouse", "PS5 Console", "Xbox Series X",
                    "Nintendo Switch", "OLED Monitor", "Razer",
                    "Logitech G Pro", "Corsair", "SteelSeries",
                    "HyperX", "ASUS ROG", "MSI Gaming"
                ],
                competitor_keywords=[
                    "amazon gaming", "flipkart gaming", "croma gaming",
                    "mdcomputers", "pcstudio", "vedantcomputers",
                    "primeabgb", "elitehubs gaming"
                ],
                total_keywords=0
            )
        }

    async def get_keywords_for_category(self, category: str) -> CategoryKeywords:
        """Get all keywords for a specific category."""
        if category.lower() in self.category_keywords:
            return self.category_keywords[category.lower()]
        
        # Default to generic keywords if category not found
        return CategoryKeywords(
            category=category,
            core_keywords=list(CORE_VOCABULARY.get("price_terms", [])),
            product_specific=[],
            competitor_keywords=[],
            total_keywords=0
        )

    async def initialize_shop_keywords(self, shop_id: int, category: str):
        """
        Initialize keyword pool for a shop's category.
        Populates keyword_pool table with category-specific terms.
        """
        keywords = await self.get_keywords_for_category(category)

        # Combine all keywords
        all_keywords = (
            keywords.core_keywords +
            keywords.product_specific +
            keywords.competitor_keywords
        )

        # Insert into database
        keyword_records = []
        for keyword in all_keywords:
            keyword_records.append({
                "term": keyword,
                "shop_id": shop_id,
                "product_category": category,
                "category": "core",
                "yield_score": 1.0,
                "is_active": True,
                "usage_count": 0,
                "last_used": datetime.utcnow().isoformat()
            })

        # Upsert to avoid duplicates
        for record in keyword_records:
            try:
                self.db.client.table("keyword_pool").upsert([record]).execute()
            except:
                pass  # Skip duplicates

    async def get_active_keywords_for_shop(self, shop_id: int, category: str, limit: int = 500) -> List[str]:
        """
        Get active keywords for a specific shop and category.
        Sorted by yield score (most effective first).
        """
        result = self.db.client.table("keyword_pool")\
            .select("term")\
            .eq("shop_id", shop_id)\
            .eq("product_category", category)\
            .eq("is_active", True)\
            .order("yield_score", desc=True)\
            .limit(limit)\
            .execute()

        return [row["term"] for row in result.data]

    async def add_learned_keyword(self, shop_id: int, term: str, category: str, yield_score: float = 1.5):
        """
        Add a new learned keyword discovered during product scraping.
        """
        self.db.client.table("keyword_pool").insert({
            "term": term,
            "shop_id": shop_id,
            "product_category": category,
            "category": "learned",
            "yield_score": yield_score,
            "is_active": True,
            "usage_count": 1,
            "last_used": datetime.utcnow().isoformat()
        }).upsert(on_conflict="term, shop_id, product_category").execute()

    async def update_keyword_yield(self, shop_id: int, term: str, category: str, success: bool):
        """
        Update keyword yield score based on search success.
        Successful searches increase yield; unsuccessful decrease it.
        """
        result = self.db.client.table("keyword_pool")\
            .select("yield_score")\
            .eq("term", term)\
            .eq("shop_id", shop_id)\
            .eq("product_category", category)\
            .limit(1)\
            .execute()

        if not result.data:
            return

        current_score = result.data[0]["yield_score"]
        new_score = current_score * 1.1 if success else current_score * 0.9
        new_score = max(0.1, min(3.0, new_score))  # Clamp between 0.1 and 3.0

        self.db.client.table("keyword_pool")\
            .update({
                "yield_score": new_score,
                "usage_count": current_score + 1,
                "last_used": datetime.utcnow().isoformat()
            })\
            .eq("term", term)\
            .eq("shop_id", shop_id)\
            .eq("product_category", category)\
            .execute()


class ProductDiscoveryFilter:
    """
    Filter discovered products to shop's specific domain/category.
    """

    def __init__(self, shop: Shop):
        self.shop = shop

    def should_process_product(self, product_name: str, product_category: str) -> bool:
        """
        Determine if a product should be processed for this shop.
        Shop only cares about their category.
        """
        # If product has explicit category, check if it matches
        if product_category:
            return product_category.lower() == self.shop.category.lower()

        # If no explicit category, assume it might be relevant
        return True

    def filter_competitors(self, competitors: List[str], shop_domain: str) -> List[str]:
        """
        Filter out the shop's own domain from competitor list.
        We only want to track actual competitors, not our own site.
        """
        return [c for c in competitors if c != shop_domain]

    def format_search_query(self, base_query: str) -> str:
        """
        Format search query for category specificity.
        
        Example:
            base_query: "iPhone 15"
            shop.category: "electronics"
            result: "iPhone 15 electronics price"
        """
        # Add category and price-finding terms
        return f"{base_query} {self.shop.category} price deal"


if __name__ == "__main__":
    import asyncio
    from database import SupabaseStore

    async def test():
        db = SupabaseStore()
        shop_mgr = ShopManager(db)
        keyword_mgr = CategoryKeywordManager(db)

        # Create a shop
        shop = await shop_mgr.create_shop(
            shop_name="ElectroHub",
            shop_domain="electrohub.com",
            category="electronics",
            description="Premium electronics retailer"
        )

        if shop:
            print(f"✓ Created shop: {shop.shop_name} (ID: {shop.id}, Category: {shop.category})")

            # Initialize keywords for this shop
            await keyword_mgr.initialize_shop_keywords(shop.id, shop.category)
            print(f"✓ Initialized {shop.category} keywords for shop")

            # Get keywords
            keywords = await keyword_mgr.get_active_keywords_for_shop(shop.id, shop.category, limit=20)
            print(f"✓ Got {len(keywords)} keywords: {keywords[:5]}")

    asyncio.run(test())
