from datetime import date, datetime
from decimal import Decimal

def serialize_value(value):
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, list):
        return [serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {
            key: serialize_value(item)
            for key, item in value.items()
        }
    return value

def success_response(message="success", data=None):
    return {
        "success": True,
        "message": message,
        "data": serialize_value(data),
    }

def error_response(message="error", data=None):
    return {
        "success": False,
        "message": message,
        "data": serialize_value(data),
    }