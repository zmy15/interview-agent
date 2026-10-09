"""
SPA 静态资源兜底路由的行为测试

背景：前端的 SPA 兜底路由（`/{full_path:path}`）会吞掉**所有**未匹配的
路径。早期实现把它无条件指向 index.html，于是当某个功能的开关没开、
路由未注册时，`/api/xxx` 会返回 HTML 而不是 JSON：

    前端 fetch -> 得到 "<!doctype html>..." -> JSON.parse 抛
    「Unexpected token '<', "<!doctype "... is not valid JSON」

用户看到的就是这句毫无意义的解析错误，完全不知道真实原因是
「功能开关没开」。因此 /api/* 必须返回结构化 JSON 错误。
"""


def test_unknown_api_path_returns_json_not_html(client):
    """未注册的 /api 路径必须返回 JSON 错误，而不是 index.html"""
    resp = client.get("/api/definitely-not-a-real-endpoint")

    assert resp.status_code == 404
    # 关键：不能是 text/html，否则前端 JSON.parse 会报解析错误
    assert "application/json" in resp.headers.get("content-type", "")

    body = resp.json()
    assert "detail" in body
    # 提示要指向「开关未开启」这个最常见原因
    assert "开关" in body["detail"]


def test_disabled_feature_api_returns_json(client):
    """功能未启用时（路由未注册），接口也应返回 JSON 提示"""
    resp = client.get("/api/not-enabled-feature/info")

    assert resp.status_code == 404
    assert "application/json" in resp.headers.get("content-type", "")
    assert "开关" in resp.json()["detail"]


def test_spa_routes_still_serve_html(client):
    """普通前端路由仍要回退到 index.html（不能被上面的改动影响）"""
    resp = client.get("/some/spa/route")

    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")