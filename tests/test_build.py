"""Unit tests for build definitions (ADR-0003..0005) on small synthetic fixtures."""

import pandas as pd
import pytest

from late_delivery.build import build_table, read_csv


def _df(columns, rows):
    return pd.DataFrame(rows, columns=columns)


def make_raw():
    orders = _df(
        ["order_id", "customer_id", "order_status", "order_purchase_timestamp",
         "order_delivered_customer_date", "order_estimated_delivery_date"],
        [
            ("a1", "ca1", "delivered", "2017-03-01 10:00:00", "2017-03-10 15:00:00", "2017-03-10 00:00:00"),  # day 0
            ("a2", "ca2", "delivered", "2017-03-01 10:05:00", "2017-03-09 12:00:00", "2017-03-20 00:00:00"),  # same session as a1
            ("b1", "cb1", "delivered", "2017-04-01 09:00:00", "2017-04-11 09:00:00", "2017-04-10 00:00:00"),  # day +1
            ("b2", "cb2", "delivered", "2017-04-05 09:00:00", "2017-04-15 09:00:00", "2017-04-25 00:00:00"),  # placed while b1 in transit
            ("c1", "cc1", "delivered", "2017-05-01 09:00:00", "2017-05-08 09:00:00", "2017-05-20 00:00:00"),
            ("c2", "cc2", "delivered", "2017-06-01 09:00:00", "2017-06-08 09:00:00", "2017-06-20 00:00:00"),  # repeat of c1
            ("d1", "cd1", "delivered", "2018-07-01 09:00:00", "2018-07-05 09:00:00", "2018-07-20 00:00:00"),  # follow-up past cap
            ("e1", "ce1", "delivered", "2017-07-01 09:00:00", "2017-07-08 09:00:00", "2017-07-20 00:00:00"),  # two sellers
            ("f1", "cf1", "canceled", "2017-08-01 09:00:00", None, "2017-08-20 00:00:00"),
            ("g1", "cg1", "delivered", "2016-10-05 09:00:00", "2016-10-15 09:00:00", "2016-10-30 00:00:00"),  # before window
            ("g2", "cg2", "delivered", "2017-09-01 09:00:00", "2017-09-08 09:00:00", "2017-09-20 00:00:00"),  # same person as g1
        ],
    )
    people = {"ca1": "uA", "ca2": "uA", "cb1": "uB", "cb2": "uB", "cc1": "uC", "cc2": "uC",
              "cd1": "uD", "ce1": "uE", "cf1": "uF", "cg1": "uG", "cg2": "uG"}
    customers = _df(
        ["customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_state"],
        [(c, u, 3003, "SP") for c, u in people.items()],
    )
    items = _df(
        ["order_id", "order_item_id", "product_id", "seller_id", "price", "freight_value"],
        [(oid, 1, "p1", "s1", 50.0, 10.0) for oid in orders["order_id"]]
        + [("e1", 2, "p2", "s2", 80.0, 12.0), ("a1", 2, "p2", "s1", 90.0, 5.0), ("b1", 2, "p3", "s1", 70.0, 5.0),
           ("c2", 2, "p1", "s1", 30.0, 3.0)],  # c2 = 80, unlike c1 = 50, so repeat GMV must use c2's items
    )
    products = _df(["product_id", "product_category_name"],
                   [("p1", "cama_mesa_banho"), ("p2", "pc_gamer"), ("p3", None)])
    translation = _df(["product_category_name", "product_category_name_english"],
                      [("cama_mesa_banho", "bed_bath_table")])
    sellers = _df(["seller_id", "seller_zip_code_prefix", "seller_state"],
                  [("s1", 1001, "SP"), ("s2", 2002, "RJ")])
    reviews = _df(
        ["review_id", "order_id", "review_score", "review_creation_date", "review_answer_timestamp"],
        [
            ("r1", "a1", 5, "2017-03-11 00:00:00", "2017-03-11 10:00:00"),
            ("r2", "a1", 1, "2017-03-11 00:00:00", "2017-03-12 10:00:00"),  # answered later -> kept
            ("r3", "b1", 2, "2017-04-12 00:00:00", "2017-04-13 10:00:00"),
            ("r3", "b2", 2, "2017-04-16 00:00:00", "2017-04-17 10:00:00"),  # same review_id, second order
        ],
    )
    geolocation = _df(["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng"],
                      [(1001, -23.5, -46.6), (2002, -22.9, -43.2), (3003, -23.0, -46.0)])
    return {"orders": orders, "customers": customers, "items": items, "reviews": reviews,
            "products": products, "sellers": sellers, "geolocation": geolocation, "translation": translation}


@pytest.fixture(scope="module")
def t():
    return build_table(make_raw()).set_index("order_id")


def test_day0_on_time_day1_late(t):
    assert t.loc["a1", "days_late"] == 0 and not t.loc["a1", "late"]
    assert t.loc["b1", "days_late"] == 1 and t.loc["b1", "late"]


def test_latest_answered_review_kept(t):
    assert t.loc["a1", "review_score"] == 1 and t.loc["a1", "low_review"]


def test_shared_review_id_counts_for_each_order(t):
    assert t.loc["b1", "review_score"] == 2 and t.loc["b2", "review_score"] == 2


def test_n_reviews_counts_raw_rows_per_order(t):
    assert t.loc["a1", "n_reviews"] == 2  # both rows count, not only the kept one
    assert t.loc["b1", "n_reviews"] == 1 and t.loc["b2", "n_reviews"] == 1  # shared review_id: once per order
    assert t.loc["c1", "n_reviews"] == 0


def test_same_session_order_not_a_repeat(t):
    assert t.loc["a1", "is_first_order"] and not t.loc["a2", "is_first_order"]
    assert t.loc["a1", "repeat_90d_eligible"] and not t.loc["a1", "repeat_90d"]


def test_order_placed_in_transit_not_a_repeat(t):
    assert t.loc["b1", "repeat_90d_eligible"] and not t.loc["b1", "repeat_90d"]


def test_order_after_delivery_is_a_repeat(t):
    assert t.loc["c1", "repeat_90d"] and t.loc["c1", "repeat_180d"]


def test_followup_eligibility_cap(t):
    assert not t.loc["d1", "repeat_90d_eligible"] and pd.isna(t.loc["d1", "repeat_90d"])


def test_review_answer_ts_from_kept_review(t):
    assert t.loc["a1", "review_answer_ts"] == pd.Timestamp("2017-03-12 10:00:00")  # latest-answered (r2), not r1
    assert t.loc["b2", "review_answer_ts"] == pd.Timestamp("2017-04-17 10:00:00")  # shared review_id, own row
    assert pd.isna(t.loc["c1", "review_answer_ts"])


def test_repeat_gmv_follows_repeat_rule(t):
    assert t.loc["c1", "repeat_90d_gmv"] == 80.0 and t.loc["c1", "repeat_180d_gmv"] == 80.0  # c2's items
    assert t.loc["a1", "repeat_90d_gmv"] == 0.0  # same-session order is not a repeat
    assert t.loc["b1", "repeat_90d_gmv"] == 0.0  # order placed in transit is not a repeat
    assert pd.isna(t.loc["d1", "repeat_90d_gmv"])  # follow-up past the cap
    assert pd.isna(t.loc["c2", "repeat_90d_gmv"])  # not a first order


def test_first_order_is_earliest_anywhere(t):
    assert not t.loc["g2", "is_first_order"] and pd.isna(t.loc["g2", "repeat_90d"])


def test_exclusions_reconcile(t):
    assert t.loc["f1", "exclusion_reason"] == "not_delivered"
    assert t.loc["g1", "exclusion_reason"] == "outside_window"
    assert t.loc["e1", "exclusion_reason"] == "multi_seller"
    assert t["in_headline"].sum() == 8 and len(t) == 11 and t.index.is_unique


def test_covariates(t):
    assert t.loc["a1", "main_category"] == "pc_gamer"  # highest-price item; untranslated name kept
    assert t.loc["b1", "main_category"] == "unknown"   # highest-price item has no category
    assert t.loc["c1", "main_category"] == "bed_bath_table"
    assert t.loc["c1", "distance_km"] > 0 and pd.isna(t.loc["e1", "seller_id"])


def test_bom_header_stripped(tmp_path):
    path = tmp_path / "translation.csv"
    path.write_bytes("﻿product_category_name,product_category_name_english\nx,y\n".encode("utf-8"))
    assert list(read_csv(path).columns)[0] == "product_category_name"
