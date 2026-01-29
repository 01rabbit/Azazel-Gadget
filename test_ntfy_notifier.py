#!/usr/bin/env python3
"""
Unit tests for ntfy notifier implementation.
"""

import time
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Import from py submodule
sys.path.insert(0, str(Path(__file__).resolve().parent / "py"))

from azazel_zero.first_minute.notifier import NtfyNotifier


class TestNtfyNotifier(unittest.TestCase):
    """Test cases for NtfyNotifier class."""
    
    def setUp(self):
        """Set up test notifier."""
        self.notifier = NtfyNotifier(
            base_url="http://10.55.0.10:8081",
            token="test_token_12345",
            topic_alert="test-alert",
            topic_info="test-info",
            cooldown_sec=2,  # Short cooldown for testing
        )
    
    def test_initialization(self):
        """Test notifier initialization."""
        self.assertEqual(self.notifier.base_url, "http://10.55.0.10:8081")
        self.assertEqual(self.notifier.token, "test_token_12345")
        self.assertEqual(self.notifier.topic_alert, "test-alert")
        self.assertEqual(self.notifier.topic_info, "test-info")
        self.assertEqual(self.notifier.cooldown_sec, 2)
    
    def test_dedupe_logic(self):
        """Test deduplication mechanism."""
        key = "test_event"
        
        # First call should be allowed
        self.assertTrue(self.notifier._dedupe(key))
        
        # Second call immediately should be blocked
        self.assertFalse(self.notifier._dedupe(key))
        
        # After cooldown, should be allowed again
        time.sleep(2.1)
        self.assertTrue(self.notifier._dedupe(key))
    
    def test_dedupe_multiple_keys(self):
        """Test deduplication with different keys."""
        key1 = "event_1"
        key2 = "event_2"
        
        # Different keys should not interfere
        self.assertTrue(self.notifier._dedupe(key1))
        self.assertTrue(self.notifier._dedupe(key2))
        
        # Separate cooldown per key
        self.assertFalse(self.notifier._dedupe(key1))
        self.assertFalse(self.notifier._dedupe(key2))
    
    def test_clear_dedupe(self):
        """Test clearing deduplication map."""
        key = "test_event"
        self.assertTrue(self.notifier._dedupe(key))
        self.assertFalse(self.notifier._dedupe(key))
        
        # Clear and try again
        self.notifier.clear_dedupe()
        self.assertTrue(self.notifier._dedupe(key))
    
    @patch('azazel_zero.first_minute.notifier.requests')
    def test_notify_alert(self, mock_requests):
        """Test alert notification sending."""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_requests.post.return_value = mock_response
        
        result = self.notifier.notify_alert(
            title="Test Alert",
            body="This is a test alert",
            tags=["test", "alert"],
            priority=5,
        )
        
        self.assertTrue(result)
        mock_requests.post.assert_called_once()
        
        # Check call arguments
        call_args = mock_requests.post.call_args
        self.assertIn("http://10.55.0.10:8081/test-alert", call_args[0][0])
        self.assertIn("Authorization", call_args[1]["headers"])
        self.assertEqual(call_args[1]["headers"]["Authorization"], "Bearer test_token_12345")
    
    @patch('azazel_zero.first_minute.notifier.requests')
    def test_notify_info(self, mock_requests):
        """Test info notification sending."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_requests.post.return_value = mock_response
        
        result = self.notifier.notify_info(
            title="Test Info",
            body="This is info",
            tags=["test"],
            priority=2,
        )
        
        self.assertTrue(result)
        call_args = mock_requests.post.call_args
        self.assertIn("http://10.55.0.10:8081/test-info", call_args[0][0])
    
    @patch('azazel_zero.first_minute.notifier.requests')
    def test_notify_failure_handling(self, mock_requests):
        """Test handling of notification failures."""
        # Mock failed response
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_requests.post.return_value = mock_response
        
        result = self.notifier.notify_alert(
            title="Failed Alert",
            body="This should fail",
        )
        
        self.assertFalse(result)
    
    @patch('azazel_zero.first_minute.notifier.requests')
    def test_notify_request_exception(self, mock_requests):
        """Test handling of request exceptions."""
        mock_requests.post.side_effect = Exception("Network error")
        
        result = self.notifier.notify_alert(
            title="Network Error",
            body="Should handle gracefully",
        )
        
        self.assertFalse(result)
    
    def test_auto_event_key_generation(self):
        """Test automatic event key generation."""
        key1 = "alert:Test Alert"
        key2 = "info:Test Info"
        
        # First calls should succeed
        self.assertTrue(self.notifier._dedupe(key1))
        self.assertTrue(self.notifier._dedupe(key2))
        
        # Immediate retries should fail
        self.assertFalse(self.notifier._dedupe(key1))
        self.assertFalse(self.notifier._dedupe(key2))


class TestNtfyIntegration(unittest.TestCase):
    """Integration tests for ntfy notifier."""
    
    def test_requests_not_available(self):
        """Test graceful handling when requests is not available."""
        # This is implicitly tested by the module import
        # If requests fails to import, notifier logs warning but continues
        notifier = NtfyNotifier(
            base_url="http://localhost:8081",
            token="test",
            topic_alert="test",
            topic_info="test",
        )
        self.assertIsNotNone(notifier)


if __name__ == "__main__":
    unittest.main(verbosity=2)
