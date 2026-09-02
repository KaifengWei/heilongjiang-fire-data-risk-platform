tests/

原项目基础
├─ test_database.py
├─ test_firms.py
└─ test_geography.py

Day2 任务底座
└─ test_tasks.py

Day3 文件进入系统
├─ test_file_intake.py
├─ test_mcd64_pair.py
├─ test_readiness.py
└─ test_task_web.py

Day4 FIRMS正式处理
├─ test_firms_normalization.py   # 算法规范化
├─ test_firms_storage.py         # 数据库存储
├─ test_firms_processing.py      # 业务处理
└─ test_firms_processing_web.py  # 网页接入



后面 Day 5 做 MCD64A1，文件按照同样层级来：

```
test_mcd64_processing.py
test_mcd64_storage.py
test_mcd64_processing_web.py
```