#!/usr/bin/env python3
"""理财产品代码 → 登记编码（Z编号）转换器

可插拔适配器架构：新增一家理财子公司时，继承 Resolver 实现 match/resolve，
然后加入 RESOLVERS 列表即可。

用法:
  python code_convert.py AF265416            # 自动识别机构，转 Z 编码
  python code_convert.py TYG3M1906 --nav     # 顺带拉最新净值
  代码调用: from code_convert import convert; convert("AF265416")

已适配:
  - 信银理财（中信理财）: AF/BF 开头，走 wechat.citic-wealth.com 免签名接口
  - 杭银理财: TYG/JQB 等内部码，走 www.hzbankwealth.cn 详情 JSON
"""
import argparse
import json
import re
import sys
from dataclasses import dataclass, field

import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def _legacy_ssl_session():
    """部分老网关（信银 wechat 站）要求允许 legacy SSL 重协商。"""
    import ssl
    from requests.adapters import HTTPAdapter
    from urllib3.util.ssl_ import create_urllib3_context

    class LegacyAdapter(HTTPAdapter):
        def init_poolmanager(self, *a, **kw):
            ctx = create_urllib3_context()
            ctx.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
            kw["ssl_context"] = ctx
            return super().init_poolmanager(*a, **kw)

    s = requests.Session()
    s.headers.update(UA)
    s.mount("https://", LegacyAdapter())
    return s


@dataclass
class ProductInfo:
    prod_code: str          # 机构自己的产品/份额代码
    name: str = ""
    reg_code: str = ""      # 登记编码 Z700xxxxx
    manager: str = ""       # 理财子公司
    extra: dict = field(default_factory=dict)  # 净值等附加信息

    def __str__(self):
        s = f"{self.prod_code} -> {self.reg_code or '?'}"
        if self.name:
            s += f"  {self.name}"
        if self.extra.get("risk"):
            s += f"  {self.extra['risk']}"
        if self.extra.get("nav"):
            s += f"  净值 {self.extra['nav']} @{self.extra.get('nav_date', '')}"
        return s


class Resolver:
    """适配器接口。子类实现 match() 和 resolve()。"""
    name = "base"

    def match(self, code: str) -> bool:
        raise NotImplementedError

    def resolve(self, code: str, with_nav: bool = False) -> ProductInfo:
        raise NotImplementedError


class CiticResolver(Resolver):
    """信银理财（原中信银行理财子公司）。

    代码规则: AF 开头公募 / BF 开头私募，后接 G/B 等份额后缀。
    接口: wechat.citic-wealth.com 微信站 API，无签名无限频，
    getTAProductDetail 直接返回 registCode（登记编码）和产品名，
    代销机构列表里也标了杭州银行。
    """
    name = "信银理财"
    SESSION = _legacy_ssl_session()
    DETAIL = ("https://wechat.citic-wealth.com/cms.product/api/custom/"
              "productInfo/getTAProductDetail")
    NAV = ("https://wechat.citic-wealth.com/cms.product/api/custom/"
           "productInfo/getTAProductNav")

    def match(self, code):
        return bool(re.fullmatch(r"[AB]F[0-9A-Z]+", code.upper()))

    def resolve(self, code, with_nav=False):
        code = code.upper()
        # 详情接口按份额代码查询；裸产品码依次尝试常见份额后缀
        candidates = [code] if re.search(r"[0-9][GB]$", code) else \
            [code, code + "G", code + "B"]
        d = {}
        share_code = code
        for c in candidates:
            r = self.SESSION.get(self.DETAIL, params={"prodCode": c,
                                                      "officialFlag": 1},
                                 timeout=20)
            d = (r.json().get("data") or {})
            if d.get("registCode"):
                share_code = c
                break
        info = ProductInfo(prod_code=code,
                           name=d.get("prodName") or d.get("fprodName") or "",
                           reg_code=d.get("registCode") or "",
                           manager="信银理财有限责任公司")
        if d.get("fprodCode") and d.get("fprodCode") != code:
            info.extra["parent_code"] = d["fprodCode"]
        for dist in d.get("distributorInfoList") or []:
            info.extra.setdefault("distributors", []).append(
                dist.get("distributorName"))
        if d.get("riskLevelStr"):
            info.extra["risk"] = d["riskLevelStr"]
        if d.get("openIntervalDays"):
            info.extra["open_rule"] = f"每{int(d['openIntervalDays'])}天开放"
        if with_nav:
            rn = self.SESSION.get(self.NAV, params={"prodCode": share_code,
                                                    "queryUnit": 1,
                                                    "privateFlag": 1},
                                  timeout=20)
            pics = (rn.json().get("data") or {}).get("productNavPic") or []
            if pics:
                last = max(pics, key=lambda x: x["navDate"])
                nd = last["navDate"]
                info.extra["nav"] = float(last["nav"])
                info.extra["nav_date"] = (f"{nd[:4]}-{nd[4:6]}-{nd[6:]}")
        return info


class HzBankResolver(Resolver):
    """杭银理财。

    代码规则: TYG/JQB/内部码（杭银不用 AF 前缀）。
    接口: 官网静态详情 JSON，dengjino 字段即登记编码，
    danweijingzhi/jingzhiriqi 顺带给出最新净值。
    """
    name = "杭银理财"
    DETAIL = "https://www.hzbankwealth.cn/eportal/hzbw/detail/{code}_detail.json"

    def match(self, code):
        # AF/BF 归信银，其余字母数字混合码归杭银
        return bool(re.fullmatch(r"[A-Z]{2,4}[0-9A-Z]+", code.upper())) \
            and not code.upper().startswith(("AF", "BF"))

    def resolve(self, code, with_nav=False):
        code = code.upper()
        r = requests.get(self.DETAIL.format(code=code), headers=UA,
                         timeout=20, verify=False)
        r.raise_for_status()
        d = r.json()
        info = ProductInfo(prod_code=code,
                           name=d.get("contenttitle") or "",
                           reg_code=d.get("dengjino") or "",
                           manager=d.get("guanliren") or "")
        if with_nav and d.get("danweijingzhi"):
            info.extra["nav"] = float(d["danweijingzhi"])
            info.extra["nav_date"] = d.get("jingzhiriqi") or ""
        if d.get("rizengzhang"):
            info.extra["risk"] = d["rizengzhang"]
        if d.get("licaiqixian"):
            info.extra["open_rule"] = d["licaiqixian"]  # 如「最低持有360天可赎」
        if d.get("touzileixin"):
            info.extra["invest_type"] = d["touzileixin"]
        return info


class CmbResolver(Resolver):
    """招行一网通代销理财（XY 开头，兴银理财等）。

    接口: cfweb.paas.cmbchina.com，需 SM4 签名头：
      key  = base64decode(AUTH_SN) 首末字符替换为 "9"/"8" (CFWEB_C2="98")，16字节
      data = appId + "|" + 毫秒时间戳
      signature = base64(SM4-ECB(key, data))，头 appId/timespan/signature
      且必须带 Content-Type: application/json，否则后端报 ERR9999。
    流程: getProductByPrdCode 拿 regCode/saaCod/funCod/名称/风险，
    再 getSAValueByPage 分页拉净值（znavDat=yyyyMMdd, znavVal=净值）。
    """
    name = "招行代销理财"
    API = "https://cfweb.paas.cmbchina.com/api"
    APP_ID = "LB50.22_CFWebUI"
    AUTH_SN = "NXF3QkdqdTczSkFYaWQ0RA=="
    C2 = "98"
    _key = None

    @classmethod
    def _sm4_key(cls):
        if cls._key is None:
            import base64
            sn = base64.b64decode(cls.AUTH_SN).decode()
            cls._key = (cls.C2[0] + sn[1:-1] + cls.C2[1]).encode()
        return cls._key

    def _post(self, path, data=None, qs=None):
        import base64
        import time
        import uuid
        from gmssl.sm4 import CryptSM4, SM4_ENCRYPT
        ts = int(time.time() * 1000)
        c = CryptSM4()
        c.set_key(self._sm4_key(), SM4_ENCRYPT)
        sig = base64.b64encode(
            c.crypt_ecb((self.APP_ID + "|" + str(ts)).encode())).decode()
        h = {"User-Agent": UA["User-Agent"], "appId": self.APP_ID,
             "timespan": str(ts), "signature": sig,
             "X-B3-BusinessId": str(uuid.uuid4()).upper(),
             "Content-Type": "application/json;charset=UTF-8",
             "Referer": "https://cfweb.paas.cmbchina.com/"}
        url = self.API + path
        if qs:
            url += "?" + qs
        r = requests.post(url, headers=h,
                          data=json.dumps(data) if data else None,
                          timeout=30, verify=False)
        return r.json()

    def match(self, code):
        # XY+6位=招行代销码；4-6位数字(可带字母)=招银销售代码；
        # GD+6位=光大理财（同走招行 cfweb 代销目录）
        return bool(re.fullmatch(r"(XY|GD)[0-9]{6}|[0-9]{4,6}[A-Z]?", code.upper()))

    def resolve(self, code, with_nav=False):
        code = code.upper()
        lst = (self._post("/ProductInfo/getProductByPrdCode",
                          qs=f"prdCode={code}").get("body") or [])
        if not lst:
            raise RuntimeError(f"招行官网查无此代码: {code}")
        d = lst[0]
        info = ProductInfo(prod_code=code, name=d.get("prdName") or "",
                           reg_code=d.get("regCode") or "",
                           manager=d.get("comNam") or "")
        info.extra["saa_cod"] = d.get("saaCod") or ""
        if d.get("style"):
            info.extra["invest_type"] = d["style"]
        if d.get("risk"):
            info.extra["risk"] = d["risk"]
        if with_nav and d.get("saaCod"):
            rows = self._post("/ProductValue/getSAValueByPage",
                              {"saaCod": d["saaCod"], "funCod": code,
                               "pageIndex": 1, "pageSize": 10})
            data = (rows.get("body") or {}).get("data") or []
            if data:
                last = max(data, key=lambda x: x["znavDat"])
                nd = last["znavDat"]
                info.extra["nav"] = float(last["znavVal"])
                info.extra["nav_date"] = f"{nd[:4]}-{nd[4:6]}-{nd[6:]}"
        return info


class MsResolver(Resolver):
    """民生理财官网代销码（招行渠道 MS+5~6位，如 MS040218）。

    民生官网接口只认自家产品名，不认代销码/登记编码，所以：
      1. 先借招行 cfweb 接口由 MS 码反查产品全名（getProductByPrdCode）；
      2. 再用名称子串查民生官网 BTAProductQry 拿管理人代码（FBAE47531F 等）、
         登记编码、最新净值；
      3. 历史净值走 BTADailyQry（见 fetch_nav_history.fetch_ms）。
    """
    name = "民生理财"
    QUERY = "https://www.cmbcwm.com.cn/gw/po_web/BTAProductQry"

    def match(self, code):
        return bool(re.fullmatch(r"MS[0-9]{5,6}", code.upper()))

    @staticmethod
    def _qry(data):
        h = dict(UA, Referer="https://www.cmbcwm.com.cn/grlc/cpxq/",
                 **{"Content-Type": "application/x-www-form-urlencoded"})
        r = requests.post(MsResolver.QUERY, headers=h, data=data, timeout=20)
        r.raise_for_status()
        return r.json()

    def resolve(self, code, with_nav=False):
        code = code.upper()
        # 1) 招行接口反查产品全名
        d = (CmbResolver()._post("/ProductInfo/getProductByPrdCode",
                                 qs=f"prdCode={code}").get("body") or [])
        if not d:
            raise RuntimeError(f"招行官网查无此代码: {code}")
        full_name = d[0].get("prdName") or ""
        info = ProductInfo(prod_code=code, name=full_name,
                           reg_code=d[0].get("regCode") or "",
                           manager=d[0].get("comNam") or "")
        if d[0].get("risk"):
            info.extra["risk"] = d[0]["risk"]
        # 2) 名称子串查民生官网（官网名称可能少"持有期"等字样，逐步截短尝试）
        m = None
        for n in range(len(full_name), 5, -1):
            kw = full_name[:n]
            body = self._qry({"prd_type": "2", "code_or_name": kw,
                              "pageNo": 1, "pageSize": 20})
            hits = [x for x in body.get("list") or [] if x.get("REAL_PRD_CODE")]
            if len(hits) == 1:
                m = hits[0]
                break
            if len(hits) > 1:  # 多条时取名称最接近的
                m = min(hits, key=lambda x: len(x.get("PRD_NAME") or ""))
                break
        if not m:
            raise RuntimeError(f"民生官网未匹配到: {full_name}")
        info.extra["ms_code"] = m.get("REAL_PRD_CODE")
        lo, hi = m.get("BENCHMARK_LOWER"), m.get("BENCHMARK_UPPER")
        if lo and hi:
            info.extra["bench"] = f"{float(lo):.2%}-{float(hi):.2%}"
        if m.get("NAV"):
            info.extra["nav"] = float(m["NAV"])
            nd = str(m.get("NAV_DATE") or "")
            info.extra["nav_date"] = f"{nd[:4]}-{nd[4:6]}-{nd[6:]}" if len(nd) == 8 else nd
        return info


RESOLVERS = [CiticResolver(), CmbResolver(), MsResolver(), HzBankResolver()]


def convert(code, with_nav=False):
    """按注册顺序尝试各适配器，返回 ProductInfo，全部失败抛 ValueError。"""
    code = code.strip().upper()
    for r in RESOLVERS:
        if r.match(code):
            try:
                return r.resolve(code, with_nav=with_nav)
            except Exception as e:
                raise ValueError(f"{r.name} 适配器查询失败: {e}") from e
    raise ValueError(f"没有适配器支持代码 {code}，当前支持: "
                     + "、".join(r.name for r in RESOLVERS))


def main():
    import urllib3
    urllib3.disable_warnings()
    ap = argparse.ArgumentParser(description="理财产品代码 → 登记编码转换")
    ap.add_argument("code", help="产品/份额代码，如 AF265416、TYG3M1906")
    ap.add_argument("--nav", action="store_true", help="同时拉最新净值")
    a = ap.parse_args()
    try:
        info = convert(a.code, with_nav=a.nav)
    except ValueError as e:
        sys.exit(str(e))
    print(f"机构:     {info.manager or '?'}")
    print(f"产品代码: {info.prod_code}")
    print(f"登记编码: {info.reg_code or '(未找到)'}")
    print(f"产品名称: {info.name or '?'}")
    if info.extra.get("risk"):
        print(f"风险等级: {info.extra['risk']}")
    if info.extra.get("invest_type"):
        print(f"投资类型: {info.extra['invest_type']}")
    if info.extra.get("distributors"):
        print(f"代销机构: {'、'.join(info.extra['distributors'])}")
    if info.extra.get("nav"):
        print(f"最新净值: {info.extra['nav']} @ {info.extra['nav_date']}")


if __name__ == "__main__":
    main()
