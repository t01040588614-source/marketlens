from app.integrations.kis_ws_client import (
    parse_h0stcnt0_body,
    parse_h0stcnt0_payload,
    parse_pipe_message,
)


def test_parse_h0stcnt0_price():
    payload = "005930^153000^71500^2^1500^2.14"
    parsed = parse_h0stcnt0_payload(payload)
    assert parsed == ("005930", 71500.0)


def test_parse_h0stcnt0_multi_record():
    fields1 = ["005930", "153000", "71500"] + ["0"] * 43
    fields2 = ["000660", "153001", "142000"] + ["0"] * 43
    body = "^".join(fields1 + fields2)
    rows = parse_h0stcnt0_body(body, 2)
    assert len(rows) == 2
    assert rows[0] == ("005930", 71500.0)
    assert rows[1] == ("000660", 142000.0)


def test_parse_pipe_message():
    raw = "0|H0STCNT0|1|005930^153000^71500^1^100^0.14"
    ticks = parse_pipe_message(raw)
    assert len(ticks) == 1
    assert ticks[0][0] == "005930"
    assert ticks[0][1] == 71500.0
