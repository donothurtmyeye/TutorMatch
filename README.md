# TutorMatch

家教兼职机会筛选 Agent MVP1。项目使用 LangGraph 编排流程，并通过 LangChain 的 `init_chat_model` 调用 OpenAI-compatible 大模型，对家教兼职机会进行评分、排序、风险判断和话术生成。

## 功能

- 终端交互式输入老师偏好档案：科目、区域、最低课酬、通勤上限、可上课时间、授课方式、年级偏好和风险关键词。
- **批量粘贴**：直接从微信群、中介等渠道复制整块机会文本，AI 自动解析并结构化。
- 老师档案持久化存储，首次输入后自动保存，下次运行自动读取。
- 调用大模型完成机会筛选：评分、结论、匹配理由、风险提醒、建议追问和联系话术。
- 生成 Markdown 筛选报告。

## 项目结构

```text
TutorMatch/
  main.py                    # 统一运行入口
  tutormatch/
    agent.py                 # LangGraph Agent 编排
    llm.py                   # 大模型调用和结果解析
    config.py                # .env 配置读取
    models.py                # 数据模型
    interactive.py           # 终端交互输入
    report.py                # 报告渲染
  tests/
    test_config.py
    test_llm.py
```

## 安装

本项目使用 Python 3.12。推荐用 `uv` 安装依赖：

```powershell
uv sync
```

## 配置大模型

在项目根目录创建 `.env` 文件。你可以使用通用字段：

```text
API_KEY="你的 API Key"
BASE_URL="https://your-compatible-endpoint/v1"
MODEL="openai:你的模型名"
```

也可以使用 OpenAI 标准字段：

```text
OPENAI_API_KEY="你的 API Key"
OPENAI_BASE_URL="https://your-compatible-endpoint/v1"
TUTORMATCH_MODEL="openai:你的模型名"
```

程序启动时会自动读取 `.env`，并把 `API_KEY`、`BASE_URL` 映射给 LangChain/OpenAI 客户端。

## 运行

统一入口，启动后按终端提示输入老师档案和家教机会即可：

```powershell
uv run python main.py
```

**老师档案持久化**：首次运行会要求输入老师档案，输入后自动保存到 `profile.json`。下次运行自动读取，按需确认是否重新输入。

**机会批量粘贴**：直接把所有机会文本一次性粘贴进去，完成后输入 `---end---` 结束：

```text
===== TutorMatch 交互式筛选 =====
已读取缓存的老师档案：候选老师
  科目: 数学, 英语, 物理
  区域: 徐汇, 静安, 黄浦, 线上
  最低时薪: 180

是否重新输入老师档案？(y/N):

===== 批量粘贴家教机会 =====
请粘贴所有机会文本，粘贴完成后在新行输入 ---end--- 结束：
==================================================
深圳F090328A
【上课地址】：龙岗区联发天境雅居
【年级科目】：二年级全科
【学员情况】：两个男孩，一对二
【时间安排】：周一周三晚，一周2次，一次2小时，具体老师带时间协商
【老师要求】：有经验，有耐心
【老师课费】：100-130/h

深圳F090334A
【上课地址】：南山区英达钰龙园D栋
【年级科目】：五年级全科
【学员情况】：女孩
【时间安排】：一周4次，一次2小时，晚上七点之后上课，具体老师带时间协商
【老师要求】：有经验，有耐心
【老师课费】：90-110/h
---end---
```

AI 会自动解析出结构化信息，然后进入筛选流程。

临时指定模型：

```powershell
uv run python main.py --model openai:你的模型名
```

指定展示前 N 个结果：

```powershell
uv run python main.py --top 10
```

运行后会生成报告：

```text
reports/screening_report.md
```

## Agent 流程

LangGraph 目前包含 2 个节点：

1. `screen_with_llm`：调用大模型完成筛选、评分和话术生成。
2. `write_report`：生成 Markdown 报告和终端摘要。

大模型初始化位置在 `tutormatch/llm.py`：

```python
from langchain.chat_models import init_chat_model

model = init_chat_model(
    model_name,
    api_key=api_key,
    base_url=base_url,
    temperature=0,
)
```

## 测试

测试不会真实请求大模型，会使用模拟模型输出：

```powershell
uv run python -m unittest discover -s tests
```
