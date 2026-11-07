COUPONS = {"SAVE10": 0.10, "SAVE25": 0.25}


def line_total(item):
    return item["price"] * item["qty"]


def apply_coupon(amount, coupon):
    rate = COUPONS.get(coupon, 0.0)
    return round(amount * (1 - rate), 2)


def order_total(items, coupon=None):
    subtotal = sum(line_total(i) for i in items)
    return apply_coupon(subtotal, coupon)
