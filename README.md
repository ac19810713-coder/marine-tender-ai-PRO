# 海事工程 AI 情報中心

這是一套每日自動執行的海事工程標案摘要工具。

功能：

- 搜尋政府電子採購網相關公開資料
- 依 `keywords.txt` 篩選海事工程、浚挖、港區、碼頭、護岸、防波堤等案件
- 產出每日 HTML 摘要
- 產出 Excel 附件
- 透過 Gmail 自動寄出
- 使用 GitHub Actions 每天台灣時間上午 8:00 自動執行

> 注意：正式投標請務必回政府電子採購網與招標文件確認。這套工具是輔助搜尋，不是官方公告本體。政府網站已經夠難用，不要再讓自己敗給未確認資訊。

---

## 一、上傳到 GitHub

1. 建立新的 Repository，例如：

```text
marine-tender-ai
```

2. 把本資料夾內所有檔案上傳到 GitHub。

一定要包含：

```text
.github/workflows/daily.yml
tender_brief.py
requirements.txt
keywords.txt
agencies.txt
README.md
```

如果 GitHub 看不到 `.github/workflows/daily.yml`，Actions 就不會出現。這就是前一版卡住的原因。

---

## 二、設定 GitHub Secrets

到 Repository：

```text
Settings → Secrets and variables → Actions → New repository secret
```

新增兩個必要 Secret：

### 1. GMAIL_USER

```text
GMAIL_USER
```

內容填你的 Gmail，例如：

```text
ac19810713@gmail.com
```

### 2. GMAIL_PASSWORD

```text
GMAIL_PASSWORD
```

內容填 Google 應用程式密碼 16 碼。

不是 Gmail 登入密碼。

---

## 三、選用 Secret

如果你想寄到不同信箱，可新增：

```text
EMAIL_TO
```

內容填收件信箱。

沒有設定時，會寄給 `GMAIL_USER`。

---

## 四、手動測試

1. 到 GitHub Repository 上方點：

```text
Actions
```

2. 左邊點：

```text
Daily Marine Tender Brief
```

3. 右邊按：

```text
Run workflow
```

成功時會出現綠色勾勾，Gmail 會收到「海事工程每日晨報」。

---

## 五、每天自動執行時間

檔案：

```text
.github/workflows/daily.yml
```

目前設定：

```yaml
- cron: '0 0 * * *'
```

這代表 UTC 00:00，也就是台灣時間每天上午 8:00。

---

## 六、調整關鍵字

編輯：

```text
keywords.txt
```

一行一個關鍵字。

例如：

```text
浚挖
疏浚
航道
港池
碼頭
防波堤
護岸
水域維護
```

---

## 七、調整追蹤機關

編輯：

```text
agencies.txt
```

一行一個機關或單位名稱。

例如：

```text
臺灣港務股份有限公司
台灣電力公司
台灣中油股份有限公司
農業部漁業署
工程處
新建工程一科
維護管理處
```

---

## 八、常見問題

### Actions 沒有出現 workflow

請確認 GitHub 裡面有：

```text
.github/workflows/daily.yml
```

注意 `.github` 前面有一個點。

### 沒收到 Email

檢查：

1. `GMAIL_USER` 是否正確
2. `GMAIL_PASSWORD` 是否是 Google 應用程式密碼
3. Gmail 垃圾郵件匣
4. Actions 執行紀錄是否紅色失敗

### 程式抓到的標案不完整

這是公開資料源限制。正式版後續可再擴充：

- 直接爬政府電子採購網
- 加入臺灣港務公司網站
- 加入台電、中油、漁業署網站
- 比對昨日資料，找出新增、刪除、變更

---

## 九、後續升級方向

可再加入：

- LINE Notify 或 LINE Messaging API 推播
- 得標公司排行榜
- 預算變更提醒
- 七日內截止提醒
- 自動下載招標文件
- 標案投標價值評分
- 每週、每月統計報表

