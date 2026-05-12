import asyncio
import os
import sys
import json
import typer
import re
from typing import List, Optional
from loguru import logger

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.session import init_db
from app.core.config import settings
from app.documents.item import ItemDocument, ItemMetadata
from app.services.embedding_encoder import encode_text

app = typer.Typer(help="Reko AI Data Ingestion & Seeding Utility")

# STARTER ITEMS (Hardcoded baseline)
STARTER_ITEMS = [
    # MOVIES
    {"name": "King of Boys", "category": "movies", "description": "A Nigerian political thriller following Eniola Salami.", "metadata": {"duration_minutes": 169, "genre": ["Thriller"], "location_tags": ["Lagos"], "nigerian_context": True}, "popularity_score": 0.9},
    {"name": "The Wedding Party", "category": "movies", "description": "A romantic comedy about a lavish Nigerian wedding.", "metadata": {"duration_minutes": 110, "genre": ["Romance"], "location_tags": ["Lagos"], "nigerian_context": True}, "popularity_score": 0.85},
    {"name": "Interstellar", "category": "movies", "description": "Explorers travel through a wormhole to ensure humanity's survival.", "metadata": {"duration_minutes": 169, "genre": ["Sci-Fi"], "nigerian_context": False}, "popularity_score": 0.95},
    # FOOD
    {"name": "Party Jollof Rice", "category": "food", "description": "Spicy smoky Nigerian party jollof rice. A Lagos favorite.", "metadata": {"location_tags": ["Lekki", "Ikeja"], "nigerian_context": True}, "popularity_score": 0.95},
    {"name": "Suya", "category": "food", "description": "Grilled spicy beef skewers. Authentic Northern Nigerian street food.", "metadata": {"location_tags": ["Ikeja", "Abuja"], "nigerian_context": True}, "popularity_score": 0.9},
    # BOOKS
    {"name": "Americanah", "category": "books", "description": "A novel about a young Nigerian woman's experiences with race and identity.", "metadata": {"nigerian_context": True}, "popularity_score": 0.93},
    {"name": "Things Fall Apart", "category": "books", "description": "The classic novel about pre-colonial life in southeastern Nigeria.", "metadata": {"nigerian_context": True}, "popularity_score": 0.95}
]

async def save_item(item_data: dict):
    """Helper to save a single item with embedding."""
    existing = await ItemDocument.find_one(ItemDocument.name == item_data["name"])
    if existing:
        return False
        
    embedding = encode_text(f"{item_data['name']} {item_data['description']}")
    item = ItemDocument(
        name=item_data["name"],
        category=item_data["category"],
        description=item_data["description"],
        embedding=embedding,
        metadata=ItemMetadata(**item_data.get("metadata", {})),
        popularity_score=item_data.get("popularity_score", 0.5)
    )
    await item.insert()
    return True

@app.command()
def starter():
    """Seed the database with hardcoded starter items."""
    async def run():
        await init_db(settings.DATABASE_URL, settings.DATABASE_NAME)
        logger.info(f"🌱 Seeding {len(STARTER_ITEMS)} starter items...")
        count = 0
        for item in STARTER_ITEMS:
            if await save_item(item):
                logger.info(f"✅ Seeded: {item['name']}")
                count += 1
        logger.info(f"✨ Finished. Seeded {count} new items.")
    
    asyncio.run(run())

@app.command()
def amazon(file_path: str, limit: int = 1000):
    """Ingest Amazon Product Data (JSON lines format)."""
    async def run():
        await init_db(settings.DATABASE_URL, settings.DATABASE_NAME)
        logger.info(f"🛒 Ingesting Amazon data from {file_path} (Limit: {limit})...")
        count = 0
        with open(file_path, 'r') as f:
            for line in f:
                if count >= limit: break
                try:
                    data = json.loads(line)
                    name = data.get('title', 'Unknown Product')
                    desc = data.get('description', [''])[0] if isinstance(data.get('description'), list) else data.get('description', '')
                    
                    item = {
                        "name": name,
                        "category": "products",
                        "description": desc or name,
                        "metadata": {
                            "genre": data.get('category', []),
                            "brand": data.get('brand', ''),
                            "price": data.get('price', '')
                        },
                        "popularity_score": 0.5
                    }
                    if await save_item(item):
                        count += 1
                        if count % 50 == 0: logger.info(f"📦 Processed {count} items...")
                except Exception as e:
                    logger.warning(f"⚠️ Skip line: {e}")
        logger.info(f"✨ Finished. Ingested {count} items.")

    asyncio.run(run())

@app.command()
def yelp(file_path: str, limit: int = 1000):
    """Ingest Yelp Business Data (JSON lines format)."""
    async def run():
        await init_db(settings.DATABASE_URL, settings.DATABASE_NAME)
        logger.info(f"🍴 Ingesting Yelp data from {file_path} (Limit: {limit})...")
        count = 0
        with open(file_path, 'r') as f:
            for line in f:
                if count >= limit: break
                try:
                    data = json.loads(line)
                    item = {
                        "name": data['name'],
                        "category": "food" if "Restaurant" in data.get('categories', '') else "services",
                        "description": f"A {data.get('categories')} located in {data.get('city')}.",
                        "metadata": {
                            "location_tags": [data.get('city'), data.get('state')],
                            "stars": data.get('stars'),
                            "review_count": data.get('review_count')
                        },
                        "popularity_score": data.get('stars', 0) / 5.0
                    }
                    if await save_item(item):
                        count += 1
                        if count % 50 == 0: logger.info(f"📍 Processed {count} items...")
                except Exception as e:
                    logger.warning(f"⚠️ Skip line: {e}")
        logger.info(f"✨ Finished. Ingested {count} items.")

    asyncio.run(run())

@app.command()
def goodreads(file_path: str, limit: int = 1000):
    """Ingest Goodreads Book Data (JSON lines format)."""
    async def run():
        await init_db(settings.DATABASE_URL, settings.DATABASE_NAME)
        logger.info(f"📚 Ingesting Goodreads data from {file_path} (Limit: {limit})...")
        count = 0
        with open(file_path, 'r') as f:
            for line in f:
                if count >= limit: break
                try:
                    data = json.loads(line)
                    item = {
                        "name": data.get('title') or data.get('title_without_series'),
                        "category": "books",
                        "description": data.get('description', 'No description available.'),
                        "metadata": {
                            "genre": [g for g in data.get('popular_shelves', []) if len(g) < 20][:3],
                            "publisher": data.get('publisher', '')
                        },
                        "popularity_score": float(data.get('average_rating', 0)) / 5.0
                    }
                    if await save_item(item):
                        count += 1
                        if count % 50 == 0: logger.info(f"📖 Processed {count} items...")
                except Exception as e:
                    logger.warning(f"⚠️ Skip line: {e}")
        logger.info(f"✨ Finished. Ingested {count} items.")

    asyncio.run(run())

if __name__ == "__main__":
    app()
