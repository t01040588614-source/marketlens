from app.services.kis_subscription_planner import plan_kis_subscriptions


def test_plan_priority_watchlist_first():
    plans = plan_kis_subscriptions(
        watchlist=["005930", "000660"],
        ws_symbols=["035420"],
        defaults=["051910"],
    )
    assert "005930" in plans["H0STCNT0"]
    assert "000660" in plans["H0STCNT0"]
    assert "035420" in plans["H0STCNT0"]
    assert plans["H0STASP0"].issubset(plans["H0STCNT0"])
