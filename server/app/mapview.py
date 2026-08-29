"""물건을 지도에 찍는 HTML 페이지. 네이버 지도 v3.

앱은 이 페이지를 WebView 로 띄우고, PC 브라우저로도 같은 주소를 연다.
네이티브 지도 SDK 를 쓰지 않는 이유는 하나다 - 안드로이드와 PC 에서
같은 화면을 두 번 만들고 두 번 고치고 싶지 않다.

네이버를 쓰는 이유는 지적편집도다. 필지 경계가 지도 위에 그대로 나와서
토지를 볼 때 '이 땅이 어디서 어디까지인지'를 지도에서 바로 본다.

물건 데이터는 페이지 안에 박아서 보낸다. 별도 XHR 로 가져오면 WebView 가
Authorization 헤더를 이어주지 않아 인증을 또 설계해야 한다.

면적 필터는 브라우저에서 건다. 이미 받아온 데이터라 서버를 다시 부를
이유가 없고, 값을 바꿀 때마다 왕복하면 느리다.
"""

from __future__ import annotations

import html
import json


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
    map_key: str,
    filters_applied: list[str],
    no_coord_count: int,
) -> str:
    if not map_key:
        return _notice(
            "지도 키가 없습니다",
            "서버 .env 에 NAVER_MAP_KEY 를 넣어야 지도가 뜹니다. "
            "네이버 클라우드 플랫폼 콘솔에서 Maps 이용 신청을 하고, "
            "Web Dynamic Map 의 Key ID 를 발급한 뒤 Web 서비스 URL 에 "
            "이 서버 도메인을 등록하세요.",
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
  * {{ box-sizing:border-box; }}
  html, body {{ margin:0; height:100%; font-family:-apple-system,'Noto Sans KR',sans-serif; }}
  #map {{ width:100%; height:100%; }}
  #bar {{ position:fixed; top:0; left:0; right:0; z-index:10; background:rgba(255,255,255,.96);
         border-bottom:1px solid #ddd; padding:8px 10px; font-size:13px; }}
  #bar .row {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; }}
  #bar input[type=number] {{ width:60px; padding:4px 6px; border:1px solid #ccc;
         border-radius:6px; font-size:13px; }}
  #count {{ font-weight:600; }}
  .warn {{ color:#b26a00; }}
  label {{ display:flex; align-items:center; gap:4px; }}
  .pin {{ width:13px; height:13px; border-radius:50%; border:2px solid #fff;
          box-shadow:0 1px 3px rgba(0,0,0,.4); }}
  .pin.live {{ background:#0a7c2f; }}
  .pin.soon {{ background:#9aa0a6; }}
  .cl {{ display:flex; align-items:center; justify-content:center; border-radius:50%;
         color:#fff; font-weight:700; font-size:12px; background:rgba(26,115,232,.85);
         border:2px solid #fff; box-shadow:0 1px 4px rgba(0,0,0,.35); }}
  .iw {{ padding:11px 13px; font-size:13px; line-height:1.55; min-width:210px; max-width:290px;
         background:#fff; border-radius:8px; }}
  .iw b {{ display:block; margin-bottom:4px; }}
  .iw .addr {{ color:#666; font-size:12px; margin-bottom:6px; word-break:keep-all; }}
  .iw a {{ display:inline-block; margin-top:7px; color:#1a73e8; text-decoration:none; }}
  .live-t {{ color:#0a7c2f; font-weight:600; }}
  .soon-t {{ color:#777; }}
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
    <label><input type="checkbox" id="live"> 입찰 가능만</label>
    <label><input type="checkbox" id="cad"> 지적편집도</label>
  </div>
</div>
<div id="map"></div>
<script src="https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId={html.escape(map_key)}"></script>
<script>
const DATA = {payload};
const PY = 3.305785;   // 1평 = 3.305785㎡

const map = new naver.maps.Map('map', {{
  center: new naver.maps.LatLng(36.5, 127.8), zoom: 7
}});

// 지적편집도. 토지를 볼 때 필지 경계가 지도에 나와야 '이 땅이 어디까지'
// 인지 알 수 있다. 기본으로 켜면 도시에서 화면이 지저분해 토글로 둔다.
const cadastral = new naver.maps.CadastralLayer();
document.getElementById('cad').addEventListener('change', e => {{
  e.target.checked ? cadastral.setMap(map) : cadastral.setMap(null);
}});

const iw = new naver.maps.InfoWindow({{ borderWidth: 0, backgroundColor: 'transparent',
  disableAnchor: false, pixelOffset: new naver.maps.Point(0, -4) }});

function won(v) {{
  if (!v) return '-';
  const eok = Math.floor(v / 1e8), man = Math.floor((v % 1e8) / 1e4);
  if (eok && man) return eok + '억 ' + man.toLocaleString() + '만';
  return eok ? eok + '억' : man.toLocaleString() + '만';
}}

function body(d) {{
  const py = d.s ? (d.s / PY).toFixed(1) + '평 (' + d.s.toFixed(1) + '㎡)' : '-';
  const rate = (d.p && d.m) ? ' · 감정가의 ' + Math.round(d.m / d.p * 100) + '%' : '';
  const st = d.b ? '<span class="live-t">지금 입찰 가능</span>'
                 : '<span class="soon-t">입찰 준비중</span>';
  return '<div class="iw"><b>' + d.t + '</b>'
    + '<div class="addr">' + d.a + '</div>'
    + st + '<br>최저 ' + won(d.m) + rate
    + '<br>면적 ' + py
    + (d.f ? '<br>유찰 ' + d.f + '회' : '')
    + (d.d ? '<br>마감 ' + d.d : '')
    + (d.u ? '<a href="' + d.u + '" target="_blank" rel="noopener">공고 보기 →</a>' : '')
    + '</div>';
}}

// 네이버 v3 에는 클러스터러가 없다. 외부 라이브러리를 끌어오는 대신
// 격자로 묶는다 - 마커 3천 개를 한꺼번에 그리면 폰에서 눈에 띄게 밀린다.
let shown = [];
function clear() {{ shown.forEach(m => m.setMap(null)); shown = []; }}

function pin(d) {{
  const m = new naver.maps.Marker({{
    position: new naver.maps.LatLng(d.la, d.lo), map: map,
    icon: {{ content: '<div class="pin ' + (d.b ? 'live' : 'soon') + '"></div>',
            anchor: new naver.maps.Point(8, 8) }},
  }});
  naver.maps.Event.addListener(m, 'click', () => {{
    iw.setContent(body(d)); iw.open(map, m);
  }});
  return m;
}}

function cluster(items, lat, lon) {{
  const n = items.length;
  const size = n < 10 ? 32 : n < 100 ? 40 : n < 1000 ? 48 : 56;
  const m = new naver.maps.Marker({{
    position: new naver.maps.LatLng(lat, lon), map: map,
    icon: {{ content: '<div class="cl" style="width:' + size + 'px;height:' + size + 'px">'
                     + n + '</div>',
            anchor: new naver.maps.Point(size / 2, size / 2) }},
  }});
  naver.maps.Event.addListener(m, 'click', () => {{
    // 묶음을 누르면 그 안으로 파고든다. 세어만 보여주고 못 열면 답답하다.
    map.setCenter(new naver.maps.LatLng(lat, lon));
    map.setZoom(Math.min(map.getZoom() + 3, 19));
  }});
  return m;
}}

function visible() {{
  const lo = parseFloat(document.getElementById('amin').value);
  const hi = parseFloat(document.getElementById('amax').value);
  const liveOnly = document.getElementById('live').checked;
  return DATA.filter(d => {{
    if (liveOnly && !d.b) return false;
    if (!isNaN(lo) || !isNaN(hi)) {{
      if (d.s == null) return false;      // 면적을 걸었으면 면적 모르는 건 뺀다
      const py = d.s / PY;
      if (!isNaN(lo) && py < lo) return false;
      if (!isNaN(hi) && py > hi) return false;
    }}
    return true;
  }});
}}

function draw() {{
  const keep = visible();
  document.getElementById('count').textContent = keep.length.toLocaleString() + '건';
  clear();
  iw.close();

  const z = map.getZoom();
  const b = map.getBounds();
  const inView = keep.filter(d => b.hasLatLng(new naver.maps.LatLng(d.la, d.lo)));

  // 충분히 당겨 봤고 화면 안이 성기면 개별 마커로 보여준다.
  if (z >= 15 || inView.length <= 60) {{
    inView.forEach(d => shown.push(pin(d)));
    return;
  }}
  // 화면을 격자로 나눠 묶는다. 칸 수를 고정하면 확대할수록 칸이 촘촘해진다.
  const sw = b.getSW(), ne = b.getNE();
  const rows = 9, cols = 9;
  const dLat = (ne.lat() - sw.lat()) / rows, dLon = (ne.lng() - sw.lng()) / cols;
  const cells = new Map();
  inView.forEach(d => {{
    const r = Math.floor((d.la - sw.lat()) / dLat), c = Math.floor((d.lo - sw.lng()) / dLon);
    const k = r + ':' + c;
    if (!cells.has(k)) cells.set(k, []);
    cells.get(k).push(d);
  }});
  cells.forEach(items => {{
    if (items.length === 1) {{ shown.push(pin(items[0])); return; }}
    const la = items.reduce((s, d) => s + d.la, 0) / items.length;
    const lo2 = items.reduce((s, d) => s + d.lo, 0) / items.length;
    shown.push(cluster(items, la, lo2));
  }});
}}

naver.maps.Event.addListener(map, 'idle', draw);
['amin', 'amax'].forEach(id =>
  document.getElementById(id).addEventListener('input', draw));
document.getElementById('live').addEventListener('change', draw);
draw();
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
