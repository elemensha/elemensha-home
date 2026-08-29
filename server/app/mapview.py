"""물건을 지도에 찍는 HTML 페이지.

앱은 이 페이지를 WebView 로 띄우고, PC 브라우저로도 같은 주소를 연다.
네이티브 지도 SDK 를 쓰지 않는 이유는 하나다 - 안드로이드와 PC 에서
같은 화면을 두 번 만들고 두 번 고치고 싶지 않다.

물건 데이터는 페이지 안에 박아서 보낸다. 별도 XHR 로 가져오면 WebView 가
Authorization 헤더를 이어주지 않아 인증을 또 설계해야 한다.

면적 필터는 브라우저에서 건다. 이미 받아온 데이터라 서버를 다시 부를
이유가 없고, 슬라이더를 움직일 때마다 왕복하면 느리다.
"""

from __future__ import annotations

import html
import json


def _fmt_price(value) -> str:
    if not value:
        return "-"
    eok, man = divmod(int(value), 100_000_000)
    man //= 10_000
    if eok and man:
        return f"{eok}억 {man:,}만"
    if eok:
        return f"{eok}억"
    return f"{man:,}만"


def to_markers(items: list[dict]) -> list[dict]:
    """지도에 필요한 것만 추린다. 통째로 실으면 페이지가 몇 MB 가 된다."""
    markers = []
    for it in items:
        lat, lon = it.get("lat"), it.get("lon")
        if lat is None or lon is None:
            continue
        markers.append({
            "la": lat,
            "lo": lon,
            "t": (it.get("title") or "")[:60],
            "a": it.get("address") or "",
            "m": it.get("min_bid_price_krw") or it.get("effective_price_krw"),
            "p": it.get("appraised_price_krw"),
            "s": it.get("exclusive_area_sqm"),
            "f": it.get("failed_bid_count") or 0,
            "d": (it.get("deadline") or "")[:10],
            "b": bool(it.get("_biddable")),
            "u": it.get("url") or "",
        })
    return markers


def render(
    *,
    markers: list[dict],
    total: int,
    js_key: str,
    filters_applied: list[str],
    no_coord_count: int,
) -> str:
    if not js_key:
        return _notice(
            "지도 키가 없습니다",
            "서버 .env 에 KAKAO_JS_KEY 를 넣어야 지도가 뜹니다. "
            "developers.kakao.com 에서 앱을 만들고 JavaScript 키를 발급한 뒤, "
            "플랫폼 &gt; Web 에 이 서버 도메인을 등록하세요.",
        )
    if not markers:
        detail = (
            f"조건에 맞는 물건 {total}건이 있지만 좌표가 아직 없습니다. "
            "수집이 한 번 더 돌면 좌표가 붙습니다."
            if total else "조건에 맞는 물건이 없습니다."
        )
        return _notice("표시할 물건이 없습니다", detail)

    payload = json.dumps(markers, ensure_ascii=False, separators=(",", ":"))
    applied = html.escape(", ".join(filters_applied)) if filters_applied else "전체"
    missing = (
        f'<span class="warn">좌표 없음 {no_coord_count}건 제외</span>'
        if no_coord_count else ""
    )

    return f"""<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>물건 지도</title>
<style>
  * {{ box-sizing: border-box; }}
  html, body {{ margin:0; height:100%; font-family:-apple-system,'Noto Sans KR',sans-serif; }}
  #map {{ width:100%; height:100%; }}
  #bar {{ position:fixed; top:0; left:0; right:0; z-index:10; background:rgba(255,255,255,.96);
         border-bottom:1px solid #ddd; padding:8px 10px; font-size:13px; }}
  #bar .row {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; }}
  #bar input[type=number] {{ width:62px; padding:4px 6px; border:1px solid #ccc; border-radius:6px;
         font-size:13px; }}
  #count {{ font-weight:600; }}
  .warn {{ color:#b26a00; }}
  label {{ display:flex; align-items:center; gap:4px; }}
  .iw {{ padding:10px 12px; font-size:13px; line-height:1.55; min-width:210px; max-width:280px; }}
  .iw b {{ display:block; margin-bottom:4px; font-size:13px; }}
  .iw .addr {{ color:#666; font-size:12px; margin-bottom:6px; word-break:keep-all; }}
  .iw a {{ display:inline-block; margin-top:7px; color:#1a73e8; text-decoration:none; }}
  .live {{ color:#0a7c2f; font-weight:600; }}
  .soon {{ color:#777; }}
</style></head><body>
<div id="bar">
  <div class="row">
    <span id="count"></span>
    <span style="color:#888">· 조건: {applied}</span>
    {missing}
  </div>
  <div class="row" style="margin-top:6px">
    <label>면적 <input type="number" id="amin" placeholder="최소" min="0"> ~
      <input type="number" id="amax" placeholder="최대" min="0"> 평</label>
    <label><input type="checkbox" id="live"> 지금 입찰 가능만</label>
  </div>
</div>
<div id="map"></div>
<script src="//dapi.kakao.com/v2/maps/sdk.js?appkey={html.escape(js_key)}&libraries=clusterer"></script>
<script>
const DATA = {payload};
const PY = 3.305785;   // 1평 = 3.305785㎡

const map = new kakao.maps.Map(document.getElementById('map'), {{
  center: new kakao.maps.LatLng(36.5, 127.8), level: 13
}});
const clusterer = new kakao.maps.MarkerClusterer({{
  map: map, averageCenter: true, minLevel: 6, disableClickZoom: false
}});
const iw = new kakao.maps.InfoWindow({{ removable: true, zIndex: 20 }});

function won(v) {{
  if (!v) return '-';
  const eok = Math.floor(v / 1e8), man = Math.floor((v % 1e8) / 1e4);
  if (eok && man) return eok + '억 ' + man.toLocaleString() + '만';
  return eok ? eok + '억' : man.toLocaleString() + '만';
}}

function body(d) {{
  const pyeong = d.s ? (d.s / PY).toFixed(1) + '평 (' + d.s.toFixed(1) + '㎡)' : '-';
  const rate = (d.p && d.m) ? ' · 감정가의 ' + Math.round(d.m / d.p * 100) + '%' : '';
  const status = d.b ? '<span class="live">지금 입찰 가능</span>'
                     : '<span class="soon">입찰 준비중</span>';
  return '<div class="iw"><b>' + d.t + '</b>'
    + '<div class="addr">' + d.a + '</div>'
    + status + '<br>최저 ' + won(d.m) + rate
    + '<br>면적 ' + pyeong
    + (d.f ? '<br>유찰 ' + d.f + '회' : '')
    + (d.d ? '<br>마감 ' + d.d : '')
    + (d.u ? '<a href="' + d.u + '" target="_blank" rel="noopener">공고 보기 →</a>' : '')
    + '</div>';
}}

// 마커는 한 번만 만들고 재사용한다. 필터를 움직일 때마다 1만 개를
// 새로 만들면 눈에 띄게 버벅인다.
const all = DATA.map(d => {{
  const mk = new kakao.maps.Marker({{ position: new kakao.maps.LatLng(d.la, d.lo) }});
  kakao.maps.event.addListener(mk, 'click', () => {{
    iw.setContent(body(d)); iw.open(map, mk);
  }});
  return {{ mk: mk, d: d }};
}});

function apply() {{
  const lo = parseFloat(document.getElementById('amin').value);
  const hi = parseFloat(document.getElementById('amax').value);
  const liveOnly = document.getElementById('live').checked;
  const keep = all.filter(x => {{
    if (liveOnly && !x.d.b) return false;
    if (!isNaN(lo) || !isNaN(hi)) {{
      if (x.d.s == null) return false;         // 면적을 걸었으면 면적 모르는 건 뺀다
      const py = x.d.s / PY;
      if (!isNaN(lo) && py < lo) return false;
      if (!isNaN(hi) && py > hi) return false;
    }}
    return true;
  }});
  clusterer.clear();
  clusterer.addMarkers(keep.map(x => x.mk));
  document.getElementById('count').textContent = keep.length.toLocaleString() + '건';
  iw.close();
}}

['amin', 'amax'].forEach(id =>
  document.getElementById(id).addEventListener('input', apply));
document.getElementById('live').addEventListener('change', apply);
apply();
</script></body></html>"""


def _notice(title: str, detail: str) -> str:
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>물건 지도</title></head>
<body style="font-family:-apple-system,'Noto Sans KR',sans-serif;padding:28px;color:#333;
             line-height:1.65">
<h3 style="margin:0 0 10px">{html.escape(title)}</h3>
<p style="color:#666;font-size:14px">{detail}</p>
</body></html>"""
