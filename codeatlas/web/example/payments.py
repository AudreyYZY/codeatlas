def charge(amount):
    return receipt(amount)


def receipt(amount):
    return {"amount": amount, "status": "paid"}
