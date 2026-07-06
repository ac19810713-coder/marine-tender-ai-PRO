# 海事工程 AI 情報中心

每天自動搜尋海事工程相關標案，產生 HTML 與 Excel 報表，並用 Gmail 寄出。

## 重要

GitHub Actions 工作流程一定要在：

```text
.github/workflows/daily.yml
```

不是放在根目錄的 `daily.yml`。GitHub 很挑，像公文少蓋章就退件。

## GitHub Secrets

到 Repository → Settings → Secrets and variables → Actions，建立：

```text
GMAIL_USER
GMAIL_PASSWORD
```

`GMAIL_PASSWORD` 請填 Google 應用程式密碼，不是 Gmail 登入密碼。

## 手動測試

Repository → Actions → Daily Marine Tender Brief → Run workflow。

## 排程

預設每天台灣時間上午 8:00 自動執行。

## 資料來源提醒

程式預設使用 pcc-openfun 公開 API 輔助查詢政府電子採購網資料。正式投標前，務必回政府電子採購網或招標機關原公告確認。
