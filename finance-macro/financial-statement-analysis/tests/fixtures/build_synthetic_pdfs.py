"""生成小型合成年报 PDF 夹具：目录偏移、书签、误命中、同名表、扫描与混合页。

属于测试代码：只生成合成内容，不包含真实年报。
"""

from __future__ import annotations

import pymupdf

PAGE_WIDTH = 595
PAGE_HEIGHT = 842
LEFT = 72
CJK_FONT = "china-s"


def _add_text_page(doc: pymupdf.Document, lines: list[str], printed_page: int | None = None):
    page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    y = 72.0
    for line in lines:
        page.insert_text((LEFT, y), line, fontsize=11, fontname=CJK_FONT)
        y += 22
    if printed_page is not None:
        page.insert_text(
            (PAGE_WIDTH / 2 - 10, PAGE_HEIGHT - 40), str(printed_page), fontsize=10, fontname=CJK_FONT
        )
    return page


def _text_pixmap(text: str) -> pymupdf.Pixmap:
    tmp = pymupdf.open()
    page = tmp.new_page(width=400, height=150)
    page.insert_text((20, 80), text, fontsize=16, fontname=CJK_FONT)
    pix = page.get_pixmap(dpi=72)
    tmp.close()
    return pix


def _add_scanned_page(doc: pymupdf.Document):
    page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    rect = pymupdf.Rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT)
    page.insert_image(rect, pixmap=_text_pixmap("附注：货币资金明细（扫描页）"), keep_proportion=False)
    return page


def _add_mixed_page(doc: pymupdf.Document, printed_page: int):
    page = _add_text_page(doc, ["签章页", "本页包含盖章扫描件。"], printed_page=printed_page)
    rect = pymupdf.Rect(150, 300, 450, 480)
    page.insert_image(rect, pixmap=_text_pixmap("（盖章区扫描图）"), keep_proportion=False)
    return page


def _add_image_table_page(doc: pymupdf.Document, lines: list[str]):
    """整页图片表格：模拟文字层损坏、表格只存在于图像中的页面。"""
    page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    tmp = pymupdf.open()
    tpage = tmp.new_page(width=500, height=320)
    y = 40.0
    for line in lines:
        tpage.insert_text((30, y), line, fontsize=12, fontname=CJK_FONT)
        y += 26
    pix = tpage.get_pixmap(dpi=72)
    tmp.close()
    page.insert_image(pymupdf.Rect(30, 72, 565, 460), pixmap=pix, keep_proportion=False)
    return page


def build_annual_report(
    *,
    with_bookmarks: bool = True,
    with_toc_page: bool = True,
    keyword_trap: bool = True,
    year_conflict: bool = False,
    include_scanned: bool = True,
    balance_continued_mismatch: bool = False,
    income_as_image: bool = False,
) -> tuple[bytes, dict]:
    """构建合成年报，返回 (pdf 字节, 标题→物理页映射)。"""
    doc = pymupdf.open()
    page_map: dict = {}

    def add_page(key: str | None, lines: list[str], printed_page: int | None):
        _add_text_page(doc, lines, printed_page=printed_page)
        if key:
            page_map[key] = doc.page_count

    add_page(
        None,
        [
            "贵州检测科技股份有限公司",
            "股票代码：300001",
            "2024 年年度报告",
            "二〇二五年四月",
        ],
        printed_page=None,
    )

    if with_toc_page:
        toc_lines = ["目 录"]
        if year_conflict:
            toc_lines.append("（2023 年年度报告信息更正说明：本页保留历史声明）")
        toc_lines += [
            "第一节 释义 " + "." * 24 + " 2",
            "第二节 公司简介 " + "." * 36 + " 3",
            "第三节 会计数据和财务指标摘要 " + "." * 22 + " 4",
            "第四节 管理层讨论与分析 " + "." * 26 + " 5",
            "第五节 重要事项 " + "." * 32 + " 7",
            "第十节 财务报告 " + "." * 32 + " 8",
        ]
        _add_text_page(doc, toc_lines, printed_page=1)

    add_page("第一节 释义", ["第一节 释义", "本报告中，除非另有说明，下列词语具有如下含义。"], printed_page=2)
    add_page(
        "第二节 公司简介",
        ["第二节 公司简介", "公司从事仪器仪表检测服务。", "注册地址位于贵州省贵阳市。"],
        printed_page=3,
    )

    summary_lines = ["第三节 会计数据和财务指标摘要", "营业收入（元） 1,234,567,890.00"]
    add_page("第三节 会计数据和财务指标摘要", summary_lines, printed_page=4)

    mdna_lines = [
        "第四节 管理层讨论与分析",
        "一、报告期内公司经营情况回顾。",
        "报告期内，公司主营业务收入稳定增长。",
    ]
    if keyword_trap:
        mdna_lines.append("合并资产负债表中货币资金较上年末增长百分之十二，结构保持稳定。")
        mdna_lines.append("2023 年年度报告中所述经营计划已实施完成。")
    add_page("管理层讨论与分析", mdna_lines, printed_page=5)
    add_page(
        None,
        ["二、主营业务分析", "分行业情况：仪器仪表行业收入占比 80%。"],
        printed_page=6,
    )
    add_page(
        "第五节 重要事项",
        ["第五节 重要事项", "报告期内无重大诉讼仲裁事项。"],
        printed_page=7,
    )

    add_page(
        "合并资产负债表",
        [
            "合并资产负债表",
            "项目        期末余额        期初余额",
            "货币资金        150,000,000.00        120,000,000.00",
            "应收账款        80,000,000.00        75,000,000.00",
        ],
        printed_page=8,
    )
    continued_header = (
        "项目        期末余额" if balance_continued_mismatch else "项目        期末余额        期初余额"
    )
    add_page(
        None,
        [
            "合并资产负债表（续）",
            continued_header,
            "资产总计        500,000,000.00        460,000,000.00",
            "负债合计        300,000,000.00        280,000,000.00",
        ],
        printed_page=9,
    )
    add_page(
        "母公司资产负债表",
        [
            "母公司资产负债表",
            "项目        期末余额        期初余额",
            "货币资金        90,000,000.00        70,000,000.00",
        ],
        printed_page=10,
    )
    income_lines = [
        "合并利润表",
        "项目        本期金额        上期金额",
        "营业总收入        1,200,000,000.00        1,000,000,000.00",
        "净利润        120,000,000.00        80,000,000.00",
        "少数股东损益        (25,000,000.00)        (20,000,000.00)",
    ]
    if income_as_image:
        _add_image_table_page(doc, income_lines)
        page_map["合并利润表"] = doc.page_count
    else:
        add_page("合并利润表", income_lines, printed_page=11)
    add_page(
        None,
        ["合并利润表（续）", "归属于母公司股东的净利润        110,000,000.00        70,000,000.00"],
        printed_page=12,
    )
    add_page(
        "合并现金流量表",
        [
            "合并现金流量表",
            "项目        本期金额        上期金额",
            "经营活动产生的现金流量净额        150,000,000.00        100,000,000.00",
            "汇率变动对现金及现金等价物的影响        —        —",
        ],
        printed_page=13,
    )
    add_page(
        "审计报告",
        [
            "审计报告",
            "贵州检测科技股份有限公司全体股东：",
            "我们审计了贵州检测科技股份有限公司财务报表。",
            "我们认为，财务报表在所有重大方面公允反映。",
        ],
        printed_page=14,
    )

    if include_scanned:
        _add_scanned_page(doc)
        page_map["_scan_page"] = doc.page_count

    _add_mixed_page(doc, printed_page=doc.page_count)
    page_map["_mixed_page"] = doc.page_count
    page_map["_page_count"] = doc.page_count

    if with_bookmarks:
        doc.set_toc(
            [
                [1, "第一节 释义", page_map["第一节 释义"]],
                [1, "第二节 公司简介", page_map["第二节 公司简介"]],
                [1, "第三节 会计数据和财务指标摘要", page_map["第三节 会计数据和财务指标摘要"]],
                [1, "管理层讨论与分析", page_map["管理层讨论与分析"]],
                [1, "第五节 重要事项", page_map["第五节 重要事项"]],
                [1, "合并资产负债表", page_map["合并资产负债表"]],
                [1, "母公司资产负债表", page_map["母公司资产负债表"]],
                [1, "合并利润表", page_map["合并利润表"]],
                [1, "合并现金流量表", page_map["合并现金流量表"]],
                [1, "审计报告", page_map["审计报告"]],
            ]
        )

    data = doc.tobytes()
    doc.close()
    return data, page_map


if __name__ == "__main__":
    pdf_bytes, mapping = build_annual_report()
    print(f"pages={mapping['_page_count']}, bytes={len(pdf_bytes)}")
