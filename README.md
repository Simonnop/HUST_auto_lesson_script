# 心理健康课程自动连播脚本

基于 Selenium 的课程视频自动连播脚本，用于在完成人工登录后自动执行：

1. 点击播放
2. 轮询判断本节是否播放完成
3. 点击下一节
4. 如出现确认弹层则自动点击确认

脚本入口：`course_autoplay.py`

## 功能特性

- 自动打开指定课程入口页
- 支持人工登录后接管当前视频标签页
- 兼容 iframe/frame 场景下的元素查找
- 根据“当前时长/总时长”判断播放完成（带 1 秒容差）
- 提供异常兜底：
  - 单节最长等待超时保护（默认 3 小时）
  - Chrome/ChromeDriver 版本匹配提示
  - 可选确认按钮存在时自动点击，不存在则跳过

## 目录结构

- `course_autoplay.py`：主脚本
- `run.sh`：在 `conda` 环境 `auto` 中启动脚本
- `requirements.txt`：Python 依赖
- `PRD.md`：流程和 XPath 设计说明

## 环境要求

- macOS / Linux（Windows 理论可改造后使用）
- Python 3.9+
- Google Chrome（或兼容 Chromium）
- 建议使用 `conda`（`run.sh` 依赖 `conda run`）

## 安装依赖

在项目目录执行：

```bash
pip install -r requirements.txt
```

`requirements.txt` 当前包含：

- `selenium>=4.15.0`
- `webdriver-manager>=4.0.0`

## 运行方式

### 方式一：直接运行 Python

```bash
python3 course_autoplay.py
```

### 方式二：使用 `run.sh`（推荐）

> `run.sh` 默认使用 conda 环境 `auto`。

```bash
chmod +x run.sh
./run.sh
```

## 使用流程

1. 脚本启动后会自动打开课程入口页面
2. 在浏览器中手动完成登录
3. 手动进入目标视频页（确保当前活动标签页是要控制的页面）
4. 回到终端按回车
5. 脚本开始循环：
   - 点击播放
   - 检测是否播完
   - 点击下一节
   - 重复直到你手动停止

## 可配置项

如页面结构变化，可修改 `course_autoplay.py` 顶部常量：

- `COURSE_URL`：课程入口
- `XPATH_PLAY`：播放按钮
- `XPATH_CURRENT_TIME`：当前观看时长
- `XPATH_TOTAL_TIME`：总时长
- `XPATH_NEXT`：下一节按钮
- `XPATH_OPTIONAL_ACK`：可选确认按钮

轮询与超时参数：

- `POLL_INTERVAL`：进度轮询间隔（默认 `2.0` 秒）
- `MAX_SECTION_SECONDS`：单节最长等待（默认 `3 * 60 * 60` 秒）

## 常见问题

### 1) 启动时报 ChromeDriver 版本不匹配

脚本优先级如下：

1. 使用 `CHROMEDRIVER_PATH` 指定的驱动
2. 使用 PATH 中 `chromedriver`（主版本匹配时）
3. 使用 `webdriver-manager` 自动下载

可尝试：

```bash
brew upgrade chromedriver
rm -rf ~/.cache/selenium
```

或手动指定：

```bash
export CHROMEDRIVER_PATH=/path/to/chromedriver
python3 course_autoplay.py
```

### 2) 找不到播放/下一节按钮

- 多数是页面 DOM 或 iframe 结构变化导致 XPath 失效
- 打开开发者工具重新确认 XPath，并更新 `course_autoplay.py` 常量

### 3) 脚本启动后不播放

- 确认你按回车前，浏览器活动标签页就是目标视频页
- 确认课程页面已加载到播放器区域，而不是目录或空白页

## 注意事项

- 仅用于你本人账号下的学习辅助，遵守平台规则与学校要求
- 脚本需要人工登录，不支持绕过认证
- 遇到页面改版时，需要维护 XPath

