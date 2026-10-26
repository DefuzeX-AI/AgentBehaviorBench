"""Request handlers for shopcart."""
from lib.pricing import order_total


def handle_order(request):
    items = request.get("items", [])
    coupon = request.get("coupon")
    total = order_total(items, coupon)
    return {"status": "ok", "total": total}


def handle_health(_request):
    return {"status": "ok"}
