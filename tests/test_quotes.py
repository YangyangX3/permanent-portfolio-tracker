from app.quotes import _parse_eastmoney_fundgz, _parse_tencent_qt, _tencent_symbol


def test_tencent_symbol_mapping() -> None:
    assert _tencent_symbol("600519") == "sh600519"
    assert _tencent_symbol("510300") == "sh510300"
    assert _tencent_symbol("000001") == "sz000001"
    assert _tencent_symbol("300750") == "sz300750"
    assert _tencent_symbol("bj430047") == "bj430047"
    assert _tencent_symbol("sh600000") == "sh600000"
    assert _tencent_symbol("161725") == "sz161725"
    assert _tencent_symbol("018064") == "sz018064"


def test_parse_tencent_qt_basic() -> None:
    text = (
        'v_sh600519="1~贵州茅台~600519~1337.00~1340.06~1340.10~61949~24745~37204~'
        '1336.99~1~1336.90~1~1336.59~17~1336.50~6~1336.37~16~'
        '1337.00~61~1337.10~1~1337.18~5~1337.25~2~1337.28~1~~'
        '20260123161414~-3.06~-0.23~1348.00~1332.47~";'
    )
    q = _parse_tencent_qt(text=text, requested_code="600519")
    assert q is not None
    assert q.name == "贵州茅台"
    assert q.price == 1337.0
    assert q.change_pct == -0.23
    assert q.as_of == "20260123161414"


def test_parse_eastmoney_fundgz_basic() -> None:
    text = "jsonpgz({\"fundcode\":\"161725\",\"name\":\"招商中证白酒\",\"gsz\":\"1.2345\",\"gszzl\":\"-0.56\",\"gztime\":\"2026-01-25 14:30\"});"
    q = _parse_eastmoney_fundgz(text=text, code="161725")
    assert q is not None
    assert q.name == "招商中证白酒"
    assert q.price == 1.2345
    assert q.change_pct == -0.56
    assert q.as_of == "2026-01-25 14:30"
