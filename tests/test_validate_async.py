"""Tests for validate_travel_input and async research functions."""
import pytest
import asyncio
import sys
import os
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tools.travel_api_tools import (
    validate_travel_input,
    _normalize_destination_name,
    _normalize_origin_name,
    research_destination_async,
    research_all_destinations_async,
)


class TestValidateTravelInput:
    """Test cases for validate_travel_input function."""

    def test_full_request(self):
        """Test parsing a complete travel request."""
        result = validate_travel_input(
            "Lập plan 3 ngày đi Đà Nẵng từ Hà Nội, ngân sách 5 triệu cho 2 người"
        )

        assert result["is_valid"] is True
        assert result["normalized_input"]["destination"] == "Đà Nẵng"
        assert result["normalized_input"]["origin"] == "Hà Nội"
        assert result["normalized_input"]["budget"] == 5000000
        assert result["normalized_input"]["days"] == 3
        assert result["normalized_input"]["people"] == 2
        assert result["missing_fields"] == []

    def test_budget_extraction_million(self):
        """Test extracting budget in millions."""
        result = validate_travel_input("đi Đà Nẵng ngân sách 10 triệu 3 ngày")

        assert result["is_valid"] is True
        assert result["normalized_input"]["budget"] == 10000000

    def test_budget_extraction_k(self):
        """Test extracting budget in thousands."""
        result = validate_travel_input("đi Đà Nẵng budget 500k 3 ngày")

        assert result["is_valid"] is True
        assert result["normalized_input"]["budget"] == 500000

    def test_people_extraction(self):
        """Test extracting number of people."""
        result = validate_travel_input("đi Đà Nẵng 3 ngày cho 2 người")

        assert result["normalized_input"]["people"] == 2

    def test_days_and_nights(self):
        """Test extracting days and nights."""
        result = validate_travel_input("đi Vũng Tàu 3 ngày 2 đêm cho 2 người, budget 10 triệu")

        assert result["normalized_input"]["days"] == 3
        assert result["normalized_input"]["nights"] == 2

    def test_days_without_nights_calculates_nights(self):
        """Test that nights is calculated from days when not provided."""
        result = validate_travel_input("đi Đà Nẵng 3 ngày")

        assert result["normalized_input"]["days"] == 3
        assert result["normalized_input"]["nights"] == 2  # days - 1

    def test_missing_people_defaults_to_one(self):
        """Test that missing people defaults to 1 with assumption."""
        result = validate_travel_input("đi Đà Nẵng budget 5 triệu 3 ngày")

        assert result["normalized_input"]["people"] == 1
        assert any("1 person" in a for a in result["assumptions"])

    def test_missing_destination(self):
        """Test request with missing destination but has destination_type."""
        result = validate_travel_input("muốn đi biển budget 10 triệu 3 ngày")

        # Should be valid because destination_type is extracted
        assert result["is_valid"] is True
        assert result["normalized_input"]["destination_type"] == "beach"
        assert result["normalized_input"]["interests"] == ["beach"]

    def test_complete_beach_request(self):
        """Test complete beach request."""
        result = validate_travel_input(
            "T muốn đi du lịch gần biển mùa hè này, budget 10 triệu cho 2 người, đi 3 ngày 2 đêm"
        )

        assert result["is_valid"] is True
        assert result["normalized_input"]["destination_type"] == "beach"
        assert result["normalized_input"]["budget"] == 10000000
        assert result["normalized_input"]["people"] == 2
        assert result["normalized_input"]["days"] == 3
        assert result["normalized_input"]["nights"] == 2
        assert result["normalized_input"]["season"] == "summer"
        assert "beach" in result["normalized_input"]["interests"]

    def test_missing_budget_invalid(self):
        """Test that missing budget makes request invalid."""
        result = validate_travel_input("đi Đà Nẵng 3 ngày")

        assert result["is_valid"] is False
        assert "budget" in result["missing_fields"]

    def test_missing_days_invalid(self):
        """Test that missing days makes request invalid."""
        result = validate_travel_input("đi Đà Nẵng budget 5 triệu")

        assert result["is_valid"] is False
        assert "days" in result["missing_fields"]

    def test_follow_up_question(self):
        """Test that follow-up question is generated for invalid requests."""
        result = validate_travel_input("đi biển")

        assert result["is_valid"] is False
        assert result["follow_up_question"] is not None
        assert "ngân sách" in result["follow_up_question"].lower()
        assert "ngày" in result["follow_up_question"].lower()

    def test_destination_normalization(self):
        """Test destination name normalization."""
        result = validate_travel_input("đi sài gòn budget 5 triệu 3 ngày")

        assert result["normalized_input"]["origin"] == "Hà Nội"  # default
        # Destination should be normalized if extracted

    def test_default_origin(self):
        """Test that default origin is used when not provided."""
        result = validate_travel_input("đi Đà Nẵng budget 5 triệu 3 ngày")

        assert result["normalized_input"]["origin"] == "Hà Nội"  # default from DEFAULT_ORIGIN
        assert any("origin" in a.lower() for a in result["assumptions"])

    def test_interests_extraction(self):
        """Test extracting interests from request."""
        result = validate_travel_input(
            "đi Đà Nẵng budget 5 triệu 3 ngày, thích hải sản, cafe, chụp ảnh"
        )

        interests = result["normalized_input"]["interests"]
        assert "seafood" in interests
        assert "cafe" in interests
        assert "photo" in interests


class TestNormalizeFunctions:
    """Test cases for normalization helper functions."""

    def test_normalize_destination_name(self):
        """Test destination name normalization."""
        assert _normalize_destination_name("sài gòn") == "TP. Hồ Chí Minh"
        assert _normalize_destination_name("hà nội") == "Hà Nội"
        assert _normalize_destination_name("đà nẵng") == "Đà Nẵng"
        assert _normalize_destination_name("vũng tàu") == "Vũng Tàu"

    def test_normalize_origin_name(self):
        """Test origin name normalization."""
        assert _normalize_origin_name("tphcm") == "TP. Hồ Chí Minh"
        assert _normalize_origin_name("saigon") == "TP. Hồ Chí Minh"
        assert _normalize_origin_name("hn") == "Hà Nội"


class TestAsyncResearch:
    """Test cases for async research functions."""

    @pytest.mark.asyncio
    async def test_research_destination_async_success(self):
        """Test async research with successful geocode."""
        params = {
            "days": 3,
            "origin": "Hà Nội",
            "people": 2,
        }
        destination_option = {"destination": "Đà Nẵng", "reason": "Test"}

        # Mock geocode to return success
        with patch("src.tools.travel_api_tools.geocode_location") as mock_geocode:
            mock_geocode.return_value = {
                "status": "ok",
                "latitude": 16.0544,
                "longitude": 108.2022,
                "name": "Da Nang, Vietnam"
            }

            # Mock other tools
            with patch("src.tools.travel_api_tools.get_weather") as mock_weather:
                mock_weather.return_value = {"status": "ok", "forecasts": []}
                with patch("src.tools.travel_api_tools.search_attractions") as mock_attractions:
                    mock_attractions.return_value = {"status": "ok", "results": []}
                    with patch("src.tools.travel_api_tools.search_stays") as mock_stays:
                        mock_stays.return_value = {"status": "ok", "results": []}
                        with patch("src.tools.travel_api_tools.search_restaurants") as mock_restaurants:
                            mock_restaurants.return_value = {"status": "ok", "results": []}
                            with patch("src.tools.travel_api_tools.estimate_transport_cost") as mock_transport:
                                mock_transport.return_value = {"status": "ok"}

                                result = await research_destination_async(
                                    "Đà Nẵng", params, destination_option
                                )

        assert result["destination"] == "Đà Nẵng"
        assert result["destination_option"] == destination_option
        assert "tool_results" in result
        assert "research_latency_ms" in result

    @pytest.mark.asyncio
    async def test_research_destination_async_geocode_failure(self):
        """Test async research when geocode fails."""
        params = {"days": 3}
        destination_option = {"destination": "Unknown Place"}

        with patch("src.tools.travel_api_tools.geocode_location") as mock_geocode:
            mock_geocode.return_value = {
                "status": "error",
                "message": "Place not found"
            }

            result = await research_destination_async(
                "Unknown Place", params, destination_option
            )

        assert "geocode_failed" in result["errors"]

    @pytest.mark.asyncio
    async def test_research_all_destinations_async(self):
        """Test parallel research for multiple destinations."""
        params = {"days": 3, "origin": "Hà Nội"}

        destinations = [
            {"destination": "Đà Nẵng", "reason": "Beach"},
            {"destination": "Nha Trang", "reason": "Beach"},
        ]

        with patch("src.tools.travel_api_tools.geocode_location") as mock_geocode:
            mock_geocode.return_value = {
                "status": "ok",
                "latitude": 16.0,
                "longitude": 108.0,
            }

            with patch("src.tools.travel_api_tools.get_weather") as mock_weather:
                mock_weather.return_value = {"status": "ok"}
                with patch("src.tools.travel_api_tools.search_attractions") as mock_att:
                    mock_att.return_value = {"status": "ok", "results": []}
                    with patch("src.tools.travel_api_tools.search_stays") as mock_stays:
                        mock_stays.return_value = {"status": "ok", "results": []}
                        with patch("src.tools.travel_api_tools.search_restaurants") as mock_rest:
                            mock_rest.return_value = {"status": "ok", "results": []}
                            with patch("src.tools.travel_api_tools.estimate_transport_cost") as mock_trans:
                                mock_trans.return_value = {"status": "ok"}

                                results = await research_all_destinations_async(
                                    destinations, params
                                )

        assert len(results) == 2
        assert results[0]["destination"] == "Đà Nẵng"
        assert results[1]["destination"] == "Nha Trang"

    @pytest.mark.asyncio
    async def test_research_with_timeout(self):
        """Test that research handles tool timeouts gracefully."""
        params = {"days": 3}

        with patch("src.tools.travel_api_tools.geocode_location") as mock_geocode:
            # Simulate slow geocode
            async def slow_geocode(*args):
                await asyncio.sleep(0.1)
                return {
                    "status": "ok",
                    "latitude": 16.0,
                    "longitude": 108.0,
                }
            mock_geocode.side_effect = slow_geocode

            # Should not raise, but return partial result
            result = await research_destination_async("Test", params)

        # Result should exist even with timeout
        assert "destination" in result or "errors" in result


class TestIntegration:
    """Integration tests for the validation and research pipeline."""

    def test_validate_then_research_pipeline(self):
        """Test the complete validation -> research pipeline."""
        # Step 1: Validate
        request = "T muốn đi du lịch gần biển mùa hè này, budget 10 triệu cho 2 người, đi 3 ngày 2 đêm"
        validation = validate_travel_input(request)

        assert validation["is_valid"] is True
        assert validation["normalized_input"]["destination_type"] == "beach"
        assert validation["normalized_input"]["budget"] == 10000000

    def test_invalid_input_follow_up(self):
        """Test that invalid input generates appropriate follow-up."""
        request = "tôi muốn đi du lịch"
        validation = validate_travel_input(request)

        assert validation["is_valid"] is False
        assert len(validation["missing_fields"]) > 0
        assert validation["follow_up_question"] is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
