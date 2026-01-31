"""Input validation utilities"""
import re
from werkzeug.utils import secure_filename
from config import Config


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS


def validate_product_name(name: str) -> tuple:
    """Validate product name"""
    if not name or not name.strip():
        return False, "Name is required"
    if len(name) > 200:
        return False, "Name too long (max 200 characters)"
    if re.search(r'[<>]', name):
        return False, "Invalid characters in name"
    return True, ""


def validate_price(price: int, is_free: bool) -> tuple:
    """Validate product price"""
    if is_free:
        return True, ""
    if price < 1:
        return False, "Price must be at least 1 star"
    if price > 10000:
        return False, "Price too high (max 10000 stars)"
    return True, ""


def validate_category(category: str) -> tuple:
    """Validate category name"""
    if not category or not category.strip():
        return False, "Category is required"
    if len(category) > 100:
        return False, "Category name too long"
    if re.search(r'[<>]', category):
        return False, "Invalid characters in category"
    return True, ""


def validate_color(color: str) -> tuple:
    """Validate hex color code"""
    if not re.match(r'^#[0-9a-fA-F]{6}$', color):
        return False, "Invalid color format (use #RRGGBB)"
    return True, ""
