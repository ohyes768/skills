#!/usr/bin/env python3
"""理财产品代码 → 登记编码（Z编号）转换器（仅招银自营 + 杭银自营）

可插拔适配器架构：新增一家理财子公司时，继承 Resolver 实现 match/resolve，
然后加入 RESOLVERS 列表即可。代销渠道（信银/光大/民生/兴银等）的研究代码
已移至 ~/study/wealth-distribution-channel/，本脚本不再支持。

用法:
  python code_convert.py 120053A               # 招银自营销售代码
  python code_convert.py TYG3M1906 --nav      # 杭银自营，顺带拉最新净值
  代码调用: from code_convert import convert; convert("120053A")

已适配:
  - 招银自营: 4-6位数字（可带份额字母），走 cfweb.paas.cmbchina.com（SM4 签名）
  - 杭银理财: TYG/JQB 等内部码，走 www.hzbankwealth.cn 详情 JSON
"""
import argparse
import json
import re
import sys
from dataclasses import dataclass, field

import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


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



class HzBankResolver(Resolver):
    """杭银理财。

    代码规则: TYG/JQB/内部码（杭银不用 AF 前缀）。
    接口: 官网静态详情 JSON，dengjino 字段即登记编码，
    danweijingzhi/jingzhiriqi 顺带给出最新净值。
    """
    name = "杭银理财"
    DETAIL = "https://www.hzbankwealth.cn/eportal/hzbw/detail/{code}_detail.json"

    def match(self, code):
        # 字母数字混合内部码归杭银（招银自营是纯数字码，已被 CmbResolver 先命中）
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
    """招银自营（cfweb 一网通，D07 份额）。

    接口: cfweb.paas.cmbchina.com，需 SM4 签名头：
      key  = base64decode(AUTH_SN) 首末字符替换为 "9"/"8" (CFWEB_C2="98")，16字节
      data = appId + "|" + 毫秒时间戳
      signature = base64(SM4-ECB(key, data))，头 appId/timespan/signature
      且必须带 Content-Type: application/json，否则后端报 ERR9999。
    流程: getProductByPrdCode 拿 regCode/saaCod/funCod/名称/风险，
    再 getSAValueByPage 分页拉净值（znavDat=yyyyMMdd, znavVal=净值）。
    """
    name = "招银自营"
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
        # 4-6位数字(可带份额字母)=招银自营销售代码（如 120053A、8914）
        return bool(re.fullmatch(r"[0-9]{4,6}[A-Z]?", code.upper()))

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



RESOLVERS = [CmbResolver(), HzBankResolver()]


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
