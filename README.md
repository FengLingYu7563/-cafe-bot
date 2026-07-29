<p align="center">
  <img src="圖片.png" alt="凹cafe logo" width="200">
</p>

# 凹cafe 私人頻道管理機器人

讓一般成員自助建立、管理自己的私人文字/語音頻道，減少管理員手動開頻道與調權限的負擔。

## 功能

| 指令 | 說明 |
|---|---|
| `/create type:<文字頻道\|語音頻道> [name]` | 建立私人頻道。每人最多 3 個文字頻道 + 1 個語音頻道（不含已廢棄的）。不填 name 則自動命名。 |
| `/delete [channel]` | 「偽刪除」：發廢棄公告、收回所有成員（含建立者本人）的權限、改名加 `🗑已廢棄-` 前綴、移到分類最底部。**不是真的刪除**，真正刪除頻道需要管理員在 Discord 手動操作。 |
| `/add member [channel]` | 把成員加入你的頻道，讓對方看得到並可使用。 |
| `/remove member [channel]` | 把成員移出你的頻道（收回權限），不能移除建立者本人。 |
| `/listch` | 查看自己建立的頻道與成員名單；管理員執行可看到全部頻道。不顯示已廢棄的頻道。 |
| `/help` | 顯示所有指令的簡易用法說明。 |

只有頻道建立者本人或管理員可以對該頻道執行 `/delete`、`/add`、`/remove`。

禁言請直接用 Discord 原生的右鍵 Timeout 功能（需要「逾時成員」權限），不需要透過本機器人。

## 安裝

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 設定

1. 複製 `.env.example` 為 `.env`
2. 到 [Discord Developer Portal](https://discord.com/developers/applications) 建立應用程式與 Bot，取得 Token 填入 `DISCORD_TOKEN`
3. 在 Developer Portal 的 Bot 設定頁**開啟 SERVER MEMBERS INTENT**（`MESSAGE CONTENT` 不需要開）
4. 用以下權限產生邀請連結並邀請機器人進伺服器：
   - 查看頻道 (View Channels)
   - 管理頻道 (Manage Channels)
   - 管理身分組 (Manage Roles)
   - 發送訊息 (Send Messages)
   - 移動成員 (Move Members)
5. **把機器人的身分組拖到比一般成員高的位置**（否則無法修改頻道權限）
6. 在伺服器建立一個分類（例如「私人頻道」），開啟開發者模式後複製其 ID，填入 `.env` 的 `CATEGORY_ID`
7. 確認管理員身分組 ID 填在 `ADMIN_ROLE_ID`
8. 開發階段建議填 `GUILD_ID`（你的測試伺服器 ID），指令會秒同步；正式上線後把 `GUILD_ID` 留空並重啟，改成全域同步（最長需 1 小時生效）

## 執行

```powershell
python main.py
```

## 維運須知

- **偽刪除不會釋放 Discord 的頻道額度**：一個分類最多 50 個頻道、一個伺服器最多 500 個頻道。長期使用需要管理員定期到已廢棄（`🗑已廢棄-` 前綴）的頻道中手動真刪除，釋放額度。
- **頻道改名有嚴格 rate limit**（每頻道 10 分鐘內僅能改名 2 次）。連續對多個頻道執行 `/delete` 時，第 3 個以後的改名可能會延遲，機器人會在回覆中提示「改名會在稍後自動完成」，此時該頻道的權限與位置已經正確變更，只是名稱顯示會晚一點更新。
- **由全域同步切換 guild 同步（或反之）時**，建議手動執行一次 `bot.tree.clear_commands(guild=...)` 對應範圍再重新同步，避免指令重複出現在清單中。
- 資料庫檔案位於 `data/channels.db`（WAL 模式，會伴隨 `.db-wal` / `.db-shm`），不會進版控。
