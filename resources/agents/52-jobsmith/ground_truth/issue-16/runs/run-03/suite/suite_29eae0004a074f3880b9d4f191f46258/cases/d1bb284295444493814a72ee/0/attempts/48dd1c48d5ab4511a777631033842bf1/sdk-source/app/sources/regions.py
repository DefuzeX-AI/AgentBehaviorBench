"""台灣縣市清單與各來源的地區對應。

單一真實來源：前端的地區格、104 來源端 `area` 代碼、以及結果端 location 過濾，
都共用這份表。code 取自 104 官方 Area.json（新竹、嘉義 104 本就縣市併為一碼）。
"""
from __future__ import annotations

# 順序與前端地區格一致（離島 澎湖／金門／連江 暫不列，與參考截圖相同）。
# key：顯示文字（前端直接顯示、後端據此回查）；code：104 area 代碼；aliases：結果端 location 子字串比對。
REGIONS: list[dict] = [
    {"key": "台北市", "code": "6001001000", "aliases": ["台北", "臺北", "taipei"]},
    {"key": "新北市", "code": "6001002000", "aliases": ["新北", "new taipei"]},
    {"key": "桃園市", "code": "6001005000", "aliases": ["桃園", "taoyuan"]},
    {"key": "台中市", "code": "6001008000", "aliases": ["台中", "臺中", "taichung"]},
    {"key": "台南市", "code": "6001014000", "aliases": ["台南", "臺南", "tainan"]},
    {"key": "高雄市", "code": "6001016000", "aliases": ["高雄", "kaohsiung"]},
    {"key": "基隆市", "code": "6001004000", "aliases": ["基隆", "keelung"]},
    {"key": "新竹縣市", "code": "6001006000", "aliases": ["新竹", "hsinchu"]},
    {"key": "苗栗縣", "code": "6001007000", "aliases": ["苗栗", "miaoli"]},
    {"key": "彰化縣", "code": "6001010000", "aliases": ["彰化", "changhua"]},
    {"key": "南投縣", "code": "6001011000", "aliases": ["南投", "nantou"]},
    {"key": "雲林縣", "code": "6001012000", "aliases": ["雲林", "yunlin"]},
    {"key": "嘉義縣市", "code": "6001013000", "aliases": ["嘉義", "chiayi"]},
    {"key": "屏東縣", "code": "6001018000", "aliases": ["屏東", "pingtung"]},
    {"key": "宜蘭縣", "code": "6001003000", "aliases": ["宜蘭", "yilan"]},
    {"key": "花蓮縣", "code": "6001020000", "aliases": ["花蓮", "hualien"]},
    {"key": "台東縣", "code": "6001019000", "aliases": ["台東", "臺東", "taitung"]},
]

_BY_KEY = {r["key"]: r for r in REGIONS}
KEYS = [r["key"] for r in REGIONS]


def parse_keys(raw: str | None) -> list[str]:
    """前端傳來的逗號字串 → 有效縣市 key（保序、去重、丟掉未知值）。"""
    out: list[str] = []
    for part in (raw or "").split(","):
        k = part.strip()
        if k in _BY_KEY and k not in out:
            out.append(k)
    return out


def area_codes(keys: list[str]) -> list[str]:
    """選定縣市 → 104 area 代碼（保序去重）。"""
    out: list[str] = []
    for k in keys:
        r = _BY_KEY.get(k)
        if r and r["code"] not in out:
            out.append(r["code"])
    return out


def match_location(location: str | None, keys: list[str]) -> bool:
    """結果端：job location 是否落在選定縣市（任一別名子字串命中）。

    keys 為空 → 不限，一律 True。location 空/未知 → 視為命中（不因缺地點而誤殺；
    104 一定有地點且已於來源端用 area 篩過，這裡只是其餘來源的保險）。
    """
    if not keys:
        return True
    loc = (location or "").lower()
    if not loc.strip():
        return True
    for k in keys:
        r = _BY_KEY.get(k)
        if r and any(a.lower() in loc for a in r["aliases"]):
            return True
    return False
