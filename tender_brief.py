"""
海事工程 AI 情報中心
- 每日搜尋政府採購相關公開資料
- 依關鍵字篩選海事工程標案
- 產出 Excel、HTML 報告
- 用 Gmail SMTP 寄送晨報

必要 GitHub Secrets:
GMAIL_USER      你的 Gmail
GMAIL_PASSWORD  Google 應用程式密碼，不是登入密碼

選用 Secrets:
EMAIL_TO        收件者，未設定則寄給 GMAIL_USER
"""
from __future__ import annotations

import html
import os
import smtplib
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

TZ = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
OUTPUT.mkdir(exist_ok=True)
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

PCC_OPENFUN_API = "https://pcc.g0v.ronny.tw/api/searchbytitle"

@dataclass
class Tender:
    date: str
    agency: str
    title: str
    amount: str
    deadline: str
    status: str
    url: str
    matched_keywords: str
    score: int
    note: str


def load_lines(name: str) -> list[str]:
    path = ROOT / name
    if not path.exists():
        return []
    return [x.strip() for x in path.read_text(encoding="utf-8").splitlines() if x.strip() and not x.strip().startswith("#")]


def fetch_pcc_by_keyword(keyword: str, timeout: int = 20) -> list[dict]:
    """使用 pcc.g0v.ronny.tw 搜尋政府電子採購網標案標題。"""
    try:
        r = requests.get(PCC_OPENFUN_API, params={"query": keyword}, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict):
            return data.get("records") or data.get("data") or []
        return data if isinstance(data, list) else []
    except Exception as exc:
        print(f"[WARN] keyword={keyword} fetch failed: {exc}")
        return []


def pick(row: dict, keys: Iterable[str], default: str = "") -> str:
    for k in keys:
        v = row.get(k)
        if v not in (None, ""):
            return str(v)
    return default


def normalize_record(row: dict, keyword: str, keywords: list[str], agencies: list[str]) -> Tender | None:
    title = pick(row, ["標案名稱", "title", "brief", "name"])
    agency = pick(row, ["機關名稱", "unit_name", "agency", "機關"])
    if not title and not agency:
        return None
    text = f"{title} {agency}"
    matched = sorted({k for k in keywords if k in text} | ({keyword} if keyword in text else set()))
    agency_hit = any(a in text for a in agencies if a != "政府電子採購網")
    if not matched and not agency_hit:
        return None

    amount = pick(row, ["預算金額", "budget", "金額", "amount", "決標金額"], "未列")
    deadline = pick(row, ["截止投標", "截止投標日期", "開標日期", "deadline", "date"], "未列")
    status = pick(row, ["招標狀態", "status", "公告類別"], "待確認")
    url = pick(row, ["url", "標案網址", "detail_url"])
    if not url:
        unit_id = pick(row, ["unit_id", "機關代碼"])
        job_number = pick(row, ["job_number", "標案案號", "jobno"])
        if unit_id and job_number:
            url = f"https://pcc.g0v.ronny.tw/tender/{unit_id}/{job_number}"
        else:
            url = "https://web.pcc.gov.tw/"

    score = 1
    high_words = ["浚挖", "疏浚", "航道", "港池", "碼頭", "防波堤", "護岸", "水域維護", "養灘"]
    score += sum(1 for w in high_words if w in text)
    if agency_hit:
        score += 2
    score = min(score, 5)

    note = "值得追蹤" if score >= 4 else "一般追蹤"
    if score >= 5:
        note = "高度符合海事工程，建議優先確認投標資格與工期"
    elif any(w in text for w in ["港", "碼頭", "航道", "漁港"]):
        note = "港區相關，建議查看圖說、船機限制與棄土條件"

    return Tender(
        date=datetime.now(TZ).strftime("%Y-%m-%d"),
        agency=agency or "未列機關",
        title=title or "未列標題",
        amount=amount,
        deadline=deadline,
        status=status,
        url=url,
        matched_keywords=", ".join(matched),
        score=score,
        note=note,
    )


def collect_tenders() -> list[Tender]:
    keywords = load_lines("keywords.txt")
    agencies = load_lines("agencies.txt")
    items: dict[str, Tender] = {}
    for keyword in keywords:
        for row in fetch_pcc_by_keyword(keyword):
            tender = normalize_record(row, keyword, keywords, agencies)
            if tender:
                key = f"{tender.agency}|{tender.title}|{tender.deadline}"
                old = items.get(key)
                if old is None or tender.score > old.score:
                    items[key] = tender
    return sorted(items.values(), key=lambda x: x.score, reverse=True)


def make_excel(tenders: list[Tender], path: Path) -> None:
    df = pd.DataFrame([asdict(t) for t in tenders])
    if df.empty:
        df = pd.DataFrame(columns=list(Tender.__dataclass_fields__.keys()))
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="今日摘要")
        top = df.head(20)
        top.to_excel(writer, index=False, sheet_name="優先追蹤")


def make_html(tenders: list[Tender]) -> str:
    today = datetime.now(TZ).strftime("%Y/%m/%d")
    top = tenders[:10]
    rows = []
    for i, t in enumerate(top, 1):
        stars = "★" * t.score + "☆" * (5 - t.score)
        rows.append(f"""
        <tr>
          <td>{i}</td>
          <td><b>{html.escape(t.title)}</b><br><small>{html.escape(t.agency)}</small></td>
          <td>{html.escape(t.amount)}</td>
          <td>{html.escape(t.deadline)}</td>
          <td>{stars}<br>{html.escape(t.note)}</td>
          <td><a href=\"{html.escape(t.url)}\">公告連結</a></td>
        </tr>
        """)
    if not rows:
        rows.append("<tr><td colspan='6'>今天沒有抓到符合條件的標案。仍建議人工確認政府電子採購網，因為政府網站偶爾像睡著的石像。</td></tr>")
    return f"""
    <html><body>
    <h2>海事工程每日晨報 {today}</h2>
    <p>今日符合關鍵字標案：<b>{len(tenders)}</b> 件。以下列出優先追蹤前 10 件。</p>
    <h3>今日重點</h3>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-family:Arial,'Microsoft JhengHei',sans-serif;font-size:14px;">
      <tr style="background:#eee"><th>#</th><th>標案</th><th>預算/金額</th><th>截止/日期</th><th>AI追蹤評分</th><th>連結</th></tr>
      {''.join(rows)}
    </table>
    <h3>後續值得追蹤</h3>
    <ul>
      <li>分數 4 星以上：優先下載招標文件、圖說、工期、船機限制。</li>
      <li>涉及浚挖、港池、航道、棄土者：注意棄置場、運距、污染檢測、天候停工條件。</li>
      <li>決標與變更公告仍需回政府電子採購網正式公告確認。</li>
    </ul>
    <p style="color:#666;font-size:12px">本報告由 GitHub Actions 自動產生。正式投標請以官方公告與招標文件為準。</p>
    </body></html>
    """


def send_email(subject: str, html_body: str, attachments: list[Path]) -> None:
    user = os.environ.get("GMAIL_USER")
    password = os.environ.get("GMAIL_PASSWORD")
    to_addr = os.environ.get("EMAIL_TO") or user
    if not user or not password:
        print("[INFO] GMAIL_USER/GMAIL_PASSWORD not set. Skip email.")
        return
    msg = MIMEMultipart()
    msg["From"] = user
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    for path in attachments:
        if path.exists():
            part = MIMEApplication(path.read_bytes(), Name=path.name)
            part["Content-Disposition"] = f'attachment; filename="{path.name}"'
            msg.attach(part)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(user, password)
        server.sendmail(user, [to_addr], msg.as_string())
    print(f"[OK] email sent to {to_addr}")


def main() -> None:
    tenders = collect_tenders()
    today = datetime.now(TZ).strftime("%Y%m%d")
    xlsx = OUTPUT / f"marine_tender_brief_{today}.xlsx"
    html_path = OUTPUT / f"marine_tender_brief_{today}.html"
    make_excel(tenders, xlsx)
    html_body = make_html(tenders)
    html_path.write_text(html_body, encoding="utf-8")
    send_email(f"海事工程每日晨報 {datetime.now(TZ).strftime('%Y/%m/%d')}", html_body, [xlsx])
    print(f"[OK] generated: {xlsx}")

if __name__ == "__main__":
    main()
