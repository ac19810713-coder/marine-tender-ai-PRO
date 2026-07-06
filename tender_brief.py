import os
import csv
import smtplib
import ssl
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import List, Dict

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "out"
DATA_DIR.mkdir(exist_ok=True)
OUT_DIR.mkdir(exist_ok=True)

TZ = timezone(timedelta(hours=8))
TODAY = datetime.now(TZ).strftime("%Y-%m-%d")

KEYWORDS = [x.strip() for x in (ROOT / "keywords.txt").read_text(encoding="utf-8").splitlines() if x.strip()]
AGENCIES = [x.strip() for x in (ROOT / "agencies.txt").read_text(encoding="utf-8").splitlines() if x.strip()]
DB_PATH = DATA_DIR / "tenders.csv"

# 這個公開 API 由第三方整理政府電子採購網資料。正式投標仍請回政府電子採購網公告確認。
API = "https://pcc.g0v.ronny.tw/api/searchbytitle"


def score_item(title: str, agency: str, summary: str) -> int:
    text = f"{title} {agency} {summary}"
    score = 0
    for kw in KEYWORDS:
        if kw in text:
            score += 2
    for ag in AGENCIES:
        if ag in text:
            score += 1
    return score


def fetch_pcc(keyword: str, limit: int = 20) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    try:
        r = requests.get(API, params={"query": keyword}, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return [{"date": TODAY, "source": "pcc-openfun", "agency": "查詢失敗", "title": keyword, "amount": "", "deadline": "", "url": "", "status": f"API error: {e}", "score": 0}]

    records = data.get("records") or data.get("data") or []
    for item in records[:limit]:
        title = str(item.get("title") or item.get("標案名稱") or item.get("brief") or keyword)
        agency = str(item.get("unit_name") or item.get("機關名稱") or item.get("unit") or "")
        url = str(item.get("url") or item.get("link") or "")
        amount = str(item.get("amount") or item.get("budget") or item.get("預算金額") or "")
        deadline = str(item.get("deadline") or item.get("截止投標") or item.get("end_date") or "")
        status = str(item.get("type") or item.get("status") or item.get("公告類別") or "")
        summary = str(item)
        sc = score_item(title, agency, summary)
        if sc > 0:
            rows.append({
                "date": TODAY,
                "source": "pcc-openfun",
                "agency": agency,
                "title": title,
                "amount": amount,
                "deadline": deadline,
                "url": url,
                "status": status,
                "score": sc,
            })
    return rows


def dedupe(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    out = []
    for r in sorted(rows, key=lambda x: int(x.get("score") or 0), reverse=True):
        key = (r.get("agency", ""), r.get("title", ""), r.get("url", ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def load_old_titles() -> set:
    if not DB_PATH.exists():
        return set()
    try:
        df = pd.read_csv(DB_PATH)
        return set(df.get("title", pd.Series(dtype=str)).astype(str).tolist())
    except Exception:
        return set()


def save_db(rows: List[Dict[str, str]]):
    df_new = pd.DataFrame(rows)
    if DB_PATH.exists():
        try:
            df_old = pd.read_csv(DB_PATH)
            df = pd.concat([df_old, df_new], ignore_index=True)
        except Exception:
            df = df_new
    else:
        df = df_new
    if not df.empty:
        df = df.drop_duplicates(subset=["agency", "title", "url"], keep="last")
    df.to_csv(DB_PATH, index=False, encoding="utf-8-sig")


def make_reports(rows: List[Dict[str, str]], old_titles: set):
    df = pd.DataFrame(rows)
    if df.empty:
        df = pd.DataFrame(columns=["date", "source", "agency", "title", "amount", "deadline", "url", "status", "score"])
    df["is_new"] = ~df["title"].astype(str).isin(old_titles) if not df.empty else []
    xlsx = OUT_DIR / f"marine_tender_report_{TODAY}.xlsx"
    html = OUT_DIR / f"marine_tender_report_{TODAY}.html"
    df.to_excel(xlsx, index=False)

    top = df.head(20).to_dict("records") if not df.empty else []
    rows_html = "".join(
        f"<tr><td>{r.get('agency','')}</td><td>{r.get('title','')}</td><td>{r.get('amount','')}</td><td>{r.get('deadline','')}</td><td>{r.get('status','')}</td><td><a href='{r.get('url','')}'>連結</a></td><td>{r.get('score','')}</td></tr>"
        for r in top
    )
    new_count = int(df["is_new"].sum()) if not df.empty and "is_new" in df else 0
    body = f"""
    <html><body>
    <h2>海事工程 AI 情報中心 - {TODAY}</h2>
    <p>今日找到 {len(df)} 筆相關資料，其中可能新增 {new_count} 筆。</p>
    <h3>AI 重點判讀</h3>
    <ul>
      <li>分數越高，代表越符合海事、浚挖、港區、碼頭、護岸、防波堤等關鍵字。</li>
      <li>正式投標前，務必回政府電子採購網或招標機關原公告確認。政府網站嘛，最後還是它說了算。</li>
      <li>建議優先查看分數高、金額大、截止日近的案件。</li>
    </ul>
    <table border="1" cellpadding="6" cellspacing="0">
      <tr><th>機關</th><th>標案名稱</th><th>預算/金額</th><th>截止</th><th>狀態</th><th>連結</th><th>分數</th></tr>
      {rows_html}
    </table>
    </body></html>
    """
    html.write_text(body, encoding="utf-8")
    return html, xlsx, body


def send_mail(subject: str, html_body: str, attachments: List[Path]):
    user = os.getenv("GMAIL_USER")
    password = os.getenv("GMAIL_PASSWORD")
    to = os.getenv("MAIL_TO") or user
    mail_from = os.getenv("MAIL_FROM") or user
    if not user or not password or not to:
        print("GMAIL_USER / GMAIL_PASSWORD not set, skip email.")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = to
    msg.set_content("你的 Email 不支援 HTML，請查看附件報表。")
    msg.add_alternative(html_body, subtype="html")

    for p in attachments:
        if not p.exists():
            continue
        data = p.read_bytes()
        if p.suffix == ".xlsx":
            maintype, subtype = "application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        else:
            maintype, subtype = "text", "html"
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=p.name)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)


def main():
    old_titles = load_old_titles()
    all_rows: List[Dict[str, str]] = []
    for kw in KEYWORDS:
        all_rows.extend(fetch_pcc(kw, limit=15))
    rows = dedupe(all_rows)
    save_db(rows)
    html_path, xlsx_path, html_body = make_reports(rows, old_titles)
    send_mail(f"海事工程標案每日摘要 {TODAY}", html_body, [html_path, xlsx_path])
    print(f"done. rows={len(rows)}")


if __name__ == "__main__":
    main()
