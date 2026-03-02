"""Tests for the Solvis client CGI control methods."""

from __future__ import annotations

import urllib.error
from unittest.mock import patch, MagicMock, call

import pytest

from custom_components.solvis_remote.client import (
    SolvisClient,
    SolvisAuthError,
    SolvisConnectionError,
)


@pytest.fixture
def client() -> SolvisClient:
    """Return a SolvisClient for testing."""
    return SolvisClient(
        host="192.168.1.100",
        username="admin",
        password="secret",
        realm="SolvisRemote",
        timeout=5,
    )


class TestOpenCgi:
    """Test the _open_cgi helper."""

    def test_success(self, client: SolvisClient) -> None:
        """Successful CGI request reads and closes response."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"OK"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch.object(client._opener, "open", return_value=mock_resp):
            client._open_cgi("http://192.168.1.100/test")

        mock_resp.read.assert_called_once()

    def test_auth_error_401(self, client: SolvisClient) -> None:
        """HTTP 401 must raise SolvisAuthError."""
        with patch.object(
            client._opener,
            "open",
            side_effect=urllib.error.HTTPError(
                "http://test", 401, "Unauthorized", {}, None
            ),
        ):
            with pytest.raises(SolvisAuthError, match="401"):
                client._open_cgi("http://192.168.1.100/test")

    def test_auth_error_403(self, client: SolvisClient) -> None:
        """HTTP 403 must raise SolvisAuthError."""
        with patch.object(
            client._opener,
            "open",
            side_effect=urllib.error.HTTPError(
                "http://test", 403, "Forbidden", {}, None
            ),
        ):
            with pytest.raises(SolvisAuthError, match="403"):
                client._open_cgi("http://192.168.1.100/test")

    def test_http_error_500(self, client: SolvisClient) -> None:
        """Non-auth HTTP error must raise SolvisConnectionError."""
        with patch.object(
            client._opener,
            "open",
            side_effect=urllib.error.HTTPError(
                "http://test", 500, "Server Error", {}, None
            ),
        ):
            with pytest.raises(SolvisConnectionError, match="500"):
                client._open_cgi("http://192.168.1.100/test")

    def test_url_error(self, client: SolvisClient) -> None:
        """URLError must raise SolvisConnectionError."""
        with patch.object(
            client._opener,
            "open",
            side_effect=urllib.error.URLError("Connection refused"),
        ):
            with pytest.raises(SolvisConnectionError, match="connection error"):
                client._open_cgi("http://192.168.1.100/test")

    def test_timeout(self, client: SolvisClient) -> None:
        """TimeoutError must raise SolvisConnectionError."""
        with patch.object(
            client._opener, "open", side_effect=TimeoutError()
        ):
            with pytest.raises(SolvisConnectionError, match="timeout"):
                client._open_cgi("http://192.168.1.100/test")


class TestSendButtonPress:
    """Test send_button_press."""

    def test_url_contains_taster_cgi(self, client: SolvisClient) -> None:
        """URL must point to Taster.CGI with button parameter."""
        with patch.object(client, "_open_cgi") as mock_open:
            client.send_button_press("links")

        url = mock_open.call_args[0][0]
        assert "Taster.CGI" in url
        assert "taste=links" in url
        assert "&i=" in url

    def test_default_button_is_links(self, client: SolvisClient) -> None:
        """Default button parameter must be 'links'."""
        with patch.object(client, "_open_cgi") as mock_open:
            client.send_button_press()

        url = mock_open.call_args[0][0]
        assert "taste=links" in url


class TestSendTouch:
    """Test send_touch."""

    def test_url_contains_touch_cgi(self, client: SolvisClient) -> None:
        """URL must point to Touch.CGI with x/y parameters."""
        with patch.object(client, "_open_cgi") as mock_open:
            client.send_touch(120, 218)

        url = mock_open.call_args[0][0]
        assert "Touch.CGI" in url
        assert "x=120" in url
        assert "y=218" in url


class TestExecuteCgiSequence:
    """Test execute_cgi_sequence."""

    def test_sequence_order(self, client: SolvisClient) -> None:
        """Must call: wakeup N times, touch at x/y, then reset touch."""
        sequence = {
            "wakeup_count": 2,
            "wakeup_delay": 0.01,  # Short delay for tests
            "x": 120,
            "y": 218,
            "reset_touch": {"x": 510, "y": 510},
        }

        with patch.object(client, "send_button_press") as mock_btn, \
             patch.object(client, "send_touch") as mock_touch, \
             patch("custom_components.solvis_remote.client.time.sleep"):
            client.execute_cgi_sequence(sequence)

        # 2 wakeup presses
        assert mock_btn.call_count == 2

        # Touch calls: mode touch + reset touch
        assert mock_touch.call_count == 2
        mock_touch.assert_any_call(120, 218)
        mock_touch.assert_any_call(510, 510)

    def test_sequence_without_reset(self, client: SolvisClient) -> None:
        """Sequence without reset_touch must skip reset."""
        sequence = {
            "wakeup_count": 1,
            "wakeup_delay": 0.01,
            "x": 315,
            "y": 215,
            "reset_touch": None,
        }

        with patch.object(client, "send_button_press"), \
             patch.object(client, "send_touch") as mock_touch, \
             patch("custom_components.solvis_remote.client.time.sleep"):
            client.execute_cgi_sequence(sequence)

        # Only mode touch, no reset
        mock_touch.assert_called_once_with(315, 215)

    def test_zero_wakeup_count(self, client: SolvisClient) -> None:
        """Zero wakeup_count must skip wakeup phase."""
        sequence = {
            "wakeup_count": 0,
            "wakeup_delay": 1.0,
            "x": 120,
            "y": 218,
            "reset_touch": None,
        }

        with patch.object(client, "send_button_press") as mock_btn, \
             patch.object(client, "send_touch") as mock_touch, \
             patch("custom_components.solvis_remote.client.time.sleep"):
            client.execute_cgi_sequence(sequence)

        mock_btn.assert_not_called()
        mock_touch.assert_called_once_with(120, 218)

    def test_sequence_with_section_touch(self, client: SolvisClient) -> None:
        """Sequence with section: Wakeup → Section-Touch → Option-Touch → Reset."""
        sequence = {
            "wakeup_count": 2,
            "wakeup_delay": 0.01,
            "section_touch": {"x": 43, "y": 25},
            "x": 120,
            "y": 218,
            "reset_touch": {"x": 510, "y": 510},
        }

        with patch.object(client, "send_button_press") as mock_btn, \
             patch.object(client, "send_touch") as mock_touch, \
             patch("custom_components.solvis_remote.client.time.sleep"):
            client.execute_cgi_sequence(sequence)

        assert mock_btn.call_count == 2
        # Touch calls: section + option + reset = 3
        assert mock_touch.call_count == 3
        touch_calls = mock_touch.call_args_list
        assert touch_calls[0] == call(43, 25)     # section touch
        assert touch_calls[1] == call(120, 218)    # option touch
        assert touch_calls[2] == call(510, 510)    # reset touch

    def test_sequence_without_section_touch(self, client: SolvisClient) -> None:
        """Sequence without section_touch must skip section step (backwards compatible)."""
        sequence = {
            "wakeup_count": 1,
            "wakeup_delay": 0.01,
            "x": 315,
            "y": 215,
            "reset_touch": {"x": 510, "y": 510},
        }

        with patch.object(client, "send_button_press"), \
             patch.object(client, "send_touch") as mock_touch, \
             patch("custom_components.solvis_remote.client.time.sleep"):
            client.execute_cgi_sequence(sequence)

        # Only option + reset, no section
        assert mock_touch.call_count == 2
        touch_calls = mock_touch.call_args_list
        assert touch_calls[0] == call(315, 215)    # option touch
        assert touch_calls[1] == call(510, 510)    # reset touch
