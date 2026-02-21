"""
ntfy (self-hosted push notification) client for Azazel-Gadget.

Provides simple HTTP-based notification for state transitions and critical signals.
Deduplication prevents notification spam via cooldown windows per event key.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Dict, List, Optional

try:
    import requests
except ImportError:
    requests = None


class NtfyNotifier:
    """
    Thin HTTP client for ntfy.sh notifications over USB-local network.
    
    Args:
        base_url: ntfy server base URL (e.g. "http://10.55.0.10:8081")
        token: Bearer token for authentication
        topic_alert: topic name for critical alerts (e.g. "azg-xxxx-alert")
        topic_info: topic name for info messages (e.g. "azg-xxxx-info")
        cooldown_sec: deduplication cooldown window (seconds)
    """
    
    def __init__(
        self,
        base_url: str,
        token: str,
        topic_alert: str,
        topic_info: str,
        cooldown_sec: int = 30,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.topic_alert = topic_alert
        self.topic_info = topic_info
        self.cooldown_sec = cooldown_sec
        self.logger = logging.getLogger("first_minute.notifier")
        
        # Deduplication: {event_key: last_sent_time}
        self._dedupe_map: Dict[str, float] = {}
        
        if requests is None:
            self.logger.warning(
                "requests library not available; ntfy notifications will be disabled"
            )
    
    def notify_alert(
        self,
        title: str,
        body: str,
        tags: Optional[List[str]] = None,
        priority: int = 5,
        event_key: Optional[str] = None,
    ) -> bool:
        """
        Send a high-priority alert to ALERT_TOPIC.
        
        Args:
            title: Notification title
            body: Message body
            tags: Optional list of tags for ntfy (e.g. ["warning", "shield"])
            priority: Priority (1-5, default 5=urgent)
            event_key: Optional deduplication key (auto-generated from title if not provided)
        
        Returns:
            True if sent successfully, False if failed or suppressed (dedupe)
        """
        if event_key is None:
            event_key = f"alert:{title}"
        
        if not self._dedupe(event_key):
            self.logger.debug(
                f"Alert suppressed by cooldown: {event_key} (TTL: {self.cooldown_sec}s)"
            )
            return False
        
        return self._send(
            topic=self.topic_alert,
            title=title,
            body=body,
            tags=tags or [],
            priority=priority,
        )
    
    def notify_info(
        self,
        title: str,
        body: str,
        tags: Optional[List[str]] = None,
        priority: int = 2,
        event_key: Optional[str] = None,
    ) -> bool:
        """
        Send an informational message to INFO_TOPIC.
        
        Args:
            title: Notification title
            body: Message body
            tags: Optional list of tags
            priority: Priority (default 2=low)
            event_key: Optional deduplication key
        
        Returns:
            True if sent, False if failed or suppressed (dedupe)
        """
        if event_key is None:
            event_key = f"info:{title}"
        
        if not self._dedupe(event_key):
            self.logger.debug(
                f"Info suppressed by cooldown: {event_key} (TTL: {self.cooldown_sec}s)"
            )
            return False
        
        return self._send(
            topic=self.topic_info,
            title=title,
            body=body,
            tags=tags or [],
            priority=priority,
        )
    
    def _send(
        self,
        topic: str,
        title: str,
        body: str,
        tags: List[str],
        priority: int,
    ) -> bool:
        """
        Low-level HTTP POST to ntfy server.
        
        Returns:
            True if 200 <= status < 300, False otherwise
        """
        if requests is None:
            self.logger.error("requests not installed; cannot send notification")
            return False
        
        url = f"{self.base_url}/{topic}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Title": title.encode("utf-8").decode("latin-1") if isinstance(title, str) else title,
            "Priority": str(priority),
            "Content-Type": "text/plain; charset=utf-8",
        }
        
        if tags:
            headers["Tags"] = ",".join(tags)
        
        try:
            resp = requests.post(
                url,
                data=body.encode("utf-8"),
                headers=headers,
                timeout=2.0,
            )
            
            if 200 <= resp.status_code < 300:
                self.logger.info(
                    f"Sent notification: {topic} / {title} (status={resp.status_code})"
                )
                return True
            else:
                self.logger.warning(
                    f"ntfy POST failed: {url} returned {resp.status_code}"
                )
                return False
        
        except Exception as e:
            # Catch both RequestException and generic exceptions
            self.logger.error(f"ntfy request error: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error sending ntfy notification: {e}")
            return False
    
    def _dedupe(self, key: str) -> bool:
        """
        Check if event_key is eligible for sending (respecting cooldown).
        Updates the timestamp if eligible.
        
        Args:
            key: Deduplication key
        
        Returns:
            True if event is new (or past cooldown), False if in cooldown window
        """
        now = time.time()
        last_sent = self._dedupe_map.get(key, 0.0)
        
        if now - last_sent >= self.cooldown_sec:
            self._dedupe_map[key] = now
            return True
        
        return False
    
    def clear_dedupe(self) -> None:
        """Clear the deduplication map (for testing/reset)."""
        self._dedupe_map.clear()
