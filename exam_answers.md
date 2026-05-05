# 軟體開發與資料庫試題答案 (Software & DB Exam Answers)

---

## 一、 Software Develop (30 分)
*以下答案根據您目前在 `project115` 的開發紀錄進行撰寫，建議根據實際情況微調。*

### 0. 請列出你的作品、github 帳號。
- **作品名稱**：台鐵智慧行程助理 (TRA AI Travel Assistant)
- **GitHub 帳號**：jenny-yuu
- **GitHub 專案**：[jenny-yuu/project115](https://github.com/jenny-yuu/project115)

### 1. 說明你曾使用版本控制的相關經驗。
- 熟悉 **Git** 版本控制系統。
- 曾在專案中使用 `git commit`, `git push`, `git pull` 進行程式碼備份與同步。
- 透過 GitHub 進行版本歷史維護，並在 `.gitignore` 中過濾敏感金鑰輔助開發。

### 2. 有使用過任何網頁框架嗎？有的話請簡述你的經驗，並說明該框架主要的架構、寫法。
- **經驗**：使用 **Flask** (Python) 開發後端 API 伺服器功能。
- **架構**：Flask 是一個微框架 (Micro-framework)，採用 **WSGI** 模式，架構簡單且擴充性強。
- **寫法**：使用裝飾器 (Decorators) 如 `@app.route()` 定義路由，並透過 `jsonify` 回傳 RESTful 風格的 JSON 資料。支援跨網域請求 (CORS) 以利行動裝置 (如 Android) 介接。

### 3. 請問有使用過 windows 系統排程經驗嗎？
- **經驗**：有。
- **簡述**：在專案開發中，通常用於自動化資料更新。可透過 Windows 內建的「工作排程器」(Task Scheduler) 定時執行 Python 腳本（如 `update_live_delay_to_firebase.py`），實現每隔固定時間抓取台鐵即時資訊的功能。

### 4. 請問有使用 python 的開發經驗嗎？
- **經驗**：非常豐富，是目前專案的主要開發語言。
- **簡述**：熟悉 Python 語法與多種第三方庫。在此專案中實作了爬蟲、API 串接、RAG (檢索增強生成) 以及 Firebase Firestore 的資料操作。

### 5. 有 HTTP Request 經驗嗎？有的話請簡述使用經驗。
- **經驗**：有。
- **簡述**：頻繁使用 `requests` 庫。曾介接 **TDX (運輸資料流通服務) API** 取得即時列車班次，處理 OAuth 2.0 驗證機制，並解析回傳的 JSON 資料。

### 6. 有開發 API 經驗嗎？有的話請簡述使用經驗與使用工具如：Flask。
- **經驗**：有，目前專案後端即是基於 Flask 開發提供給 Android App 使用。
- **工具**：使用 Flask 串接 **OpenAI GPT-4o**、**Pinecone (向量資料庫)** 與 **Firestore**，實作回傳結構化 JSON 資料的 AI 行程建議接口。

### 7. 請問有網頁的開發經驗嗎？有的話請簡述網頁架構與你在團隊中的貢獻。
- **經驗**：在專案「115 專題」中負責 **後端架構設計與 AI 模型整合**。
- **架構**：採用分離式架構 (Client-Server Architecture)。
- **貢獻**：設計 RESTful API 提供即時轉乘建議、開發自動化資料獲取腳本、實作 RAG 系統提升 AI 回答準確度，並負責後端服務在 Render 平台上的部署與維護。

---

## 二、 資料庫 (30 分)

### 1. ERD 設計與關聯式資料表結構

#### 情境分析：
- 大學 (University) 與 老師/學生：1 對 多。
- 老師 與 課程：1 對 多 (1-to-Many)。
- 學生 與 課程：多 對 多 (ManyToMany，需透過 Enrollment 轉換)。
- 課程 與 教室：多 對 1 (固定的教室)。

#### 關聯式表結構 (Relational Schema)：
1. **University** (`UnivID` PK, UnivName)
2. **Classroom** (`RoomID` PK, RoomName, `UnivID` FK)
3. **Teacher** (`TeacherID` PK, Name, `UnivID` FK)
4. **Student** (`StudentID` PK, Name, `UnivID` FK)
5. **Course** (`CourseID` PK, CourseName, `TeacherID` FK, `RoomID` FK)
6. **Enrollment** (`StudentID` PK/FK, `CourseID` PK/FK, MidtermGrade, FinalGrade)

---

### 2. SQL 查詢語句

#### A. 查詢 AA 大學的所有老師姓名
```sql
SELECT T.Name 
FROM Teacher T
JOIN University U ON T.UnivID = U.UnivID
WHERE U.UnivName = 'AA 大學';
```

#### B. 查詢 ”Frank” 老師的在哪個大學教室上課
```sql
SELECT DISTINCT R.RoomName
FROM Course C
JOIN Teacher T ON C.TeacherID = T.TeacherID
JOIN Classroom R ON C.RoomID = R.RoomID
WHERE T.Name = 'Frank';
```

#### C. 查詢某個上課教室的所有課程
```sql
SELECT CourseName 
FROM Course 
WHERE RoomID = (SELECT RoomID FROM Classroom WHERE RoomName = '指定教室名稱');
```

#### D. 查詢任一門課程期末成績在 70 分以上的 「課程名稱」+「學生姓名」+「期末分數」
```sql
SELECT C.CourseName, S.Name, E.FinalGrade
FROM Enrollment E
JOIN Course C ON E.CourseID = C.CourseID
JOIN Student S ON E.StudentID = S.StudentID
WHERE E.FinalGrade >= 70;
```

#### E. 查詢學過 ”Frank” 老師教授的任一門課程的「學生姓名」
```sql
SELECT DISTINCT S.Name
FROM Enrollment E
JOIN Student S ON E.StudentID = S.StudentID
JOIN Course C ON E.CourseID = C.CourseID
JOIN Teacher T ON C.TeacherID = T.TeacherID
WHERE T.Name = 'Frank';
```

#### F. 查出有多少學生兩門課以上的期中及期末考成績皆低於 60 分
```sql
SELECT COUNT(*) 
FROM (
    SELECT StudentID 
    FROM Enrollment 
    WHERE MidtermGrade < 60 AND FinalGrade < 60
    GROUP BY StudentID
    HAVING COUNT(CourseID) >= 2
) AS FailingStudents;
```
