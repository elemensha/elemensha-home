"""지도 페이지를 전/후 두 벌로 뽑아 같은 자료로 비교한다.

네이버 지도 캔버스는 키가 도메인에 묶여 있어 로컬에서는 뜨지 않는다.
그래서 이 비교로 확인할 수 있는 것은 **조작부(상단 띠)와 그 안의
글자·입력칸·버튼**이다. 지도 타일과 말풍선은 이 파일로 확인하지 못한다.
"""
import io
import os
import subprocess
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "tools", "mapqa")
os.makedirs(OUT, exist_ok=True)

# 두 판이 똑같은 자료를 그리도록 여기 한 벌만 둔다.
MARKERS = [
    {"k": "onbid:2026-08842-001", "la": 37.5665, "lo": 126.9780,
     "t": "서울 중구 을지로 3가 대지 82㎡", "a": "서울특별시 중구 을지로3가 12-3",
     "m": 412000000, "p": 530000000, "s": 82.4, "f": 2, "d": "2026-09-24",
     "b": True, "u": "https://www.onbid.co.kr", "n": "2026-08842-001",
     "fv": True, "sh": False},
    {"k": "onbid:2026-07711-002", "la": 37.4979, "lo": 127.0276,
     "t": "서울 강남구 역삼동 오피스텔 29㎡", "a": "서울특별시 강남구 역삼동 736-21",
     "m": 268000000, "p": 310000000, "s": 29.7, "f": 1, "d": "2026-10-02",
     "b": False, "u": "https://www.onbid.co.kr", "n": "2026-07711-002",
     "fv": False, "sh": True},
    {"k": "onbid:2026-05520-004", "la": 37.3219, "lo": 127.1268,
     "t": "경기 성남시 분당구 임야 1,204㎡", "a": "경기도 성남시 분당구 대장동 산 18",
     "m": 96000000, "p": 154000000, "s": 1204.0, "f": 3, "d": "2026-09-15",
     "b": True, "u": "https://www.onbid.co.kr", "n": "2026-05520-004",
     "fv": False, "sh": False},
]

KWARGS = dict(
    markers=MARKERS,
    total=2116,
    map_key="LOCAL-QA-KEY",
    filters_applied=["내 조건", "지분 제외"],
    no_coord_count=41,
    api_token="",
    last_collected_at="2026-09-13T05:12",
)


def load(source_text, name):
    """mapview.py 원문을 모듈로 올린다. 파일을 건드리지 않으려고 이렇게 한다."""
    mod = types.ModuleType(name)
    mod.__dict__["__name__"] = name
    exec(compile(source_text, name, "exec"), mod.__dict__)
    return mod



# 네이버 스크립트는 로컬에서 안 뜬다. 지도 대신 아무 것도 안 하는 껍데기를
# 넣어 페이지 JS 가 끝까지 돌게 한다. 조작부 글자(건수 등)는 그 JS 가 채운다.
STUB = """<script>
(function () {
  function Nop() { return new Proxy(function () {}, handler); }
  var handler = {
    get: function (t, k) { if (k === Symbol.toPrimitive) return function () { return 0; };
                           return Nop(); },
    apply: function () { return Nop(); },
    construct: function () { return Nop(); },
  };
  window.naver = Nop();
})();
</script>"""


def stub_naver(html):
    import re
    return re.sub(r'<script src="https://oapi\.map\.naver\.com[^"]*"></script>', STUB, html)

old_src = subprocess.run(
    ["git", "show", "HEAD:server/app/mapview.py"],
    cwd=ROOT, capture_output=True, check=True,
).stdout.decode("utf-8")
new_src = io.open(os.path.join(ROOT, "server", "app", "mapview.py"),
                  encoding="utf-8").read()

for label, src in (("before", old_src), ("after", new_src)):
    html = stub_naver(load(src, "mapview_" + label).render(**KWARGS))
    path = os.path.join(OUT, label + ".html")
    io.open(path, "w", encoding="utf-8", newline="\n").write(html)
    print(label, "->", path, len(html), "bytes")
