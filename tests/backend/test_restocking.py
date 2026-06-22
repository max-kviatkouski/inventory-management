"""
Tests for restocking API endpoints.

Covers GET /api/restocking/recommendations (budget-based recommendation preview)
and POST /api/restocking (places a restock order that surfaces via GET /api/orders).

Note: the server keeps orders in a shared in-memory list, so POSTing an order
mutates module state for the rest of the session. These tests assert on deltas
and order-number membership rather than absolute counts to stay order-independent.
"""
import pytest


class TestRestockingRecommendations:
    """Test suite for GET /api/restocking/recommendations."""

    def test_recommendations_zero_budget(self, client):
        """A zero budget returns candidates, but none fit (all in_budget False)."""
        response = client.get("/api/restocking/recommendations?budget=0")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data["recommendations"], list)
        assert data["budget"] == 0
        assert data["max_budget"] >= 0
        assert data["total_selected_cost"] == 0
        assert all(rec["in_budget"] is False for rec in data["recommendations"])

    def test_recommendations_high_budget_selects_all(self, client):
        """A budget above max_budget marks every candidate in_budget."""
        response = client.get("/api/restocking/recommendations?budget=100000000")
        assert response.status_code == 200

        data = response.json()
        assert len(data["recommendations"]) > 0
        assert all(rec["in_budget"] is True for rec in data["recommendations"])
        # Everything fits, so selected cost equals the max budget.
        assert abs(data["total_selected_cost"] - data["max_budget"]) < 0.01

    def test_recommendations_only_positive_gap_items(self, client):
        """Only items with growing demand (forecasted > current) are candidates."""
        response = client.get("/api/restocking/recommendations?budget=100000000")
        data = response.json()

        for rec in data["recommendations"]:
            assert rec["forecasted_demand"] > rec["current_demand"]
            # Quantity closes the demand gap exactly.
            assert rec["quantity"] == rec["forecasted_demand"] - rec["current_demand"]

    def test_recommendations_ranked_by_gap_desc(self, client):
        """Candidates are ranked by largest demand gap (quantity) first."""
        response = client.get("/api/restocking/recommendations?budget=100000000")
        quantities = [rec["quantity"] for rec in response.json()["recommendations"]]
        assert quantities == sorted(quantities, reverse=True)

    def test_recommendations_line_cost_calculation(self, client):
        """line_cost equals quantity * unit_cost for every candidate."""
        response = client.get("/api/restocking/recommendations?budget=100000000")
        for rec in response.json()["recommendations"]:
            assert abs(rec["line_cost"] - rec["quantity"] * rec["unit_cost"]) < 0.01

    def test_recommendations_selected_cost_within_budget(self, client):
        """The cost of in-budget items never exceeds the budget."""
        budget = 1000
        response = client.get(f"/api/restocking/recommendations?budget={budget}")
        data = response.json()

        selected = [rec for rec in data["recommendations"] if rec["in_budget"]]
        selected_cost = sum(rec["line_cost"] for rec in selected)
        assert selected_cost <= budget
        assert abs(data["total_selected_cost"] - selected_cost) < 0.01


class TestCreateRestockingOrder:
    """Test suite for POST /api/restocking."""

    def test_create_restocking_order(self, client):
        """A sufficient budget places a Submitted restock order."""
        response = client.post("/api/restocking", json={"budget": 100000000})
        assert response.status_code == 201

        order = response.json()
        assert order["is_restock"] is True
        assert order["status"] == "Submitted"
        assert order["customer"] == "Internal Restock"
        assert order["order_number"].startswith("RESTOCK-")
        assert len(order["items"]) > 0

        # total_value matches the sum of its line items.
        calculated = sum(item["quantity"] * item["unit_price"] for item in order["items"])
        assert abs(order["total_value"] - calculated) < 0.01

    def test_create_restocking_order_lead_time(self, client):
        """expected_delivery is 14 days after order_date."""
        from datetime import datetime

        order = client.post("/api/restocking", json={"budget": 100000000}).json()
        order_date = datetime.fromisoformat(order["order_date"])
        expected = datetime.fromisoformat(order["expected_delivery"])
        assert (expected - order_date).days == 14

    def test_create_restocking_order_zero_budget_rejected(self, client):
        """A budget too low to fit any item returns 400."""
        response = client.post("/api/restocking", json={"budget": 0})
        assert response.status_code == 400
        assert "budget" in response.json()["detail"].lower()

    def test_submitted_order_appears_in_orders(self, client):
        """A placed restock order is retrievable through GET /api/orders."""
        before = len(client.get("/api/orders").json())

        order = client.post("/api/restocking", json={"budget": 100000000}).json()

        all_orders = client.get("/api/orders").json()
        assert len(all_orders) == before + 1
        match = next((o for o in all_orders if o["order_number"] == order["order_number"]), None)
        assert match is not None
        assert match["is_restock"] is True
