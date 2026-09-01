---
name: boss-zhipin-autojob
description: >
  BOSS直聘自动沟通。用户说投N个时直接运行 zhipin_win.py apply --count N。
  不要用 Computer Use 探页面、不要改脚本、不要先设筛选再研究。
  Use when 投简历、BOSS直聘、立即沟通、自动投递, or /boss-zhipin-autojob.
---

# BOSS直聘自动沟通

禁止 Computer Use 逐条读页面。禁止中途改 `zhipin_win.py`。禁止为「工作经验/学历」开一轮探索。

解释器: `C:\Users\19045\anaconda3\envs\teacher\python.exe`  
目录: `C:\Users\19045\.agents\skills\boss-zhipin-autojob`  
配置: `memory.config.env`(排除词、通勤、`MIN_DAILY_SALARY`)

地址栏若已有 `experience=108`,页面筛的就是**在校生**,不要再去点筛选。

## 用量(先告诉用户)

BOSS 每天沟通额度大约 150 次。不要一次跑满。建议用户分多段、隔开几个小时再投,例如上午 20、下午 20、晚上 20。单次 `apply --count` 默认按用户说的来,但用户若说「今天 150 全投完」:**先劝停**,说明连续海投容易风控/封号,改成本轮最多 40–50,下次换个时间段再跑。用户坚持全投才按他说的 count 执行。

## 用户说「投 N 个」时(唯一主路径)

先读配置,然后**只跑这一条**:

每次运行都必须加 `--wait`(开始前先等,单位秒,脚本会截到最多 3 秒)。**每次自己随机一个 0.3–3.0 的小数**,不要固定写成同一个数。

```
C:\Users\19045\anaconda3\envs\teacher\python.exe C:\Users\19045\.agents\skills\boss-zhipin-autojob\zhipin_win.py apply --count 20 --min-daily 90 --wait 1.37
```

`--count` 用用户要的数量,`--min-daily` 用用户给的日薪下限(默认配置 90)。

脚本会: 先 `--wait` 再拉列表、解码薪资、算通勤、过滤、拟人点沟通; 本屏不够就自己滚左列继续,已投过和 `--after` 以上的卡不再给模型看。若暂时没有更多职位，先尝试向下滚动鼠标并继续检查；只有连续多次滚动后列表仍无变化、确认没有新增职位时，才通知用户。把 JSON `ok`/`results` 汇报即可。

`--after N`: 只处理序号 `i > N` 的卡(从上往下, N 及以前视为已看过)。默认 `-1` 表示从头。例如已看到 `i=10`,下次:

```
... zhipin_win.py apply --count 20 --min-daily 90 --after 10 --wait 2.14
```

## 只要列表、不要点

```
... python.exe ...\zhipin_win.py list --after 10 --wait 0.86
```

`jobs[]` 含 `i,title,company,salary,salary_min,commute_min,commute_status`。

## 备选

只有 `apply`/`list` 报找不到窗口时,才用 Computer Use。
