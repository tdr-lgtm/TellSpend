from fastapi import APIRouter

from tellspend.api.schemas import CategoryOption
from tellspend.categories import CATEGORY_KEYS, CATEGORY_LABELS

router = APIRouter(
    prefix="/categories",
    tags=["categories"],
)

@router.get("", response_model=list[CategoryOption])
def list_categories():
    """
    Every category in display order, with its label. Public: it's the
    same fixed list for everyone and contains no user data.

    Returns:
        Each category's key and label.
    """
    return [
        CategoryOption(key=key, label=CATEGORY_LABELS[key])
        for key in CATEGORY_KEYS
    ]