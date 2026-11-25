#!/usr/bin/env python3
"""南银理财官网历史净值抓取器（queryNetValueList）
用法: python3 ny_nav_fetch.py <salesCode> [<salesCode>...]
输出: nav/ny/<salesCode>_nav.json
注意: 需系统性重试（token/公钥/会话偶发失败率~30%），重试即成功
"""
import json, time, base64, urllib.request, secrets, string, sys, os
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding as apadding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

BASE="https://www.nanyinwealth.com"; UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"
SITE="64415e9b39814d2faa490ce414e3af26"; PID="0fe153930baa43ffa759433d276f915c"
TOKEN_URL=BASE+"/eportal/ui?portal.url=/portlet/easysite-token!getToken.portlet&moduleId=0&pageId=ee9e095407e44a3bacb00065ba3f6d11"
NAV_URL=BASE+"/eportal/ui?moduleId=5&portal.url=/portlet/article-data!queryNetValueList.portlet&TopModuelId=e7db4f2628cb40548f6101d71695ada2"
OUT=os.path.join(os.path.dirname(__file__),"ny"); os.makedirs(OUT,exist_ok=True)

def aes_enc(data,key):
    c=Cipher(algorithms.AES(key.encode()),modes.ECB()); e=c.encryptor()
    pad=16-len(data)%16
    return base64.b64encode(e.update(data.encode()+bytes([pad])*pad)+e.finalize()).decode()
def aes_dec(b64,key):
    c=Cipher(algorithms.AES(key.encode()),modes.ECB()); d=c.decryptor()
    pt=d.update(base64.b64decode(b64))+d.finalize(); pt=pt[:-pt[-1]]
    return pt.decode()

def nav_all(code,tries=8):
    """分页拉全量净值"""
    allrows=[]; page=1
    while True:
        got=[]
        for attempt in range(tries):
            try:
                tr=urllib.request.Request(TOKEN_URL,method="POST"); tr.add_header("User-Agent",UA)
                token=urllib.request.urlopen(tr,timeout=20).read().decode().strip()
                pr=urllib.request.Request(BASE+"/eportal/ui?moduleId=5&portal.url=/portlet/login-handle!publicKey.portlet&TopModelId=e7db4f2628vb40548f6101d71695ada2")
                pr.add_header("User-Agent",UA); pr.add_header("Referer",BASE+"/nanyinwealth/lccp/cpjz/index.html?id="+code)
                pub=json.load(urllib.request.urlopen(pr,timeout=20))["data"]
                pem="-----BEGIN PUBLIC KEY-----\n"+"\n".join(pub[i:i+64] for i in range(0,len(pub),64))+"\n-----END PUBLIC KEY-----\n"
                rsa_pub=serialization.load_pem_public_key(pem.encode())
                key=''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(16))
                ts=aes_enc(str(int(time.time()*1000)),key)
                payload={"productCode":code,"startDate":"","endDate":"","currentPage":page}
                body={"data":aes_enc(json.dumps(payload),key),
                      "aesKey":base64.b64encode(rsa_pub.encrypt(key.encode(),apadding.PKCS1v15())).decode(),
                      "timeStamp":ts}
                req=urllib.request.Request(NAV_URL,data=json.dumps(body).encode(),method="POST")
                req.add_header("User-Agent",UA); req.add_header("Content-Type","application/json;charset=utf-8")
                req.add_header("Referer",BASE+"/nanyinwealth/lccp/cpjz/index.html?id="+code)
                d=json.loads(aes_dec(json.load(urllib.request.urlopen(req,timeout=30))["data"]["data"],key))
                got=d.get("aaData") or []
                break
            except Exception:
                time.sleep(1.5)
        if not got: break
        allrows+=got
        if len(got)<10: break
        page+=1; time.sleep(1)
    return allrows

if __name__=="__main__":
    codes=sys.argv[1:]
    for code in codes:
        rows=nav_all(code)
        json.dump({"salesCode":code,"rows":rows},open(os.path.join(OUT,f"{code}_nav.json"),"w",encoding="utf8"),ensure_ascii=False)
        print(code,"->",len(rows),"行")
        if rows:
            print("  最新:",rows[0])
        time.sleep(1)
