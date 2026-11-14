# 网易天音接口与母带直链

## 两套系统（容易混淆）

| | A. 主站「AI 一键写歌」 | B. 编辑器「全链路创作」 |
|---|---|---|
| 位置 | `music.163.com/st/tianyin/my-assets` | `tianyin.music.163.com/editor/#/workspace/my-song` |
| 接口 | `/api/rep/...` **明文 JSON**，Cookie 直接调 | `/api/nmusic/yunshao/...` **weapi 加密** |
| 可得 | `audioUrl`(有损 mp3) + `coverUrl` + **`audioNosKey`(无损 FLAC 母带)** | 官方导出：整曲WAV / 歌声WAV / 伴奏 / 分轨 |
| 备注 | 官方没有导出入口，但 `audioNosKey` 就是母带 | 若编辑器里是空的，说明作品都在 A 套 |

**本 Skill 只走 A 套**（用户作品都在主站）。编辑器接口返回 `code:-1` 属正常，不代表 Cookie 失效。

## 资产列表接口

```
GET https://music.163.com/api/rep/ai/factory/user/song/production/page
    ?limit=20&offset=0&newVersion=true
Headers: Cookie: <整行 Cookie>  Referer: https://music.163.com/st/tianyin/my-assets
```

- 返回 `code: 200`，数据在 `data.songList`；`limit=20` 分页，`len(lst) < 20` 时停止。
- 2026-11-14 实测：账号下 61 个作品，Cookie 有效。
- **不需要**调用 batch query：`audioNosKey` 直接就在列表项里。

### 列表项关键字段

| 字段 | 说明 |
|---|---|
| `productionId` | 作品 id，母带文件名里的数字，用于精确指定 |
| `name` | 歌名（同名很多，必须靠 id 区分） |
| `audioNosKey` | 例：`music-ugc-ai-song/ai-factory-processed-<作品id>-hq-online.flac` |
| `audioUrl` | `...-online.mp3`，**有损转码，不要拿它当母带** |
| `submitTime` | 用于判断哪个是最新版本 |

其它字段：`coverUrl`, `lyric`, `lrcLyric`, `duration`, `styleParam`, `voiceGender`, `status` 等。

## 无损 FLAC 母带直链

`audioNosKey` 形如 `<bucket>/<object key>`，直链规则：

```
http://<bucket>.nos.netease.com/<object key>
→ http://music-ugc-ai-song.nos.netease.com/ai-factory-processed-<作品id>-hq-online.flac
```

- 无鉴权、支持 Range（206）。2026-11-07 起多次实测有效。
- 若字段缺失，用 id 兜底拼 `ai-factory-processed-<id>-hq-online.flac`。
- **校验**：下载后前 4 字节必须是 `fLaC`，体积通常 50 MB 左右；若是 HTML/JSON 或几 KB，说明 key 拼错或鉴权失效。
- 规格：48kHz / 立体声 / 24bit 级别，时长与普通版一致（约 4:01）。
- `engine/dsp.py` 的 soundfile 可直接读 FLAC，工作台无需再转 WAV。

## 为什么不能用 mp3

`audioUrl` 指向 `ai-factory-processed-<id>-online.mp3`，是服务端从母带转出的 320kbps/48kHz 有损版本。实测 FLAC 与 mp3 的 mean 响度都是 −13.8 dB 左右——用户说的「声音变小」多半是播放器响度归一化造成的错觉，但「细节变少/糊」是真有损。mp3→wav 只是换容器，音质上限仍是 mp3。

## Cookie

- 获取：Chrome/Edge 登录天音 → F12 → Network → 任意 `music.163.com` 请求 → Request Headers → 复制整行 Cookie（一行，不换行）。
- 存放优先级：`--cookie` > 环境变量 `TIANYIN_COOKIE` > `--cookie-file` / `TIANYIN_COOKIE_FILE` > 技能根目录 `cookie.txt` > `~/.workbuddy/tianyin_cookie.txt` > 当前目录 `cookie.txt`。`cookie.txt` 已被 `.gitignore` 排除，**绝不提交**。
- 校验：`python scripts/master_pipeline.py list` 能列出作品即有效；`code != 200` 说明过期，需重新复制。
- 编辑器 weapi 接口失败不影响本 Skill。
- Cookie 是隐私数据：不要写进脚本、报告 JSON 或日志。

## 排错

| 现象 | 原因 / 处理 |
|---|---|
| `资产接口失败` code 非 200 | Cookie 过期，重新复制 |
| 下载到几 KB 或不是 `fLaC` | `audioNosKey` 缺失/格式变化，用 `list` 看字段，必要时 `dump --id` 查完整对象 |
| 拿错歌 | 同名作品常有多个 id，**必须 `--id`** |
| 直链 403/404 | 换 `https://`，或检查 bucket 名是否变化 |

## 相关工具

- 本 Skill 只复刻了「资产列表 + 母带直链」这部分，不依赖任何外部下载器脚本，开箱即用。
