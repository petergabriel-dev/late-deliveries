"""Build the order-level analysis table: one row per order (ADR-0003..0005).

Writes data/processed/orders.parquet and outputs/exclusions.json.
Computes no outcome split by treatment (invariant 3): output is row-level
columns plus exclusion counts only.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from late_delivery import config as C

FILES = {
    "orders": "olist_orders_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "items": "olist_order_items_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "translation": "product_category_name_translation.csv",
}

# ADR-0005 exclusion rules, in precedence order: an order gets the first rule it fails.
EXCLUSION_ORDER = ["not_delivered", "missing_delivery_ts", "outside_window", "no_items", "multi_seller"]

EARTH_RADIUS_KM = 6371.0088


def read_csv(path) -> pd.DataFrame:
    # utf-8-sig strips the BOM at the start of product_category_name_translation.csv
    return pd.read_csv(path, encoding="utf-8-sig")


def read_raw(raw_dir=C.RAW_DIR) -> dict[str, pd.DataFrame]:
    return {name: read_csv(Path(raw_dir) / f) for name, f in FILES.items()}


def _ts(s: pd.Series) -> pd.Series:
    # Strict format: a malformed timestamp raises instead of silently becoming NaT.
    return pd.to_datetime(s, format=C.TS_FORMAT)


def latest_reviews(reviews: pd.DataFrame) -> pd.DataFrame:
    """One review per order: the latest-answered one (ADR-0004)."""
    r = reviews.assign(
        review_answer_timestamp=_ts(reviews["review_answer_timestamp"]),
        review_creation_date=_ts(reviews["review_creation_date"]),
    )
    r = r.sort_values(
        ["order_id", "review_answer_timestamp", "review_creation_date", "review_id"], na_position="first"
    )
    return r.drop_duplicates("order_id", keep="last").set_index("order_id")[["review_score", "review_creation_date"]]


def order_items_summary(items: pd.DataFrame, products: pd.DataFrame, translation: pd.DataFrame) -> pd.DataFrame:
    """Per-order item covariates. Main category = category of the highest-price item."""
    pt = products.set_index("product_id")["product_category_name"]
    en = translation.set_index("product_category_name")["product_category_name_english"]
    category = items["product_id"].map(pt)
    # English name where translated, else the Portuguese name, else "unknown".
    it = items.assign(category=category.map(en).fillna(category).fillna("unknown"))
    g = it.groupby("order_id")
    out = pd.DataFrame(
        {
            "n_items": g.size(),
            "n_sellers": g["seller_id"].nunique(),
            "price": g["price"].sum(),
            "freight": g["freight_value"].sum(),
        }
    )
    # ponytail: ties on the top price go to the lowest order_item_id.
    top = it.sort_values(["order_id", "price", "order_item_id"], ascending=[True, False, True])
    out["main_category"] = top.drop_duplicates("order_id").set_index("order_id")["category"]
    out["seller_id"] = g["seller_id"].first().where(out["n_sellers"] == 1)
    return out


def prefix_coords(geo: pd.DataFrame) -> pd.DataFrame:
    """Median lat/lng per zip prefix (raw data has up to ~1,100 rows per prefix)."""
    return geo.groupby("geolocation_zip_code_prefix")[["geolocation_lat", "geolocation_lng"]].median()


def haversine_km(lat1, lng1, lat2, lng2):
    lat1, lng1, lat2, lng2 = (np.radians(x) for x in (lat1, lng1, lat2, lng2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lng2 - lng1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def first_order_repeat(t: pd.DataFrame) -> pd.DataFrame:
    """First-order flag and repeat-purchase outcomes per order (ADR-0004).

    First order = a person's earliest order anywhere in the data (ties: lowest order_id).
    Repeat within w days = the same customer_unique_id places any new order (any status)
    strictly after the first order's delivery timestamp and within w days of it. Outcomes
    exist only for eligible first orders: delivered and delivery + w before FOLLOWUP_END;
    otherwise <NA>.
    """
    d = t[["order_id", "customer_unique_id", "purchase_ts", "delivery_ts"]].sort_values(
        ["customer_unique_id", "purchase_ts", "order_id"]
    )
    is_first = ~d["customer_unique_id"].duplicated()
    first = d[is_first].set_index("order_id")
    pairs = first.reset_index()[["order_id", "customer_unique_id", "delivery_ts"]].merge(
        d[["customer_unique_id", "purchase_ts"]], on="customer_unique_id"
    )
    after = pairs[pairs["purchase_ts"] > pairs["delivery_ts"]]
    next_after_delivery = after.groupby("order_id")["purchase_ts"].min().reindex(first.index)

    out = pd.DataFrame(index=pd.Index(d["order_id"], name="order_id"))
    out["is_first_order"] = is_first.to_numpy()
    for w in C.REPEAT_WINDOWS:
        horizon = first["delivery_ts"] + pd.Timedelta(days=w)
        eligible = (horizon < C.FOLLOWUP_END).reindex(out.index, fill_value=False)
        repeat = (next_after_delivery <= horizon).astype("boolean").reindex(out.index)
        out[f"repeat_{w}d_eligible"] = eligible
        out[f"repeat_{w}d"] = repeat.where(eligible, pd.NA)
    return out


def exclusion_reason(t: pd.DataFrame) -> pd.Series:
    """First failing ADR-0005 rule per order; missing means the order is in the headline sample."""
    rules = {
        "not_delivered": t["order_status"] != "delivered",
        "missing_delivery_ts": t["delivery_ts"].isna(),
        "outside_window": ~t["purchase_ts"].between(C.WINDOW_START, C.WINDOW_END, inclusive="left"),
        "no_items": t["n_items"] == 0,
        "multi_seller": t["n_sellers"] > 1,
    }
    conds = [rules[name].to_numpy(dtype=bool) for name in EXCLUSION_ORDER]
    reason = pd.Series(np.select(conds, EXCLUSION_ORDER, default=""), index=t.index)
    return reason.where(reason != "")


def build_table(raw: dict[str, pd.DataFrame]) -> pd.DataFrame:
    o = raw["orders"]
    t = pd.DataFrame(
        {
            "order_id": o["order_id"],
            "customer_id": o["customer_id"],
            "order_status": o["order_status"],
            "purchase_ts": _ts(o["order_purchase_timestamp"]),
            "delivery_ts": _ts(o["order_delivered_customer_date"]),
            "estimated_date": _ts(o["order_estimated_delivery_date"]),
        }
    )
    if not t["order_id"].is_unique:
        raise ValueError("order_id is not unique in the orders table")

    cust = raw["customers"].set_index("customer_id")
    t["customer_unique_id"] = t["customer_id"].map(cust["customer_unique_id"])
    t["customer_state"] = t["customer_id"].map(cust["customer_state"])
    customer_zip = t["customer_id"].map(cust["customer_zip_code_prefix"])

    # Treatment (ADR-0003). Day 0 = delivered on the promised date = on time.
    t["days_late"] = (t["delivery_ts"].dt.normalize() - t["estimated_date"]).dt.days.astype("Int64")
    t["late"] = t["days_late"] > 0
    t["delivery_days"] = (t["delivery_ts"] - t["purchase_ts"]) / pd.Timedelta(days=1)
    t["promised_days"] = (t["estimated_date"] - t["purchase_ts"].dt.normalize()).dt.days.astype("Int64")

    # Review outcomes (ADR-0004).
    rv = latest_reviews(raw["reviews"])
    t["review_score"] = t["order_id"].map(rv["review_score"]).astype("Int64")
    t["low_review"] = t["review_score"] <= C.LOW_REVIEW_MAX
    created = t["order_id"].map(rv["review_creation_date"])
    # Calendar-date comparison: creation dates carry no time of day.
    before = (created.dt.normalize() < t["delivery_ts"].dt.normalize()).astype("boolean")
    t["review_created_before_delivery"] = before.mask(created.isna() | t["delivery_ts"].isna())

    # Repeat outcomes (ADR-0004).
    t = t.join(first_order_repeat(t), on="order_id")

    # Item, seller, and distance covariates.
    t = t.join(order_items_summary(raw["items"], raw["products"], raw["translation"]), on="order_id")
    t["n_items"] = t["n_items"].fillna(0).astype(int)
    t["n_sellers"] = t["n_sellers"].fillna(0).astype(int)
    sellers = raw["sellers"].set_index("seller_id")
    t["seller_state"] = t["seller_id"].map(sellers["seller_state"])
    seller_zip = t["seller_id"].map(sellers["seller_zip_code_prefix"])
    xy = prefix_coords(raw["geolocation"])
    t["distance_km"] = haversine_km(
        customer_zip.map(xy["geolocation_lat"]),
        customer_zip.map(xy["geolocation_lng"]),
        seller_zip.map(xy["geolocation_lat"]),
        seller_zip.map(xy["geolocation_lng"]),
    )

    # Calendar covariates.
    day = t["purchase_ts"].dt.normalize()
    t["purchase_month"] = t["purchase_ts"].dt.strftime("%Y-%m")
    t["purchase_week"] = day - pd.to_timedelta(t["purchase_ts"].dt.day_of_week, unit="D")
    t["bf_2017"] = day == C.BLACK_FRIDAY_2017

    # Sample (ADR-0005).
    t["exclusion_reason"] = exclusion_reason(t)
    t["in_headline"] = t["exclusion_reason"].isna()

    if len(t) != len(o) or not t["order_id"].is_unique:
        raise RuntimeError("build changed the number of orders; a join multiplied or dropped rows")
    return t.sort_values("order_id").reset_index(drop=True)


def exclusion_counts(t: pd.DataFrame) -> dict:
    counts = t["exclusion_reason"].value_counts()
    summary = {
        "total_orders": int(len(t)),
        "excluded": [{"reason": r, "orders": int(counts.get(r, 0))} for r in EXCLUSION_ORDER],
        "in_headline": int(t["in_headline"].sum()),
    }
    if summary["in_headline"] + sum(e["orders"] for e in summary["excluded"]) != summary["total_orders"]:
        raise RuntimeError("exclusion counts do not reconcile to the total order count")
    return summary


def main() -> None:
    t = build_table(read_raw())
    C.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    C.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    t.to_parquet(C.ORDERS_PARQUET, index=False)
    summary = json.dumps(exclusion_counts(t), indent=2) + "\n"
    C.EXCLUSIONS_JSON.write_text(summary)
    print(summary, end="")


if __name__ == "__main__":
    main()
