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

## 用户说「投 N 个」时(唯一主路径)

先读配置,然后**只跑这一条**:

```
C:\Users\19045\anaconda3\envs\teacher\python.exe C:\Users\19045\.agents\skills\boss-zhipin-autojob\zhipin_win.py apply --count 20 --min-daily 90
```

`--count` 用用户要的数量,`--min-daily` 用用户给的日薪下限(默认配置 90)。

脚本会: 拉列表、解码薪资、算通勤、过滤、拟人点沟通; 本屏不够就自己滚左列继续,已投过和 `--after` 以上的卡不再给模型看。把 JSON `ok`/`results` 汇报即可。

`--after N`: 只处理序号 `i > N` 的卡(从上往下, N 及以前视为已看过)。默认 `-1` 表示从头。例如已看到 `i=10`,下次:

```
... zhipin_win.py apply --count 20 --min-daily 90 --after 10
```

## 只要列表、不要点

```
... python.exe ...\zhipin_win.py list --after 10
```

`jobs[]` 含 `i,title,company,salary,salary_min,commute_min,commute_status`。

## 备选

只有 `apply`/`list` 报找不到窗口时,才用 Computer Use。
