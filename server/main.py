from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta
from mock_data import inventory_items, orders, demand_forecasts, backlog_items, spending_summary, monthly_spending, category_spending, recent_transactions, purchase_orders

app = FastAPI(title="Factory Inventory Management System")

# Fixed lead time applied to internally-placed restocking orders (days).
# Submitted restock orders get expected_delivery = order_date + this many days.
RESTOCK_LEAD_TIME_DAYS = 14

# Quarter mapping for date filtering
QUARTER_MAP = {
    'Q1-2025': ['2025-01', '2025-02', '2025-03'],
    'Q2-2025': ['2025-04', '2025-05', '2025-06'],
    'Q3-2025': ['2025-07', '2025-08', '2025-09'],
    'Q4-2025': ['2025-10', '2025-11', '2025-12']
}

def filter_by_month(items: list, month: Optional[str]) -> list:
    """Filter items by month/quarter based on order_date field"""
    if not month or month == 'all':
        return items

    if month.startswith('Q'):
        # Handle quarters
        if month in QUARTER_MAP:
            months = QUARTER_MAP[month]
            return [item for item in items if any(m in item.get('order_date', '') for m in months)]
    else:
        # Direct month match
        return [item for item in items if month in item.get('order_date', '')]

    return items

def apply_filters(items: list, warehouse: Optional[str] = None, category: Optional[str] = None,
                 status: Optional[str] = None) -> list:
    """Apply common filters to a list of items"""
    filtered = items

    if warehouse and warehouse != 'all':
        filtered = [item for item in filtered if item.get('warehouse') == warehouse]

    if category and category != 'all':
        filtered = [item for item in filtered if item.get('category', '').lower() == category.lower()]

    if status and status != 'all':
        filtered = [item for item in filtered if item.get('status', '').lower() == status.lower()]

    return filtered

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data models
class InventoryItem(BaseModel):
    id: str
    sku: str
    name: str
    category: str
    warehouse: str
    quantity_on_hand: int
    reorder_point: int
    unit_cost: float
    location: str
    last_updated: str

class Order(BaseModel):
    id: str
    order_number: str
    customer: str
    items: List[dict]
    status: str
    order_date: str
    expected_delivery: str
    total_value: float
    actual_delivery: Optional[str] = None
    warehouse: Optional[str] = None
    category: Optional[str] = None
    # Flags orders created via the Restocking tab so the Orders view can list
    # them in a dedicated "Submitted Orders" section. Defaults False so the
    # existing orders.json entries (which lack this field) remain valid.
    is_restock: Optional[bool] = False

class DemandForecast(BaseModel):
    id: str
    item_sku: str
    item_name: str
    current_demand: int
    forecasted_demand: int
    trend: str
    period: str
    unit_cost: float

class BacklogItem(BaseModel):
    id: str
    order_id: str
    item_sku: str
    item_name: str
    quantity_needed: int
    quantity_available: int
    days_delayed: int
    priority: str
    has_purchase_order: Optional[bool] = False

class PurchaseOrder(BaseModel):
    id: str
    backlog_item_id: str
    supplier_name: str
    quantity: int
    unit_cost: float
    expected_delivery_date: str
    status: str
    created_date: str
    notes: Optional[str] = None

class CreatePurchaseOrderRequest(BaseModel):
    backlog_item_id: str
    supplier_name: str
    quantity: int
    unit_cost: float
    expected_delivery_date: str
    notes: Optional[str] = None

class RestockingRecommendation(BaseModel):
    item_sku: str
    item_name: str
    current_demand: int
    forecasted_demand: int
    quantity: int          # units to order: max(0, forecasted - current)
    unit_cost: float
    line_cost: float       # quantity * unit_cost
    in_budget: bool        # selected by the greedy budget fit

class RestockingRecommendationsResponse(BaseModel):
    budget: float
    max_budget: float              # cost to restock every candidate (slider max)
    total_selected_cost: float     # cost of the items that fit the budget
    recommendations: List[RestockingRecommendation]

class CreateRestockingRequest(BaseModel):
    budget: float

class Task(BaseModel):
    id: int
    title: str
    priority: str
    dueDate: str
    status: str

class CreateTaskRequest(BaseModel):
    title: str
    priority: str = "medium"
    dueDate: str

# In-memory store for tasks created through the API. Seeded mock tasks live on
# the frontend (useAuth) and are merged client-side; this list only holds tasks
# the user adds at runtime. Resets on restart. IDs start at 1000 so they never
# collide with the frontend's seeded mock task IDs (1-4).
api_tasks: List[dict] = []
_next_task_id = {"value": 1000}

# API endpoints
@app.get("/")
def root():
    return {"message": "Factory Inventory Management System API", "version": "1.0.0"}

@app.get("/api/inventory", response_model=List[InventoryItem])
def get_inventory(
    warehouse: Optional[str] = None,
    category: Optional[str] = None
):
    """Get all inventory items with optional filtering"""
    return apply_filters(inventory_items, warehouse, category)

@app.get("/api/inventory/{item_id}", response_model=InventoryItem)
def get_inventory_item(item_id: str):
    """Get a specific inventory item"""
    item = next((item for item in inventory_items if item["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item

@app.get("/api/orders", response_model=List[Order])
def get_orders(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get all orders with optional filtering"""
    filtered_orders = apply_filters(orders, warehouse, category, status)
    filtered_orders = filter_by_month(filtered_orders, month)
    return filtered_orders

@app.get("/api/orders/{order_id}", response_model=Order)
def get_order(order_id: str):
    """Get a specific order"""
    order = next((order for order in orders if order["id"] == order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@app.get("/api/demand", response_model=List[DemandForecast])
def get_demand_forecasts():
    """Get demand forecasts"""
    return demand_forecasts

def _build_restock_candidates(budget: float):
    """Build the budget-ranked restock candidate list from demand forecasts.

    A candidate is any forecast item whose demand is growing (forecasted >
    current); the order quantity closes that gap. Candidates are ranked by the
    largest gap first, then greedily marked in_budget while the running budget
    covers each line cost. Returns (candidates, total_selected_cost, max_budget)
    where max_budget is the cost to restock every candidate (the slider max).
    """
    candidates = []
    for f in demand_forecasts:
        gap = f["forecasted_demand"] - f["current_demand"]
        if gap <= 0:
            continue
        unit_cost = f["unit_cost"]
        candidates.append({
            "item_sku": f["item_sku"],
            "item_name": f["item_name"],
            "current_demand": f["current_demand"],
            "forecasted_demand": f["forecasted_demand"],
            "quantity": gap,
            "unit_cost": unit_cost,
            "line_cost": round(gap * unit_cost, 2),
            "in_budget": False,
        })

    # Largest demand gap first (quantity == gap), then greedily fit the budget.
    candidates.sort(key=lambda c: c["quantity"], reverse=True)
    remaining = budget
    total_selected_cost = 0.0
    for c in candidates:
        if c["line_cost"] <= remaining:
            c["in_budget"] = True
            remaining -= c["line_cost"]
            total_selected_cost += c["line_cost"]

    max_budget = round(sum(c["line_cost"] for c in candidates), 2)
    return candidates, round(total_selected_cost, 2), max_budget

def _next_order_id():
    """Next numeric order id as a string (orders.json uses stringified ints)."""
    nums = [int(o["id"]) for o in orders if str(o["id"]).isdigit()]
    return str(max(nums) + 1) if nums else "1"

def _next_restock_number():
    """Sequential RESTOCK-YYYY-NNNN order number based on existing restock orders."""
    seq = sum(1 for o in orders if o["order_number"].startswith("RESTOCK-")) + 1
    return f"RESTOCK-{datetime.now().year}-{seq:04d}"

@app.get("/api/restocking/recommendations", response_model=RestockingRecommendationsResponse)
def get_restocking_recommendations(budget: float = 0):
    """Recommend forecast items to restock within a budget (no order is created)."""
    candidates, total_selected_cost, max_budget = _build_restock_candidates(budget)
    return {
        "budget": budget,
        "max_budget": max_budget,
        "total_selected_cost": total_selected_cost,
        "recommendations": candidates,
    }

@app.post("/api/restocking", response_model=Order, status_code=201)
def create_restocking_order(req: CreateRestockingRequest):
    """Place a restocking order for the budget-fitting recommendations.

    Recommendations are recomputed server-side from the budget (the client item
    list is not trusted) and the resulting order is appended to the in-memory
    orders list so it surfaces through GET /api/orders. Resets on restart.
    """
    candidates, total_selected_cost, _ = _build_restock_candidates(req.budget)
    chosen = [c for c in candidates if c["in_budget"]]
    if not chosen:
        raise HTTPException(status_code=400, detail="Budget too low to restock any items")

    now = datetime.now()
    order = {
        "id": _next_order_id(),
        "order_number": _next_restock_number(),
        "customer": "Internal Restock",
        "items": [
            {
                "sku": c["item_sku"],
                "name": c["item_name"],
                "quantity": c["quantity"],
                "unit_price": c["unit_cost"],
            }
            for c in chosen
        ],
        "status": "Submitted",
        "order_date": now.isoformat(timespec="seconds"),
        "expected_delivery": (now + timedelta(days=RESTOCK_LEAD_TIME_DAYS)).isoformat(timespec="seconds"),
        "total_value": total_selected_cost,
        "actual_delivery": None,
        "warehouse": None,
        "category": None,
        "is_restock": True,
    }
    orders.append(order)
    return order

@app.get("/api/backlog", response_model=List[BacklogItem])
def get_backlog():
    """Get backlog items with purchase order status"""
    # Add has_purchase_order flag to each backlog item
    result = []
    for item in backlog_items:
        item_dict = dict(item)
        # Check if this backlog item has a purchase order
        has_po = any(po["backlog_item_id"] == item["id"] for po in purchase_orders)
        item_dict["has_purchase_order"] = has_po
        result.append(item_dict)
    return result

@app.get("/api/dashboard/summary")
def get_dashboard_summary(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get summary statistics for dashboard with optional filtering"""
    # Filter inventory
    filtered_inventory = apply_filters(inventory_items, warehouse, category)

    # Filter orders
    filtered_orders = apply_filters(orders, warehouse, category, status)
    filtered_orders = filter_by_month(filtered_orders, month)

    total_inventory_value = sum(item["quantity_on_hand"] * item["unit_cost"] for item in filtered_inventory)
    low_stock_items = len([item for item in filtered_inventory if item["quantity_on_hand"] <= item["reorder_point"]])
    pending_orders = len([order for order in filtered_orders if order["status"] in ["Processing", "Backordered"]])
    total_backlog_items = len(backlog_items)

    return {
        "total_inventory_value": round(total_inventory_value, 2),
        "low_stock_items": low_stock_items,
        "pending_orders": pending_orders,
        "total_backlog_items": total_backlog_items,
        "total_orders_value": sum(order["total_value"] for order in filtered_orders)
    }

@app.get("/api/spending/summary")
def get_spending_summary():
    """Get spending summary statistics"""
    return spending_summary

@app.get("/api/spending/monthly")
def get_monthly_spending():
    """Get monthly spending breakdown"""
    return monthly_spending

@app.get("/api/spending/categories")
def get_category_spending():
    """Get spending by category"""
    return category_spending

@app.get("/api/spending/transactions")
def get_recent_transactions():
    """Get recent transactions"""
    return recent_transactions

@app.get("/api/reports/quarterly")
def get_quarterly_reports():
    """Get quarterly performance reports"""
    # Calculate quarterly statistics from orders
    quarters = {}

    for order in orders:
        order_date = order.get('order_date', '')
        # Determine quarter
        if '2025-01' in order_date or '2025-02' in order_date or '2025-03' in order_date:
            quarter = 'Q1-2025'
        elif '2025-04' in order_date or '2025-05' in order_date or '2025-06' in order_date:
            quarter = 'Q2-2025'
        elif '2025-07' in order_date or '2025-08' in order_date or '2025-09' in order_date:
            quarter = 'Q3-2025'
        elif '2025-10' in order_date or '2025-11' in order_date or '2025-12' in order_date:
            quarter = 'Q4-2025'
        else:
            continue

        if quarter not in quarters:
            quarters[quarter] = {
                'quarter': quarter,
                'total_orders': 0,
                'total_revenue': 0,
                'delivered_orders': 0,
                'avg_order_value': 0
            }

        quarters[quarter]['total_orders'] += 1
        quarters[quarter]['total_revenue'] += order.get('total_value', 0)
        if order.get('status') == 'Delivered':
            quarters[quarter]['delivered_orders'] += 1

    # Calculate averages and fulfillment rate
    result = []
    for q, data in quarters.items():
        if data['total_orders'] > 0:
            data['avg_order_value'] = round(data['total_revenue'] / data['total_orders'], 2)
            data['fulfillment_rate'] = round((data['delivered_orders'] / data['total_orders']) * 100, 1)
        result.append(data)

    # Sort by quarter
    result.sort(key=lambda x: x['quarter'])
    return result

@app.get("/api/reports/monthly-trends")
def get_monthly_trends():
    """Get month-over-month trends"""
    months = {}

    for order in orders:
        order_date = order.get('order_date', '')
        if not order_date:
            continue

        # Extract month (format: YYYY-MM-DD)
        month = order_date[:7]  # Gets YYYY-MM

        if month not in months:
            months[month] = {
                'month': month,
                'order_count': 0,
                'revenue': 0,
                'delivered_count': 0
            }

        months[month]['order_count'] += 1
        months[month]['revenue'] += order.get('total_value', 0)
        if order.get('status') == 'Delivered':
            months[month]['delivered_count'] += 1

    # Convert to list and sort
    result = list(months.values())
    result.sort(key=lambda x: x['month'])
    return result

@app.get("/api/tasks", response_model=List[Task])
def get_tasks():
    """Get tasks created through the API (newest first)."""
    return api_tasks

@app.post("/api/tasks", response_model=Task, status_code=201)
def create_task(req: CreateTaskRequest):
    """Create a new task. New tasks default to 'pending' status."""
    task = {
        "id": _next_task_id["value"],
        "title": req.title,
        "priority": req.priority,
        "dueDate": req.dueDate,
        "status": "pending",
    }
    _next_task_id["value"] += 1
    # Prepend so the client shows the newest task at the top of the list.
    api_tasks.insert(0, task)
    return task

@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int):
    """Delete an API-created task."""
    index = next((i for i, t in enumerate(api_tasks) if t["id"] == task_id), None)
    if index is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return api_tasks.pop(index)

@app.patch("/api/tasks/{task_id}", response_model=Task)
def toggle_task(task_id: int):
    """Toggle a task between 'pending' and 'completed'."""
    task = next((t for t in api_tasks if t["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task["status"] = "completed" if task["status"] == "pending" else "pending"
    return task

@app.post("/api/purchase-orders", response_model=PurchaseOrder, status_code=201)
def create_purchase_order(req: CreatePurchaseOrderRequest):
    """Create a purchase order for a backlog item.

    Appends to the in-memory purchase_orders list so it surfaces through the
    backlog's has_purchase_order flag and GET /api/purchase-orders/{id}.
    Resets on restart.
    """
    backlog_item = next((b for b in backlog_items if b["id"] == req.backlog_item_id), None)
    if not backlog_item:
        raise HTTPException(status_code=404, detail="Backlog item not found")

    # One purchase order per backlog item: reject duplicates so the dashboard's
    # create/view toggle stays consistent.
    existing = next((po for po in purchase_orders if po["backlog_item_id"] == req.backlog_item_id), None)
    if existing:
        raise HTTPException(status_code=400, detail="Purchase order already exists for this backlog item")

    po = {
        "id": f"PO-{len(purchase_orders) + 1:04d}",
        "backlog_item_id": req.backlog_item_id,
        "supplier_name": req.supplier_name,
        "quantity": req.quantity,
        "unit_cost": req.unit_cost,
        "expected_delivery_date": req.expected_delivery_date,
        "status": "Pending",
        "created_date": datetime.now().isoformat(timespec="seconds"),
        "notes": req.notes,
    }
    purchase_orders.append(po)
    return po

@app.get("/api/purchase-orders/{backlog_item_id}", response_model=PurchaseOrder)
def get_purchase_order_by_backlog_item(backlog_item_id: str):
    """Get the purchase order associated with a backlog item."""
    po = next((po for po in purchase_orders if po["backlog_item_id"] == backlog_item_id), None)
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return po

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
