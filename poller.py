import asyncio
import os
from typing import Optional, List

import aiohttp
import redis.asyncio as redis
import feedparser
from dotenv import load_dotenv
from loguru import logger

from incident_parser import IncidentParser
from alert_formatter import AlertFormatter

# Load environment variables
load_dotenv()

# Configuration
RSS_FEED_URL = os.getenv("RSS_FEED_URL", "https://status.openai.com/history.rss")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "30"))  # 30s for RSS (event-driven on provider side)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

def setup_logger():
    logger.remove()
    logger.add(
        lambda msg: print(msg, end=""),
        format="<level>[{time:YYYY-MM-DD HH:mm:ss}]</level> <level>{level: <8}</level> {message}",
        colorize=True,
        level=LOG_LEVEL,
    )

class RSSMonitor:
    """Event-based RSS feed monitor for status page incidents."""

    def __init__(self, redis_url: str = REDIS_URL):
        self.redis_url = redis_url
        self.redis_client: redis.Redis | None = None
        self.session: aiohttp.ClientSession | None = None
        self.parser = IncidentParser()
        self.formatter = AlertFormatter()

    async def init(self):
        """Initialize Redis connection and HTTP session."""
        try:
            self.redis_client = await redis.from_url(self.redis_url)
            logger.info("Connected to Redis")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

        self.session = aiohttp.ClientSession()
        logger.info("HTTP session initialized")

    async def close(self):
        """Cleanup resources."""
        if self.session:
            await self.session.close()
        if self.redis_client:
            await self.redis_client.close()

    async def fetch_rss_feed(self) -> Optional[str]:
        """Fetch RSS feed content."""
        try:
            if self.session is None:
                logger.error("HTTP session not initialized")
                return None
            
            async with self.session.get(
                RSS_FEED_URL, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    logger.error(f"RSS fetch failed: HTTP {resp.status}")
                    return None
                return await resp.text()
        except asyncio.TimeoutError:
            logger.error("RSS fetch timeout")
            return None
        except Exception as e:
            logger.error(f"RSS fetch error: {e}")
            return None

    async def get_cached_incidents(self) -> List[str]:
        """Retrieve cached incident IDs from Redis."""
        try:
            if self.redis_client is None:
                logger.error("Redis client not initialized")
                return []
            cached = await self.redis_client.get("openai:incidents:tracked")
            if cached:
                return cached.decode().split(",")
            return []
        except Exception as e:
            logger.error(f"Redis read error: {e}")
            return []

    async def cache_incidents(self, incident_ids: List[str]):
        """Store incident IDs in Redis."""
        try:
            if self.redis_client is None:
                logger.error("Redis client not initialized")
                return
            if not incident_ids:
                # Clear cache if no active incidents
                await self.redis_client.delete("openai:incidents:tracked")
                return
            cache_key = ",".join(incident_ids)
            await self.redis_client.setex("openai:incidents:tracked", 3600, cache_key)
        except Exception as e:
            logger.error(f"Redis write error: {e}")

    def _extract_incidents(self, feed) -> List[dict]:
        """Extract incidents from feed entries."""
        incidents = []
        for entry in feed.entries:
            incident = self.parser.parse_entry(entry)
            if incident:
                incidents.append(incident)
        return incidents

    def _log_incidents(self, active_incidents: List[dict]):
        """Log active incidents and format alerts."""
        if active_incidents:
            logger.info(f"Found {len(active_incidents)} active incident(s)")
            for incident in active_incidents:
                alert = {
                    "product": incident["title"],
                    "status": incident["status"],
                    "description": incident["description"],
                }
                alert_msg = self.formatter.format_alert(alert)
                print(alert_msg)
                logger.info(alert_msg)
        else:
            logger.info("All incidents resolved")

    async def poll_once(self):
        """Execute a single feed check cycle."""
        logger.debug("Checking RSS feed")

        # Fetch RSS feed
        rss_content = await self.fetch_rss_feed()
        if rss_content is None:
            logger.debug("RSS feed check skipped (no data)")
            return

        # Parse RSS feed
        feed = feedparser.parse(rss_content)
        
        # Extract incidents from feed entries
        incidents = self._extract_incidents(feed)

        # Filter to active incidents only (exclude resolved)
        active_incidents = self.parser.filter_active_incidents(incidents)

        # Get previously tracked incident IDs
        cached_ids = await self.get_cached_incidents()

        # Check for changes
        if not self.parser.has_incident_changed(active_incidents, cached_ids):
            logger.debug("No new incidents detected")
            return

        # Log new or updated incidents
        self._log_incidents(active_incidents)

        # Update cache with new incident IDs
        incident_ids = [inc["id"] for inc in active_incidents]
        await self.cache_incidents(incident_ids)
        logger.debug("RSS feed check complete")

    async def run(self):
        """Main monitoring loop."""
        try:
            await self.init()
            logger.info(f"Starting RSS monitor (interval={POLL_INTERVAL}s)")
            logger.info(f"Monitoring: {RSS_FEED_URL}")

            while True:
                try:
                    await self.poll_once()
                except Exception as e:
                    logger.error(f"Feed check error: {e}")

                await asyncio.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            logger.info("Monitor stopped by user")
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            raise
        finally:
            await self.close()

async def main():
    """Entry point."""
    setup_logger()
    monitor = RSSMonitor()
    await monitor.run()


if __name__ == "__main__":
    asyncio.run(main())
